"""WebSocket 对话路由 — 连接 Agent 问答工作流，推送进度事件。"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from bobanana.agent import run_qa_workflow, modify_card
from bobanana.models import WSMessage

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    conn_id = await manager.connect(websocket)
    logger.info("WebSocket 连接已建立: #%d", conn_id)

    # 对话历史
    chat_history: list[dict] = []

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

            # 判断是否为"修改卡片"指令
            if user_content.startswith("修改卡片"):
                await _handle_modify(conn_id, user_content)
            else:
                # 问答
                await _handle_question(conn_id, user_content, chat_history)

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


def _run_qa_sync(question: str, chat_history: list[dict], conn_id: int, main_loop=None) -> str:
    """在线程中同步运行问答工作流。"""
    return asyncio.run(run_qa_workflow(
        question=question,
        chat_history=chat_history,
        progress_callback=make_progress_callback(conn_id, main_loop=main_loop),
    ))


async def _handle_question(conn_id: int, question: str, chat_history: list[dict]):
    """处理问答请求。"""
    # 发送"思考中"状态
    await manager.send(
        conn_id,
        WSMessage(type="progress", data={"stage": "thinking", "status": "started"}),
    )

    # 在后台线程运行问答工作流，避免阻塞 WebSocket
    loop = asyncio.get_event_loop()
    main_loop = loop  # 捕获主事件循环供线程中回调使用
    answer = await loop.run_in_executor(
        None, _run_qa_sync, question, chat_history, conn_id, main_loop
    )

    # 记录回答到历史
    chat_history.append({"role": "assistant", "content": answer})

    # 发送回答
    await manager.send(
        conn_id,
        WSMessage(type="response", content=answer),
    )


async def _handle_modify(conn_id: int, instruction: str):
    """处理卡片修改指令 — 在 executor 中运行以避免阻塞事件循环。"""
    # 解析卡片 ID (格式: "修改卡片 <id> 的内容: ...")
    parts = instruction.split(" ", 2)
    if len(parts) < 3:
        await manager.send(
            conn_id,
            WSMessage(
                type="response",
                content="请使用格式: `修改卡片 <卡片ID> 的内容: <修改说明>`\n\n"
                         "例如: `修改卡片 abc-123 的内容: 补充一个实际案例`",
            ),
        )
        return

    card_id = parts[1]
    modify_instruction = parts[2]

    await manager.send(
        conn_id,
        WSMessage(type="progress", data={"stage": "modify", "status": "started"}),
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: asyncio.run(modify_card(card_id, modify_instruction)),
    )

    if result:
        await manager.send(
            conn_id,
            WSMessage(
                type="card_update",
                content=f"卡片 {result['title']} 已更新",
                data={"card": result},
            ),
        )
    else:
        await manager.send(
            conn_id,
            WSMessage(
                type="error",
                content=f"未找到卡片: {card_id}，请先搜索确认卡片 ID",
            ),
        )
