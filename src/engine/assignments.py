from __future__ import annotations

"""通用身份分配数据结构和随机分配函数。"""

import random
from dataclasses import dataclass

from prompts.templates import (
    JUDGE_PRIVATE_CONTEXT_HEADER,
    JUDGE_PRIVATE_CONTEXT_LINE,
    PLAYER_PRIVATE_CONTEXT_PROMPT,
    WEREWOLF_TEAMMATES_PROMPT,
)
from engine.rules import format_player_ids
from roles import Role, RoleSet, role_camp


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    """单个玩家的身份分配。"""

    player_id: int
    role: Role

    @property
    def camp(self) -> str:
        """返回身份对应的中文阵营名。"""

        return role_camp(self.role).value


@dataclass(frozen=True, slots=True)
class GameAssignment:
    """一局游戏的完整身份表。"""

    role_set_id: str
    assignments: dict[int, RoleAssignment]

    def player_private_context(self, player_id: int) -> str:
        """生成某个玩家能看到的本局私有信息。"""

        assignment = self.assignments[player_id]
        sections = [
            PLAYER_PRIVATE_CONTEXT_PROMPT.format(
                player_id=player_id,
                role=assignment.role.value,
                camp=assignment.camp,
            )
        ]

        if assignment.role is Role.WEREWOLF:
            teammate_ids = [
                other.player_id
                for other in self.assignments.values()
                if other.role is Role.WEREWOLF and other.player_id != player_id
            ]
            sections.append(
                WEREWOLF_TEAMMATES_PROMPT.format(
                    teammates=format_player_ids(sorted(teammate_ids))
                )
            )

        return "\n".join(sections)

    def judge_private_context(self) -> str:
        """生成法官能看到的完整身份表。"""

        lines = [
            JUDGE_PRIVATE_CONTEXT_HEADER.format(role_set_id=self.role_set_id)
        ]
        for player_id in sorted(self.assignments):
            assignment = self.assignments[player_id]
            lines.append(
                JUDGE_PRIVATE_CONTEXT_LINE.format(
                    player_id=player_id,
                    role=assignment.role.value,
                    camp=assignment.camp,
                )
            )
        return "\n".join(lines)


def assign_roles(role_set: RoleSet, seed: int | None = None) -> GameAssignment:
    """按版型随机分配身份。"""

    roles = list(role_set.roles)
    rng = random.Random(seed)
    rng.shuffle(roles)

    assignments = {
        player_id: RoleAssignment(player_id=player_id, role=role)
        for player_id, role in enumerate(roles, start=1)
    }
    return GameAssignment(role_set_id=role_set.id, assignments=assignments)
