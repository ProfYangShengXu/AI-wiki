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

**Phase 2 已落地能力(2026-08)**

- Agent v2:结构化工具调用(Pydantic 校验/预算熔断/审批闸门/流式事件/会话记忆/供应商降级链)
- 导入任务状态机:`queued → scanning → extracting → linking → done/failed/cancelled`,支持取消、断点续跑、去重报告、限速
- 混合检索:BM25 + 向量余弦 RRF 融合,元数据过滤;检索基准 50/50、Agent 基准 20/20
- ChromaDB 生命周期:磁盘水位保护、定时 persist、失败写入重试;一键备份/恢复(`/api/backup/*`)
- 可观测性:`X-Trace-Id` 全链路、`/api/metrics` 指标、日志 Key 脱敏
- 统一契约:SW 错误码、`api/openapi.yaml` v1(39 路径)、`/api/pair/*` 设备配对
- Web 前端:流式聊天、深色主题、上传进度、审批弹窗、知识图谱
- 工程质量:ruff/mypy 零错误、覆盖率 80%(CI 门禁)、无 API Key 全绿、完整 CI(双系统矩阵 + Flutter 构建)

**下一阶段规划**

- 主方案：[docs/next-phase-optimization.md](docs/next-phase-optimization.md) — Android/Windows 客户端、UI/UX、Agent 优化、集成与 E2E 测试路线图
- 准备清单：[docs/phase2-preparation-checklist.md](docs/phase2-preparation-checklist.md)
- 技术选型 ADR：[docs/adr/0001-client-platform.md](docs/adr/0001-client-platform.md)
- Flutter 客户端：[client/README.md](client/README.md) — Android/Windows 共享前端源码
- Linux/WSL 测试：[docs/testing-linux-wsl.md](docs/testing-linux-wsl.md) — 虚拟机测试环境与一键脚本


---

**License**

MIT
