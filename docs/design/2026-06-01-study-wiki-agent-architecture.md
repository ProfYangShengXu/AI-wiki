# StudyWiki-Agent 架构文档

> **版本：** v2.0  
> **日期：** 2026-06-01  
> **基于：** 软件设计文档 v1.0  
> **面向：** 开发者与维护者

---

## 1. 系统架构总览

```
┌────────────────────────────────────────────────────────────────────┐
│                         用户层 (Browser)                           │
│  本地 HTML + Alpine.js + DaisyUI    (静态资源已下载到 static/)     │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │ CardView │ │  Sidebar   │ │ ChatPanel│ │   NavControls     │  │
│  │ 卡片展示  │ │ 目录导航    │ │ 对话窗口  │ │  前进/后退/搜索    │  │
│  └────┬─────┘ └─────┬──────┘ └────┬─────┘ └─────────┬─────────┘  │
│       │             │             │                  │            │
│  ┌────▼─────────────▼─────────────▼──────────────────▼────────┐  │
│  │            前端状态管理层 (Alpine.js Store + EventBus)      │  │
│  │   store: { currentCard, history, categories, chatMessages }│  │
│  │   EventBus: 'card:loaded' / 'sidebar:refresh' / 'nav:push' │  │
│  └────────────────────────────────────────────────────────────┘  │
└───────┬────────────────┬────────────────┬────────────────────────┘
        │ REST           │ REST           │ WebSocket
┌───────▼────────────────▼────────────────▼────────────────────────┐
│                        接入层 (FastAPI)                           │
│                                                                   │
│  ┌─ 直通路由 (数据操作，不经 Agent) ──────────────────────────┐  │
│  │  routes/cards.py     GET/POST/PUT/DELETE /api/cards/*      │  │
│  │  routes/categories   GET /api/categories                   │  │
│  │  routes/history.py   GET/POST /api/history                 │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ 转发路由 (需 AI 处理，经 Agent) ──────────────────────────┐  │
│  │  routes/upload.py    POST /api/upload → CardService → Agent │  │
│  │  routes/chat.py      WS  /ws/chat    → CardService → Agent │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────┬──────────────────────────────────────────┬─────────────┘
           │  直通 (读/简单写)                          │ 转发 (需 AI)
           ▼                                           ▼
┌────────────────────────────────────────────────────────────────────┐
│                     CardService 层 (新增)                          │
│                                                                   │
│  职责：唯一写入入口，序列化所有数据库变更                          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  interface CardService {                                   │  │
│  │    get_card(id)        → 直接读 ChromaDB                   │  │
│  │    list_cards(filter)  → 直接读 ChromaDB                   │  │
│  │    create_card(data)   → asyncio.Lock → ChromaDB.add       │  │
│  │    update_card(id,data)→ asyncio.Lock → update + re-embed  │  │
│  │    delete_card(id)     → asyncio.Lock → ChromaDB.delete    │  │
│  │    batch_import(cards) → asyncio.Lock → 逐条写入 + 关联检测 │  │
│  │  }                                                         │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────┬────────────────────────────────────────────────────────┘
           │
┌──────────▼────────────────────────────────────────────────────────┐
│                    AI Agent 层 (LangGraph)                        │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              StateGraph 工作流 (含失败恢复)               │    │
│  │                                                          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐       │    │
│  │  │ doc_parse│→│ need_    │→│ web_search (可选) │       │    │
│  │  │ (逐页)   │  │ search   │  └────────┬─────────┘       │    │
│  │  └────┬─────┘  └────┬─────┘           │                  │    │
│  │       │              │                ▼                  │    │
│  │       │              └──────────┬──────────────────┐     │    │
│  │       ▼                         ▼                  ▼     │    │
│  │  ┌──────────┐  ┌──────────────────────────────┐          │    │
│  │  │knowledge_│←│  knowledge_extract (含重试)  │          │    │
│  │  │ extract   │  └──────────────────────────────┘          │    │
│  │  └────┬─────┘                                             │    │
│  │       ▼                                                   │    │
│  │  ┌──────────┐  ┌──────────────────┐  ┌──────────────┐    │    │
│  │  │card_     │→│ chroma_store     │→│关联检测 & 通知 │    │    │
│  │  │ generate  │  │ (via CardService)│  │              │    │    │
│  │  └──────────┘  └──────────────────┘  └──────────────┘    │    │
│  │                                                          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐       │    │
│  │  │qa_search │→│qa_answer │  │ card_modify       │       │    │
│  │  │ (含重试)  │  │ (含重试)  │  │ (含 schema 校验)  │       │    │
│  │  └──────────┘  └──────────┘  └──────────────────┘       │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐      │
│  │ Tools 工具集  │  │ Memory 记忆   │  │ Prompts 模板     │      │
│  │ ├chroma_query│  │ ├对话历史      │  │ ├解析模板         │      │
│  │ ├file_parser │  │ └上下文窗口    │  │ ├问答模板         │      │
│  │ ├web_search  │  │               │  │ ├修改模板         │      │
│  │ └retry_      │  │               │  │ └失败降级模板     │      │
│  │   wrapper    │  │               │  │ (新增)            │      │
│  └──────────────┘  └───────────────┘  └──────────────────┘      │
└──────────────────────────┬────────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────────┐
│                        数据层                                     │
│                                                                   │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│  │     ChromaDB             │  │   本地文件系统                 │  │
│  │  ┌────────────────────┐  │  │  ┌────────────────────────┐  │  │
│  │  │ knowledge_cards    │  │  │  │ uploads/               │  │  │
│  │  │ collection         │  │  │  │ chroma_db/             │  │  │
│  │  │ (向量+元数据)      │  │  │  │ static/vendor/ (新增)   │  │  │
│  │  └────────────────────┘  │  │  │   ├ alpine.js.min      │  │  │
│  │                          │  │  │   ├ daisyui.css        │  │  │
│  │  ChromaDB Lifecycle:     │  │  │   └ marked.min.js      │  │  │
│  │  启动 → health check     │  │  │                        │  │  │
│  │  运行 → 定时 persist     │  │  │                        │  │  │
│  │  关闭 → 显式 persist()   │  │  │                        │  │  │
│  │  升级 → 向量维度校验     │  │  │                        │  │  │
│  └──────────────────────────┘  └──────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. 架构风格与设计原则

### 2.1 架构风格：分层单体 + CardService 写入隔离 + AI Agent 编排

| 层次 | 职责 | 技术选型 |
|------|------|---------|
| **展示层** | 卡片浏览、导航、对话交互 | HTML + Tailwind CSS + DaisyUI + Alpine.js |
| **前端状态层** | 跨组件通信、数据同步 | Alpine.js Store + EventBus |
| **接入层** | 协议适配、请求校验、路由分发 | FastAPI (routes/* 拆分) |
| **服务层** | **唯一写入入口**，写入序列化 | CardService (asyncio.Lock) |
| **Agent 编排层** | 有状态工作流、LLM 调用 | LangGraph StateGraph |
| **数据层** | 向量存储 + 文件持久化 | ChromaDB + 本地文件系统 |

**架构决策理由：**

- **单体优先** — 目标用户是个人学习者，微服务引入的分布式复杂度 > 收益
- **CardService 隔离写入** — ChromaDB 非事务性，需序列化所有变更防止竞态
- **Agent 作为智能中间件** — LLM 工作流编排替代传统 Service 层的业务逻辑
- **本地可部署** — 所有组件可在单机运行，但明确标注哪些功能需要网络

### 2.2 设计原则

| 原则 | 说明 | 约束 |
|------|------|------|
| **本地可部署** | 单机运行，数据不出本机 | **需网络的组件：** OpenAI API、DuckDuckGo 搜索、CDN 依赖（可在首次运行后缓存到 static/vendor/） |
| **渐进式复杂** | 从 sentence-transformers → OpenAI API → Ollama 逐步升级 | `config.py` 统一控制，运行时切换 |
| **可观测性** | LangGraph 节点追踪 → WebSocket 进度事件推送给前端 | 每次 LLM 调用、数据变更都产生进度事件 |
| **关注点分离** | 展示层不调用 LLM，Agent 层不处理 HTTP，数据层不包含业务逻辑 | 唯一例外：CardService 封装数据层写操作 |
| **写入序列化** | 所有 ChromaDB 写操作经过 `asyncio.Lock`，防止竞态 | 读操作不锁，不影响并发查询性能 |

---

## 3. 接入层：直通路由 vs 转发路由

### 3.1 路由决策矩阵

接入层不再笼统地"直接调用数据层"或"转发给 Agent"，而是按照**是否需要 AI 处理**明确划分：

| 请求 | 路由方式 | 路径 | 说明 |
|------|---------|------|------|
| 浏览卡片 | 直通 | `GET /api/cards` → CardService.get_card | 纯查询，不经 Agent |
| 搜索卡片 | 直通 | `GET /api/cards/search` → CardService (向量搜索) | 向量查询不经 LLM |
| 创建卡片 | 直通 | `POST /api/cards` → CardService.create_card | 用户手动创建，不经 Agent |
| 删除卡片 | **直通** | `DELETE /api/cards/{id}` → CardService.delete_card | **注意：** 若通过对话窗口删除，走 WebSocket 经 Agent |
| 上传文件 | 转发 | `POST /api/upload` → CardService → Agent 工作流 | 需 LLM 解析文档 |
| 对话提问 | 转发 | `WS /ws/chat` → CardService → Agent 工作流 | 需 LLM 生成回答 |
| 修改卡片 | **双路径** | REST: `PUT /api/cards/{id}` (直通) / WS: 指令 (转发) | **两个入口使用同一 CardService**，确保一致性 |

### 3.2 双路径修改的一致性保障

```
用户通过对话修改卡片               用户通过 REST 修改卡片
         │                                  │
         ▼                                  ▼
    Agent 解析意图 → 生成新内容       CardService.update_card()
         │                                  │
         ▼                                  ▼
    CardService.update_card() ←──── 同一写入锁 ────→ ChromaDB
         │
         ▼
    EventBus 推送 'card:updated'
         │
         ▼
    前端刷新 CardView + Sidebar 列表
```

**关键约定：** REST API 中的 `PUT /api/cards/{id}` 只接受**已经由用户确认好的结构化数据**，不做 AI 推理。所有需要 LLM 参与的修改走 WebSocket。二者在 CardService 层汇聚，由同一把锁控制写入顺序。

---

## 4. AI Agent 层：失败恢复与重试边界

### 4.1 节点级失败恢复策略

| 节点 | 失败场景 | 恢复策略 | 重试次数 | WebSocket 进度事件 |
|------|---------|---------|---------|-------------------|
| `doc_parse` | PDF 损坏/加密/图片PDF | 跳过该页，记录错误继续下一页；如果所有页失败 → 返回具体错误 | 每页重试 1 次 | `progress: { page: 3, total: 50, status: "skipped", reason: "加密PDF" }` |
| `need_search` | LLM 输出非预期格式 | 降级为"不需要补充"继续流程 | 重试 1 次后降级 | `progress: { stage: "need_search", status: "fallback" }` |
| `web_search` | DuckDuckGo 限流/超时 | 跳过搜索，用已有信息生成卡片 + 标记"来源不足" | 不重试（外部依赖不可控） | `progress: { stage: "web_search", status: "unavailable" }` |
| `knowledge_extract` | LLM 返回格式不符 JSON | 重新调用 LLM，附加更严格的 schema 约束 | 重试 2 次 → 第 3 次用降级模板生成简化卡片 | `progress: { stage: "extract", status: "retry", attempt: 2 }` |
| `card_generate` | JSON schema 校验失败 | 丢弃该条，记录错误，继续处理剩余 | 不重试（来源数据可能本身有问题） | `progress: { stage: "generate", status: "skipped", reason: "schema_validation" }` |
| `chroma_store` | ChromaDB 写入失败 | 卡片数据暂存到内存队列，下次 persist 周期重试 | 异步重试 3 次 → 写入失败日志文件 | `progress: { stage: "store", status: "retry" }` |
| `qa_search` | ChromaDB 查询超时 | 降级为纯 LLM 回答（无知识库上下文） | 重试 1 次 → 降级 | `progress: { stage: "qa", status: "no_knowledge" }` |
| `qa_answer` | LLM 超时/Token 超限 | 截断对话历史，或回复"部分回答" | 重试 1 次（较短 context）→ 返回错误 | `error: { code: "LLM_TIMEOUT", message: "…" }` |

### 4.2 重试边界设计（事务粒度）

```
逐页事务:
┌──────────────────────────────────────────────┐
│  文档解析 → 每页独立事务                      │
│                                              │
│  第1页: doc_parse → extract → generate ✅    │
│  第2页: doc_parse → extract → generate ❌     │  ← 第2页失败
│  第3页: doc_parse → extract → generate ✅    │
│                                              │
│  结果: 第2页跳过，第1、3页正常入库             │
│  不会因为第2页失败而回滚第1页的成果             │
└──────────────────────────────────────────────┘

文档批次事务 (用于批量导入):
┌──────────────────────────────────────────────┐
│  10 个文件的批量导入                          │
│                                              │
│  文件1: ✅ → 入库                            │
│  文件2: ❌ → 标记失败，继续                  │
│  文件3~10: ✅ → 入库                         │
│                                              │
│  最终: 前端收到 { imported: 9, failed: 1,    │
│         errors: ["文件2: 加密PDF无法解析"] }  │
│  不会整体回滚                                 │
└──────────────────────────────────────────────┘
```

### 4.3 WebSocket 进度事件（新增类型）

扩展设计文档中的 WebSocket 消息类型，增加进度跟踪能力：

| 类型 | 方向 | 说明 |
|------|------|------|
| `message` | 用户 → Agent | 用户提问或指令 |
| `response` | Agent → 用户 | 回答文本 |
| `progress` | Agent → 用户 | **新增** 阶段性进度（解析页码、搜索状态、重试通知） |
| `card_preview` | Agent → 用户 | 新卡片预览（待确认） |
| `card_update` | Agent → 用户 | 卡片修改结果 |
| `error` | Agent → 用户 | 错误信息 |

**`progress` 消息格式：**

```json
{
  "type": "progress",
  "stage": "doc_parse",
  "page": 3,
  "total": 50,
  "status": "ok",          // "ok" | "skipped" | "retry" | "fallback" | "unavailable"
  "reason": "可选，失败原因说明",
  "timestamp": "2026-06-01T12:00:00Z"
}
```

前端 ChatPanel 根据 `progress` 事件渲染进度条或提示文案，让用户感知 Agent 正在工作。

---

## 5. 前端架构：跨组件通信与离线方案

### 5.1 状态管理方案

放弃"每个组件靠 x-data 各自为政"的原始方案，采用 **Alpine.js Store + 事件总线**：

```
Alpine.store('app', {
    // 状态
    currentCard: null,           // 当前展示的卡片
    history: [],                 // 浏览历史栈
    categories: [],              // 分类列表
    chatMessages: [],            // 对话消息
    sidebarOpen: true,           // 侧边栏展开状态
    uploadStatus: null,          // 文件上传/解析进度

    // 操作
    navigateTo(cardId) { ... },  // 切换卡片（更新 currentCard + history）
    refreshCategories() { ... }, // 刷新目录列表
    refreshCard() { ... },       // 刷新当前卡片（修改后调用）
})
```

### 5.2 跨组件事件流

```
ChatPanel                    EventBus                    Sidebar / CardView / NavControls
─────────                    ────────                    ────────────────────────────────

Agent 返回 card_preview
  → emit('card:preview', card)
                              ──→ Sidebar.refresh()     → 刷新目录高亮
                              ──→ CardView.load(card)   → 展示新卡片
                              ──→ NavControls.push(card)→ 推入历史栈

用户通过 ChatPanel 修改卡片
  → Agent 返回 card_update
  → emit('card:updated', card)
                              ──→ CardView.refresh()    → 更新展示
                              ──→ Sidebar.refresh()     → 刷新列表
                              ──→ (可选) toast 通知

用户点击超链接
  → emit('card:navigate', cardId)
                              ──→ CardView.load(cardId) → 加载新卡片
                              ──→ NavControls.push()    → 推入历史栈
                              ──→ Sidebar.highlight()   → 高亮对应项

用户点击后退
  → NavControls.pop()
  → emit('card:navigate', prevCardId)
                              ──→ CardView.load()       → 加载上一张
                              ──→ Sidebar.highlight()   → 高亮对应项

用户上传文件
  → 收到 progress 事件
  → emit('upload:progress', { page, total })
                              ──→ ChatPanel 显示进度条  → 用户感知解析进度
```

### 5.3 前端本地化（解决离线问题）

将 CDN 依赖下载到本地，取代运行时 CDN 加载：

```
static/
├── index.html                  # 主页面 (引用 vendor/ 中的本地资源)
└── vendor/                     # 已下载的前端依赖 (新增)
    ├── alpine.js.min           # Alpine.js
    ├── daisyui.css             # DaisyUI
    ├── tailwind.css            # Tailwind CSS
    ├── marked.min.js           # Markdown 渲染 (Agent 回答)
    └── highlight.min.js        # 代码高亮 (可选)
```

**实现策略：**

```
首次运行:
  1. main.py 启动时检查 static/vendor/ 是否完整
  2. 若缺少文件，打印提示:
     "首次运行请执行: python scripts/download_vendor.py"
  3. download_vendor.py 从 CDN 下载所有依赖到 static/vendor/

离线运行:
  1. static/vendor/ 已完整 → 完全不依赖网络
  2. LLM: Ollama 模式 (本地)
  3. 嵌入: sentence-transformers (本地)
  4. 搜索: 降级提示"网络搜索不可用"
  5. 全部本地运行，无需任何外部请求
```

### 5.4 WebSocket 与 REST 的数据一致性

| 场景 | 问题 | 解决方案 |
|------|------|---------|
| Agent 通过 WS 修改卡片，REST 同时读 | 读到旧数据 | 短 TTL 缓存 + CardService 修改时原子更新 |
| 用户通过 REST 删除卡片，Agent 正引用它 | Agent 回答提到已删除卡片 | Agent 在 `qa_search` 节点先查 ChromaDB，查不到则回应"该卡片已被删除" |
| 前端 ChatPanel 引用旧卡片数据 | 显示过期信息 | ChatPanel 收到 `card:updated` 事件后，检查当前对话中是否引用了该卡片，若有则追加一条"卡片 [标题] 已被修改"的系统消息 |

---

## 6. CardService 层：写入隔离设计

### 6.1 为什么需要 CardService

```
   ┌─────────────────────────────────────────────┐
   │              问题场景                         │
   │                                               │
   │  时间 T1: Agent → chroma_store → insert(card_A)  │
   │  时间 T2: REST  → DELETE /api/cards/B            │
   │  时间 T3: Agent → 关联检测 → list_all()          │
   │              └── 读到 T2 的中间状态 ❌            │
   │                                               │
   │  ChromaDB 是进程内嵌入，但不是线程安全的。        │
   │  FastAPI 的 async worker 和 Agent 的协程          │
   │  可交叉访问同一 collection，造成竞态。            │
   └─────────────────────────────────────────────┘
```

### 6.2 CardService 接口

```python
class CardService:
    def __init__(self, collection: chromadb.Collection):
        self._collection = collection
        self._lock = asyncio.Lock()    # 写操作全局锁
        self._pending_fails: list[dict] = []  # 待重试写入队列

    # --- 读操作 (无锁) ---
    async def get_card(self, card_id: str) -> KnowledgeCard | None
    async def list_cards(self, category: str = None, page: int = 1, limit: int = 20) -> list[KnowledgeCard]
    async def search_cards(self, query: str, top_k: int = 10) -> list[KnowledgeCard]

    # --- 写操作 (有锁) ---
    async def create_card(self, data: KnowledgeCardCreate) -> KnowledgeCard
    async def update_card(self, card_id: str, data: KnowledgeCardUpdate) -> KnowledgeCard
    async def delete_card(self, card_id: str) -> bool
    async def batch_import(self, cards: list[KnowledgeCardCreate]) -> ImportResult

    # --- 生命周期 ---
    async def health_check(self) -> bool          # 启动时校验
    async def persist(self) -> None               # 关闭时显式持久化
    async def retry_failed(self) -> list[dict]    # 异步重试失败项目
```

### 6.3 批量导入的原子性约束

```
batch_import(cards):
    1. 获取锁
    2. 逐条写入，每条独立 try/except
    3. 成功卡片 → 做关联检测
    4. 失败卡片 → 加入 _pending_fails 队列
    5. 返回 ImportResult(success=[...], failed=[{card, reason}])
    6. 释放锁

    不提供整体回滚 —— 单个文档解析中部分卡片失败不应影响已写入的部分。
    这与"逐页事务"的设计一致。
```

---

## 7. ChromaDB 生命周期管理

### 7.1 生命周期四阶段

```
┌──────────────────────────────────────────────────────────┐
│ 阶段1: 启动 (app startup)                                │
│                                                          │
│  1. 检查 chroma_db/ 目录是否存在，不存在则创建             │
│  2. 初始化 ChromaDB 客户端（持久化路径=./chroma_db/）     │
│  3. CardService.health_check():                           │
│     ├─ 写入一条健康检查记录 → 读回 → 删除                 │
│     ├─ 通过 → 正常启动                                    │
│     └─ 失败 → 日志告警 + 尝试重建 collection              │
│  4. 校验嵌入维度与 config.py 一致                         │
│     ├─ 不匹配 → 日志告警 "检测到向量维度变更"              │
│     └─ 建议重建 collection (由用户确认)                   │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ 阶段2: 运行                                              │
│                                                          │
│  1. 所有写操作经 CardService._lock 序列化                 │
│  2. 异步定时 persist (默认每 60s，config.py 可配)         │
│  3. 磁盘空间监控: 每次 persist 检查剩余空间                │
│     ├─ 剩余 < 100MB → 日志警告                            │
│     └─ 剩余 < 10MB  → 拒绝写入 + 推送前端通知             │
│  4. _pending_fails 队列: 每 5min 尝试重刷失败写入         │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ 阶段3: 关闭 (app shutdown)                               │
│                                                          │
│  1. 挂起 CardService._lock (不再接受新写入)               │
│  2. 排空 _pending_fails 队列                              │
│  3. 显式调用 collection.persist()                         │
│  4. 关闭 ChromaDB 客户端                                  │
│                                                          │
│  注意: 进程 SIGKILL 跳过此阶段 → 可能丢失最近 60s 数据    │
│  缓解: 每次成功写入后立即 persist（代价：写入吞吐下降）     │
│        默认策略：每 60s 定时 persist + 关闭时显式 persist  │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ 阶段4: 升级 / 数据迁移                                   │
│                                                          │
│  场景: 切换嵌入模型 (sentence-transformers v2 → v3)      │
│                                                          │
│  1. 启动时检测到向量维度与现有 collection 不匹配          │
│  2. 方案A: 创建新 collection (knowledge_cards_v2)         │
│  3. 方案B: 重建现有 collection (丢失旧数据)               │
│  4. 决策由用户在 config.py 中配置                         │
└──────────────────────────────────────────────────────────┘
```

### 7.2 数据量退化预估

| 卡片数量 | 查询响应时间 (预估) | 说明 |
|---------|-------------------|------|
| 100 张 | < 10ms | 单文档导入级别 |
| 1,000 张 | 10-30ms | 一学期课程级别 |
| 10,000 张 | 30-100ms | 多学期积累 |
| 100,000 张 | 100-500ms | ChromaDB 进程内 HNSW 索引仍可承受 |

**结论：** 个人学习场景（< 10,000 张卡片），ChromaDB 进程内模式无需额外优化。

---

## 8. 模块依赖与项目结构（修正版）

### 8.1 模块依赖方向（修正）

```
bobanana/
├── config.py                # ← 无依赖
├── models.py                # ← config.py
├── database.py              # ← models.py, config.py (ChromaDB 客户端 + lifecycle)
├── service/                 # 新增: 服务层
│   ├── __init__.py
│   └── card_service.py     # ← database.py, models.py (写入隔离 + 业务逻辑)
├── tools.py                 # ← service/card_service.py, config.py (Agent 工具集)
├── agent.py                 # ← tools.py, models.py (LangGraph 工作流)
├── routes/                  # 新增: 路由拆分，替代单一 app.py
│   ├── __init__.py
│   ├── cards.py             # ← service/card_service.py (直通路由)
│   ├── upload.py            # ← service/card_service.py, agent.py (转发路由)
│   ├── chat.py              # ← service/card_service.py, agent.py (WebSocket 路由)
│   ├── categories.py        # ← service/card_service.py
│   └── history.py           # ← service/card_service.py
└── app.py                   # ← routes/*, service/card_service.py (注册 + 生命周期)

依赖方向: config → models → database → service → tools → agent → routes → app
          其中 routes/* 各自只取自己需要的依赖，不强制全部引入
```

### 8.2 项目文件结构（修正）

```
AIwiki/
├── bobanana/                    # Python 包
│   ├── __init__.py
│   ├── config.py                # 配置
│   ├── models.py                # 数据模型
│   ├── database.py              # ChromaDB 客户端 + lifecycle
│   ├── service/
│   │   ├── __init__.py
│   │   └── card_service.py      # 写入隔离 + 业务逻辑 (新增)
│   ├── tools.py                 # Agent 工具集
│   ├── agent.py                 # LangGraph 工作流
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── cards.py             # 卡片 CRUD 直通路由 (新增)
│   │   ├── upload.py            # 文件上传转发路由 (新增)
│   │   ├── chat.py              # WebSocket 对话路由 (新增)
│   │   ├── categories.py        # 分类路由 (新增)
│   │   └── history.py           # 浏览历史路由 (新增)
│   └── app.py                   # FastAPI 应用入口 (路由注册 + 生命周期)
├── docs/
│   ├── design/
│   │   ├── 2026-06-01-study-wiki-agent-design.md
│   │   └── 2026-06-01-study-wiki-agent-architecture.md  # 本文档
│   └── plan.md                  # 工期方案
├── scripts/
│   └── download_vendor.py       # 下载前端依赖到 static/vendor/ (新增)
├── static/
│   ├── index.html               # 前端页面
│   └── vendor/                  # 本地前端依赖 (新增，git 管理)
│       ├── alpine.js.min
│       ├── daisyui.css
│       ├── tailwind.css
│       └── marked.min.js
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_database.py
│   └── test_agent.py
├── uploads/                     # 上传文件 (gitignore)
├── chroma_db/                   # ChromaDB 持久化 (gitignore)
├── requirements.txt
├── main.py                      # 启动入口
└── README.md
```

---

## 9. 技术选型架构权衡（修正版）

| 决策点 | 选型 | 架构影响 | 弥补措施 |
|--------|------|---------|---------|
| 向量数据库 | ChromaDB (进程内) | 零运维，无法水平扩展，非事务性 | CardService 写入锁 + 定时 persist + 磁盘监控 |
| Agent 框架 | LangGraph StateGraph | 有状态条件分支，但调试周期长 | 每节点重试策略 + 进度事件追踪 |
| 前端方案 | 纯 HTML + 本地 vendor | 零构建工具链，可离线运行 | 跨组件通信靠 Alpine Store + EventBus |
| 嵌入模型 | sentence-transformers / OpenAI | 本地精度 vs 网络依赖 | 启动时维度校验，升级时通知重建 |
| LLM 推理 | GPT-4 / Ollama | 一键切换 | config.py 热切换，两侧互不侵入 |

---

## 10. 设计原则与约束对照（新增）

| 原则 | 实际程度 | 边界条件 |
|------|---------|---------|
| 本地可部署 | ⚠️ 条件成立 | 需提前执行 `download_vendor.py`；网络搜索在离线时降级 |
| 渐进式复杂 | ✅ 成立 | config.py 控制，无需改代码 |
| 可观测性 | ✅ 成立 | 每个 Agent 节点 + WebSocket progress 事件 |
| 关注点分离 | ✅ 成立 | 六层各司其职 |
| 写入序列化 | ✅ 成立 | CardService asyncio.Lock 全局唯一写入入口 |

---

## 11. 接口契约总览

### 11.1 REST API

| 方法 | 路径 | 说明 | 路由方式 |
|------|------|------|---------|
| `GET` | `/api/cards` | 获取卡片列表 (分页/分类过滤) | 直通 |
| `GET` | `/api/cards/{id}` | 获取单张卡片详情 | 直通 |
| `POST` | `/api/cards` | 创建新卡片 | 直通 |
| `PUT` | `/api/cards/{id}` | 更新卡片 (用户确认后的结构化数据) | 直通 |
| `DELETE` | `/api/cards/{id}` | 删除卡片 | 直通 |
| `GET` | `/api/cards/search` | 搜索卡片 | 直通 |
| `POST` | `/api/upload` | 上传文件并触发解析 | **转发** (→ Agent) |
| `GET` | `/api/categories` | 获取分类列表 | 直通 |
| `GET` | `/api/history` | 获取浏览历史 | 直通 |
| `POST` | `/api/history` | 记录浏览卡片 | 直通 |

### 11.2 WebSocket

| 路径 | 说明 | 路由方式 |
|------|------|---------|
| `/ws/chat` | Agent 实时对话 | **转发** (→ Agent) |

### 11.3 WebSocket 消息类型（修正版）

| 类型 | 方向 | 说明 |
|------|------|------|
| `message` | 用户 → Agent | 用户提问或指令 |
| `response` | Agent → 用户 | 回答文本 |
| `progress` | Agent → 用户 | 阶段性进度（解析页码、搜索状态、重试通知） |
| `card_preview` | Agent → 用户 | 新卡片预览（待确认） |
| `card_update` | Agent → 用户 | 卡片修改结果 |
| `error` | Agent → 用户 | 错误信息（含错误码: `LLM_TIMEOUT`, `DB_FAILURE`, `PARSE_ERROR` 等） |

### 11.4 统一响应格式

```json
{
  "status": "success" | "error",
  "data": { ... },
  "message": "操作结果说明",
  "error_code": "可选，仅 error 时有值",
  "timestamp": "2026-06-01T12:00:00Z"
}
```
