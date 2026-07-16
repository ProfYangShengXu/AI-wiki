# StudyWiki-Agent

本地知识库 AI Agent。PDF / Word / Markdown 扔进去，自动提取知识点、生成带超链接的维基式知识卡片，支持 Quiz 出题、掌握度追踪、智能组卷，全部本地运行。

---

**功能**

- 自动解析 PDF / Word / Markdown，生成知识卡片
- 卡片间自动识别标题/别名，生成超链接
- 每张卡片出 3-5 道简答题，AI 打分 + 详解
- 每次 Quiz 自动更新掌握度百分比
- 多分类勾选，AI 生成综合试卷
- 自然语言操作：「创建一张逻辑门的卡片」「为电磁感应出题」
- 语义模糊搜索，不要求精确匹配
- 纯本地运行，数据不上云

**快速开始**

```bash
git clone https://github.com/ProfYangShengXu/AI-wiki.git
cd AI-wiki
# Windows: 双击 setup.bat
# 编辑 .env 填入 DEEPSEEK_API_KEY 或 OPENAI_API_KEY
# 双击 StudyWiki-Agent.bat 或 python main.py
# 浏览器打开 http://localhost:8000
```

**系统架构**

```
Browser (DaisyUI) ← WebSocket → FastAPI Backend
  ├─ 规划层 agent_react.py (CoT+ReAct)
  ├─ 执行层 tools_schema.py (12 工具)
  └─ 记忆层 database.py (ChromaDB)
```

**技术栈**

前端: 原生 JS + 内联 CSS / 后端: FastAPI + Uvicorn / AI: DeepSeek / OpenAI / Ollama / 向量库: ChromaDB / 嵌入: sentence-transformers

---

**对比**

- Notion: 联网，数据不在本地
- Obsidian: 不自动提取，需要手动写
- ChatGPT: 聊完就忘，没有知识库

---

**License**

MIT
