from __future__ import annotations

from dataclasses import dataclass

from roles.types import Role


@dataclass(frozen=True, slots=True)
class RoleSet:
    id: str
    name: str
    roles: tuple[Role, ...]


SIX_PLAYER_CLASSIC = RoleSet(
    id="6p-classic",
    name="6 人经典版型",
    roles=(
        Role.WEREWOLF,
        Role.WEREWOLF,
        Role.VILLAGER,
        Role.VILLAGER,
        Role.SEER,
        Role.WITCH,
    ),
)


ROLE_SETS = {
    SIX_PLAYER_CLASSIC.id: SIX_PLAYER_CLASSIC,
}


def get_role_set(role_set_id: str) -> RoleSet:
    try:
        return ROLE_SETS[role_set_id]
    except KeyError as exc:
        raise ValueError(f"unknown role set: {role_set_id}") from exc
