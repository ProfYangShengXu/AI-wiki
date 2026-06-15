# StudyWiki-Agent API 文档 v0.3.0

Base URL: `http://127.0.0.1:8000`

所有返回格式: `{"status": "success|error", "data": ...}` 或 HTTP 错误码。

---

## 1. 卡片 CRUD

### `GET /api/cards`
列出卡片，支持分页和分类过滤。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `category` | string | - | 按分类过滤 |
| `page` | int | 1 | 页码 |
| `limit` | int | 50 | 每页数量 (max 1000) |

返回: `{"status":"success","data":{"cards":[...],"total":216,"page":1,"limit":50}}`

每个 card: `{id, title, aliases, content, examples, questions, category, source_file, source_page, related_cards, created_at, updated_at}`

### `GET /api/cards/{card_id}`
获取单张卡片。404 表示不存在。

### `POST /api/cards`
创建卡片。body:
```json
{"title":"标题","category":"分类","content":"内容","examples":["例1"],"aliases":["别名"]}
```

### `POST /api/cards/generate`
LLM 自动生成卡片内容。body: `{"title":"知识点","category":"分类"}`

### `PUT /api/cards/{card_id}`
更新卡片。body: `{"title":"新标题","content":"新内容",...}`（部分字段即可）

### `DELETE /api/cards/{card_id}`
删除卡片。返回 200 或 404。

### `GET /api/cards/search?q=关键词`
语义搜索卡片。

---

## 2. 分类

### `GET /api/categories`
返回所有分类名。
返回: `{"status":"success","data":{"categories":["分类1","分类2",...]}}`

---

## 3. 文件上传

### `POST /api/upload`
上传文档自动解析。`multipart/form-data`, field: `file`。
返回: `{"status":"success","data":{"file":"xxx.md","imported":5,"cards":[...]}}`

---

## 4. Quiz

### `POST /api/quiz/generate/{card_id}`
为卡片生成 3-5 道简答题。
返回: `{"status":"success","data":{"card_id":"xxx","questions":[{"question":"Q1","ref_answer":"A1"},...]}}`

### `POST /api/quiz/grade`
AI 评分。body:
```json
{"card_id":"xxx","answers":[{"question":"Q1","answer":"我的答案"}]}
```
返回: `{"status":"success","data":{"results":[{"score":8,"comment":"理由","reference":"参考答案"}],"total_score":8,"max_score":10,"mastery_pct":80}}`

### `POST /api/quiz/merge/{card_id}`
将 Quiz 结果融合进卡片内容。body 同 grade。

### `GET /api/quiz/mastery/{card_id}`
获取卡片掌握度。返回: `{"data":{"mastery_pct":80,"attempts":2,"score":16}}`

### `POST /api/quiz/exam`
智能组卷。body: `{"card_ids":["id1","id2"]}`
返回: `{"data":{"questions":[{"question":"综合题","ref_answer":"答","related_cards":["知识点"]}],"card_count":2}}`

---

## 5. WebSocket Chat

### `ws://127.0.0.1:8000/ws/chat`

发送: `{"type":"message","content":"用户输入","data":{"mode":"ask|agent"}}`

接收:
- `{"type":"response","content":"回答"}`
- `{"type":"progress","data":{"stage":"thinking|act|observe|done","tool":"工具名"}}`

---

## 6. 其他

### `GET /api/logs?n=100`
获取最近 n 条运行日志。

### `GET /health`
健康检查。返回: `{"status":"ok","cards_count":216}`
