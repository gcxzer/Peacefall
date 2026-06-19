# 平安夜

平安夜是一个多 agent 狼人杀项目。当前仅实现 6 人经典版型。

## 当前版型

当前可运行版型是 `6p-classic`：

- 狼人：2 名
- 平民：2 名
- 预言家：1 名
- 女巫：1 名

版型说明放在 `docs/role-sets/`，法官流程说明放在 `docs/judge-flows/`，通用背景知识放在 `docs/common/`。

## 目录结构

- `agents/`：12 个玩家数字人的 JSON 配置，包括名字、人设、模型偏好和局内行为边界。
- `docs/`：给 agent 读取的背景知识、版型说明和法官流程。
- `src/agents/`：读取数字人配置，创建模型和 LangChain agents。
- `src/engine/`：跨版型复用的游戏状态、身份分配、消息记录、agent 调用和通用结算工具。
- `src/model_providers/`：OpenAI、DeepSeek、Codex 模型接入。
- `src/prompts/`：prompt 模板和 prompt 组装逻辑。
- `src/role_set_engines/`：具体版型的游戏流程实现。
- `src/roles/`：角色、阵营和版型定义。

## 运行

```bash
uv run python main.py
```

常用参数：

```bash
uv run python main.py --seed 1 --max-rounds 3
uv run python main.py --show-identities
uv run python main.py --list-agents
uv run python main.py --agent-names 沈澈,陆星野 --seed 1
```

6 人版型会从 `agents/` 数字人池中抽取 6 名玩家。可以完全随机，也可以用
`--agent-names` 指定任意数量的数字人，剩余座位会从池子里随机补齐。指定顺序就是
本局入座顺序。

## 日志

每局游戏会生成独立的 JSONL 消息日志，默认写入 `logs/messages-时间戳.jsonl`。日志记录 agent 输入输出、公开消息、工具结果和私聊消息，不记录 system prompt。

