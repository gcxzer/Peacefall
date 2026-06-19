from __future__ import annotations

"""跨版型复用的轻量规则和文本工具。"""

from collections import Counter
from typing import Iterable


def format_player_ids(player_ids: Iterable[int]) -> str:
    """把玩家编号列表格式化为中文展示文本。"""

    ids = list(player_ids)
    if not ids:
        return "无"
    return "、".join(f"{player_id} 号玩家" for player_id in ids)


def plurality_winner(targets: Iterable[int], *, tie_returns_none: bool) -> int | None:
    """计算多数票胜出目标。"""

    target_list = list(targets)
    if not target_list:
        return None

    counts = Counter(target_list)
    highest = max(counts.values())
    winners = [target_id for target_id, count in counts.items() if count == highest]
    if len(winners) == 1:
        return winners[0]
    if tie_returns_none:
        return None
    return sorted(winners)[0]


def valid_target(value: object, valid_targets: list[int]) -> int | None:
    """校验模型给出的玩家编号是否是合法目标。"""

    if value is None:
        return None
    try:
        target_id = int(value)
    except (TypeError, ValueError):
        return None
    return target_id if target_id in valid_targets else None
