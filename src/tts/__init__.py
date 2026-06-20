"""Text-to-speech integrations for game messages."""

from tts.aliyun_qwen import (
    ALIYUN_QWEN_TTS_PROVIDER,
    AliyunQwenTtsConfig,
    AliyunQwenTtsListener,
    SpeakerVoiceSpec,
    build_speaker_voice_specs,
)
from tts.factory import create_tts_listener

__all__ = [
    "ALIYUN_QWEN_TTS_PROVIDER",
    "AliyunQwenTtsConfig",
    "AliyunQwenTtsListener",
    "SpeakerVoiceSpec",
    "build_speaker_voice_specs",
    "create_tts_listener",
]
