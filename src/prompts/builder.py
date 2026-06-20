from __future__ import annotations

from pathlib import Path

from prompts.templates import JUDGE_AGENT_PROMPT, PLAYER_AGENT_PROMPT
from roles import RoleSet


COMMON_BACKGROUND_PATH = Path("docs/common/background-knowledge.md")
ROLE_SETS_DIR = Path("docs/role-sets")
JUDGE_FLOWS_DIR = Path("docs/judge-flows")


def build_player_prompt(
    player_id: int,
    role_set: RoleSet,
    private_context: str,
    *,
    display_name: str | None = None,
    digital_human_context: str = "",
    memory_context: str = "",
) -> str:
    """组装玩家 agent 的完整提示词。

    玩家会读取通用背景、当前版型说明和自己的私有身份信息。
    """

    sections = [
        _read_text(COMMON_BACKGROUND_PATH),
        _read_text(_role_set_path(role_set)),
        _optional_section(digital_human_context),
        _optional_section(memory_context),
        _private_section(private_context),
        PLAYER_AGENT_PROMPT.format(
            player_id=player_id,
            display_name=display_name or f"{player_id} 号玩家",
            role_set_name=role_set.name,
            role_set_id=role_set.id,
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def build_judge_prompt(
    role_set: RoleSet,
    private_context: str,
    *,
    digital_human_context: str = "",
) -> str:
    """组装法官 agent 的完整提示词。

    法官额外读取 judge-flows 下的流程说明，并拥有完整身份表。
    """

    sections = [
        _read_text(COMMON_BACKGROUND_PATH),
        _read_text(_role_set_path(role_set)),
        _read_text(JUDGE_FLOWS_DIR / f"{role_set.id}.md"),
        _optional_section(digital_human_context),
        _private_section(private_context),
        JUDGE_AGENT_PROMPT.format(
            role_set_name=role_set.name,
            role_set_id=role_set.id,
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def _role_set_path(role_set: RoleSet) -> Path:
    """返回某个版型对应的文档路径。"""

    return ROLE_SETS_DIR / f"{role_set.id}.md"


def _read_text(path: Path) -> str:
    """读取可选文档；不存在时返回空字符串。"""

    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _private_section(private_context: str) -> str:
    """把本局私有信息包装成 prompt 段落。"""

    if not private_context.strip():
        return ""
    return f"本局私有信息：\n{private_context.strip()}"


def _optional_section(content: str) -> str:
    """返回可选 prompt 段落。"""

    return content.strip()
