from __future__ import annotations

"""6 人经典狼人杀版型引擎。"""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agents.factory import GameAgents
from engine.agent_io import agent_name, announce, ask_json, invoke_agent
from engine.message_log import (
    DEFAULT_MESSAGE_LOG_DIR,
    ENGINE_SPEAKER,
    GameRecord,
    JUDGE_SPEAKER,
    MessageLogEntry,
    SYSTEM_SPEAKER,
    new_message_log_path,
    record_message,
    record_public,
)
from engine.rules import plurality_winner, valid_target
from engine.state import GameState
from prompts.templates import (
    PLAYER_SPEECH_INSTRUCTION,
    SIX_PLAYER_CLASSIC_DAY_ANNOUNCEMENT,
    SIX_PLAYER_CLASSIC_NIGHT_ANNOUNCEMENT,
    SIX_PLAYER_CLASSIC_START_ANNOUNCEMENT,
    TARGET_JSON_INSTRUCTION,
    WEREWOLF_DISCUSSION_INSTRUCTION,
    WEREWOLF_FINAL_KILL_INSTRUCTION,
    WITCH_JSON_INSTRUCTION,
)
from roles import Camp, Role


WEREWOLF_CHAT_ROUNDS = 2
WEREWOLF_TEAM_RECIPIENT = "werewolf_team"


@dataclass(frozen=True, slots=True)
class DaySpeechOrder:
    """随机指定白天起始玩家后的发言顺序。"""

    start_player_id: int
    ordered_player_ids: list[int]


@dataclass(frozen=True, slots=True)
class WerewolfKillRoom:
    """狼人夜晚私聊房间的工具结果。"""

    wolf_ids: list[int]
    target_ids: list[int]
    submitter_id: int


@dataclass(slots=True)
class SixPlayerClassicState(GameState):
    """6 人经典版型专属状态。"""

    witch_antidote_available: bool = True
    witch_poison_available: bool = True


@dataclass(frozen=True, slots=True)
class WitchDecision:
    """女巫夜晚行动的裁决结果。"""

    use_antidote: bool = False
    poison_target_id: int | None = None


# 公共入口
def run_game(
    agents: GameAgents,
    max_rounds: int = 20,
    message_log_dir: str | Path | None = DEFAULT_MESSAGE_LOG_DIR,
    on_message: Callable[[MessageLogEntry], None] | None = None,
) -> GameRecord:
    """运行一局 6 人经典版型游戏。"""

    state = SixPlayerClassicState(
        assignment=agents.assignment,
        message_log_path=(
            new_message_log_path(Path(message_log_dir))
            if message_log_dir is not None
            else None
        ),
        on_message=on_message,
    )

    announce(
        agents.judge,
        state,
        SIX_PLAYER_CLASSIC_START_ANNOUNCEMENT,
        phase="setup",
        action="start_announcement",
    )
    _check_win_conditions(state, phase="setup")

    while not state.game_over and state.round_number <= max_rounds:
        _run_night(agents, state)
        _check_win_conditions(state, phase="night")
        if state.game_over:
            break

        _run_day(agents, state)
        _check_win_conditions(state, phase="day")
        state.round_number += 1

    if not state.game_over:
        state.game_over = True
        state.win_reason = f"达到最大轮次 {max_rounds}，游戏结束。"
        record_public(
            state,
            SYSTEM_SPEAKER,
            state.win_reason,
            phase="system",
            action="max_rounds",
        )

    return GameRecord(
        messages=state.message_log,
        message_log_path=state.message_log_path,
    )


# 阶段流程
def _run_night(agents: GameAgents, state: SixPlayerClassicState) -> None:
    """推进当前轮次的夜晚阶段。"""

    announce(
        agents.judge,
        state,
        SIX_PLAYER_CLASSIC_NIGHT_ANNOUNCEMENT.format(
            round_number=state.round_number,
        ),
        phase="night",
        action="announce",
    )

    wolf_target_id = _collect_wolf_kill(agents, state)
    _collect_seer_inspection(agents, state)
    witch_decision = _collect_witch_action(agents, state, wolf_target_id)
    deaths = _resolve_night_deaths(state, wolf_target_id, witch_decision)

    death_text = (
        f"昨夜死亡：{_format_player_labels(agents, deaths)}。"
        if deaths
        else "昨夜是平安夜。"
    )
    record_public(
        state,
        JUDGE_SPEAKER,
        death_text,
        phase="night",
        action="death_announcement",
    )


def _run_day(agents: GameAgents, state: SixPlayerClassicState) -> None:
    """推进当前轮次的白天阶段。"""

    speech_order = _use_day_speech_order_tool(agents, state)
    announce(
        agents.judge,
        state,
        SIX_PLAYER_CLASSIC_DAY_ANNOUNCEMENT.format(
            round_number=state.round_number,
            start_player=agents.player_label(speech_order.start_player_id),
            speaking_order=_format_player_labels(
                agents,
                speech_order.ordered_player_ids,
            ),
        ),
        phase="day",
        action="announce",
    )

    _collect_day_speeches(agents, state, speech_order.ordered_player_ids)
    votes = _collect_day_votes(agents, state, speech_order.ordered_player_ids)
    _resolve_day_vote(agents, state, votes)


# 夜晚行动
def _collect_wolf_kill(
    agents: GameAgents,
    state: SixPlayerClassicState,
) -> int | None:
    """收集狼人夜晚私聊后的最终击杀目标。"""

    living_wolves = _living_players_with_role(state, Role.WEREWOLF)
    if not living_wolves:
        return None

    room = _open_werewolf_kill_room(living_wolves, state.alive_player_ids)
    _record_werewolf_room(state, agents, room)

    wolf_chat: list[str] = []
    for discussion_round in range(1, WEREWOLF_CHAT_ROUNDS + 1):
        chat_snapshot = _format_wolf_chat(wolf_chat)
        round_messages: list[str] = []
        for wolf_id in room.wolf_ids:
            message = invoke_agent(
                agents.players[wolf_id],
                (
                    WEREWOLF_DISCUSSION_INSTRUCTION.format(
                        round_number=state.round_number,
                        discussion_round=discussion_round,
                    )
                    + "\n"
                    f"存活狼人：{_format_player_labels(agents, room.wolf_ids)}\n"
                    f"可选击杀目标：{_format_player_labels(agents, room.target_ids)}\n"
                    f"当前狼聊记录：\n{chat_snapshot}\n\n"
                    f"{state.player_context(wolf_id)}"
                ),
                state=state,
                phase="night",
                action=f"wolf_discussion:{discussion_round}:{wolf_id}",
                record_agent_response=False,
            )
            round_messages.append(f"{_wolf_label(agents, wolf_id)}：{message}")
            record_message(
                state,
                channel="wolf_chat",
                phase="night",
                action=f"wolf_discussion:{discussion_round}:{wolf_id}",
                speaker=_wolf_label(agents, wolf_id),
                recipient=WEREWOLF_TEAM_RECIPIENT,
                role="assistant",
                content=message,
            )
        wolf_chat.extend(round_messages)

    payload = ask_json(
        agents.players[room.submitter_id],
        (
            f"{WEREWOLF_FINAL_KILL_INSTRUCTION}\n"
            f"主刀狼人：{_wolf_label(agents, room.submitter_id)}。\n"
            f"存活狼人：{_format_player_labels(agents, room.wolf_ids)}\n"
            f"可选击杀目标：{_format_player_labels(agents, room.target_ids)}\n"
            f"完整狼聊记录：\n{_format_wolf_chat(wolf_chat)}\n\n"
            f"{state.player_context(room.submitter_id)}\n\n"
            f"{TARGET_JSON_INSTRUCTION}"
        ),
        state=state,
        phase="night",
        action=f"wolf_final_kill:{room.submitter_id}",
        record_agent_response=False,
    )
    target_id = valid_target(payload.get("target_id"), room.target_ids)
    reason = str(payload.get("reason") or "").strip()
    if target_id is None:
        record_message(
            state,
            channel="wolf_chat",
            phase="night",
            action=f"wolf_final_kill_invalid:{room.submitter_id}",
            speaker=_wolf_label(agents, room.submitter_id),
            recipient=WEREWOLF_TEAM_RECIPIENT,
            role="assistant",
            content="主刀狼人没有提交有效击杀目标，本夜狼人击杀为空。",
        )
        return None

    record_message(
        state,
        channel="wolf_chat",
        phase="night",
        action=f"wolf_final_kill:{room.submitter_id}",
        speaker=_wolf_label(agents, room.submitter_id),
        recipient=WEREWOLF_TEAM_RECIPIENT,
        role="assistant",
        content=json.dumps(
            {
                "target_id": target_id,
                "reason": reason,
            },
            ensure_ascii=False,
        ),
    )
    return target_id


def _collect_seer_inspection(
    agents: GameAgents,
    state: SixPlayerClassicState,
) -> None:
    """执行预言家夜晚查验。"""

    seer_id = _living_player_with_role(state, Role.SEER)
    if seer_id is None:
        return

    valid_targets = _other_alive_player_ids(state, seer_id)
    payload = ask_json(
        agents.players[seer_id],
        (
            "现在是夜晚预言家行动。请选择一名存活玩家查验阵营。\n"
            f"可选目标：{_format_player_labels(agents, valid_targets)}\n\n"
            f"{state.player_context(seer_id)}\n\n"
            f"{TARGET_JSON_INSTRUCTION}"
        ),
        state=state,
        phase="night",
        action=f"seer_inspection:{seer_id}",
    )
    target_id = valid_target(payload.get("target_id"), valid_targets)
    if target_id is None:
        return

    result = "狼人" if state.camp_of(target_id) is Camp.WEREWOLVES else "好人"
    state.private_notes[seer_id].append(
        f"第 {state.round_number} 夜查验：{agents.player_label(target_id)}是{result}。"
    )


def _collect_witch_action(
    agents: GameAgents,
    state: SixPlayerClassicState,
    wolf_target_id: int | None,
) -> WitchDecision:
    """执行女巫夜晚用药决策。"""

    witch_id = _living_player_with_role(state, Role.WITCH)
    if witch_id is None:
        return WitchDecision()

    valid_poison_targets = _other_alive_player_ids(state, witch_id)
    killed_text = (
        agents.player_label(wolf_target_id) if wolf_target_id is not None else "无人"
    )
    payload = ask_json(
        agents.players[witch_id],
        (
            "现在是夜晚女巫行动。请决定是否用药。\n"
            f"今晚狼人击杀目标：{killed_text}。\n"
            f"解药可用：{state.witch_antidote_available}。\n"
            f"毒药可用：{state.witch_poison_available}。\n"
            f"毒药可选目标：{_format_player_labels(agents, valid_poison_targets)}\n\n"
            f"{state.player_context(witch_id)}\n\n"
            f"{WITCH_JSON_INSTRUCTION}"
        ),
        state=state,
        phase="night",
        action=f"witch_action:{witch_id}",
    )

    use_antidote = (
        bool(payload.get("use_antidote"))
        and state.witch_antidote_available
        and wolf_target_id is not None
    )
    poison_target_id = valid_target(payload.get("poison_target_id"), valid_poison_targets)
    if not state.witch_poison_available:
        poison_target_id = None

    if use_antidote:
        state.witch_antidote_available = False
        state.private_notes[witch_id].append(f"第 {state.round_number} 夜使用了解药。")
    if poison_target_id is not None:
        state.witch_poison_available = False
        state.private_notes[witch_id].append(
            f"第 {state.round_number} 夜使用毒药，目标是 {agents.player_label(poison_target_id)}。"
        )

    return WitchDecision(use_antidote=use_antidote, poison_target_id=poison_target_id)


def _resolve_night_deaths(
    state: SixPlayerClassicState,
    wolf_target_id: int | None,
    witch_decision: WitchDecision,
) -> list[int]:
    """根据狼人刀口和女巫用药结算夜晚死亡名单。"""

    deaths: list[int] = []
    if wolf_target_id is not None and not witch_decision.use_antidote:
        deaths.append(wolf_target_id)
    if witch_decision.poison_target_id is not None:
        deaths.append(witch_decision.poison_target_id)

    unique_deaths: list[int] = []
    for player_id in deaths:
        if player_id in state.alive_player_ids and player_id not in unique_deaths:
            state.alive_player_ids.remove(player_id)
            unique_deaths.append(player_id)
    return unique_deaths


# 工具结果记录
def _open_werewolf_kill_room(
    wolf_ids: set[int] | list[int],
    alive_player_ids: set[int],
) -> WerewolfKillRoom:
    """打开狼人夜晚私聊房间，并随机指定主刀狼人。"""

    living_wolf_ids = sorted(set(wolf_ids))
    target_ids = sorted(alive_player_ids)
    if not living_wolf_ids:
        raise ValueError("cannot open werewolf kill room without living wolves")
    if not target_ids:
        raise ValueError("cannot open werewolf kill room without alive players")

    return WerewolfKillRoom(
        wolf_ids=living_wolf_ids,
        target_ids=target_ids,
        submitter_id=random.choice(living_wolf_ids),
    )


def _select_day_speech_order(alive_player_ids: set[int]) -> DaySpeechOrder:
    """从存活玩家中随机指定白天发言起始玩家。"""

    player_ids = sorted(alive_player_ids)
    if not player_ids:
        raise ValueError("cannot select day speech order from empty alive player list")

    start_player_id = random.choice(player_ids)
    start_index = player_ids.index(start_player_id)
    return DaySpeechOrder(
        start_player_id=start_player_id,
        ordered_player_ids=player_ids[start_index:] + player_ids[:start_index],
    )


def _use_day_speech_order_tool(
    agents: GameAgents,
    state: SixPlayerClassicState,
) -> DaySpeechOrder:
    """调用工具随机决定本轮白天起始发言玩家。"""

    speech_order = _select_day_speech_order(state.alive_player_ids)
    record_message(
        state,
        channel="tool",
        phase="day",
        action="select_day_speech_order",
        speaker=agent_name(agents.judge),
        recipient=ENGINE_SPEAKER,
        role="tool",
        content=json.dumps(
            {
                "tool": "select_day_speech_order",
                "alive_player_ids": sorted(state.alive_player_ids),
                "alive_players": _player_name_map(
                    agents,
                    sorted(state.alive_player_ids),
                ),
                "start_player_id": speech_order.start_player_id,
                "start_player": agents.player_label(speech_order.start_player_id),
                "ordered_player_ids": speech_order.ordered_player_ids,
                "ordered_players": _player_name_map(
                    agents,
                    speech_order.ordered_player_ids,
                ),
            },
            ensure_ascii=False,
        ),
    )
    return speech_order


def _record_werewolf_room(
    state: SixPlayerClassicState,
    agents: GameAgents,
    room: WerewolfKillRoom,
) -> None:
    """记录狼人夜晚私聊房间工具结果。"""

    record_message(
        state,
        channel="tool",
        phase="night",
        action="open_werewolf_kill_room",
        speaker=agent_name(agents.judge),
        recipient=ENGINE_SPEAKER,
        role="tool",
        content=json.dumps(
            {
                "tool": "open_werewolf_kill_room",
                "wolf_ids": room.wolf_ids,
                "wolves": _player_name_map(agents, room.wolf_ids),
                "target_ids": room.target_ids,
                "targets": _player_name_map(agents, room.target_ids),
                "submitter_id": room.submitter_id,
                "submitter": agents.player_label(room.submitter_id),
            },
            ensure_ascii=False,
        ),
    )


# 白天行动
def _collect_day_speeches(
    agents: GameAgents,
    state: SixPlayerClassicState,
    ordered_player_ids: list[int],
) -> None:
    """按给定顺序收集所有存活玩家的白天公开发言。"""

    for player_id in ordered_player_ids:
        speech = invoke_agent(
            agents.players[player_id],
            f"{PLAYER_SPEECH_INSTRUCTION}\n\n{state.player_context(player_id)}",
            state=state,
            phase="day",
            action=f"speech:{player_id}",
            record_agent_response=False,
        )
        record_public(
            state,
            agents.player_label(player_id),
            speech,
            phase="day",
            action=f"speech:{player_id}",
        )


def _collect_day_votes(
    agents: GameAgents,
    state: SixPlayerClassicState,
    ordered_player_ids: list[int],
) -> dict[int, int]:
    """收集白天投票。"""

    votes: dict[int, int] = {}
    for player_id in ordered_player_ids:
        valid_targets = _other_alive_player_ids(state, player_id)
        payload = ask_json(
            agents.players[player_id],
            (
                "现在进行白天投票。请从存活的其他玩家中选择一名放逐目标。请根据自己的策略进行投票。 \n"
                f"可选目标：{_format_player_labels(agents, valid_targets)}\n\n"
                f"{state.player_context(player_id)}\n\n"
                f"{TARGET_JSON_INSTRUCTION}"
            ),
            state=state,
            phase="day",
            action=f"vote:{player_id}",
        )
        target_id = valid_target(payload.get("target_id"), valid_targets)
        if target_id is not None:
            votes[player_id] = target_id
    return votes


def _resolve_day_vote(
    agents: GameAgents,
    state: SixPlayerClassicState,
    votes: dict[int, int],
) -> None:
    """结算白天投票并公开结果。"""

    vote_summary = "、".join(
        f"{agents.player_label(voter_id)}投票给{agents.player_label(target_id)}"
        for voter_id, target_id in sorted(votes.items())
    )
    record_public(
        state,
        JUDGE_SPEAKER,
        f"投票结果：{vote_summary or '无有效投票'}。",
        phase="day",
        action="vote_result",
    )

    exiled_player_id = plurality_winner(votes.values(), tie_returns_none=True)
    if exiled_player_id is None:
        record_public(
            state,
            JUDGE_SPEAKER,
            "本轮平票或无有效投票，无人出局。",
            phase="day",
            action="no_exile",
        )
        return

    state.alive_player_ids.remove(exiled_player_id)
    record_public(
        state,
        JUDGE_SPEAKER,
        f"{agents.player_label(exiled_player_id)} 被放逐出局。",
        phase="day",
        action="exile",
    )


# 胜负检查和状态查询
def _check_win_conditions(
    state: SixPlayerClassicState,
    *,
    phase: str,
) -> None:
    """检查当前 6 人经典版型是否已经分出胜负。"""

    if state.game_over:
        return

    living_wolves = _living_players_with_role(state, Role.WEREWOLF)
    living_villagers = _living_players_with_role(state, Role.VILLAGER)
    living_specials = _living_players_with_roles(state, {Role.SEER, Role.WITCH})

    if not living_wolves:
        state.game_over = True
        state.winner = Camp.VILLAGERS
        state.win_reason = "所有狼人均已出局。"
    elif not living_villagers:
        state.game_over = True
        state.winner = Camp.WEREWOLVES
        state.win_reason = "所有平民均已出局，狼人达成屠边。"
    elif not living_specials:
        state.game_over = True
        state.winner = Camp.WEREWOLVES
        state.win_reason = "所有神职均已出局，狼人达成屠边。"

    if state.game_over and state.winner is not None:
        record_public(
            state,
            JUDGE_SPEAKER,
            f"{state.winner.value}获胜：{state.win_reason}",
            phase=phase,
            action="win_condition",
        )


def _living_player_with_role(
    state: SixPlayerClassicState,
    role: Role,
) -> int | None:
    """查找指定身份的存活玩家。"""

    players = _living_players_with_role(state, role)
    return players[0] if players else None


def _living_players_with_role(
    state: SixPlayerClassicState,
    role: Role,
) -> list[int]:
    """查找指定身份的所有存活玩家。"""

    return _living_players_with_roles(state, {role})


def _living_players_with_roles(
    state: SixPlayerClassicState,
    roles: set[Role],
) -> list[int]:
    """查找任意指定身份的所有存活玩家。"""

    return [
        player_id
        for player_id in sorted(state.alive_player_ids)
        if state.role_of(player_id) in roles
    ]


def _other_alive_player_ids(
    state: SixPlayerClassicState,
    player_id: int,
) -> list[int]:
    """返回除指定玩家外的所有存活玩家编号。"""

    return [
        target_id
        for target_id in sorted(state.alive_player_ids)
        if target_id != player_id
    ]


def _format_wolf_chat(messages: list[str]) -> str:
    """把狼人私聊记录格式化为给狼人 agent 阅读的文本。"""

    if not messages:
        return "- 暂无"
    return "\n".join(f"- {message}" for message in messages)


def _format_player_labels(agents: GameAgents, player_ids: list[int]) -> str:
    """把玩家编号列表格式化成名字和座位号。"""

    if not player_ids:
        return "无"
    return "、".join(agents.player_label(player_id) for player_id in player_ids)


def _player_name_map(agents: GameAgents, player_ids: list[int]) -> dict[str, str]:
    """返回方便写入工具日志的玩家编号到名字映射。"""

    return {str(player_id): agents.player_label(player_id) for player_id in player_ids}


def _wolf_label(agents: GameAgents, player_id: int) -> str:
    """返回狼人私聊中使用的玩家展示名。"""

    return f"{agents.player_name(player_id)}（{player_id}号狼人）"
