"""CoT + ReAct 规划层 — Agent/Ask 双模式。

Phase 2 增强:
- 优先原生 function calling(bind_tools + AIMessage.tool_calls), 失败回退 JSON-ReAct;
- 三级预算(max_turns / max_tokens / max_wall_time), 超限抛 SW-AGENT-429;
- 审批闸门(delete_card 等危险工具), 状态存模块级 dict(单用户);
- 可选 stream_cb 流式回调。
"""

import concurrent.futures as _cf
import json
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Callable

from bobanana.config import (
    AGENT_MAX_TOKENS,
    AGENT_MAX_TURNS,
    AGENT_MAX_WALL_TIME_SEC,
    APPROVAL_TIMEOUT_SEC,
)
from bobanana.errors import SW_AGENT_400, SW_AGENT_429, SWError
from bobanana.tools import get_llm, llm_invoke, llm_stream
from bobanana.tools_schema import (
    TOOLS as TOOLS_SCHEMA,
)
from bobanana.tools_schema import (
    execute_tool,
    tool_requires_approval,
    validate_tool_args,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════

SYSTEM_ASK = """你是 StudyWiki-Agent (Ask 模式)。基于知识库内容回答问题。
规则:
1. 知识库已自动检索，检索结果附在下方
2. 回答时引用知识来源（卡片标题 + 出处文件）
3. 如果知识库中没有相关信息，明确说"知识库中暂无相关信息"
4. 不要编造知识库中没有的内容
5. 回答简洁准确，2-5 句话即可
6. Ask 模式只能回答知识库问题。如需创建/修改/删除卡片，请切换到 Agent 模式"""

SYSTEM_AGENT = """你是 StudyWiki-Agent (Agent 模式)。你可以使用所有工具来操作知识库。

可用工具:
{tools_desc}

你必须使用 CoT + ReAct 模式:
1. Thought: 分析用户意图，制定步骤计划
2. Action: 调用合适的工具（每次只能调用一个）
3. Observation: 观察工具返回结果
4. (重复 Thought → Action → Observation 直到任务完成)
5. Final Answer: 总结结果

重要规则:
- 操作前先确认（如删除卡片前先搜索确认）
- 创建卡片前先用 list_categories 查看已有分类，选择已有分类；如果无匹配再新建分类
- 创建卡片时如果用户没给详细内容，用 create_card 自动AI填充
- Quiz 需要两步: start_quiz → grade_quiz
- 组卷用 create_exam
- 回答时引用知识库出处

输出格式:
Thought: [分析]
Action: tool_name({{"param": "value"}})
---
(等待 Observation 后继续)
Thought: [分析]
Final Answer: [最终回答]"""


# ═══════════════════════════════════════════════════════════
# 审批状态 (单用户场景, 模块级 dict)
# ═══════════════════════════════════════════════════════════

_APPROVAL_STATE: dict[str, dict] = {}
_APPROVAL_LOCK = threading.Lock()

# 原生 function calling 专用线程池(带超时)
_NATIVE_POOL = None
_NATIVE_POOL_LOCK = threading.Lock()


def _get_native_pool():
    global _NATIVE_POOL
    if _NATIVE_POOL is None:
        with _NATIVE_POOL_LOCK:
            if _NATIVE_POOL is None:
                _NATIVE_POOL = _cf.ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="agent-native"
                )
    return _NATIVE_POOL


# ═══════════════════════════════════════════════════════════
# 小工具
# ═══════════════════════════════════════════════════════════

def _safe_cb(cb, evt):
    if cb is None:
        return
    try:
        cb(evt)
    except Exception:
        pass


def _emit_event(stream_cb, progress_callback, evt):
    """新类型事件优先走 stream_cb, 未提供时回退 progress_callback。"""
    if stream_cb is not None:
        _safe_cb(stream_cb, evt)
    else:
        _safe_cb(progress_callback, evt)


def _approx_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def _emit_text_delta(stream_cb, text: str) -> None:
    """原生 invoke 非增量, 按片段切块模拟流式输出。"""
    if stream_cb is None or not text:
        return
    step = 24
    for i in range(0, len(text), step):
        _safe_cb(stream_cb, {"type": "llm.delta", "delta": text[i:i + step]})


def _native_calling_enabled() -> bool:
    """测试环境(无网络/打桩)禁用原生 function calling, 走 JSON-ReAct。"""
    return os.environ.get("STUDYWIKI_TEST_MODE") != "1"


def _build_bound_llm():
    """构造 bind_tools 后的 LLM; 不支持/失败返回 None。"""
    llm = get_llm()
    if llm is None or not hasattr(llm, "bind_tools"):
        return None
    tool_schemas = []
    for t in TOOLS_SCHEMA:
        tool_schemas.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("parameters", {}),
        })
    try:
        return llm.bind_tools(tool_schemas)
    except Exception as e:
        logger.warning("bind_tools 失败, 回退 JSON-ReAct: %s", e)
        return None


def _detect_final_answer(text: str) -> str | None:
    m = re.search(r'Final Answer:\s*(.*?)$', text or "", re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _summary_args(params) -> str:
    try:
        items = []
        for k, v in (params or {}).items():
            sv = str(v)
            if len(sv) > 20:
                sv = sv[:20] + "..."
            items.append(f"{k}={sv}")
        return ",".join(items) or "-"
    except Exception:
        return "-"


def _summarize_result(result) -> str:
    try:
        if isinstance(result, dict):
            if result.get("error"):
                return str(result["error"])[:80]
            if result.get("status"):
                return str(result["status"])
            if result.get("count") is not None:
                return f"{result['count']} 条结果"
            return str(result)[:80]
        return str(result)[:80]
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════
# ReAct Loop
# ═══════════════════════════════════════════════════════════

def _build_tools_desc() -> str:
    """构建工具描述文本（精简版，只含必填参数）。"""
    lines = []
    for t in TOOLS_SCHEMA:
        required = t.get("parameters", {}).get("required", [])
        params = t.get("parameters", {}).get("properties", {})
        req_params = {k: params[k] for k in required if k in params}
        params_str = ", ".join([f"{k}" for k in req_params]) if req_params else ""
        lines.append(f"- {t['name']}({params_str}): {t['description'][:60]}")
    return "\n".join(lines)


def _history_to_text(chat_history: list[dict] | None) -> str:
    """把会话历史渲染为文本。

    历史已在 chat 路由层压缩(前缀原文 + 【历史摘要】 + 尾部原文),
    这里按序全量渲染, 保证每次请求的 prompt 前缀逐 token 一致,
    从而命中 LLM 前缀缓存。
    """
    if not chat_history:
        return ""
    lines = []
    for m in chat_history:
        role = "用户" if m.get("role") == "user" else "助手"
        lines.append(f"{role}: {m.get('content', '')}")
    return "\n".join(lines)


def run_ask_mode(question: str, chat_history: list[dict] = None, stream_cb: Callable = None) -> str:
    """Ask 模式 — 仅查知识库回答。"""
    # Step 1: 搜索知识库
    search_text = ""
    try:
        cards = card_search(question, top_k=5)
        if cards:
            parts = []
            for c in cards:
                parts.append(f"【{c['title']}】(来源: {c.get('source_file','未知')})\n{c['content'][:500]}")
            search_text = "\n---\n".join(parts)
    except Exception:
        pass

    history_text = _history_to_text(chat_history)

    prompt = f"""对话历史:
{history_text}

知识库检索结果:
{search_text or '（知识库中未找到相关信息）'}

用户问题: {question}"""

    try:
        if stream_cb is None:
            return llm_invoke(SYSTEM_ASK, prompt, timeout_sec=20).strip()
        parts = []
        for chunk in llm_stream(SYSTEM_ASK, prompt):
            parts.append(chunk)
            _safe_cb(stream_cb, {"type": "llm.delta", "delta": chunk})
        return "".join(parts).strip()
    except Exception as e:
        return f"抱歉，AI 调用失败: {e}"


def _llm_turn_text(system: str, conversation: str, timeout_sec: int, stream_cb) -> str:
    """生成一轮文本; stream_cb 提供时走流式。"""
    if stream_cb is None:
        return llm_invoke(system, conversation, timeout_sec=timeout_sec)
    parts = []
    try:
        for chunk in llm_stream(system, conversation):
            parts.append(chunk)
            _safe_cb(stream_cb, {"type": "llm.delta", "delta": chunk})
        return "".join(parts)
    except Exception:
        return llm_invoke(system, conversation, timeout_sec=timeout_sec)


def _invoke_native(bound_llm, system: str, conversation: str, timeout_sec: int):
    """原生 function calling 调用, 返回 (text, [(tool_name, args), ...])。"""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    messages = [SystemMessage(content=system), HumanMessage(content=conversation)]

    def _call():
        return bound_llm.invoke(messages)

    pool = _get_native_pool()
    future = pool.submit(_call)
    try:
        msg = future.result(timeout=timeout_sec)
    except _cf.TimeoutError:
        raise TimeoutError(f"原生 function calling 超时 ({timeout_sec}s)") from None

    text = ""
    tool_calls = []
    if isinstance(msg, AIMessage):
        text = msg.content or ""
        for tc in getattr(msg, "tool_calls", None) or []:
            name = tc.get("name")
            args = tc.get("args") or {}
            if name:
                tool_calls.append((name, args))
    else:
        text = getattr(msg, "content", str(msg))
    return text, tool_calls


def _request_approval(approval_id: str, tool_name: str, args: dict, emit_event, timeout_sec: int) -> bool:
    """发出审批请求并阻塞等待用户决定。超时/拒绝返回 False。"""
    evt = {"type": "approval_required", "approval_id": approval_id, "tool": tool_name, "args": args}
    event = threading.Event()
    with _APPROVAL_LOCK:
        _APPROVAL_STATE[approval_id] = {"event": event, "approved": False}
    emit_event(evt)
    approved = event.wait(timeout_sec)
    with _APPROVAL_LOCK:
        state = _APPROVAL_STATE.pop(approval_id, None)
    result = bool(approved and state and state["approved"])
    try:
        from bobanana.observability import metrics
        metrics.inc("approvals_total", labels={"decision": "approved" if result else "denied"})
    except Exception:  # noqa: BLE001 — 指标失败不影响审批主流程
        pass
    return result


def resolve_approval(approval_id: str, approved: bool) -> bool:
    """chat.py 收到客户端审批消息后调用, 置位对应 Event。"""
    with _APPROVAL_LOCK:
        state = _APPROVAL_STATE.get(approval_id)
        if state is None:
            return False
        state["approved"] = bool(approved)
        state["event"].set()
        return True


def run_agent_mode(
    question: str,
    chat_history: list[dict] = None,
    progress_callback: Callable = None,
    max_turns: int = None,
    stream_cb: Callable = None,
) -> str:
    """Agent 模式 — 原生 function calling 优先, JSON-ReAct 兜底。"""
    def emit(evt):
        _safe_cb(progress_callback, evt)

    def emit_event(evt):
        _emit_event(stream_cb, progress_callback, evt)

    max_turns = max_turns if max_turns is not None else AGENT_MAX_TURNS
    max_tokens = AGENT_MAX_TOKENS
    wall_deadline = time.monotonic() + AGENT_MAX_WALL_TIME_SEC
    tokens_used = 0
    steps_summary: list[str] = []
    consecutive_invalid = 0

    tools_desc = _build_tools_desc()
    system = SYSTEM_AGENT.format(tools_desc=tools_desc)

    history_text = _history_to_text(chat_history)

    conversation = f"""对话历史:
{history_text}

用户请求: {question}

请开始分析。"""

    emit({"stage": "agent", "status": "thinking"})

    bound_llm = None
    if _native_calling_enabled():
        bound_llm = _build_bound_llm()

    def check_budget():
        if time.monotonic() > wall_deadline:
            summary = "; ".join(steps_summary) if steps_summary else "(无已完成步骤)"
            raise SWError(
                SW_AGENT_429,
                f"Agent 超过 wall time 限制 ({AGENT_MAX_WALL_TIME_SEC}s)。已完成步骤: {summary}",
            )
        if tokens_used >= max_tokens:
            summary = "; ".join(steps_summary) if steps_summary else "(无已完成步骤)"
            raise SWError(
                SW_AGENT_429,
                f"Agent 累计 token 超限 ({max_tokens})。已完成步骤: {summary}",
            )

    try:
        for turn in range(max_turns):
            check_budget()
            emit({"stage": "agent", "status": f"turn_{turn+1}"})

            raw = ""
            tool_calls = []

            # 1) 原生 function calling
            if bound_llm is not None:
                try:
                    raw, tool_calls = _invoke_native(bound_llm, system, conversation, 40)
                except Exception as e:
                    logger.warning("原生 function calling 失败, 回退 JSON-ReAct: %s", e)
                    bound_llm = None
                    raw = ""
                    tool_calls = []

            # 2) JSON-ReAct 兜底
            if not tool_calls:
                if not raw:
                    raw = _llm_turn_text(system, conversation, 40, stream_cb)
                else:
                    _emit_text_delta(stream_cb, raw)
                if raw:
                    tokens_used += _approx_tokens(raw)
                final = _detect_final_answer(raw)
                if final is not None:
                    emit({"stage": "agent", "status": "done"})
                    return final
                thought, action_call = _parse_reAct(raw)
                if action_call:
                    tool_calls = [action_call]

            if tool_calls:
                known_tools = {t["name"] for t in TOOLS_SCHEMA}
                for tool_name, tool_params in tool_calls:
                    check_budget()

                    # 未知工具
                    if tool_name not in known_tools:
                        conversation += f"\n\nObservation: 未知工具 {tool_name}，请使用可用工具列表中的工具。"
                        emit({"stage": "agent", "status": "error", "tool": tool_name})
                        continue

                    # 参数校验
                    ok, validated = validate_tool_args(tool_name, tool_params)
                    if not ok:
                        consecutive_invalid += 1
                        if consecutive_invalid >= 2:
                            raise SWError(SW_AGENT_400, f"工具参数连续校验失败: {validated}")
                        conversation += (
                            f"\n\nObservation: 工具 {tool_name} 参数校验失败: {validated}。请修正参数后重试。"
                        )
                        emit_event({"type": "tool.result", "tool": tool_name, "ok": False,
                                   "summary": f"参数校验失败: {validated}"})
                        continue
                    consecutive_invalid = 0

                    # 规范化参数
                    if hasattr(validated, "model_dump"):
                        clean_params = validated.model_dump(exclude_none=True)
                    else:
                        clean_params = dict(tool_params or {})

                    # 审批闸门
                    if tool_requires_approval(tool_name):
                        approval_id = uuid.uuid4().hex
                        approved = _request_approval(
                            approval_id, tool_name, clean_params, emit_event, APPROVAL_TIMEOUT_SEC
                        )
                        if not approved:
                            conversation += f"\n\nObservation: 工具 {tool_name} 被用户拒绝或审批超时。"
                            steps_summary.append(f"{tool_name}(被拒绝)")
                            emit_event({"type": "tool.result", "tool": tool_name, "ok": False,
                                       "summary": "用户拒绝或审批超时"})
                            continue

                    # 执行工具
                    emit_event({"type": "tool.called", "tool": tool_name, "args": clean_params})
                    emit({"stage": "agent", "status": "act", "tool": tool_name})
                    result = execute_tool(tool_name, clean_params)
                    observation = json.dumps(result, ensure_ascii=False, indent=2)

                    if len(observation) > 800:
                        observation = observation[:800] + "\n...(truncated)"

                    conversation += f"\n\n执行 {tool_name}: {observation[:400]}"
                    tokens_used += _approx_tokens(observation)
                    steps_summary.append(f"{tool_name}({_summary_args(clean_params)})")
                    emit({"stage": "agent", "status": "observe", "tool": tool_name})
                    emit_event({"type": "tool.result", "tool": tool_name, "ok": True,
                               "summary": _summarize_result(result)})
            else:
                conversation += "\n\n请直接给出 Final Answer。"
                emit({"stage": "agent", "status": "force_final"})

        # 最终答案
        check_budget()
        conversation += "\n\n请给出 Final Answer。"
        final = _llm_turn_text(system, conversation, 20, stream_cb)
        emit({"stage": "agent", "status": "done"})
        match = re.search(r'Final Answer:\s*(.*?)$', final, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return final.strip()
    except SWError:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("ReAct 循环异常: %s\n%s", e, tb)
        return f"Agent 推理出错: {type(e).__name__}: {e}\n\nTraceback:\n{tb[-500:]}"


def _parse_reAct(text: str) -> tuple[str, tuple[str, dict] | None]:
    """解析 ReAct 输出，提取 Action 调用。"""
    thought = ""
    action_call = None

    # 提取 Thought
    m = re.search(r'Thought:\s*(.*?)(?=Action:|Final Answer:|\Z)', text, re.DOTALL | re.IGNORECASE)
    if m: thought = m.group(1).strip()

    # 提取 Action: tool_name({...}) (支持嵌套 JSON)
    m = re.search(r'Action:\s*(\w+)\s*\(\s*\{', text)
    if m:
        tool_name = m.group(1)
        # 找到 Action 后面的第一个 {
        try:
            brace_pos = text.index('{', m.start())
        except ValueError:
            return thought, None
        start = brace_pos
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == '{': depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        try:
            params = json.loads(text[start:end])
        except json.JSONDecodeError:
            params = {}
        action_call = (tool_name, params)

    return thought, action_call


# ═══════════════════════════════════════════════════════════
# 知识库搜索 (供 Ask 模式使用)
# ═══════════════════════════════════════════════════════════

def card_search(query: str, top_k: int = 5) -> list[dict]:
    """搜索知识库（同步）。"""
    try:
        from bobanana.service.card_service import card_service
        cards = card_service.search_cards_sync(query, top_k=top_k)
        return [c.model_dump() for c, _ in cards]
    except Exception as e:
        logger.warning("card_search failed: %s", e)
        return []
