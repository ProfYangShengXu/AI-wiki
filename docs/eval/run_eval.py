"""检索回归评测:50 条中文短查询 → Top5 命中率。

用法:
    .venv-linux/bin/python docs/eval/run_eval.py retrieval [--limit N]

流程:
    1. 在 tmp_path 隔离 ChromaDB 中创建评测知识库;
    2. 用 FakeEmbeddings 植入基准卡片集(与 docs/eval/fixtures 主题一致);
    3. 逐条执行 retrieval_queries.jsonl,统计 Top5 命中率;
    4. 结果写 docs/eval/results/retrieval-<ts>.json,命中率 <0.80 时 exit 1。

Agent 评测(agent 子命令):20 条指令在隔离库 + 脚本化 FakeLLM 下驱动
Agent v2 的 JSON-ReAct 路径,校验工具调用/审批闸门/最终回答与知识库效果;
`--real-llm` 模式为真实模型预留(见 run_agent)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402

from tests.fakes import FakeEmbeddings  # noqa: E402
from bobanana.database import db_manager  # noqa: E402
from bobanana.models import CardCreate  # noqa: E402
from bobanana.service.card_service import card_service  # noqa: E402

TARGET_HIT_RATE = 0.80
TOP_K = 5

# 基准卡片集:与 fixtures 主题一致,标题/别名/内容包含检索集期望关键词。
CARDS: list[dict] = [
    # 数字逻辑-逻辑门
    {"title": "与门", "category": "数字逻辑", "aliases": ["AND", "AND门"],
     "content": "与门逻辑表达式 Y=A·B,所有输入为1时输出才为1。", "examples": ["双钥匙门"]},
    {"title": "或门", "category": "数字逻辑", "aliases": ["OR", "OR门"],
     "content": "或门表达式 Y=A+B,任一输入为1输出即为1,并联开关。", "examples": ["楼道并联灯"]},
    {"title": "非门", "category": "数字逻辑", "aliases": ["NOT", "反相器"],
     "content": "非门输出与输入相反,表达式 Y=A'。", "examples": []},
    {"title": "异或门", "category": "数字逻辑", "aliases": ["XOR"],
     "content": "异或门两输入相异输出1,常用于奇偶校验与加法器本位和。", "examples": []},
    {"title": "与非门", "category": "数字逻辑", "aliases": ["NAND"],
     "content": "与非门是与门加非门,称为万能门,可搭建任意逻辑电路。", "examples": []},
    # 组合电路
    {"title": "半加器", "category": "数字逻辑", "aliases": [],
     "content": "半加器实现两个一位二进制数相加,S=A⊕B,C=A·B,不考虑低位进位。", "examples": []},
    {"title": "全加器", "category": "数字逻辑", "aliases": ["full adder"],
     "content": "全加器含进位输入Cin,输出本位和与进位,级联构成多位加法器。", "examples": []},
    {"title": "译码器", "category": "数字逻辑", "aliases": [],
     "content": "译码器把n位二进制码转换为2^n路输出中的一路有效,用于地址译码。", "examples": []},
    {"title": "编码器", "category": "数字逻辑", "aliases": [],
     "content": "编码器把2^n个输入信号编码为n位二进制码,如8-3编码器。", "examples": []},
    {"title": "多路选择器", "category": "数字逻辑", "aliases": ["MUX"],
     "content": "多路选择器根据选择信号从多路输入中挑一路输出。", "examples": []},
    # 电路分析
    {"title": "基尔霍夫电流定律", "category": "电路分析", "aliases": ["KCL"],
     "content": "KCL:流入节点的电流之和等于流出节点电流之和,本质是电荷守恒。", "examples": []},
    {"title": "基尔霍夫电压定律", "category": "电路分析", "aliases": ["KVL"],
     "content": "KVL:闭合回路电压降代数和为零,本质是能量守恒。", "examples": []},
    {"title": "节点电压法", "category": "电路分析", "aliases": [],
     "content": "节点电压法以节点电位为未知量列KCL方程,系统化求解电路。", "examples": []},
    {"title": "回路电流法", "category": "电路分析", "aliases": [],
     "content": "回路电流法以假想回路电流为未知量列KVL方程求解电路。", "examples": []},
    {"title": "戴维南定理", "category": "电路分析", "aliases": ["Thevenin"],
     "content": "线性含源二端网络等效为电压源与电阻串联,电压为开路电压Uoc。", "examples": []},
    {"title": "诺顿定理", "category": "电路分析", "aliases": ["Norton"],
     "content": "诺顿定理:二端网络等效为电流源与电阻并联,电流为短路电流Isc。", "examples": []},
    {"title": "最大功率传输定理", "category": "电路分析", "aliases": [],
     "content": "负载电阻等于等效内阻时获得最大功率 Pmax=Uoc²/4Req。", "examples": []},
    # 模拟电子
    {"title": "PN结", "category": "模拟电子", "aliases": [],
     "content": "PN结由P区与N区接触形成耗尽层,具有单向导电性,正偏导通反偏截止。", "examples": []},
    {"title": "二极管", "category": "模拟电子", "aliases": [],
     "content": "二极管伏安特性:硅管死区电压约0.7V,正偏导通后电压基本不变。", "examples": []},
    {"title": "稳压二极管", "category": "模拟电子", "aliases": ["齐纳管"],
     "content": "稳压二极管工作在反向击穿区,端电压稳定,需串联限流电阻。", "examples": []},
    {"title": "三极管放大电路", "category": "模拟电子", "aliases": ["共射极放大"],
     "content": "共射极放大电路:发射结正偏集电结反偏,输出与输入反相。", "examples": []},
    {"title": "静态工作点", "category": "模拟电子", "aliases": ["Q点"],
     "content": "静态工作点由偏置电阻决定,过高饱和失真,过低截止失真。", "examples": []},
    {"title": "放大倍数", "category": "模拟电子", "aliases": ["β", "beta"],
     "content": "三极管电流放大倍数β=Ic/Ib,电压放大倍数Au=-β·Rc/rbe。", "examples": []},
    # 电磁学
    {"title": "高斯定律", "category": "电磁学", "aliases": [],
     "content": "高斯定律:电场有源,电荷是电场的源,属麦克斯韦方程组。", "examples": []},
    {"title": "法拉第电磁感应定律", "category": "电磁学", "aliases": [],
     "content": "变化的磁场产生涡旋电场,属麦克斯韦方程组。", "examples": []},
    {"title": "位移电流", "category": "电磁学", "aliases": [],
     "content": "位移电流:变化的电场等价于电流,能激发磁场,麦克斯韦引入。", "examples": []},
    {"title": "安培环路定理", "category": "电磁学", "aliases": [],
     "content": "安培-麦克斯韦定律:电流与变化的电场都产生磁场。", "examples": []},
    {"title": "麦克斯韦方程组", "category": "电磁学", "aliases": ["Maxwell方程组"],
     "content": "四个方程:高斯定律、磁高斯定律、法拉第定律、安培-麦克斯韦定律,预言电磁波。", "examples": []},
    # 计算机组成
    {"title": "冯·诺依曼结构", "category": "计算机组成", "aliases": ["Von Neumann"],
     "content": "五大部件:运算器、控制器、存储器、输入设备、输出设备。", "examples": []},
    {"title": "存储程序", "category": "计算机组成", "aliases": [],
     "content": "程序与数据同存一个存储器,按地址取指令执行,冯诺依曼核心思想。", "examples": []},
    {"title": "指令周期", "category": "计算机组成", "aliases": [],
     "content": "指令周期含取指、译码、执行三阶段,程序计数器PC自动加一。", "examples": []},
    # 数据结构
    {"title": "栈", "category": "数据结构", "aliases": ["Stack"],
     "content": "栈后进先出LIFO,push/pop/peek,应用:调用栈、括号匹配、DFS。", "examples": ["浏览器后退"]},
    {"title": "队列", "category": "数据结构", "aliases": ["Queue"],
     "content": "队列先进先出FIFO,enqueue/dequeue,循环队列解决假溢出。", "examples": ["打印队列"]},
    # 操作系统
    {"title": "进程", "category": "操作系统", "aliases": ["Process"],
     "content": "进程是资源分配基本单位,PCB记录管理信息,三态:就绪/运行/阻塞。", "examples": []},
    {"title": "线程", "category": "操作系统", "aliases": ["Thread"],
     "content": "线程是CPU调度基本单位,同进程线程共享地址空间与文件资源。", "examples": []},
    {"title": "上下文切换", "category": "操作系统", "aliases": [],
     "content": "上下文切换保存恢复CPU现场,过频切换带来性能开销。", "examples": []},
    {"title": "并发与并行", "category": "操作系统", "aliases": [],
     "content": "并发是交替执行(单核轮转),并行是同时执行(多核)。", "examples": []},
]


def _build_index(embed: FakeEmbeddings, tmp_dir: Path):
    client = chromadb.PersistentClient(
        path=str(tmp_dir),
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    )
    # 注意: 不在此处恢复 db_manager,查询阶段需要保持隔离库生效;
    # 由 run_retrieval 的 finally 统一恢复。
    db_manager._client = client
    col = client.get_or_create_collection(
        name="eval_cards", metadata={"hnsw:space": "cosine"},
    )
    db_manager.switch_collection(col)
    for c in CARDS:
        card_service.create_card_sync(
            CardCreate(
                title=c["title"], category=c["category"], content=c["content"],
                aliases=c.get("aliases", []), examples=c.get("examples", []),
                source_file="eval", source_page=1,
            )
        )
    return client, col


def run_retrieval(limit: int | None, out: Path) -> dict:
    queries = [
        json.loads(line) for line in
        (HERE / "retrieval_queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if limit:
        queries = queries[:limit]

    tmp_dir = Path(tempfile.mkdtemp(prefix="swkb-eval-"))
    old_client, old_col = db_manager._client, db_manager.get_collection()
    try:
        _build_index(FakeEmbeddings(384), tmp_dir)
        hits, per_query = 0, []
        for q in queries:
            results = card_service.search_cards_sync(q["query"], top_k=TOP_K)
            kw = q["expected_keywords"]
            hit = False
            for c, _ in results[:TOP_K]:
                hay = c.title + " " + " ".join(c.aliases) + " " + c.content
                if any(k in hay for k in kw):
                    hit = True
                    break
            hits += int(hit)
            per_query.append({
                "id": q["id"], "query": q["query"], "hit": hit,
                "top5_titles": [c.title for c, _ in results[:TOP_K]],
            })
    finally:
        db_manager._client = old_client
        db_manager.switch_collection(old_col)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    hit_rate = hits / len(queries) if queries else 0.0
    report = {
        "benchmark": "retrieval",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": len(queries),
        "hits": hits,
        "hit_rate": round(hit_rate, 4),
        "target": TARGET_HIT_RATE,
        "passed": hit_rate >= TARGET_HIT_RATE,
        "per_query": per_query,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"检索评测: {hits}/{len(queries)} 命中,命中率 {hit_rate:.2%} (目标 ≥{TARGET_HIT_RATE:.0%})")
    for pq in per_query:
        if not pq["hit"]:
            print(f"  ✗ {pq['id']} {pq['query']!r} → top5: {pq['top5_titles']}")
    return report


# ═══════════════════════════════════════════════════════════
# Agent 评测(20 条指令,契约 §6.5 / docs/eval/README.md)
# ═══════════════════════════════════════════════════════════

AGENT_TARGET_RATE = 0.85

# 脚本化 ReAct 响应序列:每条指令预置「Action → Final Answer」轨迹。
# {占位符} 在运行时以种子卡片 ID 填充(如 {kcl_id})。
AGENT_SCRIPTS: dict[str, list[str]] = {
    "A-01": [
        'Action: create_card({"title": "异或门", "category": "数字逻辑", '
        '"content": "异或门真值表:两输入相异时输出1,常用于奇偶校验。", "examples": ["奇偶校验"]})',
        "Final Answer: 已创建卡片「异或门」,分类为数字逻辑。",
    ],
    "A-02": [
        'Action: create_card({"title": "半加器", "category": "数字逻辑", '
        '"content": "半加器实现两个一位二进制数相加,输出本位和S=A⊕B与进位C=A·B。", "examples": []})',
        'Action: create_card({"title": "全加器", "category": "数字逻辑", '
        '"content": "全加器含进位输入Cin,实现三位二进制求和。", "examples": []})',
        "Final Answer: 已创建「半加器」和「全加器」两张卡片。",
    ],
    "A-03": [
        'Action: create_card({"title": "PN结单向导电性", "category": "模拟电子", '
        '"content": "PN结正偏导通、反偏截止,具有单向导电性。", "examples": ["正向导通"]})',
        "Final Answer: 已创建卡片「PN结单向导电性」。",
    ],
    "A-04": [
        'Action: create_card({"title": "戴维南定理", "category": "电路分析", '
        '"content": "线性含源二端网络可等效为电压源与电阻串联,电压等于开路电压Uoc。", "examples": []})',
        "Final Answer: 已创建卡片「戴维南定理」。",
    ],
    "Q-01": [
        'Action: search_knowledge({"query": "基尔霍夫电压定律"})',
        "Final Answer: 基尔霍夫电压定律(KVL):沿闭合回路绕行一周,各元件电压降的代数和为零。",
    ],
    "Q-02": [
        'Action: search_knowledge({"query": "译码器"})',
        "Final Answer: 知识库中有「译码器」卡片:把n位二进制码转换为2^n路输出中的一路有效。",
    ],
    "Q-03": [
        'Action: search_knowledge({"query": "栈和队列的区别"})',
        "Final Answer: 栈是后进先出(LIFO),队列是先进先出(FIFO)。",
    ],
    "Q-04": [
        'Action: search_knowledge({"query": "二极管"})',
        "Final Answer: 知识库中与二极管相关的卡片有:二极管、稳压二极管、PN结。",
    ],
    "M-01": [
        'Action: search_knowledge({"query": "与门"})',
        'Action: update_card({"card_id_or_title": "与门", '
        '"content": "与门:所有输入为1时输出才为1。与非门是与门取反,被称为万能门,可搭建任意逻辑电路。"})',
        "Final Answer: 已更新「与门」卡片,补充了与非门对比说明。",
    ],
    "M-02": [
        'Action: search_knowledge({"query": "进程"})',
        'Action: update_card({"card_id_or_title": "进程", "category": "操作系统"})',
        "Final Answer: 已将「进程」卡片分类改为操作系统。",
    ],
    "M-03": [
        'Action: search_knowledge({"query": "全加器"})',
        'Action: update_card({"card_id_or_title": "全加器", "aliases": ["full adder"]})',
        "Final Answer: 已为「全加器」卡片增加别名 full adder。",
    ],
    "D-01": [
        'Action: delete_card({"card_id_or_title": "异或门"})',
        "Final Answer: 已删除「异或门」卡片。",
    ],
    "D-02": [
        'Action: search_knowledge({"query": "数字逻辑"})',
        'Action: delete_card({"card_id_or_title": "与门"})',
        'Action: delete_card({"card_id_or_title": "或门"})',
        "Final Answer: 已清空数字逻辑分类的卡片。",
    ],
    "Z-01": [
        'Action: start_quiz({"card_id_or_title": "基尔霍夫电压定律"})',
        "Final Answer: 已为「基尔霍夫电压定律」生成 3 道简答题。",
    ],
    "Z-02": [
        'Action: grade_quiz({"card_id": "@@kcl_id@@", '
        '"answers": [{"question": "什么是KCL", "answer": "流入节点的电流之和等于流出节点的电流之和"}]})',
        "Final Answer: 评分完成:KCL 回答正确,得分 8 分。",
    ],
    "Z-03": [
        'Action: start_quiz({"card_id_or_title": "三极管放大电路"})',
        "Final Answer: 已为「三极管放大电路」生成一份测验。",
    ],
    "E-01": [
        'Action: create_exam({"category_names": ["电路分析", "模拟电子"]})',
        "Final Answer: 已生成综合试卷,覆盖电路分析与模拟电子知识点。",
    ],
    "E-02": [
        'Action: create_exam({"category_names": ["数字逻辑"]})',
        "Final Answer: 已生成数字逻辑综合试卷。",
    ],
    "I-01": [
        'Action: upload_document({"file_path": "docs/eval/fixtures/md_kirchhoff.md"})',
        "Final Answer: 文档 md_kirchhoff.md 已导入知识库。",
    ],
    "I-02": [
        'Action: upload_document({"file_path": "docs/eval/fixtures/pdf_diode.pdf"})',
        "Final Answer: 文档 pdf_diode.pdf 已导入知识库。",
    ],
}

# 效果判定:评测后对知识库状态的断言(函数返回 (ok, 说明))
AGENT_EFFECTS: dict[str, list] = {
    "A-01": [lambda s: ("exists", "异或门")],
    "A-02": [lambda s: ("exists", "半加器"), lambda s: ("exists", "全加器")],
    "A-03": [lambda s: ("exists", "PN结单向导电性")],
    "A-04": [lambda s: ("exists", "戴维南定理")],
    "M-01": [lambda s: ("content_contains", "与门", "与非门")],
    "M-02": [lambda s: ("category_is", "进程", "操作系统")],
    "M-03": [lambda s: ("alias_contains", "全加器", "full adder")],
    "D-01": [lambda s: ("not_exists", "异或门")],
    "D-02": [lambda s: ("not_exists", "与门")],
    "I-01": [lambda s: ("exists", "基尔霍夫定律(导入)")],
    "I-02": [lambda s: ("exists", "二极管(导入)")],
}

# 期望触发审批闸门的指令
AGENT_APPROVAL_EXPECTED = {"D-01", "D-02"}

# 脚本化 FakeLLM:内层工具调用(出题/评分/提取)返回专用 JSON,其余按指令轨迹吐字。
class ScriptLLM:
    def __init__(self, scripts: dict[str, list[str]], seed_ids: dict[str, str]):
        self.scripts = {}
        for k, v in scripts.items():
            filled = []
            for s in v:
                for key, val in seed_ids.items():
                    s = s.replace("@@" + key + "@@", val)
                filled.append(s)
            self.scripts[k] = filled
        self.current: str | None = None
        self.pos = 0

    def set_instruction(self, iid: str):
        self.current = iid
        self.pos = 0

    def _inner(self, system: str, user: str) -> str | None:
        # 出题:仅当系统提示明确要求 JSON 数组且用户 prompt 以出题模板开头
        if system.strip().startswith("只返回 JSON 数组") and user.strip().startswith("为知识点生成"):
            return json.dumps([
                {"question": "请简述该知识点的核心内容", "ref_answer": "参考答案"},
                {"question": "举例说明其应用", "ref_answer": "应用示例"},
            ], ensure_ascii=False)
        if "严格评分" in user:
            n = user.count("Q:")
            return json.dumps([
                {"score": 8, "comment": "回答正确,掌握了核心概念。", "reference": "参考答案"}
                for _ in range(max(1, n))
            ], ensure_ascii=False)
        if "知识提取专家" in system:
            if "二极管" in user or "PN" in user:
                title, category = "二极管(导入)", "模拟电子"
            elif "基尔霍夫" in user or "电路" in user:
                title, category = "基尔霍夫定律(导入)", "电路分析"
            else:
                title, category = "知识点(导入)", "未分类"
            return json.dumps([{
                "title": title, "aliases": [],
                "content": f"{title}的核心内容:定义、原理与典型应用。",
                "examples": ["典型应用"], "questions": [f"什么是{title}"],
                "category": category,
            }], ensure_ascii=False)
        return None

    def __call__(self, system: str = "", user: str = "", timeout_sec: int | None = None) -> str:
        inner = self._inner(system or "", user or "")
        if inner is not None:
            return inner
        if self.current is None:
            return "Final Answer: 无指令。"
        seq = self.scripts.get(self.current, [])
        if not seq:
            return "Final Answer: 完成。"
        out = seq[min(self.pos, len(seq) - 1)]
        self.pos += 1
        return out

    def stream(self, system: str = "", user: str = "", timeout_sec: int | None = None):
        text = self(system, user, timeout_sec)
        step = max(1, len(text) // 8)
        for i in range(0, len(text), step):
            yield text[i:i + step]


def _find_card_by_title(title: str):
    cards, _ = card_service.list_cards_sync(limit=10000)
    for c in cards:
        if title in c.title:
            return c
    return None


def _check_effect(kind: str, *args) -> bool:
    card = _find_card_by_title(args[0]) if args else None
    if kind == "exists":
        return card is not None
    if kind == "not_exists":
        return card is None
    if kind == "content_contains":
        return card is not None and args[1] in (card.content or "")
    if kind == "category_is":
        return card is not None and card.category == args[1]
    if kind == "alias_contains":
        return card is not None and any(args[1] in a for a in (card.aliases or []))
    return False


def run_agent(limit: int | None, real_llm: bool, out: Path) -> dict:
    instructions = [
        json.loads(line) for line in
        (HERE / "agent_instructions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if limit:
        instructions = instructions[:limit]

    if real_llm:
        # 真实模型模式:不做脚本打桩,直接跑 run_agent_mode;审批事件人工/自动批准。
        report = {"benchmark": "agent", "mode": "real-llm", "results": []}
        raise NotImplementedError("真实 LLM 评测需交互式审批,暂以脚本化模式运行(--real-llm 待接)。")

    os.environ.setdefault("STUDYWIKI_TEST_MODE", "1")

    tmp_dir = Path(tempfile.mkdtemp(prefix="swkb-agent-eval-"))
    old_client, old_col = db_manager._client, db_manager.get_collection()
    try:
        client = chromadb.PersistentClient(
            path=str(tmp_dir), settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        db_manager._client = client
        col = client.get_or_create_collection(name="eval_agent_cards", metadata={"hnsw:space": "cosine"})
        db_manager.switch_collection(col)

        seed_ids: dict[str, str] = {}
        for c in CARDS:
            if c["title"] == "异或门":  # A-01 创建 / D-01 删除,种子库不预置
                continue
            created = card_service.create_card_sync(CardCreate(
                title=c["title"], category=c["category"], content=c["content"],
                aliases=c.get("aliases", []), examples=c.get("examples", []),
                source_file="eval", source_page=1,
            ))
            if c["title"] == "基尔霍夫电流定律":
                seed_ids["kcl_id"] = created.get("id", "")

        script_llm = ScriptLLM(AGENT_SCRIPTS, seed_ids)

        # 打桩:agent_react 经 tools 模块 import,双路径都替换;get_llm 返回无 bind_tools 对象,
        # 强制走 JSON-ReAct 兜底(与 STUDYWIKI_TEST_MODE=1 双重保险)。
        import bobanana.tools as bt
        import bobanana.agent_react as ar
        import bobanana.tools_schema as ts
        saved = (bt.llm_invoke, bt.llm_stream, bt.get_llm,
                 ar.llm_invoke, ar.llm_stream, ar.get_llm, ts.llm_invoke)
        bt.llm_invoke = script_llm
        bt.llm_stream = script_llm.stream
        bt.get_llm = lambda: None
        ar.llm_invoke = script_llm
        ar.llm_stream = script_llm.stream
        ar.get_llm = lambda: None
        ts.llm_invoke = script_llm

        results = []
        for ins in instructions:
            iid = ins["id"]
            events: list[dict] = []

            def stream_cb(evt):
                events.append(dict(evt))
                if evt.get("type") == "approval_required":
                    # 自动批准(评测脚本态),真实产品路径由客户端弹窗决定
                    from threading import Thread
                    Thread(
                        target=ar.resolve_approval,
                        args=(evt.get("approval_id"), True),
                        daemon=True,
                    ).start()

            script_llm.set_instruction(iid)
            passed, notes = True, []
            try:
                final = ar.run_agent_mode(ins["text"], [], None, None, stream_cb)
            except Exception as e:
                passed, final = False, f"异常: {e}"
                notes.append(f"异常 {type(e).__name__}")

            tools_called = {e["tool"] for e in events if e.get("type") == "tool.called"}
            expected = set(ins.get("expected_tools", []))
            if not expected.issubset(tools_called):
                passed = False
                notes.append(f"工具缺失: {sorted(expected - tools_called)}")

            for kw in ins.get("expected_keywords", []):
                if kw not in (final or ""):
                    passed = False
                    notes.append(f"最终回答缺少关键词 {kw!r}")

            approvals = [e for e in events if e.get("type") == "approval_required"]
            if iid in AGENT_APPROVAL_EXPECTED and not approvals:
                passed = False
                notes.append("缺少审批闸门事件")
            if iid not in AGENT_APPROVAL_EXPECTED and approvals:
                passed = False
                notes.append("意外触发审批闸门")

            for check in AGENT_EFFECTS.get(iid, []):
                kind, *args2 = check(None)
                if not _check_effect(kind, *args2):
                    passed = False
                    notes.append(f"效果校验失败: {kind} {args2}")

            results.append({
                "id": iid, "intent": ins.get("intent"), "text": ins["text"],
                "passed": passed, "notes": notes,
                "tools_called": sorted(tools_called), "final": (final or "")[:200],
            })
            print(f"  {'✓' if passed else '✗'} {iid} {ins['text'][:38]} → {notes or 'OK'}")

        # 还原打桩
        bt.llm_invoke, bt.llm_stream, bt.get_llm = saved[0], saved[1], saved[2]
        ar.llm_invoke, ar.llm_stream, ar.get_llm = saved[3], saved[4], saved[5]
        ts.llm_invoke = saved[6]
    finally:
        db_manager._client = old_client
        db_manager.switch_collection(old_col)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total, passed_n = len(results), sum(1 for r in results if r["passed"])
    rate = passed_n / total if total else 0.0
    report = {
        "benchmark": "agent",
        "mode": "scripted",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": total, "passed_count": passed_n, "success_rate": round(rate, 4),
        "target": AGENT_TARGET_RATE, "passed": rate >= AGENT_TARGET_RATE,
        "results": results,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Agent 评测: {passed_n}/{total} 成功,成功率 {rate:.0%} (目标 ≥{AGENT_TARGET_RATE:.0%})")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="StudyWiki 评测")
    ap.add_argument("bench", choices=["retrieval", "agent"], help="评测集")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    ap.add_argument("--real-llm", action="store_true", help="Agent 评测使用真实 LLM")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d-%H%M%S")
    out = HERE / "results" / f"{args.bench}-{ts}.json"

    if args.bench == "retrieval":
        report = run_retrieval(args.limit, out)
        return 0 if report["passed"] else 1

    report = run_agent(args.limit, args.real_llm, out)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
