"""数据模型定义 — KnowledgeCard 及其 API Schema。"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

# ── 内部模型 ──────────────────────────────────────────────

class KnowledgeCard(BaseModel):
    """知识卡片 — ChromaDB 存储的核心数据模型。"""
    id: str = Field(default="", description="UUID 标识符")
    title: str = Field(..., description="知识点名词（主标题）")
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    content: str = Field(default="", description="详细解释内容")
    examples: list[str] = Field(default_factory=list, description="案例列表")
    questions: list[str] = Field(default_factory=list, description="相关问题列表")
    category: str = Field(default="未分类", description="知识领域分类")
    source_file: str = Field(default="", description="来源文件名")
    source_page: int = Field(default=0, description="来源页码")
    related_cards: list[str] = Field(default_factory=list, description="关联卡片 ID 列表")
    mastery_attempts: int = Field(default=0, description="答题次数")
    mastery_score: int = Field(default=0, description="累计最高分")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def embedding_text(self) -> str:
        """生成用于向量嵌入的文本。"""
        parts = [self.title]
        parts.extend(self.aliases)
        parts.append(self.content)
        return "\n".join(parts)


# ── API 请求 Schema ───────────────────────────────────────

class CardCreate(BaseModel):
    """创建卡片请求。"""
    title: str = Field(..., min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    content: str = Field(default="")
    examples: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    category: str = Field(default="未分类")
    source_file: str = Field(default="")
    source_page: int = Field(default=0)
    related_cards: list[str] = Field(default_factory=list)


class CardUpdate(BaseModel):
    """更新卡片请求（所有字段可选）。"""
    title: str | None = None
    aliases: list[str] | None = None
    content: str | None = None
    examples: list[str] | None = None
    questions: list[str] | None = None
    category: str | None = None
    source_file: str | None = None
    source_page: int | None = None
    related_cards: list[str] | None = None


# ── API 响应 Schema ──────────────────────────────────────

class CardResponse(BaseModel):
    """卡片响应。"""
    id: str
    title: str
    aliases: list[str]
    content: str
    examples: list[str]
    questions: list[str]
    category: str
    source_file: str
    source_page: int
    related_cards: list[str]
    created_at: str
    updated_at: str


class CardListResponse(BaseModel):
    """卡片列表响应。"""
    cards: list[CardResponse]
    total: int
    page: int
    limit: int


class ImportResult(BaseModel):
    """批量导入结果。"""
    success: list[CardResponse] = Field(default_factory=list)
    failed: list[dict] = Field(default_factory=list)
    total: int = 0


class ApiResponse(BaseModel):
    """统一 API 响应格式。"""
    status: str = Field(..., pattern="^(success|error)$")
    data: dict | None = None
    message: str = ""
    error_code: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── WebSocket 消息 ───────────────────────────────────────

class WSMessage(BaseModel):
    """WebSocket 消息。"""
    # Phase 2 事件字典(契约 §1.4):在原有类型基础上新增流式/工具/审批/会话事件。
    type: str = Field(
        ...,
        pattern=(
            "^(message|response|progress|card_preview|card_update|error|"
            "llm.delta|tool.called|tool.result|approval_required|approval|"
            "session.started|session.done|session.error|import.done)$"
        ),
    )
    content: str = ""
    data: dict | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
