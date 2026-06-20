from __future__ import annotations

"""为长期记忆生成赛后复盘。"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain.agents import create_agent

from agents.factory import GameAgents
from agents.profiles import AgentProfile
from engine.agent_io import extract_response_text, parse_json_object
from engine.message_log import GameRecord, MessageLogEntry
from memory.store import append_memory_entry
from model_providers import ModelProviderConfig, create_chat_model
from roles import Camp, RoleSet, role_camp


logger = logging.getLogger(__name__)

REFLECTION_MODE_OFF = "off"
REFLECTION_MODE_OMNISCIENT = "omniscient"
REFLECTION_MODES = (REFLECTION_MODE_OFF, REFLECTION_MODE_OMNISCIENT)
MAX_REFLECTION_LOG_ENTRIES = 180
MAX_REFLECTION_CONTENT_CHARS = 600
DEFAULT_CONFIG_PATH = Path("config.json")

REFLECTION_SYSTEM_PROMPT = (
    "你是狼人杀赛后复盘助手，负责为单个数字人沉淀长期记忆。\n"
    "长期记忆会跨局使用，只能记录数字人名字、行为倾向、决策教训、证据和应对策略。\n"
    "不要记录或引用座位号，因为每局座位会变化。\n"
    "不要把某位玩家上一局的身份当作下局事实；身份只能作为本局复盘背景，不能写成固定结论。\n"
    "只输出 JSON 对象，不要 Markdown，不要额外解释。"
)


def write_postgame_reflections(
    *,
    agents: GameAgents,
    role_set: RoleSet,
    record: GameRecord,
    memory_dir: str | Path,
    mode: str = REFLECTION_MODE_OMNISCIENT,
) -> list[Path]:
    """为每名玩家生成并写入一条赛后长期记忆。"""

    if mode == REFLECTION_MODE_OFF:
        return []
    if mode != REFLECTION_MODE_OMNISCIENT:
        raise ValueError(f"unsupported reflection mode: {mode}")

    paths: list[Path] = []
    game_context = _format_game_context(agents, role_set, record)
    evidence_log = _format_evidence_log(record.messages)
    winning_camp = _winning_camp_from_record(record)
    player_items = sorted(agents.player_profiles.items())
    model_config = _load_reflection_model_config()

    logger.info("开始赛后复盘：共 %s 名玩家。", len(player_items))
    logger.info("赛后复盘模型：%s/%s", model_config.provider, model_config.model)

    for index, (player_id, profile) in enumerate(player_items, start=1):
        logger.info(
            "赛后复盘 %s/%s：%s",
            index,
            len(player_items),
            profile.display_name,
        )
        prompt = _build_reflection_prompt(
            agents=agents,
            role_set=role_set,
            record=record,
            player_id=player_id,
            profile=profile,
            game_context=game_context,
            evidence_log=evidence_log,
        )
        try:
            payload = _invoke_reflection_agent(profile, prompt, model_config)
        except Exception:
            logger.exception("生成 %s 的赛后复盘失败", profile.display_name)
            continue

        entry = _build_memory_entry(
            agents=agents,
            role_set=role_set,
            record=record,
            player_id=player_id,
            profile=profile,
            payload=payload,
            winning_camp=winning_camp,
            mode=mode,
        )
        path = append_memory_entry(memory_dir, profile.agent_id, entry)
        paths.append(path)
        logger.info("赛后复盘已写入：%s", path)

    logger.info("赛后复盘完成：成功写入 %s/%s 条记忆。", len(paths), len(player_items))
    return paths


def _invoke_reflection_agent(
    profile: AgentProfile,
    prompt: str,
    model_config: ModelProviderConfig,
) -> dict[str, Any]:
    """调用统一配置的反思模型，生成结构化复盘 JSON。"""

    reflection_agent = create_agent(
        model=create_chat_model(model_config),
        tools=[],
        system_prompt=REFLECTION_SYSTEM_PROMPT,
        name=f"{profile.runtime_name}-赛后复盘",
    )
    result = reflection_agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    response_text = extract_response_text(result)
    payload = parse_json_object(response_text)
    if payload:
        return payload
    return {
        "game_summary": {"key_events": []},
        "self_reflection": [],
        "opponent_analysis": [],
        "raw_response": response_text,
        "parse_error": "model did not return a JSON object",
    }


def _load_reflection_model_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> ModelProviderConfig:
    """从根目录 config.json 读取赛后反思模型配置。"""

    path = Path(config_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"reflection config not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")

    reflection = data.get("reflection")
    if not isinstance(reflection, dict):
        raise ValueError(f"{path} field 'reflection' must be object")

    model_data = reflection.get("model")
    if not isinstance(model_data, dict):
        raise ValueError(f"{path} field 'reflection.model' must be object")

    return ModelProviderConfig.from_env(
        provider=_optional_text(model_data.get("provider")),
        model=_optional_text(model_data.get("name") or model_data.get("model")),
        temperature=_optional_float(model_data.get("temperature")),
        thinking=_optional_text(model_data.get("thinking")),
    )


def _build_reflection_prompt(
    *,
    agents: GameAgents,
    role_set: RoleSet,
    record: GameRecord,
    player_id: int,
    profile: AgentProfile,
    game_context: str,
    evidence_log: str,
) -> str:
    """构造单个数字人的赛后复盘 prompt。"""

    assignment = agents.assignment.assignments[player_id]
    return (
        f"请为 {profile.display_name} 生成一条赛后长期记忆。\n"
        f"本局版型：{role_set.name}（{role_set.id}）。\n"
        f"该玩家本局真实身份：{assignment.role.value}，阵营：{assignment.camp}。\n\n"
        "输出 JSON 必须包含这些字段：\n"
        "{\n"
        '  "game_summary": {"key_events": ["关键事件，最多5条"]},\n'
        '  "self_reflection": [\n'
        "    {\n"
        '      "lesson": "这名玩家自己的可迁移教训",\n'
        '      "future_adjustment": "下次遇到类似局面应如何调整",\n'
        '      "basis": [消息index数字],\n'
        '      "confidence": 0.0到1.0,\n'
        '      "tags": ["简短标签"]\n'
        "    }\n"
        "  ],\n"
        '  "opponent_analysis": [\n'
        "    {\n"
        '      "opponent_name": "对手名字",\n'
        '      "observed_tendency": "这个对手在本局表现出的行为倾向",\n'
        '      "counter_strategy": "下次对上此人时可用的应对策略",\n'
        '      "basis": [消息index数字],\n'
        '      "confidence": 0.0到1.0\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "要求：\n"
        "- 长期记忆里只写数字人名字，不写几号玩家、座位号或座位顺序。\n"
        "- 自我反思重点关注如何帮助自己阵营获胜，不要写空泛鸡汤。\n"
        "- 对手分析只总结行为模式和应对方式，不要写成“下局某人一定是某身份”。\n"
        "- 如果引用证据日志中带有座位号的内容，复盘结论里要转换成对应数字人名字。\n"
        "- basis 必须引用下面证据日志里的消息 index；没有证据就降低 confidence。\n"
        "- 每个列表最多 5 项，句子要短而具体。\n\n"
        f"对局基本信息：\n{game_context}\n\n"
        f"证据日志：\n{evidence_log}"
    )


def _build_memory_entry(
    *,
    agents: GameAgents,
    role_set: RoleSet,
    record: GameRecord,
    player_id: int,
    profile: AgentProfile,
    payload: dict[str, Any],
    winning_camp: Camp | None,
    mode: str,
) -> dict[str, Any]:
    """把模型复盘结果包装成最终写入 JSONL 的记忆对象。"""

    assignment = agents.assignment.assignments[player_id]
    winning_players = _winning_players(agents, winning_camp)
    game_summary = payload.get("game_summary")
    self_reflection = payload.get("self_reflection")
    opponent_analysis = payload.get("opponent_analysis")
    return {
        "agent_id": profile.agent_id,
        "display_name": profile.display_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "game_id": _game_id(record),
        "role_set_id": role_set.id,
        "reflection_mode": mode,
        "message_log_path": str(record.message_log_path) if record.message_log_path else "",
        "winners": winning_players,
        "self": {
            "agent_id": profile.agent_id,
            "display_name": profile.display_name,
            "role": assignment.role.value,
            "result": _result_text(role_camp(assignment.role), winning_camp),
        },
        "allies": _related_players(agents, player_id, same_camp=True),
        "opponents": _related_players(agents, player_id, same_camp=False),
        "game_summary": game_summary if isinstance(game_summary, dict) else {},
        "self_reflection": self_reflection if isinstance(self_reflection, list) else [],
        "opponent_analysis": (
            opponent_analysis if isinstance(opponent_analysis, list) else []
        ),
        "raw_reflection": {
            key: value
            for key, value in payload.items()
            if key
            not in {"game_summary", "self_reflection", "opponent_analysis"}
        },
    }


def _format_game_context(
    agents: GameAgents,
    role_set: RoleSet,
    record: GameRecord,
) -> str:
    """生成赛后复盘可读取的对局基本信息。"""

    winning_camp = _winning_camp_from_record(record)
    winning_players = _winning_players(agents, winning_camp)
    lines = [
        f"game_id：{_game_id(record)}",
        f"版型：{role_set.name}（{role_set.id}）",
        f"获胜玩家：{_format_player_names(winning_players)}",
        "完整身份表：",
    ]
    for seat, profile in sorted(agents.player_profiles.items()):
        assignment = agents.assignment.assignments[seat]
        lines.append(f"- {profile.display_name}：{assignment.role.value}")
    return "\n".join(lines)


def _format_evidence_log(messages: list[MessageLogEntry]) -> str:
    """从完整消息流水中抽取适合做复盘证据的日志文本。"""

    selected = [message for message in messages if _include_in_reflection_log(message)]
    if len(selected) > MAX_REFLECTION_LOG_ENTRIES:
        selected = selected[-MAX_REFLECTION_LOG_ENTRIES:]
    lines = []
    for message in selected:
        content = _clip(message.content, MAX_REFLECTION_CONTENT_CHARS)
        lines.append(
            f"[{message.index}] 第{message.round_number}轮/"
            f"{message.phase}/{message.channel}/{message.action} "
            f"{message.speaker}->{message.recipient}：{content}"
        )
    return "\n".join(lines) if lines else "- 无可用证据"


def _include_in_reflection_log(message: MessageLogEntry) -> bool:
    """判断一条消息是否应该进入赛后复盘证据日志。"""

    if message.channel in {"public", "wolf_chat", "tool"}:
        return True
    return message.channel == "agent" and message.role == "assistant" and (
        message.action.startswith("seer_inspection:")
        or message.action.startswith("witch_action:")
        or message.action.startswith("vote:")
    )


def _winning_camp_from_record(record: GameRecord) -> Camp | None:
    """从公开胜负公告中解析获胜阵营。"""

    for message in reversed(record.messages):
        if message.action != "win_condition":
            continue
        if message.content.startswith(Camp.WEREWOLVES.value):
            return Camp.WEREWOLVES
        if message.content.startswith(Camp.VILLAGERS.value):
            return Camp.VILLAGERS
    return None


def _related_players(
    agents: GameAgents,
    player_id: int,
    *,
    same_camp: bool,
) -> list[dict[str, Any]]:
    """返回与指定玩家同阵营或敌对阵营的数字人简要信息。"""

    own_camp = agents.assignment.assignments[player_id].camp
    players = []
    for other_id, profile in sorted(agents.player_profiles.items()):
        if other_id == player_id:
            continue
        assignment = agents.assignment.assignments[other_id]
        if (assignment.camp == own_camp) != same_camp:
            continue
        players.append(
            {
                "agent_id": profile.agent_id,
                "display_name": profile.display_name,
                "role": assignment.role.value,
            }
        )
    return players


def _winning_players(
    agents: GameAgents,
    winning_camp: Camp | None,
) -> list[str]:
    """返回获胜阵营对应的数字人名字列表。"""

    if winning_camp is None:
        return []
    return [
        agents.player_name(player_id)
        for player_id in sorted(agents.player_profiles)
        if role_camp(agents.assignment.assignments[player_id].role) is winning_camp
    ]


def _format_player_names(players: list[str]) -> str:
    """把数字人名字列表格式化成中文顿号分隔文本。"""

    names = [name.strip() for name in players if name.strip()]
    return "、".join(names) if names else "无"


def _result_text(camp: Camp, winner: Camp | None) -> str:
    """根据自己的阵营和获胜阵营返回胜负文本。"""

    if winner is None:
        return "未分胜负"
    return "胜利" if camp is winner else "失败"


def _game_id(record: GameRecord) -> str:
    """从消息日志路径推导稳定的对局 ID。"""

    if record.message_log_path is None:
        return datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = record.message_log_path.stem
    return stem.removeprefix("messages-")


def _clip(text: str, max_chars: int) -> str:
    """压缩并截断过长的证据文本，避免复盘 prompt 过大。"""

    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1] + "…"


def _optional_text(value: Any) -> str | None:
    """把可选字符串字段归一化。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    """把可选数字字段归一化。"""

    if value is None:
        return None
    return float(value)
