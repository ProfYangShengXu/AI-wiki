# StudyWiki-Agent / AIwiki2.0 下一阶段优化方案（Phase 2）

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 适用仓库 | `AIwiki2.0`（StudyWiki-Agent） |
| 当前版本 | v0.3.0 |
| 文档状态 | 待评审 |
| 建议周期 | 8 周（1 人全栈可按 10~12 周拆解） |
| 关联文档 | `docs/phase2-preparation-checklist.md`、`docs/adr/0001-client-platform.md` |

---

## 0. 执行摘要

当前 StudyWiki-Agent 已经具备“上传文档 → 提取知识卡片 → 问答/Quiz/组卷”的核心闭环，但产品形态仍是 **229 行单文件网页 + FastAPI**，存在 1 个启动级语法错误、Agent 手写 ReAct 脆弱、设置页可泄露 API Key、E2E 依赖真实 LLM 等问题。

下一阶段将把产品从“能跑通的课程项目”升级为“可分发、可测试、可维护的本地 AI 学习工具”：

1. **前端重写为 Android + Windows 应用**：Windows 作为完整本地工作台，Android 作为复习/Quiz/远程控制伴侣端；现有 Web 前端降级为兼容入口。
2. **UI/UX 产品化**：建立设计系统、深色/浅色主题、流式回答、上传进度、知识图谱、无障碍与中英文界面。
3. **Agent 优化**：从手写 CoT+ReAct 升级为结构化工具调用 + LangGraph 工作流，补齐校验、重试、流式、记忆、评测。
4. **集成**：统一本地服务打包、双端配对、LLM 供应商管理、ChromaDB 迁移、CI/CD 与分发。
5. **E2E 测试补全**：现有约 1,500 行测试基础上，补齐 WebSocket、上传后台任务、双端 UI E2E、FakeLLM/FakeEmbedding 测试底座与 CI 门禁。
6. **前期准备**：本次已完成基线盘点、路线图、准备清单、ADR 草案，并修复 4 个 P0 级基础问题（详见 12.1）。

---

## 1. 项目遍历与基线盘点

### 1.1 仓库结构（排除 `chroma_db/`、`uploads/`、`logs/` 等运行数据）

```text
AIwiki2.0/
├── main.py                         # 51 行，uvicorn 启动入口
├── pyproject.toml                  # pytest 配置（无 ruff/mypy/coverage 配置）
├── requirements.txt                # 40 行依赖
├── README.md                       # 64 行（本次已增加规划入口）
├── 2026-06-01-study-wiki-agent-design.md  # 651 行设计文档
├── setup.bat / start_studywiki.bat / create_*.ps1
├── bobanana/
│   ├── app.py                      # 177 行 FastAPI 入口（本次已做 P0 修复）
│   ├── config.py                   # 70 行配置
│   ├── models.py                   # 113 行 Pydantic 模型
│   ├── database.py                 # 221 行 ChromaDB 封装
│   ├── log_handler.py              # 38 行内存日志
│   ├── agent.py                    # 372 行三阶段导入工作流
│   ├── agent_react.py              # 246 行手写 CoT+ReAct
│   ├── tools.py                    # 490 行解析/分块/LLM/预扫描（含 P0 修复）
│   ├── tools_schema.py             # 340 行 12 个工具定义与执行
│   ├── routes/                     # cards/categories/history/upload/chat/quiz/settings/knowledgebase
│   └── service/card_service.py     # 315 行卡片服务（唯一写入口）
├── static/index.html               # 229 行单文件前端
├── static/vendor/                  # Pico/Alpine/marked CDN 本地化文件
├── tests/                          # 8 个测试文件，约 1,500 行
├── docs/                           # api/plan/design/optimization-plan
├── chroma_db/                      # 向量库运行数据（已 gitignore）
├── uploads/ / logs/ / tmp/
└── ltspice_installer.msi           # 应移出仓库的安装包
```

### 1.2 当前能力

| 能力 | 现状 |
| --- | --- |
| 文档解析 | PDF（PyMuPDF+OCR 降级）、Word、Markdown、TXT |
| 知识提取 | 三阶段流水线：预扫描 → 区间提取（短区间逐页/长区间聚合）→ 批量入库 |
| 知识库 | ChromaDB 向量检索 + 分类 + 多知识库 collection 切换 |
| Agent | Ask 模式（检索+回答）与 Agent 模式（手写 ReAct 调 12 个工具） |
| Quiz | 出题、AI 评分、掌握度追踪、综合组卷、Quiz 融合回卡片 |
| 前端 | 单文件 HTML（Pico CSS + 内联 CSS/JS + WebSocket） |
| 测试 | 8 个测试文件，覆盖模型/解析/部分路由/部分 Agent 解析 |
| 分发 | BAT 启动脚本 + PowerShell 快捷方式，无客户端安装包 |

### 1.3 现状问题清单

| 编号 | 级别 | 问题 | 证据 | 处置 |
| --- | --- | --- | --- | --- |
| F1 | P0 | `app.py` lifespan 存在重复 `except`，文件无法导入 | 原 58~65 行出现两个连续 `except Exception` | 本次已用嵌套 try 临时修复，M1 清理 |
| F2 | P0 | `tools.py get_llm()` 使用未定义的 `_llm`，首次调用必现 `NameError` | `get_llm` 第 300 行 `global _llm` 但模块级未初始化 | 本次已修复，见 `tools.py` 顶部 `_llm = None` |
| F3 | P0 | 设置页读写错误 `.env` 路径 | `routes/settings.py` 原 `ENV_PATH = Path(__file__).parent.parent / ".env"` 实际指向 `bobanana/.env`，而 `config.py` 读取根目录 `.env` | 本次已改为 `BASE_DIR / ".env"` |
| F4 | P0 | 设置 API 原样返回并允许覆盖全部 `.env`，含 API Key | `/api/settings/` 返回 `env` 字典无脱敏；`save_setting` 不校验 key 白名单 | M1 修复：脱敏 + 白名单 + 本地令牌 |
| F5 | P1 | 前端单文件 229 行，`innerHTML` 拼接未做 HTML 转义，存在存储型 XSS | `static/index.html` 中 `linkify()` 后直接插入 `innerHTML`；测试 `test_xss_in_title` 甚至断言 `<script>` 原样保存 | 新客户端强制渲染前消毒；Web 端同步修复 |
| F6 | P1 | CORS `allow_origins=["*"]` 与 `allow_credentials=True` 组合非法且不安全 | `app.py` 85~92 行 | 改为白名单 + 本地 Token |
| F7 | P1 | Agent 手写字符串 ReAct，无参数 Schema 校验、无确认闸门、无流式输出 | `agent_react.py` 全文；`execute_tool` 只捕获异常 | M3 重构 |
| F8 | P1 | 导入任务不可取消/不可恢复，进度只到区间粒度；上传后 `run_in_executor` 任务无持久化 | `agent.py` 309~343 行；`routes/upload.py` 22~54 行 | M2/M3 重构 |
| F9 | P1 | Quiz/生成/评分接口直接依赖真实 LLM，E2E 测试不稳定且烧钱 | `tests/test_e2e.py` Quiz 类未 mock；`routes/quiz.py` 直调 `llm_invoke` | 补 FakeLLM 夹具，测试与真实模型分离 |
| F10 | P1 | 测试直接使用生产 `chroma_db/`，缺少临时库隔离，多测试文件可能互相污染 | 各测试 `fixture` 直接 `PersistentClient(path=str(CHROMA_DB_DIR))` | 统一 `tmp_path` 夹具 |
| F11 | P2 | 多知识库通过全局 `_collection` 切换，上传任务与用户在途请求可能读到错误库 | `database.py` + `knowledgebase.py` | M3 改为请求级绑定/租户上下文 |
| F12 | P2 | 检索仅有向量相似度，无 BM25/混合检索/重排，中文短查询召回一般 | `database.py search_cards` | M3 混合检索 |
| F13 | P2 | 仓库根目录存在 `ltspice_installer.msi` 等大文件与 `tmp/` 运行数据 | 根目录遍历 | P0 清理并补 `.gitattributes` |
| F14 | P2 | 缺少 CI、ruff、mypy、覆盖率门禁 | 无 `.github/workflows`，`pyproject.toml` 仅 pytest | P0/M1 补工程化 |
| F15 | P2 | 版本与启动脚本不一致 | `setup.bat` 显示 v0.3.6，后端为 v0.3.0；`start_studywiki.bat` 固定等待 10 秒后打开浏览器，不检查 `/health` | M1 统一版本源 + 健康检查后打开浏览器 |
| F16 | P1 | 无首次进入强制配置 API Key 机制 | 新用户未配置 Key 时会直接进入主界面，随后所有 Agent/导入操作失败，错误信息散落在日志 | 架构文档 5.5：灰屏强制配置 + `/api/bootstrap/*` |

---

## 2. 阶段目标与成功指标

### 2.1 目标

- G1：交付 Android 与 Windows 两个可安装 MVP，核心旅程“连接服务 → 浏览知识库 → 提问 → Quiz → 查看掌握度”可用。
- G2：UI/UX 达标：新手 5 分钟内完成首次连接；核心任务完成率 ≥ 90%；SUS ≥ 80。
- G3：Agent 在 20 条固定评测指令上任务成功率 ≥ 85%，工具调用参数合法率 100%。
- G4：后端以 sidecar 方式被 Windows 端可靠拉起，Android 可扫码/验证码配对。
- G5：E2E 全链路在 CI 中全绿，核心库覆盖率 ≥ 80%。

### 2.2 非目标

- 不把现有 Web 前端删除：作为轻量兼容入口和维护界面保留。
- 不在 Android 端内置完整 Python 运行时/导入引擎；Android 以学习、Quiz、缓存与远程控制为主。
- 不引入需要云端的用户系统；本地单用户优先，预留未来同步接口。

### 2.3 指标

| 维度 | 指标 | 目标 |
| --- | --- | --- |
| 客户端 | Android/Windows 核心旅程自动化通过率 | 100% |
| 客户端 | 双端崩溃率（灰度） | ≤ 0.5% |
| 体验 | 首次连接成功率 | ≥ 95% |
| 体验 | SUS | ≥ 80 |
| Agent | 20 条评测指令成功率 | ≥ 85% |
| Agent | 工具参数 JSON 合法率 | 100% |
| 检索 | 中文短查询 Top5 命中率（人工标注集） | ≥ 0.80 |
| 测试 | 核心库行覆盖率 | ≥ 80% |
| 工程 | PR 门禁时长 | ≤ 12 分钟 |

---

## 3. 总体路线图

| 阶段 | 时间 | 主题 | 关键交付 |
| --- | --- | --- | --- |
| P0 | 第 0 周 | 准备与止血 | 本文档、清单、ADR、P0 修复、基线标签、CI 骨架 |
| M1 | 第 1~2 周 | 服务契约与工程底座 | OpenAPI v1、鉴权、FakeLLM/Embedding 测试底座、临时 Chroma 夹具、CI |
| M2 | 第 3~5 周 | 双端客户端与 UI/UX | Windows MVP、Android MVP、设计系统、流式 UI、上传进度 |
| M3 | 第 6~7 周 | Agent 与集成 | 结构化工具调用、LangGraph 化、混合检索、本地服务打包、双端配对 |
| M4 | 第 8 周 | E2E 与发布 | 客户端 E2E 补全、性能/无障碍验收、MSIX+AAB 打包发布 |

---

## 4. 工作流 W1：前端重写为 Android 与 Windows 应用

### 4.1 重写范围

- 现有 `static/index.html`（原生 JS + 内联 CSS）不再作为主要体验，转为：
  - 浏览器轻量兼容入口（保留只读浏览、上传、Ask）；
  - 新客户端开发期间的调试界面。
- 新前端由 **Flutter 单码库**同时产出 Android 与 Windows（默认方案，ADR 已记录），或按 ADR 回退为 Kotlin/Compose + WinUI 3 双原生。

### 4.2 推荐技术栈（ADR-0001 草案）

| 层 | 选择 |
| --- | --- |
| UI | Flutter 3.x + Material 3，自适应桌面/手机布局 |
| 状态管理 | Riverpod；导航 go_router |
| 网络 | Dio + WebSocket；`openapi-generator` 生成 DTO |
| 本地存储 | Windows：Drift(SQLite)/文件缓存；Android：Room 或 Drift + DataStore |
| 安全 | flutter_secure_storage / Windows DPAPI（经平台通道） |
| 打包 | Android AAB；Windows MSIX（`msix` 工具链） |

备选：若 Windows 端需要深度托盘/文件关联/进程管理，可仅将 Windows 壳层改为 WinUI 3，核心 Dart 业务仍可复用。

### 4.3 目标架构

```text
┌─────────────────────────┐      ┌──────────────────────────┐
│ Android App（复习伴侣）  │      │ Windows App（完整工作台） │
│ Flutter / 离线缓存       │      │ Flutter + 本地 sidecar    │
└────────────┬────────────┘      └────────────┬─────────────┘
             │ 局域网配对 HTTPS/WSS            │ 本地 127.0.0.1
             └───────────────┬────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │ study-wiki-core      │
                  │ FastAPI v1 服务       │
                  │ REST + WebSocket      │
                  │ 鉴权/租户/任务/日志    │
                  └──────────┬───────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
          ChromaDB       LLM 适配层      文件解析/OCR
```

- Windows 端负责完整能力：导入文档、Agent 操作、Quiz、模型配置、日志。
- Android 端支持两种模式：
  1. 配对模式：通过局域网连接 Windows 上的 `study-wiki-core`；
  2. 离线复习模式：从 Windows 导出只读知识包后本地浏览、Quiz、掌握度缓存，回连后同步答题结果。

### 4.4 Windows 客户端页面

| 页面 | 关键能力 |
| --- | --- |
| 首次启动向导 | 检测 Python/uv 环境 → 启动 sidecar → 配置模型 → 导入示例文档 |
| 知识库工作台 | 多库切换、分类树、卡片列表、知识图谱视图 |
| 卡片详情 | Markdown 渲染（消毒）、超链接跳转、来源页码、编辑历史 |
| Agent 对话 | Ask/Agent 模式切换、工具调用时间线、流式回答、操作审批 |
| 导入中心 | 拖拽上传、OCR/解析进度、区间提取进度、失败重试、任务取消 |
| Quiz/Exam | 出题、答题、评分详情、掌握度热力图 |
| 设置 | 供应商配置（Key 脱敏）、嵌入模型、检索参数、日志查看 |

### 4.5 Android 客户端页面

| 页面 | 关键能力 |
| --- | --- |
| 配对 | 二维码/6 位配对码连接 Windows 服务 |
| 今日复习 | 掌握度最低卡片优先、每日目标 |
| 卡片阅读 | 离线缓存、字号调节、深色模式、卡片间跳转 |
| 快问快答 | Ask 模式（在线）；离线时可浏览缓存卡片 |
| Quiz | 答题/自评、结果回传、错题本 |
| 我的 | 知识库同步状态、存储占用、导出/导入 |

### 4.6 共享契约

- `api/openapi.yaml`：`/v1/auth`、`/v1/kbs`、`/v1/cards`、`/v1/chat`、`/v1/upload/tasks`、`/v1/quiz`、`/v1/mastery`。
- WebSocket `/v1/ws/chat` 事件：
  `session.started`、`llm.delta`、`tool.called`、`tool.result`、`approval_required`、`session.done`、`session.error`。
- 错误码：`SW-<DOMAIN>-<CODE>`，如 `SW-AUTH-001`、`SW-TASK-404`。
- 所有时间字段 ISO 8601 UTC；所有长任务返回 `task_id` 并支持轮询或 SSE。

---

## 5. 工作流 W2：UI/UX 提升

### 5.1 当前体验问题

- 单页混合中英文控件，无设计令牌，内联样式与 Tailwind 类混用。
- 上传后无实时进度，聊天无流式输出，思考状态只有“thinking”。
- 卡片内容直接 `innerHTML`，缺少安全渲染和 Markdown 完整支持。
- 无深色模式、无响应式布局、无键盘导航、无空/错/加载态规范。

### 5.2 设计系统

- 令牌：颜色（浅/深/高对比三套）、字体、间距、圆角、阴影、动效。
- 组件：知识卡片、分类树、Agent 步骤时间线、工具调用卡、流式 Markdown、掌握度环图、导入进度条、审批弹窗。
- 交互规范：
  - 加载：骨架屏优先于 spinner；
  - 空态：引导导入第一份文档；
  - 错误态：可操作提示（重试/复制日志/切换模型）；
  - 危险操作：删除卡片/知识库/清除数据必须确认，Agent 删除走审批。
- 无障碍：对比度 WCAG AA、触控目标 ≥ 48dp、焦点顺序、屏幕阅读器标签、字号缩放 200%。
- 中英文 i18n：客户端字符串全部走 ARB/资源文件，不硬编码。

### 5.3 关键体验流程

| 流程 | Phase 2 体验目标 |
| --- | --- |
| 首次启动 | 未配置 API Key 时强制进入灰屏引导页，禁止跳过；配置并验证成功后进入“导入示例 → 开始使用”，全程 ≤ 5 分钟 |
| 文档导入 | 实时显示“解析 12/40 页 → 提取区间 3/6 → 已入库 18 张卡”，可取消 |
| Agent 对话 | 逐 token 流式显示；工具调用折叠为步骤卡；删除/覆盖操作弹审批 |
| Quiz | 答完即时反馈，错题可一键生成复习卡片补充 |
| 学习复习 | 掌握度热力图 + 每日推荐，弱项优先 |
| 错误恢复 | 所有失败可复制 trace_id，日志页支持过滤与导出 |

### 5.3.1 首次进入灰屏强制配置 API Key

- 首次进入且无有效云端 API Key 时，主界面被全屏灰屏遮罩（`blur + grayscale`），不可跳过、不可关闭。
- 灰屏包含：供应商选择、API Key 输入、显示/隐藏、测试连接、保存并进入。
- 后端新增 `/api/bootstrap/status`、`/api/bootstrap/test`、`/api/bootstrap/configure`。
- 只有 Key 验证成功并写入根目录 `.env` 后，灰屏才解除。
- 刷新或重启后，已配置用户直接进入主界面；删除 `.env` 后灰屏重新出现。
- 详细状态机、API 契约、安全与验收见 `docs/design/2026-06-01-study-wiki-agent-architecture.md` 5.5 节。


### 5.4 UX 度量与验证

- 每迭代 1 轮 5 人可用性测试，核心任务记录成功率/耗时/错误数。
- 灰度埋点（默认关闭、可授权）：页面耗时、上传成功率、Agent 成功率、Quiz 完成率。
- 发布前执行设计 QA 清单与无障碍检查。

---

## 6. 工作流 W3：Agent 优化

### 6.1 现状与重构方向

现状：`agent_react.py` 把工具说明拼进 Prompt，依赖正则解析 `Action: tool({...})`，存在以下问题：

- 工具参数不经过 JSON Schema 校验，错误参数会被 `execute_tool` 吞成 `{"error": ...}`；
- 无重试策略、无工具调用预算、无确认闸门；
- 每次循环拼接越来越长的 conversation，Token 成本高；
- 模型只有单点调用，`get_llm()` 初始化失败无降级链。

### 6.2 Agent v2 架构

```text
用户指令
   ↓
意图分类：ask | kb_operation | import | quiz
   ↓
LangGraph StateGraph
   ├─ plan（生成步骤）
   ├─ tool_calls（结构化 function calling，一次可调用 1 个）
   ├─ validate（Pydantic/JSON Schema 校验 + 参数补全）
   ├─ approve（删除/批量更新/清库需用户确认）
   ├─ observe（结果摘要 + 引用来源）
   └─ final（最终回答，附卡片链接）
```

关键规则：

| 能力 | 实现 |
| --- | --- |
| 工具调用 | 优先使用模型原生 tool/function calling；Ollama 不支持时回退结构化 JSON ReAct |
| 参数校验 | `tools_schema.py` 由 Pydantic 模型生成，非法调用不进入执行层 |
| 重试 | 参数错误重试 1 次；模型超时退避重试 2 次 |
| 预算 | `max_turns`、`max_tokens`、`max_wall_time` 三级预算 |
| 流式 | `astream_events` 推送 `llm.delta` 与 `tool.called` |
| 记忆 | 会话历史持久化到本地 SQLite；跨会话项目上下文（当前 KB、常用分类） |
| 审批 | 删除卡片/知识库、批量修改默认 `approval_required`，客户端弹窗确认 |
| 降级链 | DeepSeek → OpenAI → Ollama 按可用性自动降级 |

### 6.3 导入 Agent 增强

- 任务状态机：`queued → scanning → extracting → linking → done/failed/cancelled`。
- 断点续跑：区间结果先写 `tmp/import_tasks/{task_id}/`，重启可恢复。
- 取消：解析与提取循环检查 `cancel_event`，取消后保留已完成卡片。
- 速率控制：Token bucket，默认 10s/15 次 LLM 调用可配置。
- 入库：每完成一个区间立即批量入库并推送进度，避免“全部完成后一次性导入”。
- 去重：标题规范化 + 别名 + 语义相似度双重去重，重复项返回 `skipped` 而不是静默丢弃。

### 6.4 检索增强

- BM25 + 向量混合检索，RRF 融合；
- 查询扩展/改写（同义词、课程术语）；
- 元数据过滤：分类、来源文件、掌握度；
- 检索结果附带出处卡片链接，供 UI 引用；
- 建立 50 条中文课程问答标注集，作为检索回归基准。

### 6.5 Agent 评测

- 固定评测集：20 条指令（创建/查询/修改/删除/Quiz/组卷/导入各 2~4 条）+ 10 份小型文档夹具。
- 指标：任务成功率、工具调用准确率、参数合法率、平均轮次、Token 成本、完成耗时。
- 模型切换或 Prompt 变更必须跑评测集，结果写入 `docs/eval/`。

---

## 7. 工作流 W4：集成

### 7.1 本地服务打包与双端连接

| 集成项 | 方案 |
| --- | --- |
| Windows sidecar | PyInstaller 打包 `study-wiki-core.exe`；客户端负责启动/停止/健康检查/日志收集 |
| Android 配对 | 同一局域网二维码配对或 6 位码；短期 JWT + 设备 ID；TLS 自签证书指纹校验 |
| 服务发现 | mDNS/Bonjour 广播，可选手动 IP:Port |
| 本地鉴权 | 启动时生成 `~/.studywiki/auth.json`，API 除 `/health` 外要求 `Authorization: Bearer` |

### 7.2 LLM 与 Embedding 集成

- 供应商统一适配器：DeepSeek / OpenAI / Ollama，统一 `chat()`、`embed()`、`list_models()` 接口。
- API Key 使用 Windows DPAPI / Android Keystore 加密存储，`/api/settings` 只回显末 4 位。
- 嵌入模型维度在启动时与 ChromaDB 实际维度校验，不一致时提供迁移命令而非仅 warning。
- 离线模式：模型缓存路径显式配置，失败原因可读。

### 7.3 数据与文件集成

- ChromaDB schema 加版本号与迁移脚本；集合切换改为“请求级绑定”，移除全局可变 `_collection` 竞态。
- 导出/导入：知识库导出为 Markdown + 元数据 JSON 或 `.swkb` 压缩包；Android 离线包由此生成。
- 文件安全：上传大小限制（默认 100MB）、扩展名+魔数校验、文件名 UUID 化、原始名入元数据。
- 仓库清理：移除 `ltspice_installer.msi`、`tmp/` 运行数据，补充 `.gitattributes`。

### 7.4 工程与发布集成

- GitHub Actions：`lint → unit → contract → api-e2e → coverage → build-clients`。
- Windows：MSIX 签名、自动更新源；Android：AAB + 内部测试轨道。
- 浏览器兼容入口继续由 FastAPI 静态目录提供，但版本号统一从 `bobanana/__init__.py` 读取。

---

## 8. 工作流 W5：E2E 测试补全

### 8.1 现状

- 已有 8 个测试文件、约 1,500 行，覆盖 Pydantic 模型、Markdown/文本解析、PDF 解析、ChromaDB CRUD、部分路由与 ReAct 解析器。
- 主要缺口：真实 LLM 测试、真实生产 Chroma 路径、WebSocket、后台上传任务轮询、设置安全、客户端 UI、CI 门禁。

### 8.2 目标测试金字塔

```text
L5 双端 E2E：Android(Maestro/Compose) + Windows(FlaUI/WinAppDriver)
L4 服务 E2E：TestClient + WebSocket + 上传任务轮询 + FakeLLM/FakeEmbedding
L3 API 集成：全部路由，使用临时 Chroma 目录
L2 契约：OpenAPI、工具 Schema、模型序列化、配置项
L1 单元：解析、分块、ReAct/JSON、设置、检索融合、任务状态机
```

### 8.3 关键补全清单

| 测试 | 覆盖点 |
| --- | --- |
| `tests/contract/test_tools_schema.py` | 12 个工具 schema 可生成 Pydantic 模型，必填/类型正确 |
| `tests/contract/test_openapi.py` | OpenAPI 与路由实现一致，响应模型可序列化 |
| `tests/e2e/test_ws_chat.py` | 欢迎消息、Ask 流式、Agent 工具事件、断线清理 |
| `tests/e2e/test_upload_task.py` | 上传返回 task_id → 轮询到 done → 卡片可检索；失败任务可重试 |
| `tests/e2e/test_settings_security.py` | Key 脱敏、白名单、未授权 401 |
| `tests/e2e/test_kb_isolation.py` | 并发切换 KB 时数据隔离（用临时库） |
| `tests/e2e/android/`、`tests/e2e/windows/` | 配对、浏览、Quiz、断线重连、冷启动 |
| `tests/perf/test_import_smoke.py` | 10 页样例导入 < 阈值（FakeLLM） |

### 8.4 测试底座

- `tests/fakes.py`：
  - `FakeLLM`：按指令返回预置 JSON/工具调用/流式事件；
  - `FakeEmbeddings`：确定性哈希向量；
  - 通过 `monkeypatch` 注入 `bobanana.tools.llm_invoke` 与 `card_service._embedding_fn`。
- ChromaDB 夹具：每个测试使用 `tmp_path` 新建 PersistentClient；禁止使用生产 `chroma_db/`。
- 环境变量：`STUDYWIKI_TEST_MODE=1` 禁用网络检查与真实模型加载。
- CI：`windows-latest` + `ubuntu-latest`，Python 3.11/3.12/3.13；pytest-cov、pytest-xdist、ruff、mypy。
- 报告：JUnit XML + HTML 覆盖率 + E2E 截图/录屏；失败自动附服务日志。

### 8.5 质量门禁

- PR：L1+L2+L3+L4 必过；核心库覆盖率 ≥ 80%；ruff/mypy 零新增错误。
- 发布候选：L5 双端核心旅程全绿 + Agent 评测集 ≥ 85% + UX 可用性测试通过。
- 数据迁移/ChromaDB 版本变更：额外跑迁移回滚测试。

---

## 9. 阶段分工建议（1 人全栈顺序）

1. 先完成 P0 清理与测试底座（测试先行，锁定现有 API）。
2. 定义 OpenAPI v1 与 WebSocket 事件字典，冻结后双端并行开发。
3. Windows 端先做（sidecar 调试链短），Android 端复用契约与组件。
4. Agent 重构放在双端 MVP 之后，避免 UI 同时依赖不稳定的 Agent 接口。
5. 最后两周集中 E2E、打包、性能与验收。

---

## 10. 风险与应对

| 风险 | 概率 | 影响 | 应对 |
| --- | --- | --- | --- |
| Flutter Windows 端成熟度不满足 | 中 | 高 | 第 1 周做平台探针：托盘/进程/WebSocket/MSIX；不通过则 ADR 回退 WinUI 3 |
| 真实 LLM 测试烧钱且不稳定 | 高 | 中 | FakeLLM 默认；真实模型测试标记 `@llm` 仅夜间手动跑 |
| ChromaDB 多集合并发问题 | 中 | 高 | 请求级上下文绑定 + 并发隔离测试先行 |
| 双端 UI 人力不足 | 中 | 中 | 单码库 Flutter；Web 兼容入口保留 |
| 数据迁移损坏现有知识库 | 低 | 高 | 迁移前自动备份 ChromaDB；提供 dry-run 与回滚 |
| 局域网配对安全风险 | 中 | 高 | 短期 Token + 设备指纹 + 高危操作二次确认，不暴露公网 |

---

## 11. 验收标准（Phase 2 完成定义）

- [ ] Windows MVP 与 Android MVP 均能构建、安装、连接本地服务。
- [ ] 双端完成“连接 → 浏览卡片 → 提问 → Quiz → 掌握度”核心旅程且 L5 E2E 通过。
- [ ] 现有 Web 入口无回归，且 XSS 修复完成。
- [ ] Agent 工具调用参数合法率 100%，20 条评测指令成功率 ≥ 85%。
- [ ] 导入任务可取消、失败可重试、进度实时可见。
- [ ] `/api/settings` 不再泄露 Key；所有 API 有本地 Token 保护。
- [ ] 首次进入且无有效 Key 时，Web/Windows/Android 均显示灰屏，不可跳过；Key 验证成功后才进入主界面。
- [ ] 删除 `.env` 后重启会重新触发灰屏；已配置用户重启不触发。
- [ ] CI 全绿：lint/type/unit/contract/api-e2e/coverage。
- [ ] 核心库覆盖率 ≥ 80%，测试不触碰生产 `chroma_db/`。
- [ ] MSIX 与 AAB 产物可安装，README 与 `docs/api.md` 同步更新。

---

## 12. 前期准备（P0）

### 12.1 本次已落地

| 事项 | 状态 |
| --- | --- |
| 正确工作区 `AIwiki2.0` 全量遍历与基线盘点 | ✅ 见第 1 节 |
| 创建下一阶段优化主文档 | ✅ `docs/next-phase-optimization.md` |
| 创建可勾选准备清单 | ✅ `docs/phase2-preparation-checklist.md` |
| 完成客户端技术选型 ADR 草案 | ✅ `docs/adr/0001-client-platform.md` |
| 修复 `tools.py` 缺失 `_llm` 初始化（F2） | ✅ 已修改 |
| 修复 `app.py` 重复 `except` 语法错误（F1，临时 workaround） | ✅ 已修改，M1 清理 |
| 修复设置页 `.env` 路径错误（F3） | ✅ 已修改 |
| 统一根路由版本号为 v0.3.0 | ✅ 已修改 |
| `start_studywiki.bat` 改为直连 venv Python + `/health` 就绪轮询，不再固定等 10 秒 | ✅ 已实现 |
| `setup.bat` 改为直连 venv Python + pip 错误可见 | ✅ 已实现 |
| `tools.py` LLM 调用复用全局线程池，不再每次创建/销毁 executor | ✅ 已实现 |
| 首次进入灰屏强制配置 API Key 架构方案 | ✅ 已写入架构文档 5.5 与 `docs/api.md` |
| 首次进入灰屏后端实现 | ✅ `bobanana/routes/bootstrap.py` + `app.py` 路由注册 + `config.OPENAI_BASE_URL` |
| 首次进入灰屏 Web 实现 | ✅ `static/index.html` 灰屏遮罩、Key 验证/保存、主界面锁定 |
| 首次进入灰屏测试 | ✅ `tests/test_bootstrap.py` |
| Flutter 客户端前端源码（Android/Windows 共享） | ✅ `client/`：灰屏配置页、知识库、对话、Quiz、设置 |
| 设置 API Key 脱敏 + 白名单校验 | ✅ `bobanana/routes/settings.py` |
| CORS 本地白名单 | ✅ `bobanana/app.py` |
| 可选本地 Token 鉴权 | ✅ `STUDYWIKI_AUTH_TOKEN` + `app.py` 中间件；Flutter 支持 `--dart-define=API_TOKEN` |
| 上传大小限制 + 魔数校验 + UUID 文件名 | ✅ `bobanana/routes/upload.py` |
| Web 前端 XSS 基础修复（esc + linkify 转义） | ✅ `static/index.html` |
| 掌握度算法修复（最高分/满分，不再越答越低） | ✅ `bobanana/routes/quiz.py`、`tools_schema.py` |
| FakeLLM / FakeEmbeddings 测试替身 | ✅ `tests/fakes.py` |
| CI 工作流 | ✅ `.github/workflows/ci.yml` |
| `.gitattributes` 二进制与换行规则 | ✅ 已创建 |
| README 增加下一阶段规划入口 | ✅ 已更新 |

### 12.2 开发前仍需完成

剩余事项（代码侧已完成，以下需要本地执行或发布资源）：

1. 本地验证：`python -c "import bobanana.app"`、`pytest`、`flutter pub get` / `flutter test`。
2. 生成 Flutter 平台壳并编译：`flutter create . --platforms=android,windows`。
3. 打基线标签 `v0.3.0-phase2-baseline` 并清理 `ltspice_installer.msi`、`tmp/` 等运行数据。
4. Flutter Windows 平台探针，确认或推翻 ADR-0001。
5. 冻结 OpenAPI v1 与 WebSocket 事件字典。
6. 准备 20 条 Agent 评测指令与 10 份文档夹具。
7. 确认 Android 签名、Windows 签名/分发通道。
8. 可用性测试与双端 E2E 执行。

---

## 13. 补充计划（2026-07-15 增补）

### 13.1 建议必做的 4 项

| 补充项 | 原因 | 计划 |
| --- | --- | --- |
| S1 掌握度模型修复 | 当前 `mastery_pct = score / (attempts * 10)` 会随着答题次数增加而下降；`create_exam` 还会无条件给卡片加分 | 改为指数加权或滑动窗口模型，长期引入 SM-2 间隔重复；掌握度只由真实评分更新 |
| S2 启动性能与后台预热 | `app.py` lifespan 同步预加载 sentence-transformers，会阻塞启动；`CHROMA_DISK_WARN_MB/STOP_MB` 配置存在但未使用 | 增加 `--skip-model-preload`；模型改为后台预热，`/health` 区分 `ready/warming`；接入磁盘水位保护 |
| S3 备份/恢复/迁移 | ChromaDB、`uploads/`、`mastery.json`、`.env` 目前无备份方案 | Windows 端增加一键备份/恢复；任何 schema 或 collection 变更前自动备份，支持 dry-run 与回滚 |
| S4 安全收口 | 上传文件名只做简单替换，无大小限制、魔数校验；日志和设置可能泄露 Key；Agent 可能被 Prompt Injection 诱导执行危险操作 | 上传 UUID 化 + 大小/魔数校验；日志脱敏；删除/清库/批量覆盖必须审批；CORS 白名单 |

### 13.2 建议作为增强的 4 项

| 补充项 | 说明 |
| --- | --- |
| S5 可观测性 | 所有请求、导入任务、LLM 调用带 `trace_id`；结构化 JSON 日志 + 滚动；记录导入成功率、LLM 延迟/Token、检索延迟、Quiz 完成率 |
| S6 AI 成本与质量治理 | Prompt 版本化管理；按任务设置 Token 预算；LLM 响应缓存（只缓存确定性请求）；DeepSeek → OpenAI → Ollama 熔断降级链 |
| S7 检索质量专项 | BM25 + 向量混合检索、RRF 融合、重排；OCR 质量评分；中文短查询评测集进入 CI 夜间任务 |
| S8 离线与同步 | Android 离线知识包带版本哈希；增量同步卡片、掌握度、Quiz 记录；冲突进入“待确认队列”而不是自动覆盖 |

### 13.3 建议补充到 Phase 2 验收标准

- [ ] 掌握度不因多次答题下降，并有回归测试。
- [ ] 备份→删除库→恢复演练通过。
- [ ] 200 页 PDF 冒烟测试不阻塞 UI，可取消。
- [ ] 服务冷启动 P95 ≤ 10 秒，模型预热不阻塞 `/health` 就绪。
- [ ] `/api/settings` 与日志中不出现完整 API Key。
- [ ] Android 离线包可导入、可增量更新。

---

## 附录 A：问题 → 工作项映射

| 问题 | 主责工作项 | 验收 |
| --- | --- | --- |
| F1 | P0/M1 | `bobanana.app` 可导入，启动无警告 |
| F2 | P0 | `get_llm()` 单测覆盖 |
| F3 | P0 | 设置页读写根 `.env`，测试覆盖 |
| F4 | W4 | Key 脱敏 + 白名单 + 鉴权 |
| F5 | W2/W4 | 新客户端与 Web 入口均无 XSS |
| F6 | W4 | CORS 白名单，预检测试 |
| F7 | W3 | Agent v2 + 评测 |
| F8 | W2/W3 | 任务状态机 + 取消/恢复 E2E |
| F9 | W5 | FakeLLM 底座，真实模型测试独立 |
| F10 | W5 | 测试全用 `tmp_path` |
| F11 | W3/W4 | KB 隔离并发测试 |
| F12 | W3 | 混合检索 + 中文标注集 |
| F13 | P0 | 仓库清洁检查 |
| F14 | P0/M1 | CI 全绿 |
| F15 | M1 | 单一版本源，启动脚本等待 `/health` 就绪 |
| F16 | M1/M2 | 三端灰屏强制配置，`/api/bootstrap/*` 测试通过 |

## 附录 B：基线文件与本次修改点

- `bobanana/tools.py`：新增 `_llm = None`；新增共享 LLM 线程池与 `_ExecutorProxy`，`llm_invoke` 不再每次创建线程池。
- `start_studywiki.bat`：直连 `.venv\Scripts\python.exe`，用 `/health` 轮询替代固定 `timeout 10`，失败可见。
- `setup.bat`：直连 venv Python 安装依赖，pip 失败时停止并显示错误。
- `bobanana/app.py`：重复 `except` 临时 workaround；根路由版本改为 0.3.0。
- `bobanana/routes/settings.py`：`ENV_PATH` 改为 `BASE_DIR / ".env"`。
- 新增 `bobanana/routes/bootstrap.py`：`/api/bootstrap/status|test|configure` 三个接口。
- `static/index.html`：首次进入灰屏遮罩、Key 测试与保存、主界面锁定/解锁。
- 新增 `tests/test_bootstrap.py`：灰屏状态、Key 验证、`.env` 写入与明文泄漏回归。
- 新增 `client/`：Flutter 前端源码，包含 BootstrapGate、灰屏配置页、知识库、对话、Quiz、设置页。
- 新增 `docs/next-phase-optimization.md`、`docs/phase2-preparation-checklist.md`、`docs/adr/0001-client-platform.md`。
- `README.md`：新增“下一阶段规划”章节。
