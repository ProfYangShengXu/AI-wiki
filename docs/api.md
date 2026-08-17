# StudyWiki-Agent API 手册 v1.0.0

> **本文档与 `api/openapi.yaml` 同步，以 yaml 为准。**
> Base URL: `http://127.0.0.1:8000`　|　自动导出: `/docs`（Swagger UI）、`/openapi.json`、手写契约: `/api/openapi.yaml`

## 通用约定

- 成功响应顶层通常含 `"status": "success"`，数据放在 `data` 中；部分端点额外携带 `message` / `error_code` / `timestamp`（经 `ApiResponse` 包装）。
- 错误响应统一为：

```json
{ "status": "error", "error_code": "SW-...", "message": "...", "timestamp": "2026-08-15T00:00:00+00:00" }
```

- `/health` 例外，返回 `{ "status": "ok", "cards_count": N }`。

### 鉴权

- 当 `.env` 配置 `STUDYWIKI_AUTH_TOKEN` 时启用；业务 API 需携带请求头 `Authorization: Bearer <token>`。
- **public 路径（无需鉴权）**：`/`、`/health`、`/docs`、`/openapi.json`、`/api/openapi.yaml`、`/api/bootstrap/status`、`/api/bootstrap/test`、`/api/bootstrap/configure`、`/static/*`。
- 未授权返回 `401`，错误码 `SW-AUTH-001`。

---

## 错误码表

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| `SW-AUTH-001` | 401 | 未授权：Bearer Token 缺失或无效 |
| `SW-CARD-400` | 400 | 卡片请求参数非法 |
| `SW-CARD-404` | 404 | 卡片不存在 |
| `SW-CARD-500` | 500 | 卡片生成或处理失败 |
| `SW-UPLOAD-400` | 400 | 不支持的文件类型 / 内容与扩展名不匹配 |
| `SW-UPLOAD-413` | 413 | 文件超过 100MB 限制 |
| `SW-UPLOAD-500` | 500 | 文件解析或导入失败 |
| `SW-QUIZ-400` | 400 | Quiz 请求非法（如无有效卡片） |
| `SW-QUIZ-404` | 404 | 卡片不存在（Quiz 上下文） |
| `SW-QUIZ-500` | 500 | Quiz 生成/评分/合并/组卷失败 |
| `SW-TASK-404` | 404 | 上传任务不存在 |
| `SW-SETTINGS-400` | 400 | 非法配置项 / 掩码 Key / 非法供应商 |
| `SW-KB-400` | 400 | 非法知识库操作（如删除默认库） |
| `SW-KB-404` | 404 | 知识库不存在 |
| `SW-KB-500` | 500 | 知识库切换失败 |
| `SW-BOOTSTRAP-400` | 400 | 请求非法（占位 API Key） |
| `SW-BOOTSTRAP-401` | 401 | API Key 无效或未授权 |
| `SW-BOOTSTRAP-429` | 429 | 请求过于频繁或额度不足 |
| `SW-BOOTSTRAP-UPSTREAM` | 502 | 上游模型服务返回异常状态码 |
| `SW-BOOTSTRAP-TIMEOUT` | 504 | 验证 API Key 超时 |
| `SW-BOOTSTRAP-NETWORK` | 503 | 无法连接模型服务 |
| `SW-GENERIC-400/401/403/404/405/409/413/422/500/502/503/504` | 对应状态码 | HTTPException 包装后的通用错误码 |

> 数值后缀的错误码通常与 HTTP 状态码一致；`UPSTREAM`→502、`TIMEOUT`→504、`NETWORK`→503。

---

## 端点手册

### 0. 健康检查与杂项

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/` | 公开 | 返回前端页面（`static/index.html`）或 `{service, version}` |
| GET | `/health` | 公开 | 健康检查 → `{status:"ok", cards_count}`；数据库异常返回 503 |
| GET | `/api/logs?level=&n=` | 需要 | 最近日志（`level` 可选过滤，`n` 默认 100） |
| GET | `/api/openapi.yaml` | 公开 | 返回手写 OpenAPI 契约 YAML |

### 1. Bootstrap（首次灰屏强制配置）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/bootstrap/status` | 公开 | 查询灰屏状态，永不返回完整 Key |
| POST | `/api/bootstrap/test` | 公开 | 验证 Key（不落盘） |
| POST | `/api/bootstrap/configure` | 公开 | 验证成功后写入 `.env` 并解除灰屏 |

`GET /api/bootstrap/status` 返回：

```json
{ "status":"success", "data":{ "required":true, "provider":"deepseek", "has_key":false, "key_tail":"", "base_url":"https://api.deepseek.com" } }
```

`POST /test`、`POST /configure` 请求体（`BootstrapConfigRequest`）：

```json
{ "provider":"deepseek", "api_key":"sk-...", "base_url":"https://api.deepseek.com", "model":"deepseek-v4-flash" }
```

失败时返回 `200` + `{ "status":"error", "error_code":"SW-BOOTSTRAP-401", ... }`；占位 Key 直接返回 `400`。

### 2. 卡片（Cards）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/cards?category=&page=&limit=` | 列表；`page≥1`，`1≤limit≤1000` |
| POST | `/api/cards` | 创建卡片 → **201** |
| GET | `/api/cards/search?q=` | 语义搜索（`q` 必填） |
| POST | `/api/cards/generate` | LLM 生成卡片 → **201** |
| POST | `/api/cards/deduplicate` | 语义去重 |
| GET | `/api/cards/{card_id}` | 单卡详情，不存在 404 |
| PUT | `/api/cards/{card_id}` | 部分更新，不存在 404 |
| DELETE | `/api/cards/{card_id}` | 删除，不存在 404 |

`CardCreate`（创建/生成请求，仅 `title` 必填）：

```json
{ "title":"CPU", "aliases":["中央处理器"], "content":"...", "examples":["Intel i7"],
  "questions":["CPU 是什么？"], "category":"硬件", "source_file":"", "source_page":0, "related_cards":[] }
```

`CardUpdate`：上述字段全部可选（部分更新）。

`CardResponse` 字段：`id, title, aliases, content, examples, questions, category, source_file, source_page, related_cards, created_at, updated_at`。

### 3. 分类（Categories）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/categories` | 所有分类名 → `data.categories: [string]` |

### 4. 浏览历史（History）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/history` | 最近 200 条 → `data.history: [...]` |
| POST | `/api/history` | 记录一条，body: `{card_id, title, timestamp}` |

### 5. 文件上传（Upload）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | `multipart/form-data`：`file`（必填）+ `file_type`（`course`/`hw`）+ `kb_id` |
| GET | `/api/upload/status/{task_id}` | 查询后台解析任务状态 |

- 支持扩展名：`.pdf .docx .doc .md .txt`；上限 100MB（超限 413）。
- 上传立即返回 `data: {task_id, filename, storage_name, size}`，解析后台执行。
- 任务状态：`processing` / `done`（含 `imported`、`failed`、`cards`）/ `error`。

### 6. Quiz

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/quiz/generate/{card_id}` | 生成 3-5 道简答题 |
| POST | `/api/quiz/grade` | AI 评分简答题 |
| POST | `/api/quiz/merge/{card_id}` | 将问答反馈融合回卡片 |
| POST | `/api/quiz/exam` | 智能组卷 |
| GET | `/api/quiz/mastery/{card_id}` | 单卡掌握度 |
| GET | `/api/quiz/mastery/batch?card_ids=id1,id2` | 批量掌握度 |

`QuizSubmission`（grade/merge 请求体）：

```json
{ "card_id":"...", "answers":[ { "question":"Q1", "answer":"我的答案" } ] }
```

`ExamRequest`（组卷请求体）：

```json
{ "card_ids":["id1","id2"] }
```

#### Quiz 流程示例

1. 生成题目：`POST /api/quiz/generate/{card_id}` → `data.questions: [{question, ref_answer}]`
2. 提交作答：`POST /api/quiz/grade` → `data: {card_id, results:[{question, answer, score, comment, reference}], total_score, max_score, mastery_pct}`
3. 融合回卡片：`POST /api/quiz/merge/{card_id}` → `data.card`
4. 查看掌握度：`GET /api/quiz/mastery/{card_id}` → `data: {card_id, attempts, score, mastery_pct}`

### 7. 设置（Settings）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings/` | 读取配置（API Key 已脱敏） |
| POST | `/api/settings/` | 更新单条，body: `{key, value}` |
| POST | `/api/settings/batch` | 批量更新，body: `[{key, value}, ...]` |

可写配置项（白名单）：`OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_BASE_URL`、`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL`、`OLLAMA_BASE_URL`、`OLLAMA_MODEL`、`LLM_PROVIDER`、`LLM_TEMPERATURE`、`LLM_MAX_TOKENS`、`LLM_TIMEOUT_SEC`、`EMBEDDING_PROVIDER`。

### 8. 知识库（Knowledgebase）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kb/list` | 列出所有库 + 当前库 → `data: {current, kbs:[KBMeta]}` |
| POST | `/api/kb/create` | 创建库，body: `{name}` |
| POST | `/api/kb/switch/{kb_id}` | 切换当前库 |
| DELETE | `/api/kb/{kb_id}` | 删除库（默认库不可删 → 400） |
| POST | `/api/kb/rename/{kb_id}` | 重命名，body: `{name}` |

`KBMeta`：`{id, name, created, card_count}`。

---

## WebSocket 事件表（`/ws/chat`）

连接建立后服务端先发送一条欢迎 `response`。

**客户端 → 服务端**：

| type | 字段 | 说明 |
|------|------|------|
| `message` | `content`: 用户输入；`data.mode`: `ask`/`agent` | `ask` 仅检索知识库；`agent` 走 ReAct 循环 |

**服务端 → 客户端**：

| type | 说明 |
|------|------|
| `response` | 最终回答文本（`content`） |
| `progress` | 阶段进度（`data.stage`，如 `thinking`/`agent`） |
| `error` | 错误信息（`content`） |
| `llm.delta` | 流式增量（`data.delta`） |
| `tool.called` / `tool.result` | 工具调用步骤（`data.tool`/`data.args`/`data.ok`/`data.summary`） |
| `approval_required` | 危险操作审批请求（`data.approval_id`/`data.tool`/`data.args`，60s 超时自动拒绝） |
| `session.started` / `session.done` / `session.error` | 会话生命周期（`data.session_id`） |
| `card_preview` / `card_update` | 预留 |

**客户端 → 服务端**（除 `message` 外的控制消息）：

| type | 说明 |
|------|------|
| `approval` | 审批答复：`data.approval_id` + `data.approved`（布尔） |

`WSMessage` 结构：`{type, content, data, timestamp}`；`type` 枚举含 `message|response|progress|llm.delta|tool.called|tool.result|approval_required|approval|session.started|session.done|session.error|card_preview|card_update|error`。

发送示例：

```json
{ "type":"message", "content":"什么是 CPU？", "data":{ "mode":"ask" } }
```

### 9. 导入任务（Upload tasks，Phase 2 §2）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/upload/status/{task_id}` | 任务状态：`{task_id,status,message,progress{stage,current,total},result{imported,skipped,failed,errors}}` |
| POST | `/api/upload/cancel/{task_id}` | 取消任务（幂等；保留已完成卡片） |
| POST | `/api/upload/resume/{task_id}` | 续跑 failed/cancelled 任务（断点区间恢复） |

状态机：`queued → scanning → extracting → linking → done / failed / cancelled`；
任务不存在 → `SW-TASK-404`；状态不允许续跑 → `SW-UPLOAD-400`。

### 10. 备份 / 恢复（Phase 2 §4）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/backup/create` | 快照 chroma_db + uploads + mastery.json → `backups/swkb-*.zip` |
| GET | `/api/backup/list` | 备份列表（name/size/created_at） |
| POST | `/api/backup/restore/{name}` | 恢复；body `{dry_run: bool}`，真实恢复前自动 pre-restore 备份 |

### 11. 指标（Phase 2 §5）

`GET /api/metrics` → 内存累积指标：`uptime_seconds`、`requests_total`、`llm_calls_total`、`llm_call_seconds`、`import_tasks_total{status}`、`quiz_graded_total`、`search_seconds`、`approvals_total{approved,denied}` 等。

### 12. 设备配对（Phase 2 §7.1）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/pair/code` | 生成一次性 6 位配对码（TTL 默认 300s） |
| POST | `/api/pair/verify` | body `{code, device_id}`，恒定时间比较、一次性使用，成功登记设备 |
| GET | `/api/pair/status` | 活跃码状态与已登记设备（脱敏哈希） |

错误码：`SW-PAIR-400`（格式错误）/ `SW-PAIR-401`（错误/过期）/ `SW-PAIR-404`（未生成码）。

---

## 说明

- 本文档为 Markdown 速查，字段级定义与响应 schema 以 [`api/openapi.yaml`](../api/openapi.yaml) 为准。
- 404/405 由按状态码注册的 handler 处理，响应体为 `ApiResponse` 结构（含 `data: null`）；其余 `HTTPException`（400/413/500 等）统一包装为 `{status, error_code, message, timestamp}`。
- 422 校验失败仍为 FastAPI 默认 `{detail: [...]}` 结构。
