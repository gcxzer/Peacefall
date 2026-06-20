from __future__ import annotations

"""Aliyun Bailian Qwen TTS integration."""

import base64
import hashlib
import json
import logging
import os
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agents.factory import GameAgents
from agents.profiles import AgentProfile
from engine.message_log import JUDGE_SPEAKER, MessageLogEntry
from model_providers.config import load_env_files


logger = logging.getLogger(__name__)

ALIYUN_QWEN_TTS_PROVIDER = "aliyun-qwen"
DEFAULT_TTS_MODEL = "qwen3-tts-vd-2026-01-26"
DEFAULT_VOICE_DESIGN_MODEL = "qwen-voice-design"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_OUTPUT_DIR = Path("logs/audio")
DEFAULT_VOICE_CACHE_PATH = Path("logs/aliyun-qwen-voices.json")
DEFAULT_LANGUAGE_TYPE = "Chinese"
DEFAULT_RESPONSE_FORMAT = "wav"


@dataclass(frozen=True, slots=True)
class SpeakerVoiceSpec:
    """Voice-design prompt and preview text for one speaker."""

    name: str
    voice_prompt: str
    preview_text: str


@dataclass(frozen=True, slots=True)
class AliyunQwenTtsConfig:
    """Configuration for Aliyun Bailian Qwen TTS."""
    api_key: str
    model: str = DEFAULT_TTS_MODEL
    voice_design_model: str = DEFAULT_VOICE_DESIGN_MODEL
    base_url: str = DEFAULT_BASE_URL
    language_type: str = DEFAULT_LANGUAGE_TYPE
    output_dir: Path = DEFAULT_OUTPUT_DIR
    voice_cache_path: Path = DEFAULT_VOICE_CACHE_PATH
    response_format: str = DEFAULT_RESPONSE_FORMAT
    sample_rate: int = 24_000
    timeout: float = 90.0
    max_workers: int = 2
    player_speech_only: bool = True

    @classmethod
    def from_env(
        cls,
        *,
        output_dir: str | Path = DEFAULT_OUTPUT_DIR,
        voice_cache_path: str | Path = DEFAULT_VOICE_CACHE_PATH,
        player_speech_only: bool = True,
    ) -> AliyunQwenTtsConfig:
        """Load TTS config from environment variables."""

        load_env_files()
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY is required when --tts aliyun-qwen is enabled.")

        sample_rate = 24_000
        sample_rate_text = os.getenv("ALIYUN_TTS_SAMPLE_RATE", "").strip()
        if sample_rate_text:
            try:
                sample_rate = int(sample_rate_text)
            except ValueError:
                pass

        timeout = 90.0
        timeout_text = os.getenv("ALIYUN_TTS_TIMEOUT", "").strip()
        if timeout_text:
            try:
                timeout = float(timeout_text)
            except ValueError:
                pass

        max_workers = 2
        max_workers_text = os.getenv("ALIYUN_TTS_MAX_WORKERS", "").strip()
        if max_workers_text:
            try:
                max_workers = int(max_workers_text)
            except ValueError:
                pass

        return cls(
            api_key=api_key,
            output_dir=Path(output_dir),
            voice_cache_path=Path(voice_cache_path),
            model=os.getenv("ALIYUN_TTS_MODEL", "").strip()
            or DEFAULT_TTS_MODEL,
            voice_design_model=(
                os.getenv("ALIYUN_VOICE_DESIGN_MODEL", "").strip()
                or DEFAULT_VOICE_DESIGN_MODEL
            ),
            base_url=(
                os.getenv("ALIYUN_TTS_BASE_URL", "").strip()
                or DEFAULT_BASE_URL
            ).rstrip("/"),
            language_type=(
                os.getenv("ALIYUN_TTS_LANGUAGE_TYPE", "").strip()
                or DEFAULT_LANGUAGE_TYPE
            ),
            response_format=(
                os.getenv("ALIYUN_TTS_RESPONSE_FORMAT", "").strip()
                or DEFAULT_RESPONSE_FORMAT
            ),
            sample_rate=sample_rate,
            timeout=timeout,
            max_workers=max_workers,
            player_speech_only=player_speech_only,
        )


class AliyunQwenTtsListener:
    """Background message listener that writes game speech to audio files."""

    def __init__(
        self,
        *,
        config: AliyunQwenTtsConfig,
        speaker_voices: dict[str, SpeakerVoiceSpec],
    ) -> None:
        self.config = config
        self.speaker_voices = speaker_voices
        self.run_output_dir = config.output_dir / datetime.now().strftime(
            "%Y%m%d-%H%M%S-%f"
        )
        self.run_output_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.run_output_dir / "manifest.jsonl"
        self._client = _AliyunQwenTtsClient(config)
        self._voice_cache = _VoiceCache(config.voice_cache_path)
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, config.max_workers),
            thread_name_prefix="aliyun-qwen-tts",
        )
        self._futures: list[Future[Path | None]] = []
        self._manifest_lock = threading.Lock()

    def __call__(self, entry: MessageLogEntry) -> None:
        if not self._should_synthesize(entry):
            return

        future = self._executor.submit(self._synthesize_entry, entry)
        self._futures.append(future)

    def close(self) -> None:
        """Wait for queued TTS jobs and surface failures in the log."""

        self._executor.shutdown(wait=False)
        synthesized = 0
        for future in as_completed(self._futures):
            try:
                if future.result() is not None:
                    synthesized += 1
            except Exception:
                logger.exception("TTS 生成失败")
        self._executor.shutdown(wait=True)
        if synthesized:
            logger.info("tts audio: %s", self.run_output_dir)

    def _should_synthesize(self, entry: MessageLogEntry) -> bool:
        if entry.channel != "public" or not entry.content.strip():
            return False
        if self.config.player_speech_only and not entry.action.startswith("speech:"):
            return False
        return entry.speaker in self.speaker_voices

    def _synthesize_entry(self, entry: MessageLogEntry) -> Path | None:
        voice_spec = self.speaker_voices[entry.speaker]
        voice_id = self._voice_cache.get_or_create(
            speaker=voice_spec.name,
            voice_prompt=voice_spec.voice_prompt,
            model=self.config.model,
            create_voice=lambda preferred_name: self._client.create_voice(
                voice_spec,
                preferred_name=preferred_name,
            ),
        )

        output_path = self.run_output_dir / _audio_filename(
            entry,
            self.config.response_format,
        )
        if not output_path.exists():
            self._client.synthesize_to_file(
                text=entry.content,
                voice=voice_id,
                output_path=output_path,
            )
        self._append_manifest(entry, voice_spec, voice_id, output_path)
        return output_path

    def _append_manifest(
        self,
        entry: MessageLogEntry,
        voice_spec: SpeakerVoiceSpec,
        voice_id: str,
        output_path: Path,
    ) -> None:
        payload = {
            "message_index": entry.index,
            "round_number": entry.round_number,
            "phase": entry.phase,
            "action": entry.action,
            "speaker": entry.speaker,
            "voice_name": voice_spec.name,
            "voice_id": voice_id,
            "audio_path": str(output_path),
            "content": entry.content,
        }
        with self._manifest_lock:
            with self.manifest_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(payload, ensure_ascii=False) + "\n")


class _AliyunQwenTtsClient:
    """Small HTTP client for the DashScope Qwen TTS endpoints."""

    def __init__(self, config: AliyunQwenTtsConfig) -> None:
        self.config = config

    def create_voice(
        self,
        voice_spec: SpeakerVoiceSpec,
        *,
        preferred_name: str,
    ) -> str:
        payload = {
            "model": self.config.voice_design_model,
            "input": {
                "action": "create",
                "target_model": self.config.model,
                "preferred_name": preferred_name,
                "voice_prompt": voice_spec.voice_prompt,
                "preview_text": voice_spec.preview_text,
            },
            "parameters": {
                "sample_rate": self.config.sample_rate,
                "response_format": self.config.response_format,
            },
        }
        result = self._post_json("/services/audio/tts/customization", payload)
        try:
            return str(result["output"]["voice"])
        except KeyError as exc:
            raise RuntimeError(f"无法解析百炼音色创建响应: {result}") from exc

    def synthesize_to_file(
        self,
        *,
        text: str,
        voice: str,
        output_path: Path,
    ) -> None:
        payload = {
            "model": self.config.model,
            "input": {
                "text": text,
                "voice": voice,
                "language_type": self.config.language_type,
            },
        }
        result = self._post_json(
            "/services/aigc/multimodal-generation/generation",
            payload,
        )
        audio = result.get("output", {}).get("audio", {})
        output_path.parent.mkdir(parents=True, exist_ok=True)

        audio_data = str(audio.get("data") or "")
        if audio_data:
            output_path.write_bytes(base64.b64decode(audio_data))
            return

        audio_url = str(audio.get("url") or "")
        if not audio_url:
            raise RuntimeError(f"百炼 TTS 响应里没有音频 URL 或 data: {result}")
        self._download_file(audio_url, output_path)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.base_url}{path}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"百炼请求失败 {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"无法连接百炼 TTS 服务: {exc}") from exc

        result = json.loads(response_body)
        status_code = int(result.get("status_code") or 200)
        if status_code >= 400 or result.get("code"):
            raise RuntimeError(f"百炼请求失败: {result}")
        return result

    def _download_file(self, url: str, output_path: Path) -> None:
        try:
            with urlopen(url, timeout=self.config.timeout) as response:
                output_path.write_bytes(response.read())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"下载 TTS 音频失败 {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"无法下载 TTS 音频: {exc}") from exc


class _VoiceCache:
    """Thread-safe cache for Aliyun custom voice IDs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def get_or_create(
        self,
        *,
        speaker: str,
        voice_prompt: str,
        model: str,
        create_voice: Any,
    ) -> str:
        key = _voice_cache_key(speaker, voice_prompt, model)
        with self._lock:
            data = self._read()
            voices = data.setdefault("voices", {})
            cached = voices.get(key)
            if isinstance(cached, dict) and cached.get("voice_id"):
                return str(cached["voice_id"])

            voice_id = create_voice(_preferred_voice_name(speaker, key))
            voices[key] = {
                "speaker": speaker,
                "model": model,
                "voice_id": voice_id,
                "voice_prompt_hash": hashlib.sha256(
                    voice_prompt.encode("utf-8")
                ).hexdigest(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._write(data)
            return voice_id

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "voices": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def build_speaker_voice_specs(
    agents: GameAgents,
    *,
    include_judge: bool = False,
) -> dict[str, SpeakerVoiceSpec]:
    """Build speaker-to-voice specs for the selected players."""

    specs: dict[str, SpeakerVoiceSpec] = {}
    for player_id, profile in agents.player_profiles.items():
        spec = _voice_spec_from_profile(profile)
        specs[profile.display_name] = spec
        specs[agents.player_label(player_id)] = spec

    if include_judge:
        specs[JUDGE_SPEAKER] = SpeakerVoiceSpec(
            name=JUDGE_SPEAKER,
            voice_prompt=(
                "沉稳清晰的中文普通话主持人声音，语速平稳，吐字清楚，"
                "情绪克制，适合狼人杀法官宣读流程和结果。"
            ),
            preview_text="天黑请闭眼。现在进入夜晚阶段，请各位玩家保持安静。",
        )
    return specs


def _voice_spec_from_profile(profile: AgentProfile) -> SpeakerVoiceSpec:
    human = profile.digital_human
    if human.has_structured_profile:
        voice_prompt = "\n".join(
            part
            for part in (
                "中文普通话，适合狼人杀桌游角色发言。",
                _voice_prompt_line("角色原型", human.core_identity.get("archetype")),
                _voice_prompt_line("整体气质", human.core_identity.get("vibe")),
                _voice_prompt_line(
                    "核心动机",
                    human.core_identity.get("core_motivation"),
                ),
                _voice_prompt_line(
                    "场上存在感",
                    human.behavioral_traits.get("table_presence"),
                ),
                _voice_prompt_line(
                    "说话风格",
                    human.linguistic_profile.get("speaking_style"),
                ),
                _voice_prompt_list(
                    "口头习惯",
                    human.linguistic_profile.get("speech_habits"),
                ),
                "声音要求：自然、清晰、有角色辨识度；不要夸张表演，不要模仿名人。",
            )
            if part
        )
        examples = human.speech_example_texts()
        preview_text = (
            examples[0]
            if examples
            else f"我是{profile.display_name}，这一轮我先听大家发言，再补关键细节。"
        )
        return SpeakerVoiceSpec(
            name=profile.display_name,
            voice_prompt=voice_prompt[:2048],
            preview_text=preview_text,
        )

    voice_prompt = "\n".join(
        part
        for part in (
            "中文普通话，适合狼人杀桌游角色发言。",
            f"角色气质：{human.summary}",
            f"场上存在感：{human.table_presence}",
            f"说话风格：{human.speaking_style}",
            _join_optional("口头习惯", human.speech_habits),
            "声音要求：自然、清晰、有角色辨识度；不要夸张表演，不要模仿名人。",
        )
        if part
    )
    preview_text = (
        human.speech_examples[0]
        if human.speech_examples
        else f"我是{profile.display_name}，这一轮我先听大家发言，再补关键细节。"
    )
    return SpeakerVoiceSpec(
        name=profile.display_name,
        voice_prompt=voice_prompt[:2048],
        preview_text=preview_text,
    )


def _join_optional(label: str, values: list[str]) -> str:
    if not values:
        return ""
    return f"{label}：" + "；".join(values)


def _voice_prompt_line(label: str, value: Any) -> str:
    text = str(value or "").strip()
    return f"{label}：{text}" if text else ""


def _voice_prompt_list(label: str, value: Any) -> str:
    if not isinstance(value, list):
        return ""
    items = [str(item).strip() for item in value if str(item).strip()]
    return f"{label}：" + "；".join(items) if items else ""


def _voice_cache_key(speaker: str, voice_prompt: str, model: str) -> str:
    return hashlib.sha256(
        f"{model}\n{speaker}\n{voice_prompt}".encode("utf-8")
    ).hexdigest()[:16]


def _preferred_voice_name(speaker: str, key: str) -> str:
    return f"pinganye_{key[:7]}"


def _audio_filename(entry: MessageLogEntry, extension: str) -> str:
    return (
        f"{entry.index:04d}-"
        f"{_safe_filename_token(entry.speaker)}-"
        f"{_safe_filename_token(entry.action)}."
        f"{extension.lstrip('.')}"
    )


def _safe_filename_token(value: str) -> str:
    token = "".join(char if char.isalnum() else "-" for char in value).strip("-")
    token = re.sub(r"-+", "-", token)
    return token[:80] or "message"
