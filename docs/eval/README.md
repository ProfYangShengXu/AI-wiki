# 评测资产(Eval Assets)

Agent 与检索回归评测的数据集与夹具,对应 `docs/next-phase-optimization.md` §6.5 与准备清单第 5 节。

## 目录

| 文件 | 内容 | 规模 |
| --- | --- | --- |
| `agent_instructions.jsonl` | 固定 Agent 评测指令 | 20 条(创建4/查询4/修改3/删除2/Quiz3/组卷2/导入2) |
| `retrieval_queries.jsonl` | 中文短查询 → 期望卡片关键词 | 50 条 |
| `fixtures/` | 小型课程文档夹具 | 10 份(4 Markdown + 3 PDF + 3 Word) |
| `generate_fixtures.py` | 重新生成 `fixtures/` 的脚本 | — |
| `run_eval.py` | 评测执行脚本(Agent 指令 + 检索) | 见脚本说明 |

## 字段说明

### agent_instructions.jsonl(每行一条)

```json
{
  "id": "A-01",
  "intent": "create|query|modify|delete|quiz|exam|import",
  "text": "自然语言指令",
  "expected_tools": ["预期被调用的工具"],
  "expected_title": "期望涉及的卡片标题(可选)",
  "expected_category": "期望分类(可选)",
  "expected_keywords": ["结果中应出现的关键词(可选)"],
  "requires_approval": true   // 删除/批量操作应为 true,评测时校验审批闸门
}
```

### retrieval_queries.jsonl(每行一条)

```json
{"id": "R-01", "query": "什么是与门", "expected_keywords": ["与门", "AND"]}
```

判定:对每条 query 取检索 Top5 卡片,若其中至少一张卡片的标题/别名/内容命中
`expected_keywords` 中任一关键词,记命中。指标 = 命中数 / 50,目标 ≥ 0.80。

## 夹具主题(与查询集一一对应)

| # | 文件 | 主题 | 覆盖查询 |
| --- | --- | --- | --- |
| 1 | md_digital_logic_gates.md | 逻辑门基础(与/或/非/异或/与非) | R-01~05 |
| 2 | md_digital_logic_combinational.md | 组合电路(加减法器/编译码/MUX) | R-06~10 |
| 3 | md_kirchhoff.md | 基尔霍夫定律 | R-11~15 |
| 4 | md_thevenin.md | 戴维南/诺顿定理 | R-16~20 |
| 5 | pdf_diode.pdf | 二极管与 PN 结 | R-21~25 |
| 6 | pdf_transistor.pdf | 三极管放大电路 | R-26~30 |
| 7 | pdf_maxwell.pdf | 麦克斯韦方程组 | R-31~35 |
| 8 | docx_von_neumann.docx | 冯·诺依曼结构 | R-36~40 |
| 9 | docx_stack_queue.docx | 栈与队列 | R-41~45 |
| 10 | docx_process_thread.docx | 进程与线程 | R-46~50 |

## 使用约定

1. 评测在隔离的临时知识库(`tmp_path` ChromaDB)中进行,不得污染生产 `chroma_db/`。
2. 检索评测不调用真实 LLM:embedding 用 `tests/fakes.py` 的 FakeEmbeddings。
3. Agent 评测默认使用 FakeLLM;真实模型跑分需显式 `--real-llm` 并配置 Key。
4. 模型切换或 Prompt 变更后必须跑评测,结果写入 `docs/eval/results/`(git 不入库)。
5. 重新生成夹具:`python docs/eval/generate_fixtures.py`。
