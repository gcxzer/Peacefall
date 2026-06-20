from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable

from agents.factory import create_game_agents
from agents.profiles import DEFAULT_AGENT_CONFIG_DIR
from agents.selection import (
    format_agent_pool,
    format_selected_players,
    parse_agent_names,
)
from engine.assignments import assign_roles
from engine.live_logging import configure_live_logging, log_live_message
from engine.message_listeners import combine_message_listeners
from engine.message_log import GameRecord, MessageLogEntry
from memory.reflection import REFLECTION_MODES, write_postgame_reflections
from memory.store import DEFAULT_MEMORY_DIR, DEFAULT_MEMORY_LIMIT
from role_set_engines.six_player_classic import run_game
from roles import get_role_set
from tts import ALIYUN_QWEN_TTS_PROVIDER, create_tts_listener


logger = logging.getLogger(__name__)


def run_game_once(
    *,
    role_set_id: str = "6p-classic",
    seed: int | None = None,
    agent_config_dir: str | Path = DEFAULT_AGENT_CONFIG_DIR,
    selected_agents: list[str] | None = None,
    max_rounds: int = 20,
    show_identities: bool = False,
    on_message: Callable[[MessageLogEntry], None] | None = None,
    tts_provider: str = "off",
    tts_output_dir: str | Path = "logs/audio",
    tts_voice_cache_path: str | Path = "logs/aliyun-qwen-voices.json",
    tts_include_judge: bool = False,
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
    memory_limit: int = DEFAULT_MEMORY_LIMIT,
    reflection_mode: str = "off",
) -> GameRecord:
    """创建 agents 并运行一局游戏。"""

    role_set = get_role_set(role_set_id)
    assignment = assign_roles(role_set, seed=seed)
    agents = create_game_agents(
        role_set,
        assignment,
        agent_config_dir=agent_config_dir,
        selected_agents=selected_agents,
        seed=seed,
        memory_dir=memory_dir,
        memory_limit=memory_limit,
    )
    logger.info("本局玩家：%s", format_selected_players(agents.player_profiles))

    if show_identities:
        logger.info(agents.assignment.judge_private_context())

    tts_listener = create_tts_listener(
        tts_provider,
        agents=agents,
        output_dir=tts_output_dir,
        voice_cache_path=tts_voice_cache_path,
        include_judge=tts_include_judge,
    )
    message_listener = combine_message_listeners(on_message, tts_listener)
    try:
        record = run_game(
            agents,
            max_rounds=max_rounds,
            on_message=message_listener,
        )
    finally:
        if tts_listener is not None:
            tts_listener.close()

    memory_paths = write_postgame_reflections(
        agents=agents,
        role_set=role_set,
        record=record,
        memory_dir=memory_dir,
        mode=reflection_mode,
    )
    if memory_paths:
        logger.info(
            "memory updated: %s",
            "、".join(sorted({str(path) for path in memory_paths})),
        )

    return record


def main() -> None:
    """命令行入口。"""

    configure_live_logging()
    args = _parse_args()
    if args.list_agents:
        logger.info(format_agent_pool(args.agents_dir))
        return

    record = run_game_once(
        role_set_id=args.role_set,
        seed=args.seed,
        agent_config_dir=args.agents_dir,
        selected_agents=parse_agent_names(args.agent_names),
        max_rounds=args.max_rounds,
        show_identities=args.show_identities,
        on_message=log_live_message,
        tts_provider=args.tts,
        tts_output_dir=args.tts_output_dir,
        tts_voice_cache_path=args.tts_voice_cache,
        tts_include_judge=args.tts_include_judge,
        memory_dir=args.memory_dir,
        memory_limit=args.memory_limit,
        reflection_mode=args.reflection,
    )
    logger.info("message log: %s", record.message_log_path)


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(description="开始一局狼人杀。")
    parser.add_argument("--role-set", default="6p-classic", help="版型 ID。")
    parser.add_argument("--seed", type=int, default=None, help="身份分配随机种子。")
    parser.add_argument("--max-rounds", type=int, default=20, help="最大轮次。")
    parser.add_argument("--agents-dir", default=str(DEFAULT_AGENT_CONFIG_DIR), help="数字人 JSON 配置目录。")
    parser.add_argument("--agent-names", action="append", default=[], help="指定本局使用的数字人，逗号分隔；不足人数时从数字人池随机补齐。例如：--agent-names 沈澈,陆星野")
    parser.add_argument("--list-agents", action="store_true", help="列出数字人池并退出，不开始游戏。")
    parser.add_argument("--show-identities", action="store_false", help="打印完整身份分配。")
    parser.add_argument("--tts", choices=["off", ALIYUN_QWEN_TTS_PROVIDER], default="off", help="启用文字转语音。aliyun-qwen 使用百炼 qwen3-tts-vd-2026-01-26。")
    parser.add_argument("--tts-output-dir", default="logs/audio", help="TTS 音频输出目录。")
    parser.add_argument("--tts-voice-cache", default="logs/aliyun-qwen-voices.json", help="阿里云声音设计 voice_id 缓存文件。")
    parser.add_argument("--tts-include-judge", action="store_true", help="同时为法官公告生成语音；默认只处理玩家白天发言。")
    parser.add_argument("--memory-dir", default=str(DEFAULT_MEMORY_DIR), help="长期复盘记忆 JSONL 目录。")
    parser.add_argument("--memory-limit", type=int, default=DEFAULT_MEMORY_LIMIT, help="每名玩家开局读取的最近复盘记忆条数；设为 0 可禁用读取。")
    parser.add_argument("--reflection", choices=REFLECTION_MODES, default="off", help="赛后反思写入模式；omniscient 使用完整身份和消息日志生成长期记忆。")
    return parser.parse_args()


if __name__ == "__main__":
    main()


# 常用运行示例
# uv run python main.py
# uv run python main.py --list-agents
# uv run python main.py --reflection omniscient
# uv run python main.py --tts aliyun-qwen --tts-include-judge
