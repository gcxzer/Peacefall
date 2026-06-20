from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain.agents import create_agent

from agents.profiles import (
    DEFAULT_AGENT_CONFIG_DIR,
    AgentProfile,
    load_judge_profile,
    load_player_profiles,
)
from engine.assignments import GameAssignment
from memory.store import (
    DEFAULT_MEMORY_DIR,
    DEFAULT_MEMORY_LIMIT,
    format_memory_context,
    load_memory_entries,
)
from model_providers import ModelProviderConfig, create_chat_model
from prompts.builder import build_judge_prompt, build_player_prompt
from roles import RoleSet


@dataclass(frozen=True, slots=True)
class GameAgents:
    """一局游戏启动后持有的所有 agent 和身份分配。"""

    judge: Any
    players: dict[int, Any]
    assignment: GameAssignment
    player_profiles: dict[int, AgentProfile] = field(default_factory=dict)

    def player_name(self, player_id: int) -> str:
        """返回玩家数字人名字。"""

        profile = self.player_profiles.get(player_id)
        return profile.display_name if profile else f"{player_id} 号玩家"

    def player_label(self, player_id: int) -> str:
        """返回带座位号的玩家展示名。"""

        return f"{self.player_name(player_id)}（{player_id}号）"


def create_game_agents(
    role_set: RoleSet,
    assignment: GameAssignment,
    *,
    agent_config_dir: str | Path = DEFAULT_AGENT_CONFIG_DIR,
    selected_agents: list[str] | None = None,
    seed: int | None = None,
    memory_dir: str | Path | None = DEFAULT_MEMORY_DIR,
    memory_limit: int = DEFAULT_MEMORY_LIMIT,
) -> GameAgents:
    """为一个版型创建法官和所有玩家 agent。"""

    profiles = load_player_profiles(
        len(role_set.roles),
        config_dir=agent_config_dir,
        selected_agents=selected_agents,
        seed=seed,
    )
    judge_profile = load_judge_profile(agent_config_dir)
    judge_name = judge_profile.runtime_name if judge_profile else "法官"
    judge_prompt = build_judge_prompt(
        role_set,
        assignment.judge_private_context(),
        digital_human_context=judge_profile.prompt_context() if judge_profile else "",
    )
    judge = create_agent(
        model=_build_chat_model(profile=judge_profile),
        tools=[],
        system_prompt=judge_prompt,
        name=judge_name,
    )

    players: dict[int, Any] = {}
    for player_id in range(1, len(role_set.roles) + 1):
        profile = profiles[player_id]
        player_prompt = build_player_prompt(
            player_id,
            role_set,
            assignment.player_private_context(player_id),
            display_name=profile.display_name,
            digital_human_context=profile.prompt_context(),
            memory_context=_player_memory_context(
                profile,
                role_set_id=role_set.id,
                memory_dir=memory_dir,
                memory_limit=memory_limit,
            ),
        )
        players[player_id] = create_agent(
            model=_build_chat_model(
                profile=profile,
            ),
            tools=[],
            system_prompt=player_prompt,
            name=profile.runtime_name,
        )

    return GameAgents(
        judge=judge,
        players=players,
        assignment=assignment,
        player_profiles=profiles,
    )


def _build_chat_model(
    *,
    profile: AgentProfile | None = None,
) -> object:
    """根据数字人配置和环境变量创建聊天模型。"""

    llm_config = ModelProviderConfig.from_env(
        provider=profile.model.provider if profile else None,
        model=profile.model.name if profile else None,
        temperature=profile.model.temperature if profile else None,
        thinking=profile.model.thinking if profile else None,
    )
    return create_chat_model(llm_config)


def _player_memory_context(
    profile: AgentProfile,
    *,
    role_set_id: str,
    memory_dir: str | Path | None,
    memory_limit: int,
) -> str:
    """读取该数字人当前版型的长期复盘记忆，并格式化进玩家 prompt。"""

    if memory_dir is None or memory_limit <= 0:
        return ""
    return format_memory_context(
        load_memory_entries(
            memory_dir,
            profile.agent_id,
            role_set_id=role_set_id,
            limit=memory_limit,
        )
    )
