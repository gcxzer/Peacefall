from __future__ import annotations

"""数字人池选择相关的 CLI 辅助函数。"""

from pathlib import Path

from agents.profiles import AgentProfile, load_agent_pool


def parse_agent_names(values: list[str]) -> list[str]:
    """解析可重复、逗号分隔的数字人名称参数。"""

    names: list[str] = []
    for value in values:
        names.extend(name.strip() for name in value.split(",") if name.strip())
    return names


def format_agent_pool(agent_config_dir: str | Path) -> str:
    """格式化当前可用于随机抽取的数字人池。"""

    return "\n".join(
        f"{profile.seat}：{profile.display_name}"
        for profile in load_agent_pool(agent_config_dir)
    )


def format_selected_players(player_profiles: dict[int, AgentProfile]) -> str:
    """格式化本局实际入座的数字人。"""

    return "、".join(
        f"{seat}号={profile.display_name}"
        for seat, profile in sorted(player_profiles.items())
    )
