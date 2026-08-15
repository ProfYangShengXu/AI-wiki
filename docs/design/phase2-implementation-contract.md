# Phase 2 实现约定(接口契约)

> 本文档锁定 Phase 2 各工作流的对外接口与文件归属,供各实现工作流对齐。
> 与 `docs/next-phase-optimization.md` 第 3~8 节对应。实现时以本文档为准。

## 0. 通用约定

- 所有新增路由挂在现有 `/api/*` 下,保留旧路径向后兼容;OpenAPI 契约见 `api/openapi.yaml`。
- 错误统一走 `bobanana.errors.SWError`(`sw_raise(code, message, status_code=None)`),错误码格式 `SW-<DOMAIN>-<CODE>`。
- 测试永不依赖真实 LLM/网络;`tests/fakes.py` 提供 FakeLLM/FakeEmbeddings;隔离 ChromaDB 夹具在 `tests/conftest.py`。
- LLM/嵌入调用只在 `bobanana/tools.py` 出现(唯一入口),业务模块不得自行 new 模型客户端。

## 1. Agent v2(文件: bobanana/agent_react.py、bobanana/tools_schema.py、bobanana/memory.py[新]、bobanana/routes/chat.py)

### 1.1 对外接口(chat.py 调用面,保持不变)

```python
# 现有:
#   run_ask_mode(instruction, chat_history, progress_cb) -> str
#   run_agent_mode(instruction, chat_history, progress_cb, max_turns=6) -> str
# 新增流式变体(向后兼容,旧调用仍可用):
#   run_agent_mode(..., stream_cb: Callable[[dict], None] | None = None) -> str
```

### 1.2 结构化工具调用

- 优先模型原生 tool/function calling:`ChatDeepSeek/ChatOpenAI` 用 `bind_tools(tools_schema_objects)`;Ollama 不支持时回退 JSON-ReAct(保留现有 `Action: tool({...})` 解析器作为兜底)。
- 工具参数在进入执行层前经 Pydantic 校验(`tools_schema.py` 生成 Pydantic 模型);非法参数自动重试 1 次,再失败返回明确 `SW-AGENT-400`。
- 三级预算:max_turns(默认 6)、max_tokens(默认 8192,累计)、max_wall_time(默认 120s);超预算输出 `SW-AGENT-429` 风格错误并附已完成的步骤摘要。

### 1.3 审批闸门

- `tools_schema.py` 给工具元数据加 `"approval_required": bool`;删除卡片/清空分类/删除知识库/批量更新默认 true。
- 执行到需审批的工具时:推送 WS 事件 `{"type":"approval_required","tool":...,"args":...,"approval_id":...}`,挂起等待用户回复 `{"type":"approval","approval_id":...,"approved":bool}`,默认超时 60s 未回复视为拒绝。审批器状态存内存 dict(单用户场景),`bobanana/routes/chat.py` 负责转发。

### 1.4 流式与事件

WS 事件字典(在现有 message/response/progress/error 基础上新增):

| type | 方向 | 数据 |
| --- | --- | --- |
| `llm.delta` | 服务端→客户端 | `{"delta": "...", "session_id": "..."}` |
| `tool.called` | 服务端→客户端 | `{"tool": "...", "args": {...}}` |
| `tool.result` | 服务端→客户端 | `{"tool": "...", "ok": true, "summary": "..."}` |
| `approval_required` | 服务端→客户端 | `{"approval_id", "tool", "args"}` |
| `approval` | 客户端→服务端 | `{"approval_id", "approved"}` |
| `session.started` / `session.done` / `session.error` | 服务端→客户端 | `{"session_id"}` |

### 1.5 会话记忆

- `bobanana/memory.py`:SQLite 存于 `BASE_DIR/data/session_memory.db`(目录自动创建),表 sessions(id, created_at, context_json)与 messages(id, session_id, role, content, created_at)。
- 每轮对话追加消息;跨会话项目上下文(当前 KB、常用分类)存 context_json,由 knowledgebase 路由写入。

### 1.6 LLM 降级链

- `get_llm()` 按 `LLM_PROVIDERS`(逗号分隔,如 `deepseek,openai,ollama`)顺序构造候选;调用失败且错误为 auth/connection/timeout 时熔断该 provider(冷却 60s)并尝试下一个;全部失败抛 `SW-LLM-503`。配置项加进 `bobanana/config.py`。

## 2. 导入任务状态机(文件: bobanana/import_tasks.py[新]、bobanana/routes/upload.py、bobanana/agent.py 接线)

### 2.1 状态

`queued → scanning → extracting → linking → done / failed / cancelled`

- `POST /api/upload` 仍返回 `{task_id, filename, storage_name, size}`,立即 queued,后台线程推进状态。
- `GET /api/upload/status/{task_id}` 返回 `{task_id, status, message, progress:{stage,current,total}, result:{imported,skipped,failed,errors}}`。
- `POST /api/upload/cancel/{task_id}`:置 cancel_event(threading.Event),解析/提取循环每页/每区间检查;取消后保留已完成卡片,状态 cancelled。

### 2.2 断点续跑

- 每完成一个区间,把区间结果与进度写入 `tmp/import_tasks/{task_id}/state.json`(tmp/ 加入 .gitignore)。
- 重启后任务列表来自扫描 `tmp/import_tasks/`,提供 `POST /api/upload/resume/{task_id}` 从未完成区间继续。

### 2.3 其它

- 速率控制:LLM 调用 token bucket(默认 10s 内 15 次,`config.py` 可配)。
- 去重:标题规范化 + 别名匹配 + 与既有卡片语义相似度(阈值可配),重复项记入 `skipped` 报告。
- 每区间入库即推送 `progress` WS 事件(progress_cb 已存在,继续用)。

## 3. 混合检索(文件: bobanana/retrieval.py[新]、bobanana/database.py 的 search 段、bobanana/service/card_service.py 接线)

- BM25(rank_bm25 依赖,加入 requirements.txt)+ 向量余弦,RRF 融合(默认 k=60)。
- 元数据过滤:`search_cards(query, top_k, category=None, source_file=None, min_mastery=None)`。
- 查询改写(可选,默认关闭):短查询 <6 字且无检索结果时用 LLM 扩展同义词,测试环境禁用。
- 保持旧调用 `search_cards(query_embedding, top_k)` 兼容(判定:第一个参数是 list 走纯向量)。

## 4. ChromaDB 生命周期与备份(文件: bobanana/database.py、bobanana/backup.py[新]、bobanana/routes/backup.py[新]、scripts/migrate_embedding.py[新])

- 写入前检查磁盘剩余空间:<`CHROMA_DISK_WARN_MB` 记警告、<`CHROMA_DISK_STOP_MB` 拒绝写入并抛 `SW-DB-507`。
- 后台线程每 60s 触发 persist;`db_manager.shutdown()` 在 app lifespan 关闭时调用(flush 失败队列 + persist)。
- 失败写入队列 `_pending_fails`,每 5min 重试 3 次,失败落日志。
- 备份:`POST /api/backup/create` → `backups/swkb-YYYYmmdd-HHMMSS.zip`(含 chroma_db、uploads、mastery.json,.env 排除);`GET /api/backup/list`;`POST /api/backup/restore/{name}` 支持 dry-run 参数。备份前自动快照当前 chroma_db。
- `scripts/migrate_embedding.py --target-dim 768 --dry-run`:维度不匹配时新建 collection 迁移。

## 5. 可观测性(文件: bobanana/log_handler.py、bobanana/app.py 中间件、bobanana/config.py)

- 每个 HTTP 请求与后台任务带 `trace_id`(请求头 `X-Trace-Id` 或生成 uuid4 hex 前 12 位),响应头回传;日志 JSON 行格式含 trace_id、level、time、logger、message。
- 日志过滤器:任何字段匹配 API Key 正则(如 `sk-[A-Za-z0-9]{16,}`)时替换为 `***`。
- 指标(内存累积,`GET /api/metrics`):导入成功率、LLM 调用次数/延迟、检索延迟、Quiz 完成率。

## 6. Web 前端(文件: static/index.html)

- 聊天流式渲染(`llm.delta` 追加);工具调用折叠为步骤卡;`approval_required` 弹确认框。
- 深色/浅色主题切换(持久化 localStorage);上传进度面板(轮询 `/api/upload/status/{id}`)。
- 知识图谱视图:基于卡片 related_cards 用内联 SVG 力导向布局(自实现,无新 CDN 依赖)。
- 所有插入 innerHTML 的文本必须先 `esc()` 转义(现有 helper),Markdown 渲染后消毒。

## 7. Flutter 客户端(文件: client/)

- 新增:配对页(6 位配对码 + 二维码展示,依赖 qr_flutter)、离线知识包导出/导入(JSON + Markdown)、Quiz 掌握度回传队列。
- 网络层 `api_client.dart` 解析 `{status, error_code, message}` 统一错误,错误码常量与后端一致。
- `pubspec.yaml` 依赖锁定到当前稳定版本;`flutter analyze` 零错误。
- 本环境无 Flutter SDK:平台壳与构建由 CI(`.github/workflows/ci.yml` client job,windows-latest 出 MSIX 候选与 debug APK 产物)完成;本地只交付 Dart 源码 + 测试。

## 8. 评测资产(文件: docs/eval/)

- 数据:`agent_instructions.jsonl`(20 条)、`retrieval_queries.jsonl`(50 条)、`fixtures/`(10 份)。
- `run_eval.py`:检索评测(50 查询 Top5 命中率,目标 ≥0.80)+ Agent 评测(20 指令成功率,目标 ≥85%,`--real-llm` 才走真实模型),结果写 `docs/eval/results/`。

## 9. 文件归属(避免并行冲突)

| 工作流 | 独占文件 |
| --- | --- |
| 契约 | bobanana/errors.py、api/openapi.yaml、docs/api.md |
| 工程化 | pyproject.toml、requirements*.txt、.github/workflows/ci.yml、docs/engineering-gaps.md、scripts/linux_setup.sh、scripts/run_tests_linux.sh |
| 测试底座 | tests/** |
| Agent v2 | bobanana/agent_react.py、bobanana/tools_schema.py、bobanana/memory.py、bobanana/routes/chat.py、bobanana/config.py(LLM_PROVIDERS 段) |
| 导入任务 | bobanana/import_tasks.py、bobanana/routes/upload.py、bobanana/agent.py |
| 检索 | bobanana/retrieval.py、bobanana/service/card_service.py、bobanana/database.py(search 段) |
| 生命周期/备份 | bobanana/database.py(其余段)、bobanana/backup.py、bobanana/routes/backup.py、scripts/migrate_embedding.py |
| 可观测性 | bobanana/log_handler.py、bobanana/app.py(中间件段)、bobanana/routes/metrics.py |
| Web 前端 | static/index.html |
| Flutter | client/** |
| 评测 | docs/eval/** |

共享文件(bobanana/app.py、bobanana/config.py、bobanana/database.py)按段落归属,冲突时由主控(集成轮)仲裁。
