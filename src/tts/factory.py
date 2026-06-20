from __future__ import annotations

"""Factory helpers for optional TTS message listeners."""

from pathlib import Path

from agents.factory import GameAgents
from tts.aliyun_qwen import (
    ALIYUN_QWEN_TTS_PROVIDER,
    AliyunQwenTtsConfig,
    AliyunQwenTtsListener,
    build_speaker_voice_specs,
)


def create_tts_listener(
    provider: str,
    *,
    agents: GameAgents,
    output_dir: str | Path,
    voice_cache_path: str | Path,
    include_judge: bool,
) -> AliyunQwenTtsListener | None:
    """Create the requested TTS listener."""

    if provider == "off":
        return None
    if provider != ALIYUN_QWEN_TTS_PROVIDER:
        raise ValueError(f"unsupported TTS provider: {provider}")

    config = AliyunQwenTtsConfig.from_env(
        output_dir=output_dir,
        voice_cache_path=voice_cache_path,
        player_speech_only=not include_judge,
    )
    return AliyunQwenTtsListener(
        config=config,
        speaker_voices=build_speaker_voice_specs(
            agents,
            include_judge=include_judge,
        ),
    )
