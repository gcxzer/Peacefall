from __future__ import annotations

from typing import Any

from model_providers.aliyun_provider import create_aliyun_chat_model
from model_providers.codex_provider import create_codex_chat_model
from model_providers.config import (
    ALIYUN_PROVIDER,
    CODEX_PROVIDER,
    DEEPSEEK_PROVIDER,
    OPENAI_PROVIDER,
    ModelProviderConfig,
)
from model_providers.deepseek_provider import create_deepseek_chat_model
from model_providers.openai_provider import create_openai_chat_model


def create_chat_model(config: ModelProviderConfig) -> Any:
    if config.provider == ALIYUN_PROVIDER:
        return create_aliyun_chat_model(config)
    if config.provider == OPENAI_PROVIDER:
        return create_openai_chat_model(config)
    if config.provider == DEEPSEEK_PROVIDER:
        return create_deepseek_chat_model(config)
    if config.provider == CODEX_PROVIDER:
        return create_codex_chat_model(config)
    raise ValueError(f"unsupported model provider: {config.provider}")
