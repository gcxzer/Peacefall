from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from model_providers.codex_auth import (
    DEFAULT_CODEX_BASE_URL,
    codex_default_headers,
    runtime_codex_credentials,
)
from model_providers.config import ModelProviderConfig
from engine.live_logging import emit_model_delta


class CodexChatModel:
    """给 LangChain agent 使用的 Codex OAuth 聊天模型适配器。

    LangChain create_agent 需要模型对象支持 bind/invoke；Codex 后端又要求
    Responses API 使用 stream，所以这里做一个很薄的兼容层。
    """

    def __init__(
        self,
        config: ModelProviderConfig,
        *,
        bound_options: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.bound_options = bound_options or {}

    def bind(self, **kwargs: Any) -> CodexChatModel:
        """返回绑定了运行时参数的新模型实例。"""

        return CodexChatModel(
            self.config,
            bound_options={**self.bound_options, **kwargs},
        )

    def bind_tools(
        self,
        tools: list[Any],
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> CodexChatModel:
        """兼容 LangChain 的工具绑定接口。

        当前游戏没有工具调用，所以先明确拒绝非空 tools，避免静默失败。
        """

        if tools:
            raise NotImplementedError("CodexChatModel does not support tools yet.")
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return self.bind(**kwargs)

    def invoke(self, messages: list[BaseMessage], **_: Any) -> AIMessage:
        """同步调用 Codex，并把流式结果聚合成 AIMessage。"""

        from openai import OpenAI

        credentials = runtime_codex_credentials(
            auth_path=self.config.options.get("auth_path")
        )
        if not credentials.access_token:
            raise RuntimeError(
                "Codex OAuth is not connected. Run Codex login first or set "
                "PINGAN_YE_CODEX_AUTH_PATH to a valid auth.json."
            )

        client = OpenAI(
            api_key=credentials.access_token,
            base_url=str(
                self.config.options.get("base_url")
                or credentials.base_url
                or DEFAULT_CODEX_BASE_URL
            ).rstrip("/"),
            default_headers=codex_default_headers(credentials),
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )
        response, streamed_text = _stream_responses_response(
            client,
            self._responses_payload(messages),
        )
        content = _response_text(response) or streamed_text
        return AIMessage(content=content, response_metadata=_metadata(response))

    def _responses_payload(self, messages: list[BaseMessage]) -> dict[str, Any]:
        """把 LangChain messages 转成 Codex Responses API payload。"""

        instructions, input_items = _messages_to_responses_input(messages)
        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": input_items,
            "store": False,
        }
        temperature = self.bound_options.get("temperature", self.config.temperature)
        if temperature is not None:
            payload["temperature"] = temperature
        thinking = self.bound_options.get("thinking") or self.bound_options.get(
            "reasoning_effort",
            self.config.thinking,
        )
        if thinking is not None:
            payload["reasoning"] = {"effort": thinking}
        if instructions:
            payload["instructions"] = instructions
        return payload


def create_codex_chat_model(config: ModelProviderConfig) -> CodexChatModel:
    """根据统一配置创建 Codex 模型。"""

    return CodexChatModel(config)


def _stream_responses_response(client: Any, payload: dict[str, Any]) -> tuple[Any, str]:
    """调用 Codex streaming Responses API 并收集最终 response。

    ChatGPT/Codex 后端会拒绝非 stream 请求，所以正常路径必须走
    client.responses.stream。fallback 只保留给测试替身或兼容 OpenAI SDK 对象。
    """

    stream_factory = getattr(getattr(client, "responses", None), "stream", None)
    if not callable(stream_factory):
        response = client.responses.create(**payload)
        return response, ""

    text_parts: list[str] = []
    final_response: Any | None = None
    terminal_response: Any | None = None
    with stream_factory(**payload) as stream:
        for event in stream:
            event_type = str(getattr(event, "type", "") or "")
            if event_type in {"response.output_text.delta", "response.text.delta"}:
                delta = str(getattr(event, "delta", "") or "")
                if delta:
                    text_parts.append(delta)
                    emit_model_delta(delta)
            elif event_type in {"response.completed", "response.incomplete", "response.failed"}:
                terminal_response = getattr(event, "response", None) or terminal_response

        get_final_response = getattr(stream, "get_final_response", None)
        if callable(get_final_response):
            final_response = get_final_response()

    return final_response or terminal_response, "".join(text_parts)


def _messages_to_responses_input(
    messages: list[BaseMessage],
) -> tuple[str, list[dict[str, Any]]]:
    """拆分 system/developer instructions 和对话 input。"""

    instructions: list[str] = []
    input_items: list[dict[str, Any]] = []

    for message in messages:
        role = str(getattr(message, "type", "") or "")
        content = _content_text(getattr(message, "content", ""))
        if role in {"system", "developer"}:
            if content:
                instructions.append(content)
        elif role == "ai":
            if content:
                input_items.append({"role": "assistant", "content": content})
        else:
            input_items.append({"role": "user", "content": content})

    if not input_items:
        input_items.append({"role": "user", "content": ""})

    return "\n\n".join(part for part in instructions if part).strip(), input_items


def _content_text(content: Any) -> str:
    """把 LangChain content 转成纯文本。"""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part)
    return str(content) if content is not None else ""


def _response_text(response: Any) -> str:
    """从 Responses API 最终对象中提取 assistant 文本。"""

    output_text = str(getattr(response, "output_text", "") or "").strip()
    if output_text:
        return output_text

    parts: list[str] = []
    output = getattr(response, "output", None)
    if isinstance(output, list):
        for item in output:
            if str(getattr(item, "type", "") or "") != "message":
                continue
            content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for part in content:
                part_type = str(getattr(part, "type", "") or "")
                if part_type in {"output_text", "text"}:
                    text = getattr(part, "text", "")
                    if isinstance(text, str):
                        parts.append(text)

    return "".join(parts).strip()


def _metadata(response: Any) -> dict[str, Any]:
    """提取响应元数据，写入 AIMessage.response_metadata。"""

    metadata = {
        "model_provider": "codex",
        "response_id": getattr(response, "id", None),
        "status": getattr(response, "status", None),
        "usage": getattr(response, "usage", None),
    }
    return {key: value for key, value in metadata.items() if value not in (None, "")}
