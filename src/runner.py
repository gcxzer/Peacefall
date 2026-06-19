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
from engine.message_log import GameRecord, MessageLogEntry
from role_set_engines.six_player_classic import run_game
from roles import get_role_set


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
    )
    logger.info("本局玩家：%s", format_selected_players(agents.player_profiles))

    if show_identities:
        logger.info(agents.assignment.judge_private_context())

    return run_game(
        agents,
        max_rounds=max_rounds,
        on_message=on_message,
    )


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
    parser.add_argument("--show-identities", action="store_true", help="打印完整身份分配，仅用于调试。")
    return parser.parse_args()


if __name__ == "__main__":
    main()


# uv run python main.py --list-agents
# uv run python main.py --seed 1 --max-rounds 3
# uv run python main.py --show-identities
# uv run python main.py --agent-names 沈澈,陆星野 --seed 1
