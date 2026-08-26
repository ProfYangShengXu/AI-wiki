"""WebSocket 对话路由 — 连接 Agent 问答工作流，推送进度事件。

Phase 2 增强:
- 每连接生成 session_id, 会话记忆持久化到 SQLite;
- 流式(llm.delta)/工具(tool.called/tool.result)/审批(approval_required)事件经
  stream_cb 用 call_soon_threadsafe 投递;
- 连接生命周期事件 session.started/done/error。
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from bobanana import memory
from bobanana.errors import SWError
from bobanana.models import WSMessage

logger = logging.getLogger(__name__)

router = APIRouter()

# 语义事件类型白名单(契约 §1.4),未知类型回退为 progress 以兼容旧客户端。
_SEMANTIC_EVENT_TYPES = {
    "llm.delta", "tool.called", "tool.result", "approval_required",
    "approval", "session.started", "session.done", "session.error", "progress",
}

# ── 上下文压缩 (前缀稳定, 保 LLM 前缀缓存命中率) ────────
# 历史超过阈值时: 保留前 COMPRESS_PREFIX 条原文(缓存前缀, 逐 token 不变),
# 中间用 LLM 压缩成一条摘要, 保留尾部 COMPRESS_TAIL 条原文。
# 摘要固定插在「前缀之后、尾部之前」, 因此每次请求的 prompt 前缀完全一致,
# 可命中 DeepSeek 等 provider 的前缀缓存; 压缩结果写回 SQLite 持久化。
COMPRESS_THRESHOLD = 24
COMPRESS_PREFIX = 6
COMPRESS_TAIL = 8
_SUMMARY_TAG = "【历史摘要】"

_SYSTEM_COMPRESS = """你是一个对话压缩器。把下面这段多轮对话压缩成一段简洁的中文摘要：
1. 保留用户的所有重要问题、已确认的结论、使用过的工具与导入的文件名
2. 省略寒暄与重复内容
3. 120 字以内，用第三人称陈述，不要使用"对话中"等元描述
4. 只输出摘要正文，不要任何前后缀"""


def _summarize_middle(middle: list[dict]) -> str:
    """把中间历史用 LLM 压缩为摘要; 失败则退化为截断拼接。"""
    from bobanana.tools import llm_invoke
    text = "\n".join(
        ("用户" if m.get("role") == "user" else "助手") + ": " + str(m.get("content", ""))
        for m in middle
    )
    try:
        summary = llm_invoke(_SYSTEM_COMPRESS, text, timeout_sec=15).strip()
        if summary:
            return summary[:500]
    except Exception as e:
        logger.warning("历史摘要生成失败, 退化为截断: %s", e)
    # 退化: 拼接各条内容的前 60 字
    parts = []
    for m in middle:
        c = str(m.get("content", "")).strip().replace("\n", " ")
        parts.append(c[:60])
    return "；".join(parts)[:500]


def _maybe_compress(session_id: str, chat_history: list[dict]) -> list[dict]:
    """超过阈值时压缩中间历史, 保持前缀稳定; 压缩结果落盘。"""
    if len(chat_history) <= COMPRESS_THRESHOLD:
        return chat_history
    prefix = chat_history[:COMPRESS_PREFIX]
    tail = chat_history[-COMPRESS_TAIL:]
    middle = chat_history[COMPRESS_PREFIX:len(chat_history) - COMPRESS_TAIL]
    if not middle:
        return chat_history
    summary = _summarize_middle(middle)
    compressed = prefix + [{"role": "assistant", "content": f"{_SUMMARY_TAG}\n{summary}"}] + tail
    memory.replace_history(session_id, compressed)
    logger.info(
        "会话 %s 上下文压缩: %d 条 → %d 条 (前缀 %d 条保持原文)",
        session_id, len(chat_history), len(compressed), COMPRESS_PREFIX,
    )
    return compressed

class ConnectionManager:
    """管理 WebSocket 连接和消息发送。"""

    def __init__(self):
        self.active_connections: dict[int, WebSocket] = {}
        self._counter = 0

    async def connect(self, websocket: WebSocket) -> int:
        await websocket.accept()
        self._counter += 1
        conn_id = self._counter
        self.active_connections[conn_id] = websocket
        return conn_id

    def disconnect(self, conn_id: int):
        self.active_connections.pop(conn_id, None)

    async def send(self, conn_id: int, msg: WSMessage):
        ws = self.active_connections.get(conn_id)
        if ws:
            try:
                await ws.send_text(msg.model_dump_json())
            except Exception as e:
                logger.warning("发送失败 (连接 %d): %s", conn_id, e)

    async def broadcast(self, msg: WSMessage):
        for conn_id in list(self.active_connections.keys()):
            await self.send(conn_id, msg)

manager = ConnectionManager()

# 导入完成 → 广播给所有活跃 WS 连接 (import_tasks 后台线程调用,
# 需调度回主事件循环)。_broadcast_loop 在连接建立时保存。
_broadcast_loop: asyncio.AbstractEventLoop | None = None


def _on_import_finished(state: dict) -> None:
    """导入任务到达终态时, 推送 import.done 事件给前端。"""
    loop = _broadcast_loop
    if loop is None or not loop.is_running():
        return
    try:
        msg = WSMessage(
            type="import.done",
            content=state.get("message", ""),
            data={
                "task_id": state.get("task_id", ""),
                "status": state.get("status", ""),
                "imported": state.get("result", {}).get("imported", 0),
                "skipped": state.get("result", {}).get("skipped", 0),
                "failed": state.get("result", {}).get("failed", 0),
                "errors": state.get("result", {}).get("errors", []),
            },
        )
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(manager.broadcast(msg))
        )
    except Exception as e:
        logger.warning("导入完成广播失败: %s", e)


from bobanana.import_tasks import register_import_finish_listener  # noqa: E402

register_import_finish_listener(_on_import_finished)

def make_progress_callback(conn_id: int, main_loop=None):
    """创建进度回调函数 — 用 call_soon_threadsafe 在主循环上调度。"""
    if main_loop is None:
        try:
            main_loop = asyncio.get_running_loop()
        except RuntimeError:
            main_loop = None

    def callback(event: dict):
        """向 WebSocket 推送进度事件。"""
        try:
            msg = WSMessage(
                type="progress",
                content=event.get("stage", ""),
                data=event,
            )
            if main_loop and main_loop.is_running():
                main_loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(manager.send(conn_id, msg))
                )
        except Exception as e:
            logger.warning("进度回调失败: %s", e)

    return callback

def make_event_callback(conn_id: int, main_loop=None):
    """创建事件回调(llm.delta/tool.called/tool.result/approval_required 等)。

    事件 dict 的 "type" 键映射为 WSMessage.type,payload 随 data 字段承载。
    """
    if main_loop is None:
        try:
            main_loop = asyncio.get_running_loop()
        except RuntimeError:
            main_loop = None

    def callback(event: dict):
        try:
            msg_type = event.get("type") or "progress"
            if msg_type not in _SEMANTIC_EVENT_TYPES:
                msg_type = "progress"
            msg = WSMessage(
                type=msg_type,
                content=str(event.get("delta", event.get("summary", ""))),
                data=event,
            )
            if main_loop and main_loop.is_running():
                main_loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(manager.send(conn_id, msg))
                )
        except Exception as e:
            logger.warning("事件回调失败: %s", e)

    return callback

async def _send_event(conn_id: int, evt: dict):
    """发送语义事件(session.started/done/error 等)。"""
    msg_type = evt.get("type") or "progress"
    await manager.send(
        conn_id,
        WSMessage(
            type=msg_type if msg_type in _SEMANTIC_EVENT_TYPES else "progress",
            content=evt.get("content", ""),
            data=evt,
        ),
    )

@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    global _broadcast_loop
    conn_id = await manager.connect(websocket)
    try:
        _broadcast_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    logger.info("WebSocket 连接已建立: #%d", conn_id)

    # 会话记忆
    session_id = uuid.uuid4().hex
    memory.init_db()
    chat_history: list[dict] = memory.get_history(session_id, limit=1000)
    chat_history = _maybe_compress(session_id, chat_history)

    await _send_event(conn_id, {"type": "session.started", "session_id": session_id})

    # 发送欢迎消息
    await manager.send(
        conn_id,
        WSMessage(
            type="response",
            content="你好！我是 StudyWiki Agent。你可以:\n"
                     "1. 问我关于知识库的问题\n"
                     "2. 说 '修改卡片 XXX' 来编辑卡片\n"
                     "3. 上传文件让我自动解析",
        ),
    )

    try:
        while True:
            raw = await websocket.receive_text()

            # 审批消息 (客户端 → 服务端)
            # 兼容两种负载形态: {"type":"approval","approval_id":...,"approved":...}
            # 与 {"type":"approval","data":{"approval_id":...,"approved":...}}
            try:
                raw_obj = json.loads(raw)
                if isinstance(raw_obj, dict) and raw_obj.get("type") == "approval":
                    from bobanana.agent_react import resolve_approval
                    data = raw_obj.get("data")
                    payload = data if isinstance(data, dict) else raw_obj
                    approval_id = payload.get("approval_id")
                    approved = bool(payload.get("approved"))
                    resolved = resolve_approval(str(approval_id), approved)
                    await _send_event(conn_id, {
                        "type": "approval",
                        "approval_id": approval_id,
                        "approved": approved,
                        "resolved": resolved,
                    })
                    continue
            except Exception:
                pass

            try:
                msg = WSMessage.model_validate_json(raw)
            except Exception:
                msg = WSMessage(type="message", content=raw)

            if msg.type != "message":
                await manager.send(
                    conn_id,
                    WSMessage(type="error", content=f"未知消息类型: {msg.type}"),
                )
                continue

            user_content = msg.content.strip()
            if not user_content:
                continue

            # 记录对话历史
            chat_history.append({"role": "user", "content": user_content})
            memory.append_message(session_id, "user", user_content)
            chat_history = _maybe_compress(session_id, chat_history)

            # 判断模式
            mode = msg.data.get("mode", "ask") if msg.data else "ask"

            if mode == "agent":
                # Agent 模式挂后台任务执行,保持接收循环活跃,
                # 以便处理客户端回发的审批消息 (approval)。
                task = asyncio.create_task(_handle_agent(conn_id, user_content, chat_history))

                def _finish(t: asyncio.Task):
                    nonlocal chat_history
                    failed = False
                    try:
                        answer = t.result()
                    except SWError as e:
                        failed = True
                        answer = e.message
                        logger.error("Agent 失败 (%s): %s", e.error_code, e.message)
                    except Exception as e:  # noqa: BLE001
                        failed = True
                        answer = f"处理失败: {e}"
                        logger.error("Agent 失败: %s", e)
                    chat_history.append({"role": "assistant", "content": answer})
                    memory.append_message(session_id, "assistant", answer)
                    chat_history = _maybe_compress(session_id, chat_history)
                    asyncio.ensure_future(manager.send(
                        conn_id, WSMessage(type="response", content=answer),
                    ))
                    if failed:
                        asyncio.ensure_future(_send_event(conn_id, {
                            "type": "session.error", "session_id": session_id,
                            "message": answer,
                        }))
                    else:
                        asyncio.ensure_future(_send_event(conn_id, {
                            "type": "session.done", "session_id": session_id,
                        }))

                task.add_done_callback(_finish)
                continue

            failed = False
            try:
                answer = await _handle_question(conn_id, user_content, chat_history)
            except SWError as e:
                failed = True
                logger.error("处理失败 (%s): %s", e.error_code, e.message)
                answer = e.message
                await _send_event(conn_id, {
                    "type": "session.error",
                    "session_id": session_id,
                    "error_code": e.error_code,
                    "message": e.message,
                })
            except Exception as e:
                failed = True
                logger.error("处理失败: %s", e)
                answer = f"处理失败: {e}"
                await _send_event(conn_id, {
                    "type": "session.error",
                    "session_id": session_id,
                    "message": str(e),
                })

            # 记录回答到历史并持久化
            chat_history.append({"role": "assistant", "content": answer})
            memory.append_message(session_id, "assistant", answer)
            chat_history = _maybe_compress(session_id, chat_history)

            # 发送回答
            await manager.send(
                conn_id,
                WSMessage(type="response", content=answer),
            )
            if not failed:
                await _send_event(conn_id, {"type": "session.done", "session_id": session_id})

    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开: #%d", conn_id)
    except Exception as e:
        logger.error("WebSocket 错误 (#%d): %s", conn_id, e)
        try:
            await manager.send(
                conn_id,
                WSMessage(type="error", content=f"服务器内部错误: {str(e)}"),
            )
        except Exception:
            pass
    finally:
        manager.disconnect(conn_id)

async def _handle_question(conn_id: int, question: str, chat_history: list[dict]) -> str:
    """处理问答请求, 返回回答文本。"""
    # 发送"思考中"状态
    await manager.send(
        conn_id,
        WSMessage(type="progress", data={"stage": "thinking", "status": "started"}),
    )

    # Ask 模式 — 仅查知识库回答
    from bobanana.agent_react import run_ask_mode
    loop = asyncio.get_event_loop()
    stream_cb = make_event_callback(conn_id, main_loop=loop)
    answer = await loop.run_in_executor(None, run_ask_mode, question, chat_history, stream_cb)
    return answer

async def _handle_agent(conn_id: int, instruction: str, chat_history: list[dict]) -> str:
    """Agent 模式 — CoT + ReAct 循环, 返回回答文本。"""
    from bobanana.agent_react import run_agent_mode
    await manager.send(conn_id, WSMessage(type="progress", data={"stage": "agent", "status": "thinking"}))

    loop = asyncio.get_event_loop()
    main_loop = loop
    progress_cb = make_progress_callback(conn_id, main_loop=main_loop)
    stream_cb = make_event_callback(conn_id, main_loop=main_loop)
    answer = await loop.run_in_executor(
        None, run_agent_mode, instruction, chat_history, progress_cb, None, stream_cb
    )
    return answer
