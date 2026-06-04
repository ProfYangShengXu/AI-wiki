# 大文件解析优化方案

> 目标：让 StudyWiki-Agent 能够高效解析 100+ 页的大型 PDF/Word 文档，不卡死、不丢数据、用户可见进度。

---

## 1. 现有瓶颈分析

| 瓶颈 | 原因 | 后果 |
|------|------|------|
| **全量逐页 LLM** | 每页都调 LLM 提取，67 页 = 67 次调用 | 大文件耗时 10min+，事件循环堵塞 |
| **无结构预扫描** | 不知道文档结构，封面/目录/参考文献也提取 | 大量无用 LLM 调用，知识点重复 |
| **全部提取完才入库** | `node_extract_knowledge` 收集完所有结果才批量导入 | 中途崩溃丢全部进度 |
| **无去重边界** | 同一概念多页出现则重复提取 | 知识库冗余卡片 |
| **无速率控制** | ThreadPoolExecutor 无限制并发 | DeepSeek/OpenAI 限流报错 |

---

## 2. 优化架构：三阶段流水线

```
Phase 1                    Phase 2                       Phase 3
预扫描                     智能提取                       增量入库
─────────                 ──────────                     ──────────
解析文档结构               跳过封面/目录/引用页            逐条入库
识别有效页区间             并发提取有效页                  已提取的不丢
检测语言/编码              自适应上下文窗口                入库后推送 WebSocket
输出: [page_ranges]        LLM 提取 + 去重                实时进度
                           输出: [knowledge_items]
```

### Phase 1: 文档预扫描（新增）

```
parse_document(file)
  → 获取总页数、每页字符数、检测空白页
  → LLM 快速扫描前 3 页，识别:
      - 语言 (中文/英文)
      - 文档类型 (教材/论文/PPT/讲义)
      - 目录结构 (章节标题列表)
  → 输出:
      - valid_ranges: [(start_page, end_page, topic), ...]
      - skip_pages: [封面, 目录, 参考文献, 索引]
      - language: "zh" | "en"
```

**收益：** 跳过 20-40% 的无效页面（封面/目录/引用/附录），减少 LLM 调用量。

### Phase 2: 智能并发提取（优化）

```
对 valid_ranges 中的每个区间:
  1. 取该区间的前 3 页作为"上下文样本"
  2. LLM 一次性提取该区间的核心知识点（聚合提取）
  3. 短区间 (1-3页) → 逐页提取
  4. 长区间 (4+页) → 聚合提取 + 差异提取

并发控制:
  - max_workers = 3 (降低并发防限流)
  - 每完成一个区间 → 立即进入 Phase 3（不等待全部完成）
  - 速率限制: 10 秒内最多 15 次 LLM 调用
```

**收益：** 长区间用聚合提取替代逐页提取，LLM 调用量减少 60-80%。

### Phase 3: 增量入库 + 实时进度（优化）

```
每提取一个知识点 → 立即:
  1. 去重检查 (标题/别名已在库中?)
  2. 若为新 → 单独入库 (非批量)
  3. 推 WebSocket 进度: {type: "progress", page: N, total: M, title: "xxx"}
  4. 前端实时显示: "第 5/67 页 → 已提取 CPU 基本结构"
```

**收益：** 用户实时看到进展，不会以为卡死。中途崩溃已入库的数据不丢失。

---

## 3. 核心代码改动

### 3.1 新增: 文档预扫描器

```python
class DocumentScanner:
    """Phase 1: 预扫描文档结构。"""
    
    def scan(self, file_path: str) -> ScanResult:
        pages = parse_document(file_path)
        
        # 统计分析
        stats = self._analyze_pages(pages)
        
        # LLM 快速扫描前几页识别结构
        structure = self._detect_structure(pages[:3])
        
        # 跳过低内容页
        valid_ranges = self._compute_valid_ranges(pages, stats)
        
        return ScanResult(
            total_pages=len(pages),
            valid_ranges=valid_ranges,  # [(1,5,"引言"), (6,20,"核心章节"), ...]
            language=structure["language"],
            doc_type=structure["doc_type"],
        )
    
    def _analyze_pages(self, pages) -> PageStats:
        """统计每页字符数、空白比例。"""
        
    def _detect_structure(self, sample_pages) -> dict:
        """LLM 快速识别文档类型和语言。"""
        
    def _compute_valid_ranges(self, pages, stats) -> list:
        """跳过低内容页，合并相邻有效页为区间。"""
```

### 3.2 优化: 智能提取器

```python
class SmartExtractor:
    """Phase 2: 智能提取，支持聚合提取。"""
    
    MAX_WORKERS = 3   # 降低并发防限流
    RATE_LIMIT = (15, 10)  # 10秒内最多15次调用
    
    def extract_range(self, pages: list, page_range: tuple, context: str) -> list[dict]:
        """提取一个区间。短区间逐页，长区间聚合。"""
        start, end, topic = page_range
        length = end - start + 1
        
        if length <= 3:
            return self._extract_each_page(pages, start, end)
        else:
            return self._extract_aggregated(pages, start, end, topic)
    
    def _extract_aggregated(self, pages, start, end, topic):
        """聚合提取: 将整个区间的文本合并，一次 LLM 调用提取所有知识点。"""
        combined = "\n".join([p["text"][:1500] for p in pages[start-1:end]])
        prompt = f"以下是关于「{topic}」的文档内容({start}-{end}页)，请提取所有知识点..."
        return llm_extract(prompt, combined)
```

### 3.3 优化: 增量入库

```python
# 不再等待全部提取完毕，而是每提取一个立即入库
for item in extracted_items:
    if not self._is_duplicate(item, existing_titles):
        card = card_service.create_card(item)
        ws_push_progress({"page": current_page, "title": item["title"]})
```

---

## 4. 前端改动

在对话窗口中添加**实时解析进度条**：

```
┌─────────────────────────────────────────────┐
│ 📖 正在解析 "计算机组成原理.pdf"             │
│ ████████░░░░░░░░░░░░ 第 12/67 页            │
│ ✅ 已提取: CPU基本结构, 存储器层次结构       │
│ ⏳ 当前: 正在提取第15页...                   │
└─────────────────────────────────────────────┘
```

---

## 5. 性能预期

| 场景 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| 10 页小文档 | ~30s | ~10s | 3x |
| 67 页 PDF (数字逻辑) | ~8min | ~2min | 4x |
| 200 页教材 | 不可用 | ~8min | ∞ |
| 无效页面 (封面/目录) | 照样提取 | 自动跳过 | 20-40% 无效调用 |

---

## 6. 实现路线

1. Phase 1: 文档预扫描器 (`tools.py` 新增 `DocumentScanner`)
2. Phase 2: 智能提取器 (`agent.py` 重构 `run_import_workflow`)
3. Phase 3: 增量入库 + 前端进度条 (`agent.py` + `static/index.html`)
4. 测试: 用 67 页 PDF 验证
