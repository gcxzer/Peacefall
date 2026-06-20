from __future__ import annotations

"""每个数字人的长期记忆存储和 prompt 格式化。"""

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_MEMORY_DIR = Path("memories")
DEFAULT_MEMORY_LIMIT = 5


def append_memory_entry(
    memory_dir: str | Path,
    agent_id: str,
    entry: dict[str, Any],
) -> Path:
    """把一条赛后复盘记忆追加写入对应数字人的 JSONL 文件。"""

    path = memory_file_path(memory_dir, agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def load_memory_entries(
    memory_dir: str | Path,
    agent_id: str,
    *,
    role_set_id: str | None = None,
    limit: int = DEFAULT_MEMORY_LIMIT,
) -> list[dict[str, Any]]:
    """读取指定数字人在同一版型下最近的长期记忆。"""

    if limit <= 0:
        return []

    path = memory_file_path(memory_dir, agent_id)
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and _matches_role_set(payload, role_set_id):
            entries.append(payload)
    return entries[-limit:]


def format_memory_context(entries: list[dict[str, Any]]) -> str:
    """把长期记忆格式化成紧凑的玩家 prompt 段落。"""

    if not entries:
        return ""

    lines = [
        "历史复盘记忆：",
        "以下内容只代表过往对局经验，不代表本局真实身份、阵营或隐藏信息。",
        "你可以把它当成自己的长期经验和对手习惯参考，但必须以本局可见信息为准。",
    ]
    for entry in entries:
        self_info = _mapping(entry.get("self"))
        game_id = _text(entry.get("game_id"), "未知对局")
        role = _text(self_info.get("role"), "未知身份")
        result = _text(self_info.get("result"), "未知结果")
        lines.append(f"- 对局 {game_id}：你当时是{role}，结果：{result}。")

        for item in _list_of_mappings(entry.get("self_reflection")):
            lesson = _text(item.get("lesson"))
            adjustment = _text(item.get("future_adjustment"))
            if lesson:
                lines.append(f"  自我经验：{lesson}")
            if adjustment:
                lines.append(f"  下次调整：{adjustment}")

        for item in _list_of_mappings(entry.get("opponent_analysis")):
            opponent = _text(
                item.get("opponent_name"),
                "某位对手",
            )
            tendency = _text(item.get("observed_tendency"))
            strategy = _text(item.get("counter_strategy"))
            if tendency or strategy:
                lines.append(
                    f"  对手{opponent}：{tendency}"
                    + (f" 应对：{strategy}" if strategy else "")
                )

    return "\n".join(lines)


def memory_file_path(memory_dir: str | Path, agent_id: str) -> Path:
    """返回指定数字人的长期记忆 JSONL 文件路径。"""

    return Path(memory_dir) / f"{_safe_filename_token(agent_id)}.jsonl"


def _safe_filename_token(value: str) -> str:
    """把数字人 ID 转成适合文件名使用的安全片段。"""

    token = "".join(char if char.isalnum() else "-" for char in value).strip("-")
    token = re.sub(r"-+", "-", token)
    return token[:80] or "agent"


def _matches_role_set(entry: dict[str, Any], role_set_id: str | None) -> bool:
    """判断一条记忆是否属于当前版型。"""

    return role_set_id is None or entry.get("role_set_id") == role_set_id


def _mapping(value: Any) -> dict[str, Any]:
    """确保任意值以 dict 形式参与后续读取。"""

    return value if isinstance(value, dict) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    """从任意值中提取 dict 列表，忽略不合法项目。"""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any, default: str = "") -> str:
    """把任意值转换成去掉首尾空白的文本。"""

    text = str(value or "").strip()
    return text or default
