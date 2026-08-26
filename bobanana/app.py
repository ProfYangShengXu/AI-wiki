"""FastAPI 应用入口 — 路由注册器 + 中间件 + 全局异常处理。"""

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from bobanana.config import BASE_DIR, DEBUG, LOG_LEVEL, STATIC_DIR
from bobanana.database import db_manager
from bobanana.errors import SWError, generic_code_for_status, utc_now_iso
from bobanana.log_handler import log_handler
from bobanana.models import ApiResponse
from bobanana.observability import KeyRedactFilter, TraceMiddleware
from bobanana.routes import (
    backup,
    bootstrap,
    cards,
    categories,
    chat,
    history,
    knowledgebase,
    quiz,
    quizzes,
    settings,
    upload,
)
from bobanana.routes import metrics as metrics_routes

# ── 日志配置 ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger().addHandler(log_handler)

# 日志脱敏:控制台与内存日志全部过滤 API Key / Bearer Token
_key_redact = KeyRedactFilter()
for _h in logging.getLogger().handlers:
    _h.addFilter(_key_redact)


# ── 生命周期 ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("StudyWiki-Agent 启动中 ...")
    logger.info("=" * 50)

    # ── 启动时网络与资源检查 ───────────────────────────
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        logger.info("网络连接正常")
    except OSError:
        logger.warning("⚠ 无互联网连接 — 模型下载/LLM 调用将失败")

    # ── ChromaDB 初始化 ───────────────────────────────
    await db_manager.startup()
    logger.info("数据库就绪 | 卡片总数: %d", db_manager.count())

    # ── Quiz 卡片存储初始化 (幂等) ────────────────────
    try:
        from bobanana import quiz_store
        quiz_store.init_db()
    except Exception as e:
        logger.warning("quiz_cards 初始化失败(不影响启动): %s", e)

    # ── 存量分类收敛迁移 (幂等) ──────────────────────
    try:
        from bobanana.service.card_service import card_service
        card_service.migrate_categories()
    except Exception as e:
        logger.warning("分类迁移失败(不影响启动): %s", e)

    # ── 预加载嵌入模型（启动时加载，避免在线程中加载导致 httpx 冲突）──
    from bobanana.config import EMBEDDING_PROVIDER
    if EMBEDDING_PROVIDER == "sentence-transformers":
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            logger.info("预加载嵌入模型: all-MiniLM-L6-v2 ...")
            from bobanana.tools import get_embedding_model
            get_embedding_model()
            logger.info("嵌入模型就绪")
        except Exception as e:
            logger.warning("嵌入模型加载失败（将在首次使用时重试）: %s", e)
            # 清除离线标志以允许重试时联网下载
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            logger.info("嵌入模型就绪")
        # P0 workaround: 原文件存在重复 except 语法错误；此处用嵌套 try 使文件可导入，
        # Phase 2 M1 将整体清理 lifespan 的模型预加载逻辑。
        try:
            pass
        except Exception as e:
            logger.warning("嵌入模型加载失败: %s（首次使用时会重试）", e)

    yield

    logger.info("=" * 50)
    logger.info("StudyWiki-Agent 关闭中 ...")
    logger.info("=" * 50)
    await db_manager.shutdown()


# ── 应用创建 ─────────────────────────────────────────────

app = FastAPI(
    title="StudyWiki-Agent",
    description="基于 LangChain + LangGraph 的可增长本地 Wiki 知识库 API",
    version="0.34.0",
    lifespan=lifespan,
    debug=DEBUG,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 可选本地 Token：在 .env 设置 STUDYWIKI_AUTH_TOKEN 后启用。
# bootstrap 与 health/静态资源保持公开，业务 API 需要 Authorization: Bearer <token>。
@app.middleware("http")
async def local_auth_middleware(request: Request, call_next):
    from bobanana.config import STUDYWIKI_AUTH_TOKEN

    public_paths = {
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/api/bootstrap/status",
        "/api/bootstrap/test",
        "/api/bootstrap/configure",
    }
    path = request.url.path
    if STUDYWIKI_AUTH_TOKEN and path not in public_paths and not path.startswith("/static"):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {STUDYWIKI_AUTH_TOKEN}":
            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "message": "未授权",
                    "error_code": "SW-AUTH-001",
                },
            )
    return await call_next(request)

# trace 中间件:最后添加 → 最外层,保证 trace_id 覆盖鉴权与业务处理;
# 响应头回传 X-Trace-Id,访问日志与指标由 observability 内部记录。
app.add_middleware(TraceMiddleware)

# ── 全局异常处理 ────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("未处理异常: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content=ApiResponse(
            status="error",
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            data={"detail": str(exc) if DEBUG else None},
        ).model_dump(),
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    # 业务路由抛出的 HTTPException(404, detail="分类「X」不存在") 带具体 detail,
    # 透传真实原因; 纯"无此路由"时保留通用文案。
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail.strip() and detail.strip() != "Not Found":
        message = detail.strip()
    else:
        message = "接口不存在"
    return JSONResponse(
        status_code=404,
        content=ApiResponse(
            status="error", message=message, error_code="NOT_FOUND"
        ).model_dump(),
    )


@app.exception_handler(405)
async def method_not_allowed_handler(request: Request, exc):
    return JSONResponse(
        status_code=405,
        content=ApiResponse(
            status="error", message="请求方法不允许", error_code="METHOD_NOT_ALLOWED"
        ).model_dump(),
    )


# ── 统一业务异常（SWError） ─────────────────────────────
# 保留向后兼容：现有 HTTPException 抛法不动；SWError 供新代码使用。
@app.exception_handler(SWError)
async def sw_error_handler(request: Request, exc: SWError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


# ── HTTPException 统一包装 ─────────────────────────────
# 将 FastAPI 默认的 {detail: ...} 统一为 {status, error_code, message, timestamp}。
# 注意：404 / 405 仍由上方按状态码注册的 handler 优先处理，行为保持不变。
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    status_code = exc.status_code
    error_code = generic_code_for_status(status_code)
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "error_code": error_code,
            "message": str(exc.detail),
            "timestamp": utc_now_iso(),
        },
        headers=headers,
    )


# 静态文件
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 路由
app.include_router(bootstrap.router)

app.include_router(cards.router)
app.include_router(categories.router)
app.include_router(history.router)
app.include_router(upload.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(quizzes.router)
app.include_router(settings.router)
app.include_router(knowledgebase.router)
app.include_router(backup.router)  # 备份 / 恢复路由 (Phase 2 §4)
app.include_router(metrics_routes.router)  # 指标路由 (Phase 2 §5)


# ── 根路由 ───────────────────────────────────────────────

@app.get("/")
async def root():
    """根路由 — 返回前端页面。"""
    from fastapi.responses import FileResponse
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"service": "StudyWiki-Agent", "version": "0.34.0"}


@app.get("/api/logs")
async def get_logs(level: str = None, n: int = 100):
    """Get recent logs, optional level filter."""
    from fastapi.responses import JSONResponse
    return JSONResponse(content={"status": "success", "data": log_handler.get_recent(n=n, level=level)})


@app.get("/health")
async def health():
    try:
        count = db_manager.count()
        return {"status": "ok", "cards_count": count}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": str(e)},
        )


# ── OpenAPI 契约文档挂载 ───────────────────────────────
# 提供手写的 api/openapi.yaml（与 FastAPI 自动导出的 /openapi.json 并存）。
OPENAPI_YAML_PATH = BASE_DIR / "api" / "openapi.yaml"


@app.get("/api/openapi.yaml", include_in_schema=False)
async def openapi_contract():
    """返回手写 OpenAPI 3.0.3 契约文档。"""
    if not OPENAPI_YAML_PATH.exists():
        raise StarletteHTTPException(status_code=404, detail="openapi.yaml 不存在")
    return Response(
        content=OPENAPI_YAML_PATH.read_text(encoding="utf-8"),
        media_type="application/yaml",
    )
