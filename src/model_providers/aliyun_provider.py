from __future__ import annotations

import os
from typing import Any

from model_providers.config import ModelProviderConfig, load_env_files


def create_aliyun_chat_model(config: ModelProviderConfig) -> Any:
    load_env_files()

    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": config.model,
        "timeout": config.timeout,
        "max_retries": config.max_retries,
        "base_url": config.options["base_url"],
        "extra_body": {
            "enable_thinking": bool(config.options.get("enable_thinking")),
        },
    }
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature

    api_key = (
        os.getenv("DASHSCOPE_API_KEY", "").strip()
        or os.getenv("ALIYUN_API_KEY", "").strip()
    )
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is required when using the aliyun provider.")
    kwargs["api_key"] = api_key

    return ChatOpenAI(**kwargs)
