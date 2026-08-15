"""混合检索 — BM25(纯 Python 实现)+ 向量余弦 + RRF 融合。

本模块只依赖标准库,不引入任何第三方 BM25 依赖(rank_bm25 亦不使用)。

分词策略(tokenize):
- 中文(CJK)连续段 → 字符 bigram(连续两字一组),并追加单字(unigram)补全,
  保证单字查询与边界字符也能命中;公共单字由 IDF 自然降权。
- 拉丁字母/数字连续段 → 按空白切分、小写归一化后提取 [a-z0-9]+ 的 word。
- 中英混合文本按「CJK 段 / 非 CJK 段」分别处理。

BM25:标准公式,k1=1.5,b=0.75,IDF 平滑 ln(1 + (N - df + 0.5)/(df + 0.5)),
文档长度为「加权词频之和」(标题/别名/正文权重不同)。

RRF:score = Σ 1/(k + rank),k=60;向量与 BM25 各取 top_k*2 候选后融合排序。
向量侧带 vector_weight(默认 0.1):中文精确主题匹配以 BM25 为主,向量作次级补充
(契约 §3 允许按需调整「向量权重」;英文 MiniLM 对中文向量的噪声较大)。

查询改写:rewrite_query 默认关闭,异常时原样返回;仅当调用方显式 enable 才启用。
"""

from __future__ import annotations

import math
import re

# CJK 统一表意文字(U+4E00–U+9FFF)与扩展 A(U+3400–U+4DBF)
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_SEGMENT_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+|[^\u4e00-\u9fff\u3400-\u4dbf]+")
_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str, include_unigrams: bool = True) -> list[str]:
    """将文本切分为检索 token。

    - CJK 段:字符 bigram(连续两字一组);include_unigrams=True 时追加单字补全(unigram),
      用于覆盖单字查询与首尾边界字符。
    - 非 CJK 段:lower() 后按 [a-z0-9]+ 提取 word。
    """
    if not text:
        return []
    text = text.lower()
    tokens: list[str] = []
    for seg in _SEGMENT_RE.findall(text):
        seg = seg.strip()
        if not seg:
            continue
        if _CJK_RE.match(seg):
            n = len(seg)
            if n == 1:
                tokens.append(seg)
            else:
                # 连续两字一组(bigram)
                for i in range(n - 1):
                    tokens.append(seg[i:i + 2])
                # 单字补全(unigram)
                if include_unigrams:
                    for ch in seg:
                        tokens.append(ch)
        else:
            for w in _WORD_RE.findall(seg):
                tokens.append(w)
    return tokens


class BM25Index:
    """标准 BM25 索引(k1=1.5, b=0.75),支持浮点加权词频(字段加权)。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[dict[str, float]] = []
        self.doc_len: list[float] = []
        self.avgdl: float = 0.0
        self.doc_freq: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.N: int = 0

    def fit(self, documents: list[dict[str, float]]) -> None:
        """documents: 每篇文档的 token -> 加权词频(浮点)Counter。"""
        self.documents = documents
        self.N = len(documents)
        self.doc_len = []
        df: dict[str, int] = {}
        for doc in documents:
            length = 0.0
            for tok, w in doc.items():
                length += w
                df[tok] = df.get(tok, 0) + 1
            self.doc_len.append(length)
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        self.doc_freq = df
        self.idf = {}
        for tok, d in df.items():
            self.idf[tok] = math.log(1.0 + (self.N - d + 0.5) / (d + 0.5))

    def score(self, query_tokens: list[str]) -> list[float]:
        """返回每篇文档的 BM25 得分(与文档顺序对齐)。"""
        if self.N == 0:
            return []
        scores = [0.0] * self.N
        if not query_tokens:
            return scores
        # 标准 BM25 不对查询词频加权,仅对去重后的查询 token 求和
        for t in set(query_tokens):
            idf = self.idf.get(t)
            if not idf:
                continue
            for i, doc in enumerate(self.documents):
                tf = doc.get(t, 0.0)
                if tf <= 0:
                    continue
                dl = self.doc_len[i]
                norm = tf + self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl if self.avgdl else 1.0))
                scores[i] += idf * (tf * (self.k1 + 1.0)) / norm
        return scores


def _normalize(vector: list[float] | None) -> list[float] | None:
    """L2 归一化,None/空/零向量返回 None。兼容 list 与 numpy 一维数组。"""
    if vector is None:
        return None
    if len(vector) == 0:
        return None
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return None
    return [x / norm for x in vector]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def rewrite_query(query: str, llm_invoke=None) -> str:
    """查询改写(默认关闭):调用 LLM 生成同义词扩展,任何异常都原样返回。

    llm_invoke 需为 (system_prompt, user_prompt) -> str 的可调用对象。
    扩展文本与原 query 拼接,失败/为空时返回原 query。
    """
    if not query or llm_invoke is None:
        return query
    try:
        system = "你是中文知识检索的同义词扩展助手。只输出扩展后的检索关键词(空格分隔),不要解释。"
        prompt = f"请为以下查询生成同义词扩展(保留原词,补充近义/相关表达):\n{query}"
        expanded = (llm_invoke(system, prompt) or "").strip()
        if not expanded:
            return query
        return f"{query} {expanded}"
    except Exception:
        return query


class HybridRetriever:
    """混合检索器:BM25(纯 Python)+ 向量余弦,RRF 融合。

    - build() 一次性灌入全量卡片(ids/titles/contents/embeddings + 可选 aliases/metadatas);
    - search() 返回 [(card_id, rrf_score, rank_info)],rank_info 为诊断信息 dict。
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        rrf_k: float = 60.0,
        title_weight: float = 3.0,
        alias_weight: float = 2.0,
        content_weight: float = 1.0,
        include_unigrams: bool = True,
        vector_weight: float = 0.1,
    ):
        self.k1 = k1
        self.b = b
        self.rrf_k = rrf_k
        self.title_weight = title_weight
        self.alias_weight = alias_weight
        self.content_weight = content_weight
        self.include_unigrams = include_unigrams
        self.vector_weight = vector_weight
        self._ids: list[str] = []
        self._metadatas: list[dict] = []
        self._embeddings: list[list[float] | None] = []
        self._bm25: BM25Index | None = None

    def build(
        self,
        ids: list[str],
        titles: list[str],
        contents: list[str],
        embeddings: list[list[float] | None],
        aliases: list[list[str]] | None = None,
        metadatas: list[dict] | None = None,
    ) -> None:
        n = len(ids)
        self._ids = list(ids)
        self._metadatas = [m or {} for m in metadatas] if metadatas else [{} for _ in range(n)]
        self._embeddings = []
        documents: list[dict[str, float]] = []
        for i in range(n):
            counter: dict[str, float] = {}
            title = titles[i] if i < len(titles) and titles[i] else ""
            content = contents[i] if i < len(contents) and contents[i] else ""
            alias_list = aliases[i] if aliases and i < len(aliases) else []
            alias_list = alias_list or []
            for tok in tokenize(title, self.include_unigrams):
                counter[tok] = counter.get(tok, 0.0) + self.title_weight
            for a in alias_list:
                for tok in tokenize(a, self.include_unigrams):
                    counter[tok] = counter.get(tok, 0.0) + self.alias_weight
            for tok in tokenize(content, self.include_unigrams):
                counter[tok] = counter.get(tok, 0.0) + self.content_weight
            documents.append(counter)
            emb = embeddings[i] if (embeddings is not None and i < len(embeddings)) else None
            self._embeddings.append(_normalize(emb))
        self._bm25 = BM25Index(self.k1, self.b)
        self._bm25.fit(documents)

    def search(
        self,
        query: str,
        query_embedding: list[float] | None,
        top_k: int = 5,
        category: str | None = None,
        source_file: str | None = None,
        min_mastery: int | None = None,
        enable_rewrite: bool = False,
        llm_invoke=None,
    ) -> list[tuple[str, float, dict]]:
        results = self._search_impl(query, query_embedding, top_k, category, source_file, min_mastery)
        # 查询改写:默认关闭;仅当显式 enable 且短查询(<6 字)且首轮 0 命中时触发。
        if enable_rewrite and llm_invoke is not None and len(query) < 6 and not results:
            expanded = rewrite_query(query, llm_invoke)
            if expanded != query:
                results = self._search_impl(
                    expanded, query_embedding, top_k, category, source_file, min_mastery
                )
        return results

    def _search_impl(
        self,
        query: str,
        query_embedding: list[float] | None,
        top_k: int,
        category: str | None,
        source_file: str | None,
        min_mastery: int | None,
    ) -> list[tuple[str, float, dict]]:
        n = len(self._ids)
        if n == 0 or top_k <= 0 or self._bm25 is None:
            return []
        candidate_k = max(top_k * 2, 1)
        q_tokens = tokenize(query, self.include_unigrams)
        bm25_scores = self._bm25.score(q_tokens)
        vec_scores = self._vector_scores(query_embedding)

        # 只对「确实被该路检索命中」的候选排序:BM25 取得分 >0 的文档,
        # 向量取有有效 embedding 的文档。避免把零分文档塞进 RRF 制造伪排名。
        bm25_valid = [i for i in range(n) if bm25_scores[i] > 0.0]
        bm25_valid.sort(key=lambda i: bm25_scores[i], reverse=True)
        bm25_ranked = bm25_valid[:candidate_k]

        vec_valid = [i for i in range(n) if self._embeddings[i] is not None]
        vec_valid.sort(key=lambda i: vec_scores[i], reverse=True)
        vec_ranked = vec_valid[:candidate_k]

        # RRF 融合:只考虑进入任一边 top(candidate_k) 的候选;
        # 向量侧乘以 vector_weight(默认 0.1):中文精确主题匹配以 BM25 为主,
        # 向量仅作次级补充(英文 MiniLM 对中文的向量噪声较大,见报告)。
        rrf: dict[int, float] = {}
        for rank, idx in enumerate(bm25_ranked, start=1):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (self.rrf_k + rank)
        for rank, idx in enumerate(vec_ranked, start=1):
            rrf[idx] = rrf.get(idx, 0.0) + self.vector_weight / (self.rrf_k + rank)

        ordered = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)
        results: list[tuple[str, float, dict]] = []
        for idx, score in ordered:
            # 元数据过滤:在候选取出后按 category/source_file/min_mastery 过滤
            if not self._matches_filters(idx, category, source_file, min_mastery):
                continue
            rank_info = {
                "rrf_score": score,
                "bm25_score": bm25_scores[idx] if idx < len(bm25_scores) else 0.0,
                "bm25_rank": self._rank_of(bm25_ranked, idx),
                "vector_score": vec_scores[idx] if idx < len(vec_scores) else 0.0,
                "vector_rank": self._rank_of(vec_ranked, idx),
            }
            results.append((self._ids[idx], score, rank_info))
            if len(results) >= top_k:
                break
        return results

    def _vector_scores(self, query_embedding: list[float] | None) -> list[float]:
        q = _normalize(query_embedding)
        if q is None:
            return [0.0] * len(self._ids)
        return [(_dot(q, e) if e is not None else 0.0) for e in self._embeddings]

    @staticmethod
    def _rank_of(ranked: list[int], idx: int) -> int | None:
        try:
            return ranked.index(idx) + 1
        except ValueError:
            return None

    def _matches_filters(
        self,
        idx: int,
        category: str | None,
        source_file: str | None,
        min_mastery: int | None,
    ) -> bool:
        meta = self._metadatas[idx] if idx < len(self._metadatas) else {}
        if category is not None and str(meta.get("category", "")) != str(category):
            return False
        if source_file is not None and str(meta.get("source_file", "")) != str(source_file):
            return False
        if min_mastery is not None and _mastery_score(meta) < int(min_mastery):
            return False
        return True


def _mastery_score(meta: dict) -> int:
    """掌握度口径:max_score 语义 —— 取 metadata 的 mastery_score(累计最高分)。

    说明:KnowledgeCard 存有 mastery_attempts(答题次数)与 mastery_score(累计最高分)。
    本实现采用「max_score」口径,即 mastery_score >= min_mastery 视为达标;
    不使用 score/attempts 平均值,因为 attempts=0 时该比值无定义,且「累计最高分」
    更贴近「是否已掌握到某水平」的直觉。ChromaDB metadata 中该值为字符串,此处容错解析。
    """
    raw = meta.get("mastery_score", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0
