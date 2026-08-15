# StudyWiki-Agent 工期方案

> **估算基准：** 1 人全栈开发（Python + 前端）  
> **总工期：** 5-6 周（乐观/保守）  
> **总工时：** ~26 人天

---

## 第一期：核心骨架 (Week 1) — 可运行的空项目

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 项目脚手架搭建 | 0.5d | `main.py`, `requirements.txt`, 目录结构 |
| 配置文件实现 | 0.5d | `config.py` — LLM/Embedding/ChromaDB 配置 |
| 数据模型定义 | 1d | `models.py` — KnowledgeCard Pydantic 模型 |
| ChromaDB 操作封装 | 1d | `database.py` — CRUD + 向量搜索 + 集合管理 |
| FastAPI 应用骨架 | 1d | `app.py` — 路由注册、CORS、静态文件挂载 |
| 前端骨架 (DaisyUI 布局) | 1d | `static/index.html` — Header/Sidebar/Content/Chat 布局 |

**里程碑：** `python main.py` 能启动，浏览器显示空壳页面 ✅

---

## 第二期：核心功能 (Week 2-3) — 能跑通主流程

| 任务 | 工时 | 交付物 |
|------|------|--------|
| Agent 工具集开发 | 2d | `tools.py` — 文档解析(PDF/Word/MD)、网络搜索、ChromaDB查询 |
| LangGraph 导入工作流 | 2d | `agent.py` — doc_parse → need_search → web_search → card_generate |
| LangGraph 问答工作流 | 1d | `agent.py` — qa_search → qa_answer 子图 |
| REST API 卡片 CRUD | 1d | GET/POST/PUT/DELETE `/api/cards/*` |
| REST API 文件上传 | 0.5d | POST `/api/upload` |
| WebSocket 对话接口 | 1d | `/ws/chat` — 用户 ↔ Agent 实时通信 |
| 前端：卡片展示组件 | 1d | CardView — 标题/内容/案例/问题渲染 |
| 前端：对话窗口组件 | 1d | ChatPanel — 消息列表 + 输入框 + Markdown 渲染 |
| 前端：文件上传交互 | 0.5d | 拖拽/选择文件 → 上传 → 进度显示 |

**里程碑：** 上传 PDF → 自动解析 → 生成卡片 → 问答对话 全链路跑通 ✅

---

## 第三期：交互增强 (Week 4)

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 前端：目录侧边栏 | 1d | Sidebar — 按分类展开/折叠、卡片列表 |
| 前端：搜索栏 | 0.5d | SearchBar — 实时搜索、结果列表 |
| 前端：前进/后退导航 | 0.5d | NavControls — 浏览历史栈管理 |
| 前端：超链接跳转 | 0.5d | 卡片内容中关键词 → 关联卡片跳转 |
| 卡片修改工作流 | 1.5d | Agent 修改 + ChromaDB 更新 |
| 知识补全工作流 (网络搜索) | 1d | Agent 搜索 → 生成预览 → 确认 → 入库 |
| 关联检测逻辑 | 0.5d | 入库/修改时自动建立卡片关联 |
| 分类与历史 API | 1d | `/api/categories`, `/api/history` |

**里程碑：** 完整 Wiki 浏览体验 — 目录导航、搜索、超链接跳转、前进后退 ✅

---

## 第四期：打磨与收尾 (Week 5)

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 单元测试 | 1.5d | `tests/` — models、database、agent 测试 |
| 错误处理与异常恢复 | 1d | 文件解析失败、LLM 超时、网络搜索失败处理 |
| UI 细节打磨 | 1d | 加载状态、空状态、错误提示、响应式适配 |
| README 与使用说明 | 0.5d | 安装步骤、配置说明、使用指南 |
| 本地模型集成 (Ollama) | 1d | 可选后端，零 API Key 运行 |

**里程碑：** v1.0 正式版可交付 ✅

---

## 总工期汇总

| 阶段 | 周期 | 工时 | 产出 |
|------|------|------|------|
| **P1 核心骨架** | 1 周 | 5 人天 | 可启动的空项目 |
| **P2 核心功能** | 2 周 | 10 人天 | 文档导入 → 解析 → 问答全链路 |
| **P3 交互增强** | 1 周 | 6 人天 | 完整 Wiki 浏览体验 |
| **P4 打磨收尾** | 1 周 | 5 人天 | 测试 + 容错 + 文档 |
| **总计** | **5-6 周** | **26 人天** | **v1.0 正式版** |

---

## 甘特图

```
Week 1     Week 2     Week 3     Week 4     Week 5
├──────────┼──────────┼──────────┼──────────┼──────────┤
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
│  P1       │      P2        │     P3     │     P4     │
│ 骨架      │   核心功能      │  交互增强   │  打磨收尾  │
│           │                │            │            │
│ config    │ tools          │ Sidebar    │ tests      │
│ models    │ agent(导入)    │ SearchBar  │ error-handle│
│ database  │ agent(问答)    │ NavControls│ UI polish  │
│ app       │ 卡片CRUD       │ 超链接     │ README     │
│ index.html│ WebSocket      │ 修改工作流  │ Ollama     │
│           │ CardView       │ 补全工作流  │            │
│           │ ChatPanel      │ 关联检测    │            │
│           │ 文件上传        │ 分类/历史   │            │
└──────────┴──────────────┴────────────┴────────────┘
```

---

## 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| LLM 解析 PDF 逐页调用 Token 超限 | 中 | 高 | 实现分页策略 + 文本截断，单页超限时降级摘要 |
| ChromaDB 嵌入维度配置不匹配 | 低 | 中 | `config.py` 统一维度配置，启动时校验 |
| 前端 Alpine.js 状态管理复杂度超预期 | 中 | 中 | 监控状态膨胀，必要时引入轻量状态库 |
| DuckDuckGo 搜索结果不稳定/限流 | 低 | 中 | tools.py 中实现缓存 + 降级提示 |
| 本地 Ollama 推理速度影响体验 | 中 | 低 | GPT-4 为默认后端，Ollama 列为可选项 |

---

## 交付检查清单

### P1 结束检查
- [ ] `python main.py` 可启动
- [ ] 浏览器访问 `localhost:8000` 显示布局
- [ ] 所有依赖在 `requirements.txt` 中

### P2 结束检查
- [ ] 上传 PDF → 解析 → 生成卡片 → 存入 ChromaDB
- [ ] 对话窗口可发送问题 → 收到 Agent 回答
- [ ] REST API 卡片 CRUD 全部通过

### P3 结束检查
- [ ] 侧边栏展开/折叠正常
- [ ] 搜索栏实时过滤
- [ ] 前进/后退导航正常
- [ ] 超链接跳转关联卡片
- [ ] 修改/补全工作流通用

### P4 结束检查
- [ ] 单元测试覆盖率 > 70%
- [ ] 所有异常路径有处理
- [ ] README 可指导新用户完成安装
- [ ] Ollama 模式可离线运行
