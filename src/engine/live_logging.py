from __future__ import annotations

"""把完整消息流水实时写入 logging。"""

import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass

from engine.message_log import MessageLogEntry


STREAM_LOGGER_NAME = "pingan_ye.stream"
logger = logging.getLogger(__name__)
_current_stream: ContextVar[StreamContext | None] = ContextVar(
    "current_model_stream",
    default=None,
)


@dataclass(slots=True)
class StreamContext:
    """一次模型调用对应的流式输出状态。"""

    label: str
    started: bool = False
    streamed: bool = False


def configure_live_logging() -> None:
    """配置 CLI 实时日志，并压掉第三方 HTTP 请求日志。"""

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    configure_stream_logger()
    for logger_name in ("httpx", "httpcore", "openai"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def configure_stream_logger() -> None:
    """配置不自动换行的流式输出 logger。"""

    stream_logger = logging.getLogger(STREAM_LOGGER_NAME)
    stream_logger.setLevel(logging.INFO)
    stream_logger.propagate = False

    if any(
        getattr(handler, "_pingan_stream_handler", False)
        for handler in stream_logger.handlers
    ):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.terminator = ""
    handler._pingan_stream_handler = True  # type: ignore[attr-defined]
    stream_logger.addHandler(handler)


def set_stream_context(context: StreamContext) -> Token[StreamContext | None]:
    """设置当前模型调用的流式输出上下文。"""

    return _current_stream.set(context)


def reset_stream_context(token: Token[StreamContext | None]) -> None:
    """恢复上一个流式输出上下文。"""

    _current_stream.reset(token)


def emit_model_delta(delta: str) -> None:
    """把模型流式 delta 写入终端。"""

    context = _current_stream.get()
    if context is None or not delta:
        return

    configure_stream_logger()
    stream_logger = logging.getLogger(STREAM_LOGGER_NAME)
    if not context.started:
        stream_logger.info("%s：", context.label)
        context.started = True
    stream_logger.info("%s", delta)
    context.streamed = True


def finish_model_stream(context: StreamContext) -> None:
    """结束本次模型流式输出，补一个换行。"""

    if context.started:
        logging.getLogger(STREAM_LOGGER_NAME).info("\n")


def log_live_message(entry: MessageLogEntry) -> None:
    """把一条游戏消息格式化后写入终端日志。"""

    if entry.channel == "public":
        logger.info("%s：%s", entry.speaker, entry.content)
        return

    if _is_replayed_as_public_or_private_chat(entry):
        return

    label = _message_label(entry)
    if entry.role == "user":
        logger.info("%s 请求 %s 执行 %s", label, entry.recipient, entry.action)
        return

    logger.info("%s %s -> %s：%s", label, entry.speaker, entry.recipient, entry.content)


log_live_message.stream_model_output = True  # type: ignore[attr-defined]


def _is_replayed_as_public_or_private_chat(entry: MessageLogEntry) -> bool:
    """跳过随后会以公开消息或私聊消息再次出现的原始 agent 输出。"""

    if entry.channel != "agent" or entry.role != "assistant":
        return False
    return (
        entry.action in {"start_announcement", "announce"}
        or entry.action.startswith("speech:")
        or entry.action.startswith("wolf_discussion:")
        or entry.action.startswith("wolf_final_kill:")
    )


def _message_label(entry: MessageLogEntry) -> str:
    """生成终端实时输出的短标签。"""

    phase_names = {
        "setup": "开局",
        "night": "夜晚",
        "day": "白天",
        "system": "系统",
    }
    channel_names = {
        "agent": "agent",
        "tool": "工具",
        "wolf_chat": "狼人私聊",
        "public": "公开",
    }
    phase = phase_names.get(entry.phase, entry.phase)
    channel = channel_names.get(entry.channel, entry.channel)
    return f"[第 {entry.round_number} 轮/{phase}/{channel}]"
