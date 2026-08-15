"""应用配置 — LLM/Embedding/ChromaDB 等集中管理。"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# ── 加载 .env 文件（如果存在）────────────────────────────────
load_dotenv()

# ── 路径 ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
STATIC_DIR = BASE_DIR / "static"
VENDOR_DIR = STATIC_DIR / "vendor"
LOGS_DIR = BASE_DIR / "logs"

# ── LLM 配置 ─────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # openai | ollama | deepseek
# 降级链: 逗号分隔, 按顺序尝试 (Phase 2)
LLM_PROVIDERS: str = os.getenv("LLM_PROVIDERS", "deepseek,openai,ollama")
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
DEEPSEEK_API_KEY: str | None = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_TIMEOUT_SEC: int = int(os.getenv("LLM_TIMEOUT_SEC", "60"))  # LLM 调用超时

# ── Embedding 配置 ───────────────────────────────────────────
EMBEDDING_PROVIDER: Literal["openai", "sentence-transformers"] = os.getenv(
    "EMBEDDING_PROVIDER", "sentence-transformers"
)  # type: ignore[assignment]  # os.getenv 返回 str|None, 运行时默认值保证为合法字面量
OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
SENTENCE_TRANSFORMERS_MODEL: str = os.getenv(
    "SENTENCE_TRANSFORMERS_MODEL", "all-MiniLM-L6-v2"
)
EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "384"))
# all-MiniLM-L6-v2 → 384 维
# text-embedding-ada-002 → 1536 维

# ── ChromaDB 配置 ────────────────────────────────────────────
CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "knowledge_cards")
CHROMA_PERSIST_INTERVAL: int = int(os.getenv("CHROMA_PERSIST_INTERVAL", "60"))  # 秒
CHROMA_DISK_WARN_MB: int = int(os.getenv("CHROMA_DISK_WARN_MB", "100"))
CHROMA_DISK_STOP_MB: int = int(os.getenv("CHROMA_DISK_STOP_MB", "10"))

# ── 检索配置 ─────────────────────────────────────────────────
RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "10"))
RETRIEVAL_SCORE_THRESHOLD: float = float(os.getenv("RETRIEVAL_SCORE_THRESHOLD", "0.5"))

# ── Agent 配置 ───────────────────────────────────────────────
AGENT_MAX_RETRIES: int = int(os.getenv("AGENT_MAX_RETRIES", "2"))
AGENT_TIMEOUT_SEC: int = int(os.getenv("AGENT_TIMEOUT_SEC", "30"))

# ── Agent v2 三级预算 (Phase 2) ──────────────────────────────
AGENT_MAX_TURNS: int = int(os.getenv("AGENT_MAX_TURNS", "6"))
AGENT_MAX_TOKENS: int = int(os.getenv("AGENT_MAX_TOKENS", "8192"))
AGENT_MAX_WALL_TIME_SEC: int = int(os.getenv("AGENT_MAX_WALL_TIME_SEC", "120"))
APPROVAL_TIMEOUT_SEC: int = int(os.getenv("APPROVAL_TIMEOUT_SEC", "60"))

# ── 服务配置 ─────────────────────────────────────────────────
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))
STUDYWIKI_AUTH_TOKEN: str = os.getenv("STUDYWIKI_AUTH_TOKEN", "")

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")
DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

# ── 可观测性配置 (Phase 2 §5) ─────────────────────────────────
LOG_JSON: bool = os.getenv("LOG_JSON", "true").lower() == "true"
TRACE_HEADER_NAME: str = os.getenv("TRACE_HEADER_NAME", "X-Trace-Id")
METRICS_ENABLED: bool = os.getenv("METRICS_ENABLED", "true").lower() == "true"

# ── 确保目录存在 ──────────────────────────────────────────────
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
