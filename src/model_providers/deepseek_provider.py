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
        os.environ.get("PINGAN_YE_DEEPSEEK_API_KEY", "").strip()
        or os.environ.get("DEEPSEEK_API_KEY", "").strip()
        or os.environ.get("API_KEY", "").strip()
    )
    if api_key:
        kwargs["api_key"] = api_key

    if config.options.get("base_url"):
        kwargs["base_url"] = config.options["base_url"]

    if config.thinking is not None:
        kwargs["extra_body"] = {"thinking": config.thinking}

    return ChatDeepSeek(**kwargs)
