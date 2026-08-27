# StudyWiki-Agent

本地优先的知识库 AI Agent。把 PDF / Word / Markdown / TXT 扔进去，自动提取知识点、生成带超链接的维基式知识卡片，支持 Agent 自然语言操作、Quiz 出题与评分、掌握度追踪、智能组卷。数据全部本地保存，不上云。

多端可用：**Web 前端**、**Windows 客户端**、**Android App**、**Linux 桌面**（WSL 测试）。

---

## 功能

**知识导入与整理**
- 自动解析 PDF / Word / Markdown / TXT，提取知识点生成知识卡片
- 卡片间自动识别标题/别名，生成可点击的超链接关联
- 分类管理：新建 / 重命名 / 删除（含自定义分类与 7 类规范分类收敛）
- 语义混合检索：BM25 + 向量余弦 RRF 融合，不要求精确匹配
- 导入任务状态机：排队 → 扫描 → 提取 → 关联 → 完成/失败/取消，支持取消、断点续跑、去重报告、限速

**Agent 模式**
- 自然语言操作：「创建一张逻辑门的卡片」「为电磁感应出题」「导入 XXX.pdf」
- 13 个工具：搜索/建卡/改卡/删卡/导入文档/出题/评分/组卷/查掌握度/联网补充
- 结构化工具调用（Pydantic 校验、token 预算熔断、审批闸门、流式输出、会话记忆）

**Quiz 与学习**
- 每张卡片生成 3-5 道简答题，AI 评分 + 详解
- Quiz 卡片**永久保存**（SQLite），支持中途编辑题目/答案、草稿、提交评分
- Quiz 页按关键词搜索卡片（重合度排序）一键出题
- 掌握度追踪、多分类智能组卷

**多模型与成本**
- 8 家 LLM 供应商：DeepSeek / OpenAI / Ollama（本地）/ Kimi / GLM / Grok / Anthropic / Gemini
- 客户端一键切换供应商（即时生效，无需重启）
- Token 消耗统计（`/api/metrics`）

**其它**
- 设备配对：手机扫码连接电脑后端（局域网真机可用）
- 一键备份 / 恢复（`/api/backup/*`）
- 全链路可观测：`X-Trace-Id`、指标埋点、日志脱敏
- 纯本地运行，数据与 API Key 均留在本机

---

## 快速开始

**Windows（推荐）**
1. 下载 [最新 release](https://github.com/ProfYangShengXu/AI-wiki/releases/latest) 的 `client-windows.zip`（免安装）或 `studywiki-setup.exe`（一键安装）
2. 解压双击 `studywiki_client.exe`，首次启动按引导填入 API Key（如 DeepSeek）
3. 客户端会自动拉起内置后端，浏览器打开 `http://127.0.0.1:8000` 也可用 Web 版

**Android**
1. 安装 `studywiki-client-debug.apk`
2. 模拟器：直接打开即可（后端在宿主机）
3. 真机：电脑端「设置 → 设备配对 → 生成二维码」→ 手机「设备配对 → 扫码配对」→ 自动连接

**从源码跑后端（开发）**
```bash
git clone https://github.com/ProfYangShengXu/AI-wiki.git
cd AI-wiki
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 编辑 .env 填入 DEEPSEEK_API_KEY（或其它供应商 KEY）
python main.py
# 浏览器打开 http://localhost:8000
```

---

## 系统架构

```
┌───────────── 客户端 ─────────────────────────────────────────────┐
│  Web (原生 JS)  /  Flutter (Windows·Android·Linux)              │
│       │  HTTP (REST) + WebSocket (流式)                          │
└───────┼──────────────────────────────────────────────────────────┘
        ▼
┌───────────── 后端 (FastAPI) ────────────────────────────────────┐
│  规划层  agent_react.py   (CoT + ReAct 循环)                    │
│  执行层  tools_schema.py  (13 工具 · Pydantic 校验 · 审批)       │
│  检索层  retrieval.py     (BM25 + 向量余弦 RRF 混合检索)         │
│  记忆层  ChromaDB(卡片+向量) · SQLite(会话/Quiz) · JSON(掌握度)  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 技术栈

**后端**
- 语言：Python 3.11 / 3.12
- Web 框架：FastAPI + Uvicorn，REST + WebSocket 流式
- 向量库：ChromaDB（持久化，384 维）
- 嵌入：sentence-transformers（all-MiniLM-L6-v2，本地运行）
- LLM：LangChain 统一抽象，支持 8 家供应商（DeepSeek / OpenAI / Ollama / Kimi / GLM / Grok / Anthropic / Gemini）
- 文档解析：PyMuPDF（PDF）/ python-docx（Word）/ markdown / pytesseract（OCR）
- 联网补充：duckduckgo_search

**客户端**
- Flutter（Dart），一套代码三端：Windows / Android / Linux 桌面
- 状态管理：flutter_riverpod
- 网络：dio（HTTP）+ web_socket_channel（WS 流式）
- 其它：tray_manager（托盘）、file_picker（选文件）、qr_flutter + mobile_scanner（配对扫码）、shared_preferences（本地配置）

**Web 前端**
- 原生 JS + 内联 CSS（无框架），`static/index.html` 单文件

**工程质量**
- 测试：pytest（后端）+ flutter test（客户端）
- 静态检查：ruff / mypy（后端）、flutter analyze（客户端）
- CI/CD：GitHub Actions —— 双系统测试矩阵 + 三端产物构建（PyInstaller 后端 exe、Flutter Windows/Android、安装包）

---

## 项目结构

```
AI-wiki/
├── bobanana/            # 后端（FastAPI）
│   ├── agent_react.py   #   Agent 规划层（ReAct）
│   ├── tools_schema.py  #   工具定义与执行
│   ├── database.py      #   ChromaDB 封装
│   ├── quiz_store.py    #   Quiz 卡片 SQLite 存储
│   ├── routes/          #   API 路由（cards/categories/quizzes/chat/...）
│   └── config.py        #   配置与 .env
├── client/              # Flutter 客户端
│   ├── lib/pages/       #   页面（wiki/chat/quiz/settings/...）
│   ├── lib/widgets/     #   组件（聊天面板/分类下拉/...）
│   └── lib/core/        #   API 客户端 / 配置
├── static/index.html    # Web 前端
├── tests/               # 后端测试
└── .github/workflows/   # CI / 发布流水线
```

---

## License

MIT
