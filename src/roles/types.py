from __future__ import annotations

from enum import Enum


class Camp(str, Enum):
    WEREWOLVES = "狼人阵营"
    VILLAGERS = "好人阵营"


class Role(str, Enum):
    WEREWOLF = "狼人"
    VILLAGER = "平民"
    SEER = "预言家"
    WITCH = "女巫"


def role_camp(role: Role) -> Camp:
    if role is Role.WEREWOLF:
        return Camp.WEREWOLVES
    return Camp.VILLAGERS

