"""CoT + ReAct 规划层 — Agent/Ask 双模式。"""

import json
import re
import logging
from typing import Any, Callable, Optional

from bobanana.tools import llm_invoke
from bobanana.tools_schema import TOOLS as TOOLS_SCHEMA, execute_tool

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


def run_ask_mode(question: str, chat_history: list[dict] = None) -> str:
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

    history_text = ""
    for m in (chat_history or [])[-4:]:
        role = "用户" if m.get("role") == "user" else "助手"
        history_text += f"{role}: {m.get('content', '')}\n"

    prompt = f"""对话历史:
{history_text}

知识库检索结果:
{search_text or '（知识库中未找到相关信息）'}

用户问题: {question}"""

    try:
        return llm_invoke(SYSTEM_ASK, prompt, timeout_sec=20).strip()
    except Exception as e:
        return f"抱歉，AI 调用失败: {e}"


def run_agent_mode(
    question: str,
    chat_history: list[dict] = None,
    progress_callback: Callable = None,
    max_turns: int = 6,
) -> str:
    """Agent 模式 — CoT + ReAct 循环。"""
    def emit(evt):
        if progress_callback:
            try: progress_callback(evt)
            except Exception: pass

    tools_desc = _build_tools_desc()
    system = SYSTEM_AGENT.format(tools_desc=tools_desc)

    history_text = ""
    for m in (chat_history or [])[-4:]:
        role = "用户" if m.get("role") == "user" else "助手"
        history_text += f"{role}: {m.get('content', '')}\n"

    conversation = f"""对话历史:
{history_text}

用户请求: {question}

请开始分析。"""

    emit({"stage": "agent", "status": "thinking"})

    try:
      for turn in range(max_turns):
        emit({"stage": "agent", "status": f"turn_{turn+1}"})

        # Step 1: LLM 生成 Thought + Action
        try:
            raw = llm_invoke(system, conversation, timeout_sec=40)
        except Exception as e:
            logger.error("ReAct LLM 调用失败: %s", e)
            emit({"stage": "agent", "status": "error"})
            return f"抱歉，AI 调用失败: {e}"

        # Step 2: 解析输出，检测 Final Answer
        final_match = re.search(r'Final Answer:\s*(.*?)$', raw, re.DOTALL | re.IGNORECASE)
        if final_match:
            emit({"stage": "agent", "status": "done"})
            return final_match.group(1).strip()

        thought, action_call = _parse_reAct(raw)

        if action_call:
            tool_name, tool_params = action_call

            # 验证工具名是否存在
            if tool_name not in [t["name"] for t in TOOLS_SCHEMA]:
                conversation += f"\n\nObservation: 未知工具 {tool_name}，请使用可用工具列表中的工具。"
                emit({"stage": "agent", "status": "error", "tool": tool_name})
                continue

            # Step 3: 执行工具
            emit({"stage": "agent", "status": "act", "tool": tool_name})
            result = execute_tool(tool_name, tool_params)
            observation = json.dumps(result, ensure_ascii=False, indent=2)

            # 截断过长观察结果（保留关键信息）
            if len(observation) > 800:
                observation = observation[:800] + "\n...(truncated)"

            # 紧凑追加对话上下文
            conversation += f"\n\n执行 {tool_name}: {observation[:400]}"
            emit({"stage": "agent", "status": "observe", "tool": tool_name})

        else:
            conversation += "\n\n请直接给出 Final Answer。"
            emit({"stage": "agent", "status": "force_final"})

      # Step 5: 获取最终答案
      conversation += "\n\n请给出 Final Answer。"
      try:
          final = llm_invoke(system, conversation, timeout_sec=20)
      except Exception as e:
          return f"抱歉，生成最终答案时失败: {e}"
      emit({"stage": "agent", "status": "done"})
      match = re.search(r'Final Answer:\s*(.*?)$', final, re.DOTALL | re.IGNORECASE)
      if match: return match.group(1).strip()
      return final.strip()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("ReAct 循环异常: %s\n%s", e, tb)
        return f"Agent 推理出错: {type(e).__name__}: {e}\n\nTraceback:\n{tb[-500:]}"


def _parse_reAct(text: str) -> tuple[str, Optional[tuple[str, dict]]]:
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
