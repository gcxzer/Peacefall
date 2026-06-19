from __future__ import annotations

"""调用 agent、记录输入输出、解析结构化回复。"""

import json
import re
from typing import Any

from engine.live_logging import (
    StreamContext,
    finish_model_stream,
    reset_stream_context,
    set_stream_context,
)
from engine.message_log import (
    ENGINE_SPEAKER,
    JUDGE_SPEAKER,
    record_message,
    record_public,
)
from engine.state import GameState


def announce(
    judge_agent: Any,
    state: GameState,
    instruction: str,
    *,
    phase: str,
    action: str,
) -> None:
    """让法官 agent 根据指令生成一条公开公告。"""

    content = invoke_agent(
        judge_agent,
        f"{instruction}\n\n{state.public_context()}",
        state=state,
        phase=phase,
        action=action,
        record_agent_response=False,
    )
    record_public(
        state,
        JUDGE_SPEAKER,
        content,
        phase=phase,
        action=action,
    )


def ask_json(
    agent: Any,
    message: str,
    *,
    state: GameState,
    phase: str,
    action: str,
    record_agent_response: bool = True,
) -> dict[str, Any]:
    """向 agent 提问，并把返回内容尽量解析为 JSON 对象。"""

    text = invoke_agent(
        agent,
        message,
        state=state,
        phase=phase,
        action=action,
        record_agent_response=record_agent_response,
    )
    return parse_json_object(text)


def invoke_agent(
    agent: Any,
    message: str,
    *,
    state: GameState,
    phase: str,
    action: str,
    record_agent_response: bool = True,
) -> str:
    """调用一个 LangChain agent，并按需记录本次调用的输入和输出。"""

    name = agent_name(agent)
    record_message(
        state,
        channel="agent",
        phase=phase,
        action=action,
        speaker=ENGINE_SPEAKER,
        recipient=name,
        role="user",
        content=message,
    )
    stream_context: StreamContext | None = None
    stream_token = None
    if _should_stream_model_output(state):
        stream_context = StreamContext(label=name)
        stream_token = set_stream_context(stream_context)

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": message}]})
    finally:
        if stream_context is not None:
            finish_model_stream(stream_context)
        if stream_token is not None:
            reset_stream_context(stream_token)

    if stream_context is not None and stream_context.streamed:
        state.streamed_actions.add((state.round_number, phase, action))

    response_text = extract_response_text(result)
    if record_agent_response:
        record_message(
            state,
            channel="agent",
            phase=phase,
            action=action,
            speaker=name,
            recipient=ENGINE_SPEAKER,
            role="assistant",
            content=response_text,
        )
    return response_text


def extract_response_text(result: Any) -> str:
    """从 LangChain agent 的不同返回形态中抽取最终文本。"""

    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            return message_content(messages[-1])
        if "output" in result:
            return str(result["output"]).strip()
    return message_content(result)


def message_content(message: Any) -> str:
    """把 message 对象中的 content 统一转换成字符串。"""

    if isinstance(message, dict):
        return str(message.get("content") or message.get("text") or "").strip()

    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    """从模型输出中尽量提取 JSON 对象。"""

    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _should_stream_model_output(state: GameState) -> bool:
    """判断当前消息监听器是否支持模型 delta 流式输出。"""

    return bool(getattr(state.on_message, "stream_model_output", False))


def agent_name(agent: Any) -> str:
    """返回写入消息日志时使用的 agent 名称。"""

    name = getattr(agent, "name", None)
    return str(name or agent.__class__.__name__)
