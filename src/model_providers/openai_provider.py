from __future__ import annotations

import os
from typing import Any

from model_providers.config import ModelProviderConfig, load_env_files


def create_openai_chat_model(config: ModelProviderConfig) -> Any:
    load_env_files()

    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": config.model,
        "timeout": config.timeout,
        "max_retries": config.max_retries,
    }
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if config.thinking is not None:
        kwargs["reasoning_effort"] = config.thinking
    if config.use_responses_api:
        kwargs["use_responses_api"] = True

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        kwargs["api_key"] = api_key

    return ChatOpenAI(**kwargs)
