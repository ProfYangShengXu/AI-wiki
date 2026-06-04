# StudyWiki-Agent

基于 LangChain + LangGraph 的可增长可编辑本地 Wiki 知识库 AI Agent。

将散乱的课件文档（PDF/Word/MD）转化为结构化的、可交互的本地 Wiki 知识库，支持智能问答和知识卡片关联跳转。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. （可选）下载前端资源，支持完全离线
python scripts/download_vendor.py

# 3. 启动服务
python main.py

# 4. 打开浏览器
#    http://localhost:8000
```

> **首次启动**会自动下载 sentence-transformers 嵌入模型（~80MB），需联网。

---

## 配置

通过环境变量配置，无需修改代码：

### LLM 配置（至少配一个）

```bash
# 方式 A: OpenAI (推荐)
export OPENAI_API_KEY=sk-xxxxx

# 方式 B: Ollama (本地离线)
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=llama3
```

### 嵌入模型配置

```bash
# 默认使用 sentence-transformers (本地，无需 API Key)
# 也可切换为 OpenAI 嵌入:
export EMBEDDING_PROVIDER=openai
export OPENAI_API_KEY=sk-xxxxx
```

### 服务配置

```bash
export HOST=0.0.0.0       # 监听所有网卡 (默认 127.0.0.1)
export PORT=8000          # 端口 (默认 8000)
export DEBUG=true         # 调试模式
```

---

## 功能

| 功能 | 状态 | 说明 |
|------|------|------|
| **文档解析** | ✅ | PDF / Word / Markdown / 纯文本 |
| **知识提取** | ✅ | LLM 自动提取知识点，生成结构化卡片 |
| **语义搜索** | ✅ | 向量相似度搜索，支持自然语言查询 |
| **智能问答** | ✅ | 基于知识库的上下文问答 |
| **网络补充** | ✅ | 信息不足时自动搜索网络补充 |
| **卡片关联** | ✅ | 内容中自动检测卡片关系，双向链接 |
| **超链接导航** | ✅ | Wiki 风格的内容内链接跳转 |
| **离线运行** | ✅ | 配置 Ollama + sentence-transformers |
| **卡片 CRUD** | ✅ | 创建、读取、更新、删除知识卡片 |

---

## 项目结构

```
AIwiki/
├── bobanana/                  # Python 主包
│   ├── config.py              # 集中配置 (环境变量驱动)
│   ├── models.py              # Pydantic 数据模型
│   ├── database.py            # ChromaDB 操作 + lifecycle
│   ├── service/
│   │   └── card_service.py    # 写入隔离 + 关联检测
│   ├── tools.py               # 文档解析 / 嵌入 / 网络搜索
│   ├── agent.py               # LangGraph 工作流
│   ├── routes/                # API 路由
│   │   ├── cards.py           # 卡片 CRUD
│   │   ├── upload.py          # 文件上传 + Agent 导入
│   │   ├── chat.py            # WebSocket 对话
│   │   ├── categories.py      # 分类
│   │   └── history.py         # 浏览历史
│   └── app.py                 # FastAPI 应用 + 异常处理
├── static/index.html          # 前端页面
├── tests/                     # 36 个单元测试
├── docs/                      # 设计 / 架构 / 工期文档
├── uploads/                   # 上传文件
├── chroma_db/                 # 向量数据库
├── main.py                    # 启动入口
└── requirements.txt           # Python 依赖
```

---

## 开发路线

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 核心骨架 — 项目结构 + 数据库 + 路由 + 前端布局 | ✅ 完成 |
| P2 | 核心功能 — 文档解析 + Agent 工作流 + 问答 | ✅ 完成 |
| P3 | 交互增强 — 关联检测 + 超链接 + 搜索浮窗 + 目录 | ✅ 完成 |
| P4 | 打磨收尾 — 测试 + 错误处理 + 文档 + 离线 | ✅ 完成 |

---

## API 概览

```
GET    /api/cards              # 卡片列表 (支持 ?category=&page=&limit=)
GET    /api/cards/{id}         # 卡片详情
POST   /api/cards              # 创建卡片
PUT    /api/cards/{id}         # 更新卡片
DELETE /api/cards/{id}         # 删除卡片
GET    /api/cards/search?q=    # 语义搜索
POST   /api/upload             # 上传文件 (PDF/Word/MD)
GET    /api/categories         # 分类列表
GET    /api/history            # 浏览历史
WS     /ws/chat                # Agent 对话
GET    /health                 # 健康检查
```

---

## 运行测试

```bash
python -m pytest tests/ -v
```

---

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | Python 3.12+, FastAPI |
| AI 框架 | LangChain, LangGraph |
| LLM | OpenAI GPT-4 / Ollama |
| 向量数据库 | ChromaDB (进程内) |
| 嵌入模型 | sentence-transformers / OpenAI |
| 文档解析 | PyMuPDF, python-docx, markdown |
| 网络搜索 | DuckDuckGo |
| 前端 | Alpine.js + DaisyUI + Tailwind CSS |

## License

MIT
