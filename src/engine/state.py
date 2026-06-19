from __future__ import annotations

"""不同版型都可以复用的基础游戏状态。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from engine.assignments import GameAssignment
from engine.message_log import MessageLogEntry
from engine.rules import format_player_ids
from roles import Camp, Role, role_camp


PUBLIC_LOG_LIMIT = 30


@dataclass(slots=True)
class GameState:
    """一局游戏的可变基础状态。"""

    assignment: GameAssignment
    round_number: int = 1
    alive_player_ids: set[int] = field(default_factory=set)
    public_log: list[str] = field(default_factory=list)
    private_notes: dict[int, list[str]] = field(default_factory=dict)
    message_log: list[MessageLogEntry] = field(default_factory=list)
    message_log_path: Path | None = None
    on_message: Callable[[MessageLogEntry], None] | None = None
    streamed_actions: set[tuple[int, str, str]] = field(default_factory=set)
    game_over: bool = False
    winner: Camp | None = None
    win_reason: str = ""

    def __post_init__(self) -> None:
        """根据身份分配补齐开局状态。"""

        if not self.alive_player_ids:
            self.alive_player_ids = set(self.assignment.assignments)
        if not self.private_notes:
            self.private_notes = {
                player_id: [] for player_id in self.assignment.assignments
            }

    def role_of(self, player_id: int) -> Role:
        """返回指定玩家的身份。"""

        return self.assignment.assignments[player_id].role

    def camp_of(self, player_id: int) -> Camp:
        """返回指定玩家所属阵营。"""

        return role_camp(self.role_of(player_id))

    def is_alive(self, player_id: int) -> bool:
        """判断指定玩家是否仍然存活。"""

        return player_id in self.alive_player_ids

    def alive_players_text(self) -> str:
        """把当前存活玩家格式化成给 agent 阅读的中文文本。"""

        return format_player_ids(sorted(self.alive_player_ids))

    def public_context(self) -> str:
        """生成所有 agent 都可以看到的公共上下文。"""

        recent_log = "\n".join(
            f"- {item}" for item in self.public_log[-PUBLIC_LOG_LIMIT:]
        )
        return (
            f"当前轮次：第 {self.round_number} 轮\n"
            f"存活玩家：{self.alive_players_text()}\n"
            f"公开记录：\n{recent_log if recent_log else '- 暂无'}"
        )

    def player_context(self, player_id: int) -> str:
        """生成单个玩家行动前可见的上下文。"""

        notes = "\n".join(f"- {item}" for item in self.private_notes[player_id])
        return (
            f"{self.public_context()}\n\n"
            f"你的私有记录：\n{notes if notes else '- 暂无'}"
        )
