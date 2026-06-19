from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


OPENAI_PROVIDER = "openai"
DEEPSEEK_PROVIDER = "deepseek"
CODEX_PROVIDER = "codex"
DEFAULT_PROVIDER = DEEPSEEK_PROVIDER

DEFAULT_MODELS = {
    OPENAI_PROVIDER: "gpt-5.4",
    DEEPSEEK_PROVIDER: None,
    CODEX_PROVIDER: "gpt-5.4",
}

DEFAULT_THINKING = {
    OPENAI_PROVIDER: None,
    DEEPSEEK_PROVIDER: None,
    CODEX_PROVIDER: "xhigh",
}

PROVIDER_ALIASES = {
    "api-key": OPENAI_PROVIDER,
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
            or _env_text("PINGAN_YE_PROVIDER")
            or _env_text("LLM_PROVIDER")
            or DEFAULT_PROVIDER
        )
        return cls(
            provider=resolved_provider,
            model=_resolve_model(resolved_provider, model),
            timeout=_env_float("PINGAN_YE_LLM_TIMEOUT", 60.0),
            max_retries=_env_int("PINGAN_YE_LLM_MAX_RETRIES", 2),
            temperature=(
                temperature
                if temperature is not None
                else _env_optional_float("PINGAN_YE_LLM_TEMPERATURE")
            ),
            thinking=(
                _normalize_thinking(thinking)
                if thinking is not None
                else _provider_thinking_from_env(resolved_provider)
            )
            or DEFAULT_THINKING[resolved_provider],
            use_responses_api=_env_bool("PINGAN_YE_USE_RESPONSES_API", True),
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
    if provider == DEEPSEEK_PROVIDER:
        return (
            _env_text("PINGAN_YE_DEEPSEEK_MODEL")
            or _env_text("DEEPSEEK_MODEL")
            or _env_text("MODEL_NAME")
            or _env_text("PINGAN_YE_MODEL")
        )
    if provider == CODEX_PROVIDER:
        return _env_text("CODEX_MODEL") or _env_text("PINGAN_YE_MODEL")
    return _env_text("OPENAI_MODEL") or _env_text("PINGAN_YE_MODEL")


def _resolve_model(provider: str, explicit_model: str | None) -> str:
    model = (
        explicit_model
        or _provider_model_from_env(provider)
        or DEFAULT_MODELS[provider]
    )
    if not model:
        raise ValueError(
            "DeepSeek model is not configured. Set MODEL_NAME, DEEPSEEK_MODEL, "
            "PINGAN_YE_DEEPSEEK_MODEL, or PINGAN_YE_MODEL in .env."
        )
    return model


def _provider_thinking_from_env(provider: str) -> str | None:
    if provider == CODEX_PROVIDER:
        return _normalize_thinking(
            _env_text("CODEX_THINKING") or _env_text("PINGAN_YE_THINKING")
        )
    if provider == OPENAI_PROVIDER:
        return _normalize_thinking(
            _env_text("OPENAI_REASONING_EFFORT")
            or _env_text("OPENAI_THINKING")
            or _env_text("PINGAN_YE_THINKING")
        )
    if provider == DEEPSEEK_PROVIDER:
        return _env_text("DEEPSEEK_THINKING") or None
    return _normalize_thinking(_env_text("PINGAN_YE_THINKING"))


def _provider_options_from_env(provider: str) -> dict[str, Any]:
    options: dict[str, Any] = {}

    if provider == CODEX_PROVIDER:
        auth_path = _env_text("PINGAN_YE_CODEX_AUTH_PATH") or _env_text(
            "CODEX_AUTH_PATH"
        )
        if auth_path:
            options["auth_path"] = auth_path
        base_url = _env_text("PINGAN_YE_CODEX_BASE_URL")
        if base_url:
            options["base_url"] = base_url

    if provider == DEEPSEEK_PROVIDER:
        base_url = _env_text("PINGAN_YE_DEEPSEEK_BASE_URL") or _env_text(
            "DEEPSEEK_BASE_URL"
        ) or _env_text("BASE_URL")
        if base_url:
            options["base_url"] = base_url

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


def _env_text(name: str) -> str:
    return os.environ.get(name, "").strip()


def _env_float(name: str, default: float) -> float:
    value = _env_text(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_optional_float(name: str) -> float | None:
    value = _env_text(name)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _env_int(name: str, default: int) -> int:
    value = _env_text(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env_text(name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}
