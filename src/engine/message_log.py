from __future__ import annotations

"""完整消息流水的数据结构、文件写入和记录入口。"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from engine.state import GameState


DEFAULT_MESSAGE_LOG_DIR = Path("logs/messages")
ENGINE_SPEAKER = "游戏引擎"
JUDGE_SPEAKER = "法官"
SYSTEM_SPEAKER = "系统"


@dataclass(frozen=True, slots=True)
class MessageLogEntry:
    """完整消息流水的一行 JSONL 记录。"""

    index: int  # 这条消息在本局完整消息流水里的序号，从 1 开始递增。
    round_number: int  # 产生这条消息时所在的轮次；setup 阶段也会记为第 1 轮。
    channel: str  # 消息通道，例如 public 公开消息、agent 模型调用、tool 工具结果。
    phase: str  # 游戏阶段，例如 setup 开局、night 夜晚、day 白天、system 系统结束。
    action: str  # 触发这条消息的具体动作，例如发言、投票、查验、选择起始玩家。
    speaker: str  # 消息发送方，可以是法官、玩家 agent、游戏引擎或工具名。
    recipient: str  # 消息接收方，可以是 public、某个 agent 或游戏引擎。
    role: str  # 在消息协议里的角色，例如 user、assistant、public、tool。
    content: str  # 消息正文；agent 输入输出、公开发言、工具返回都会写在这里。


@dataclass(frozen=True, slots=True)
class GameRecord:
    """一局游戏结束后返回给调用方的完整结果。"""

    messages: list[MessageLogEntry]
    message_log_path: Path | None = None


def new_message_log_path(log_dir: Path) -> Path:
    """创建本局专属的 JSONL 消息日志文件路径。"""

    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = log_dir / f"messages-{timestamp}.jsonl"
    counter = 2
    while path.exists():
        path = log_dir / f"messages-{timestamp}-{counter}.jsonl"
        counter += 1
    path.touch()
    return path


def append_message_log_file(path: Path, message: MessageLogEntry) -> None:
    """把单条消息以 JSONL 格式追加写入日志文件。"""

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(asdict(message), ensure_ascii=False) + "\n")


def record_public(
    state: GameState,
    speaker: str,
    content: str,
    *,
    phase: str,
    action: str,
) -> None:
    """记录所有玩家都可见的公开消息。"""

    content = _strip_redundant_speaker_prefix(speaker, content.strip())
    state.public_log.append(f"{speaker}：{content}")
    record_message(
        state,
        channel="public",
        phase=phase,
        action=action,
        speaker=speaker,
        recipient="public",
        role="public",
        content=content,
    )


def record_message(
    state: GameState,
    *,
    channel: str,
    phase: str,
    action: str,
    speaker: str,
    recipient: str,
    role: str,
    content: str,
) -> MessageLogEntry:
    """记录一条完整消息流水。"""

    message = MessageLogEntry(
        index=len(state.message_log) + 1,
        round_number=state.round_number,
        channel=channel,
        phase=phase,
        action=action,
        speaker=speaker,
        recipient=recipient,
        role=role,
        content=content.strip(),
    )
    state.message_log.append(message)
    if state.message_log_path is not None:
        append_message_log_file(state.message_log_path, message)
    if state.on_message is not None and _should_notify_message(state, message):
        state.on_message(message)
    return message


def _strip_redundant_speaker_prefix(speaker: str, content: str) -> str:
    """去掉模型正文里重复写出的发言人前缀。"""

    for prefix in (f"{speaker}：", f"{speaker}:"):
        if content.startswith(prefix):
            return content[len(prefix):].lstrip()
    return content


def _should_notify_message(state: GameState, message: MessageLogEntry) -> bool:
    """判断这条消息是否需要实时通知外部监听器。"""

    if (message.round_number, message.phase, message.action) not in state.streamed_actions:
        return True
    return message.channel not in {"agent", "public", "wolf_chat"}
