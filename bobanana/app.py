"""FastAPI 应用入口 — 路由注册器 + 中间件 + 全局异常处理。"""

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from bobanana.config import STATIC_DIR, DEBUG, LOG_LEVEL
from bobanana.database import db_manager
from bobanana.log_handler import log_handler
from bobanana.models import ApiResponse
from bobanana.routes import cards, categories, history, upload, chat, quiz, settings, knowledgebase

# ── 日志配置 ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger().addHandler(log_handler)


# ── 生命周期 ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("StudyWiki-Agent 启动中 ...")
    logger.info("=" * 50)

    # ── 启动时网络与资源检查 ───────────────────────────
    import socket
    network_ok = True
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        logger.info("网络连接正常")
    except OSError:
        network_ok = False
        logger.warning("⚠ 无互联网连接 — 模型下载/LLM 调用将失败")

    # ── ChromaDB 初始化 ───────────────────────────────
    await db_manager.startup()
    logger.info("数据库就绪 | 卡片总数: %d", db_manager.count())

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
    version="0.3.0",
    lifespan=lifespan,
    debug=DEBUG,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return JSONResponse(
        status_code=404,
        content=ApiResponse(
            status="error", message="接口不存在", error_code="NOT_FOUND"
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


# 静态文件
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 路由
app.include_router(cards.router)
app.include_router(categories.router)
app.include_router(history.router)
app.include_router(upload.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(settings.router)
app.include_router(knowledgebase.router)


# ── 根路由 ───────────────────────────────────────────────

@app.get("/")
async def root():
    """根路由 — 返回前端页面。"""
    from fastapi.responses import FileResponse
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"service": "StudyWiki-Agent", "version": "0.2.0"}


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
