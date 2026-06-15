# 🧠 StudyWiki-Agent

> 你的私人维基百科，由 AI 代笔，为学习而生 📚✨

---

**StudyWiki-Agent** 是一个本地知识库 AI Agent。扔给它 PDF/Word/Markdown，它会自动提取知识点、生成带超链接的维基式知识卡片，还能用 LLM 出题考你、跟踪掌握度、智能组卷——全部跑在你自己的电脑上。

---

## 🔥 它能干什么？

| 功能 | 说明 |
|------|------|
| 📄 **自动解析** | PDF / Word / Markdown 扔进去，知识卡片自动生成 |
| 🔗 **知识链接** | 卡片内容自动识别其他卡片标题/别名，生成超级链接 |
| ❓ **Quiz 闯关** | 每张卡片出 3-5 道简答题，AI 严肃打分 + 详解 |
| 📊 **掌握度追踪** | 每次 Quiz 自动更新百分比，绿色进度条一目了然 |
| 📝 **智能组卷** | 勾选多个分类，AI 生成跨知识点的综合试卷 |
| ✏️ **编辑/删除** | 不满意？随时改、随时删 |
| 🤖 **Agent 模式** | 用自然语言操作：「创建一张逻辑门的卡片」「为电磁感应出题」 |
| 🔍 **语义搜索** | 不用精确匹配，模糊搜索自动检索知识库 |
| 🏠 **纯本地** | 数据在你自己硬盘里，不传云端 |

---

## 🚀 5 秒快速开始

```bash
# 1. 下载
git clone https://github.com/ProfYangShengXu/AI-wiki.git
cd AI-wiki

# 2. 安装 (Windows)
双击 setup.bat

# 3. 配置 API Key
# 编辑 .env 填入你的 DEEPSEEK_API_KEY 或 OPENAI_API_KEY

# 4. 启动
双击桌面 StudyWiki-Agent.bat
# 或者
python main.py
# 打开 http://localhost:8000
```

---

## 🏗️ 系统架构

```
┌─ 你 ──────────────────────────────────┐
│  Browser (DaisyUI) ←→ WebSocket Chat   │
└────────────┬──────────────────────────-┘
             │ HTTP / WS
┌────────────▼──────────────────────────┐
│  FastAPI Backend                       │
│  ├── 规划层 agent_react.py (CoT+ReAct) │
│  ├── 执行层 tools_schema.py (12 工具)   │
│  └── 记忆层 database.py (ChromaDB)     │
└────────────────────────────────────────┘
```

---

## 🛠️ 技术栈

- **前端**: 原生 JS + 内联 CSS（零框架依赖，轻如鸿毛）
- **后端**: FastAPI + Uvicorn
- **AI**: DeepSeek / OpenAI / Ollama
- **向量库**: ChromaDB（本地持久化）
- **嵌入**: sentence-transformers（all-MiniLM-L6-v2）

---

## 🎯 为什么不用 XXXX？

- **Notion** → 联网的，数据不在你手
- **Obsidian** → 不自动提取，得自己写
- **ChatGPT** → 聊完就忘，没有知识库

**StudyWiki-Agent** = 自动提取 + 知识链接 + Quiz 掌握 + 全部本地

---

## 🤝 贡献

提 Issue 或 PR 都欢迎。自己用的项目，顺手就行。

---

## 📜 License

MIT — 随便用，随便改。
