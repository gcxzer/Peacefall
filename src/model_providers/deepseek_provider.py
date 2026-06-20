from __future__ import annotations

import os
from typing import Any

from model_providers.config import ModelProviderConfig, load_env_files


def create_deepseek_chat_model(config: ModelProviderConfig) -> Any:
    load_env_files()

    from langchain_deepseek import ChatDeepSeek

    kwargs: dict[str, Any] = {
        "model": config.model,
        "timeout": config.timeout,
        "max_retries": config.max_retries,
    }
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature

    api_key = (
        os.getenv("PINGAN_YE_DEEPSEEK_API_KEY", "").strip()
        or os.getenv("DEEPSEEK_API_KEY", "").strip()
        or os.getenv("API_KEY", "").strip()
    )
    if api_key:
        kwargs["api_key"] = api_key

    if config.options.get("base_url"):
        kwargs["base_url"] = config.options["base_url"]

    thinking_options = _deepseek_thinking_options(config.thinking)
    if thinking_options is not None:
        kwargs.update(thinking_options)

    return ChatDeepSeek(**kwargs)


def _deepseek_thinking_options(thinking: str | None) -> dict[str, Any] | None:
    """把统一 thinking 配置转换成 DeepSeek V4 的请求参数。"""

    if thinking is None:
        return None
    if thinking == "none":
        return {"extra_body": {"thinking": {"type": "disabled"}}}

    effort = "max" if thinking == "xhigh" else "high"
    return {
        "reasoning_effort": effort,
        "extra_body": {"thinking": {"type": "enabled"}},
    }
