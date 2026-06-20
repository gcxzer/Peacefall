from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


OPENAI_PROVIDER = "openai"
ALIYUN_PROVIDER = "aliyun"
DEEPSEEK_PROVIDER = "deepseek"
CODEX_PROVIDER = "codex"
DEFAULT_PROVIDER = ALIYUN_PROVIDER

DEFAULT_MODELS = {
    ALIYUN_PROVIDER: "qwen3.7-plus",
    OPENAI_PROVIDER: "gpt-5.4",
    DEEPSEEK_PROVIDER: None,
    CODEX_PROVIDER: "gpt-5.4",
}

DEFAULT_THINKING = {
    ALIYUN_PROVIDER: None,
    OPENAI_PROVIDER: None,
    DEEPSEEK_PROVIDER: None,
    CODEX_PROVIDER: "xhigh",
}

DEFAULT_TIMEOUTS = {
    ALIYUN_PROVIDER: 180.0,
    OPENAI_PROVIDER: 60.0,
    DEEPSEEK_PROVIDER: 60.0,
    CODEX_PROVIDER: 60.0,
}

DEFAULT_MAX_RETRIES = {
    ALIYUN_PROVIDER: 3,
    OPENAI_PROVIDER: 2,
    DEEPSEEK_PROVIDER: 2,
    CODEX_PROVIDER: 2,
}

PROVIDER_ALIASES = {
    "api-key": OPENAI_PROVIDER,
    "bailian": ALIYUN_PROVIDER,
    "dashscope": ALIYUN_PROVIDER,
    "qwen": ALIYUN_PROVIDER,
    ALIYUN_PROVIDER: ALIYUN_PROVIDER,
    "openai-api-key": OPENAI_PROVIDER,
    OPENAI_PROVIDER: OPENAI_PROVIDER,
    DEEPSEEK_PROVIDER: DEEPSEEK_PROVIDER,
    "deep-seek": DEEPSEEK_PROVIDER,
    CODEX_PROVIDER: CODEX_PROVIDER,
    "codex-oauth": CODEX_PROVIDER,
    "openai-codex": CODEX_PROVIDER,
}


@dataclass(frozen=True, slots=True)
class ModelProviderConfig:
    provider: str = DEFAULT_PROVIDER
    model: str = ""
    timeout: float = 60.0
    max_retries: int = 2
    temperature: float | None = None
    thinking: str | None = DEFAULT_THINKING[DEFAULT_PROVIDER]
    use_responses_api: bool = True
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(
        cls,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        thinking: str | None = None,
    ) -> ModelProviderConfig:
        load_env_files()
        resolved_provider = normalize_provider(
            provider
            or os.getenv("PINGAN_YE_PROVIDER", "").strip()
            or os.getenv("LLM_PROVIDER", "").strip()
            or DEFAULT_PROVIDER
        )

        timeout = DEFAULT_TIMEOUTS[resolved_provider]
        timeout_text = os.getenv("PINGAN_YE_LLM_TIMEOUT", "").strip()
        if resolved_provider == ALIYUN_PROVIDER:
            timeout_text = (
                os.getenv("ALIYUN_LLM_TIMEOUT", "").strip()
                or os.getenv("DASHSCOPE_LLM_TIMEOUT", "").strip()
                or timeout_text
            )
        if timeout_text:
            try:
                timeout = float(timeout_text)
            except ValueError:
                pass

        max_retries = DEFAULT_MAX_RETRIES[resolved_provider]
        max_retries_text = os.getenv("PINGAN_YE_LLM_MAX_RETRIES", "").strip()
        if resolved_provider == ALIYUN_PROVIDER:
            max_retries_text = (
                os.getenv("ALIYUN_LLM_MAX_RETRIES", "").strip()
                or os.getenv("DASHSCOPE_LLM_MAX_RETRIES", "").strip()
                or max_retries_text
            )
        if max_retries_text:
            try:
                max_retries = int(max_retries_text)
            except ValueError:
                pass

        resolved_temperature = temperature
        temperature_text = os.getenv("PINGAN_YE_LLM_TEMPERATURE", "").strip()
        if resolved_temperature is None and temperature_text:
            try:
                resolved_temperature = float(temperature_text)
            except ValueError:
                pass

        use_responses_api = True
        use_responses_api_text = os.getenv("PINGAN_YE_USE_RESPONSES_API", "").strip().lower()
        if use_responses_api_text:
            use_responses_api = use_responses_api_text in {"1", "true", "yes", "on"}

        return cls(
            provider=resolved_provider,
            model=_resolve_model(resolved_provider, model),
            timeout=timeout,
            max_retries=max_retries,
            temperature=resolved_temperature,
            thinking=(
                _normalize_thinking(thinking)
                if thinking is not None
                else _provider_thinking_from_env(resolved_provider)
            )
            or DEFAULT_THINKING[resolved_provider],
            use_responses_api=use_responses_api,
            options=_provider_options_from_env(resolved_provider),
        )


def normalize_provider(provider: str) -> str:
    key = provider.strip().lower().replace("_", "-")
    normalized = PROVIDER_ALIASES.get(key)
    if not normalized:
        raise ValueError(f"unsupported model provider: {provider}")
    return normalized


def load_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    for path in (Path(".env.local"), Path(".env")):
        if path.exists() and path.is_file():
            load_dotenv(path, override=False)


def _provider_model_from_env(provider: str) -> str:
    if provider == ALIYUN_PROVIDER:
        return (
            os.getenv("ALIYUN_MODEL", "").strip()
            or os.getenv("DASHSCOPE_MODEL", "").strip()
            or os.getenv("PINGAN_YE_MODEL", "").strip()
        )
    if provider == DEEPSEEK_PROVIDER:
        return (
            os.getenv("PINGAN_YE_DEEPSEEK_MODEL", "").strip()
            or os.getenv("DEEPSEEK_MODEL", "").strip()
            or os.getenv("MODEL_NAME", "").strip()
            or os.getenv("PINGAN_YE_MODEL", "").strip()
        )
    if provider == CODEX_PROVIDER:
        return os.getenv("CODEX_MODEL", "").strip() or os.getenv(
            "PINGAN_YE_MODEL",
            "",
        ).strip()
    return os.getenv("OPENAI_MODEL", "").strip() or os.getenv(
        "PINGAN_YE_MODEL",
        "",
    ).strip()


def _resolve_model(provider: str, explicit_model: str | None) -> str:
    model = (
        explicit_model
        or _provider_model_from_env(provider)
        or DEFAULT_MODELS[provider]
    )
    if not model:
        raise ValueError(
            f"{provider} model is not configured. Set a provider-specific model "
            "or PINGAN_YE_MODEL in .env."
        )
    return model


def _provider_thinking_from_env(provider: str) -> str | None:
    if provider == CODEX_PROVIDER:
        return _normalize_thinking(
            os.getenv("CODEX_THINKING", "").strip()
            or os.getenv("PINGAN_YE_THINKING", "").strip()
        )
    if provider == OPENAI_PROVIDER:
        return _normalize_thinking(
            os.getenv("OPENAI_REASONING_EFFORT", "").strip()
            or os.getenv("OPENAI_THINKING", "").strip()
            or os.getenv("PINGAN_YE_THINKING", "").strip()
        )
    if provider == DEEPSEEK_PROVIDER:
        return os.getenv("DEEPSEEK_THINKING", "").strip() or None
    if provider == ALIYUN_PROVIDER:
        return os.getenv("ALIYUN_THINKING", "").strip() or None
    return _normalize_thinking(os.getenv("PINGAN_YE_THINKING", "").strip())


def _provider_options_from_env(provider: str) -> dict[str, Any]:
    options: dict[str, Any] = {}

    if provider == CODEX_PROVIDER:
        auth_path = os.getenv("PINGAN_YE_CODEX_AUTH_PATH", "").strip() or os.getenv(
            "CODEX_AUTH_PATH",
            "",
        ).strip()
        if auth_path:
            options["auth_path"] = auth_path
        base_url = os.getenv("PINGAN_YE_CODEX_BASE_URL", "").strip()
        if base_url:
            options["base_url"] = base_url

    if provider == DEEPSEEK_PROVIDER:
        base_url = (
            os.getenv("PINGAN_YE_DEEPSEEK_BASE_URL", "").strip()
            or os.getenv("DEEPSEEK_BASE_URL", "").strip()
            or os.getenv("BASE_URL", "").strip()
        )
        if base_url:
            options["base_url"] = base_url

    if provider == ALIYUN_PROVIDER:
        options["base_url"] = (
            os.getenv("ALIYUN_BASE_URL", "").strip()
            or os.getenv("DASHSCOPE_BASE_URL", "").strip()
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        enable_thinking = os.getenv("ALIYUN_ENABLE_THINKING", "").strip().lower()
        options["enable_thinking"] = enable_thinking in {"1", "true", "yes", "on"}

    return options


def _normalize_thinking(value: str | None) -> str | None:
    if value is None:
        return None
    thinking = value.strip().lower().replace("_", "-").replace(" ", "-")
    if not thinking:
        return None

    aliases = {
        "none": "none",
        "off": "none",
        "min": "minimal",
        "minimum": "minimal",
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "med": "medium",
        "mid": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "x-high": "xhigh",
        "extra-high": "xhigh",
        "highest": "xhigh",
        "max": "xhigh",
        "maximum": "xhigh",
    }
    normalized = aliases.get(thinking)
    if not normalized:
        raise ValueError(
            "unsupported thinking level: "
            f"{value!r}. Use none, minimal, low, medium, high, or xhigh."
        )
    return normalized
