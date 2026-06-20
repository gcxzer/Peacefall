from __future__ import annotations

"""从根目录 agents/*.json 读取数字人配置。"""

import json
import random
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


DEFAULT_AGENT_CONFIG_DIR = Path("agents")


@dataclass(frozen=True, slots=True)
class AgentModelProfile:
    """数字人偏好的模型配置。"""

    provider: str | None = None
    name: str | None = None
    temperature: float | None = None
    thinking: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalHumanProfile:
    """数字人的人设、表达方式和行为倾向。"""

    core_identity: dict[str, Any] = field(default_factory=dict)
    behavioral_traits: dict[str, Any] = field(default_factory=dict)
    linguistic_profile: dict[str, Any] = field(default_factory=dict)
    strategic_gameplay: dict[str, Any] = field(default_factory=dict)
    thought_process_and_examples: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    task_personality: str = ""
    table_presence: str = ""
    speaking_style: str = ""
    speech_habits: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    speech_examples: list[str] = field(default_factory=list)

    @property
    def has_structured_profile(self) -> bool:
        """判断是否使用新版分块数字人结构。"""

        return any(
            (
                self.core_identity,
                self.behavioral_traits,
                self.linguistic_profile,
                self.strategic_gameplay,
                self.thought_process_and_examples,
            )
        )

    def speech_example_texts(self) -> list[str]:
        """返回可作为语气参考的自然发言示例。"""

        examples = self.thought_process_and_examples.get("speech_examples")
        if isinstance(examples, dict):
            return [str(value) for value in examples.values() if str(value).strip()]
        if isinstance(examples, list):
            return [str(value) for value in examples if str(value).strip()]
        return list(self.speech_examples)


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """单个玩家数字人配置。"""

    agent_id: str
    kind: str
    seat: int
    display_name: str
    model: AgentModelProfile
    digital_human: DigitalHumanProfile
    game_task: dict[str, str] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)

    @property
    def runtime_name(self) -> str:
        """返回 LangChain agent 和消息日志里使用的名字。"""

        return self.display_name

    def prompt_context(self) -> str:
        """把数字人配置格式化成玩家 prompt 段落。"""

        if self.digital_human.has_structured_profile:
            return self._structured_prompt_context()
        return self._legacy_prompt_context()

    def _structured_prompt_context(self) -> str:
        """把新版分块数字人配置格式化成玩家 prompt 段落。"""

        sections = [
            "数字人设定：",
            f"- 名字：{self.display_name}",
        ]
        section_specs = (
            ("核心身份", self.digital_human.core_identity),
            ("行为特征", self.digital_human.behavioral_traits),
            ("语言风格", self.digital_human.linguistic_profile),
            ("局内策略", self.digital_human.strategic_gameplay),
            ("思考流程与示例", self.digital_human.thought_process_and_examples),
        )
        for title, payload in section_specs:
            if payload:
                sections.append(f"{title}：")
                sections.extend(_format_profile_value(payload, indent=1))
        if self.game_task:
            sections.append("局内任务偏好：")
            for key, value in self.game_task.items():
                sections.append(f"- {_profile_label(key)}：{value}")
        if self.constraints:
            sections.append("行为边界：")
            sections.extend(f"- {constraint}" for constraint in self.constraints)
        return "\n".join(section for section in sections if section.strip())

    def _legacy_prompt_context(self) -> str:
        """把旧版扁平数字人配置格式化成玩家 prompt 段落。"""

        sections = [
            "数字人设定：",
            f"- 名字：{self.display_name}",
            f"- 简介：{self.digital_human.summary}",
            f"- 任务个性：{self.digital_human.task_personality}",
            f"- 场上存在感：{self.digital_human.table_presence}",
            f"- 说话风格：{self.digital_human.speaking_style}",
        ]
        if self.digital_human.speech_habits:
            sections.append("- 说话习惯：" + "；".join(self.digital_human.speech_habits))
        if self.digital_human.strengths:
            sections.append("- 擅长：" + "；".join(self.digital_human.strengths))
        if self.digital_human.weaknesses:
            sections.append("- 弱点：" + "；".join(self.digital_human.weaknesses))
        if self.digital_human.speech_examples:
            sections.append("自然发言示例，只参考语感，不要照抄句式和口头禅：")
            sections.extend(f"- {example}" for example in self.digital_human.speech_examples)
        if self.game_task:
            sections.append("局内任务偏好：")
            for key, value in self.game_task.items():
                sections.append(f"- {key}：{value}")
        if self.constraints:
            sections.append("行为边界：")
            sections.extend(f"- {constraint}" for constraint in self.constraints)
        return "\n".join(section for section in sections if section.strip())


def load_player_profiles(
    player_count: int,
    config_dir: str | Path = DEFAULT_AGENT_CONFIG_DIR,
    *,
    selected_agents: list[str] | None = None,
    seed: int | None = None,
) -> dict[int, AgentProfile]:
    """从数字人池中选择本局需要的玩家配置。"""

    pool = load_agent_pool(config_dir)
    requested_profiles = _resolve_requested_profiles(pool, selected_agents or [])
    if len(requested_profiles) > player_count:
        raise ValueError(
            f"selected {len(requested_profiles)} agents, but role set only needs "
            f"{player_count} players"
        )
    if len(pool) < player_count:
        raise FileNotFoundError(
            f"agent pool has {len(pool)} players, but role set needs {player_count}"
        )

    requested_ids = {profile.agent_id for profile in requested_profiles}
    remaining_pool = [
        profile for profile in pool if profile.agent_id not in requested_ids
    ]
    rng = random.Random(seed)
    selected_profiles = requested_profiles + rng.sample(
        remaining_pool,
        player_count - len(requested_profiles),
    )

    return {
        seat: replace(profile, seat=seat)
        for seat, profile in enumerate(selected_profiles, start=1)
    }


def load_agent_pool(
    config_dir: str | Path = DEFAULT_AGENT_CONFIG_DIR,
) -> list[AgentProfile]:
    """读取根目录 agents/*.json，作为可抽取的数字人池。"""

    directory = Path(config_dir)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"agent config dir not found: {directory}")
    profiles: dict[int, AgentProfile] = {}
    for path in sorted(directory.glob("*.json")):
        profile = _load_agent_profile(path)
        if profile.kind != "player":
            raise ValueError(f"{path} kind must be player, got {profile.kind!r}")
        if profile.seat in profiles:
            raise ValueError(f"duplicate agent profile seat: {profile.seat}")
        profiles[profile.seat] = profile

    if not profiles:
        raise FileNotFoundError(f"no agent profiles found in {directory}")
    return [profiles[seat] for seat in sorted(profiles)]


def _resolve_requested_profiles(
    pool: list[AgentProfile],
    selected_agents: list[str],
) -> list[AgentProfile]:
    """把用户指定的名字、agent_id 或池子座位号解析成数字人配置。"""

    index = _agent_lookup_index(pool)
    selected_profiles: list[AgentProfile] = []
    seen_ids: set[str] = set()
    for raw_name in selected_agents:
        name = raw_name.strip()
        if not name:
            continue
        profile = index.get(_normalize_agent_key(name))
        if profile is None:
            available = "、".join(profile.display_name for profile in pool)
            raise ValueError(f"unknown agent {name!r}. Available agents: {available}")
        if profile.agent_id in seen_ids:
            raise ValueError(f"duplicate selected agent: {name}")
        selected_profiles.append(profile)
        seen_ids.add(profile.agent_id)
    return selected_profiles


def _agent_lookup_index(pool: list[AgentProfile]) -> dict[str, AgentProfile]:
    """生成用户可输入名称到数字人配置的索引。"""

    index: dict[str, AgentProfile] = {}
    for profile in pool:
        aliases = {
            profile.agent_id,
            profile.display_name,
            str(profile.seat),
            f"{profile.seat}号",
            f"{profile.seat}号玩家",
        }
        for alias in aliases:
            key = _normalize_agent_key(alias)
            existing = index.get(key)
            if existing is not None and existing.agent_id != profile.agent_id:
                raise ValueError(f"ambiguous agent alias: {alias}")
            index[key] = profile
    return index


def _normalize_agent_key(value: str) -> str:
    """归一化用户输入的数字人名称。"""

    return value.strip().lower()


def _load_agent_profile(path: Path) -> AgentProfile:
    """读取并校验单个数字人 JSON。"""

    data = json.loads(path.read_text(encoding="utf-8"))
    _require_keys(
        data,
        path,
        {
            "agent_id",
            "kind",
            "seat",
            "display_name",
            "model",
            "digital_human",
            "game_task",
            "constraints",
        },
    )
    model_data = _dict_value(data, "model", path)
    human_data = _dict_value(data, "digital_human", path)
    return AgentProfile(
        agent_id=str(data["agent_id"]),
        kind=str(data["kind"]),
        seat=int(data["seat"]),
        display_name=str(data["display_name"]),
        model=AgentModelProfile(
            provider=_optional_text(model_data.get("provider")),
            name=_optional_text(model_data.get("name")),
            temperature=_optional_float(model_data.get("temperature")),
            thinking=_optional_text(model_data.get("thinking")),
        ),
        digital_human=DigitalHumanProfile(
            core_identity=_optional_dict(human_data.get("core_identity"), path, "core_identity"),
            behavioral_traits=_optional_dict(
                human_data.get("behavioral_traits"),
                path,
                "behavioral_traits",
            ),
            linguistic_profile=_optional_dict(
                human_data.get("linguistic_profile"),
                path,
                "linguistic_profile",
            ),
            strategic_gameplay=_optional_dict(
                human_data.get("strategic_gameplay"),
                path,
                "strategic_gameplay",
            ),
            thought_process_and_examples=_optional_dict(
                human_data.get("thought_process_and_examples"),
                path,
                "thought_process_and_examples",
            ),
            summary=str(human_data.get("summary", "")),
            task_personality=str(human_data.get("task_personality", "")),
            table_presence=str(human_data.get("table_presence", "")),
            speaking_style=str(human_data.get("speaking_style", "")),
            speech_habits=_string_list(
                human_data.get("speech_habits", []),
                path,
                "speech_habits",
            ),
            strengths=_string_list(human_data.get("strengths", []), path, "strengths"),
            weaknesses=_string_list(human_data.get("weaknesses", []), path, "weaknesses"),
            speech_examples=_string_list(
                human_data.get("speech_examples", []),
                path,
                "speech_examples",
            ),
        ),
        game_task={
            str(key): str(value)
            for key, value in _dict_value(data, "game_task", path).items()
        },
        constraints=_string_list(data["constraints"], path, "constraints"),
    )


def _require_keys(data: dict[str, Any], path: Path, required: set[str]) -> None:
    """检查 JSON object 是否包含必需字段。"""

    missing = required - set(data)
    if missing:
        raise ValueError(f"{path} missing keys: {sorted(missing)}")


def _dict_value(data: dict[str, Any], key: str, path: Path) -> dict[str, Any]:
    """读取 dict 字段并做类型校验。"""

    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{path} field {key!r} must be object")
    return value


def _optional_dict(value: Any, path: Path, key: str) -> dict[str, Any]:
    """读取可选 dict 字段并做类型校验。"""

    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} field {key!r} must be object")
    return dict(value)


def _string_list(value: Any, path: Path, key: str) -> list[str]:
    """读取字符串列表字段并做类型校验。"""

    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{path} field {key!r} must be list[str]")
    return list(value)


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


PROFILE_LABELS = {
    "anti_AI_guidelines": "反 AI 腔约束",
    "archetype": "角色原型",
    "behavioral_traits": "行为特征",
    "catching_logic_leap": "抓逻辑跳步示例",
    "cold_humor_comment": "冷幽默示例",
    "core_identity": "核心身份",
    "core_motivation": "核心动机",
    "data_driven_deduction": "数据反推示例",
    "defending_against_accusation": "被攻击时防守示例",
    "front_position_conservative": "前置位保守发言示例",
    "inner_monologue_guideline": "隐性思考指引",
    "interaction_dynamics": "互动动态",
    "linguistic_profile": "语言风格",
    "situational_responses": "局势反应",
    "speaking_style": "说话风格",
    "speech_examples": "自然发言示例",
    "speech_habits": "说话习惯",
    "strategic_gameplay": "局内策略",
    "strengths": "擅长",
    "table_presence": "场上存在感",
    "task_personality": "任务个性",
    "thought_process_and_examples": "思考流程与示例",
    "to_aggressive_players": "面对强势玩家",
    "to_logical_players": "面对逻辑玩家",
    "vibe": "整体气质",
    "weaknesses": "弱点",
    "when_accused": "被攻击时",
    "when_interrupted": "被打断时",
    "when_playing_good": "拿好人身份时",
    "when_playing_werewolf": "拿狼人身份时",
}


def _format_profile_value(value: Any, *, indent: int = 0) -> list[str]:
    """把嵌套数字人配置格式化成 prompt 行。"""

    prefix = "  " * indent + "- "
    child_indent = indent + 1
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            label = _profile_label(str(key))
            if isinstance(item, dict):
                lines.append(f"{prefix}{label}：")
                lines.extend(_format_profile_value(item, indent=child_indent))
            elif isinstance(item, list):
                lines.append(f"{prefix}{label}：")
                lines.extend(_format_profile_value(item, indent=child_indent))
            else:
                text = str(item).strip()
                if text:
                    lines.append(f"{prefix}{label}：{text}")
        return lines
    if isinstance(value, list):
        return [
            f"{prefix}{str(item).strip()}"
            for item in value
            if str(item).strip()
        ]
    text = str(value).strip()
    return [f"{prefix}{text}"] if text else []


def _profile_label(key: str) -> str:
    """把数字人配置字段名转换成 prompt 里更自然的中文标签。"""

    return PROFILE_LABELS.get(key, key)
