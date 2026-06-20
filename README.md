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

- `agents/`：12 个玩家数字人和 1 个法官数字人的 JSON 配置，包括名字、人设、模型偏好和局内行为边界。
- `config.json`：项目级配置，目前用于设置赛后反思模型。
- `docs/`：给 agent 读取的背景知识、版型说明和法官流程。
- `src/agents/`：读取数字人配置，创建模型和 LangChain agents。
- `src/engine/`：跨版型复用的游戏状态、身份分配、消息记录、agent 调用和通用结算工具。
- `src/model_providers/`：阿里云百炼、OpenAI、DeepSeek、Codex 模型接入。
- `src/memory/`：赛后反思、长期记忆 JSONL 读写和开局记忆注入。
- `src/prompts/`：prompt 模板和 prompt 组装逻辑。
- `src/role_set_engines/`：具体版型的游戏流程实现。
- `src/roles/`：角色、阵营和版型定义。
- `src/tts/`：文字转语音接入和音色缓存逻辑。

## 运行

```bash
uv run python main.py
```

常用参数：

```bash
uv run python main.py
uv run python main.py --list-agents
uv run python main.py --reflection omniscient
uv run python main.py --tts aliyun-qwen --tts-include-judge
```

6 人版型会从 `agents/` 数字人池中抽取 6 名玩家。可以完全随机，也可以用`--agent-names` 指定任意数量的数字人，剩余座位会从池子里随机补齐。指定顺序就是本局入座顺序。


## 日志

每局游戏会生成独立的 JSONL 消息日志，默认写入 `logs/messages/messages-时间戳.jsonl`。日志记录 agent 输入输出、公开消息、工具结果和私聊消息。

仓库里的 `examples/logs/20260620-133318/` 放了一份示例产出：`messages/` 里是完整 JSONL 消息流水，`audio/` 里是对应的 TTS 音频和 `manifest.jsonl`。

## 长期记忆

可以在赛后为每个玩家生成私人复盘记忆：

```bash
uv run python main.py --reflection omniscient
```

`omniscient` 会在游戏结束后读取完整身份和消息日志，为每个数字人写入 `memories/{agent_id}.jsonl`。每条记忆包含对局基本信息、自我反思、对手分析和消息 index 证据。开局创建玩家 prompt 时会自动读取当前版型最近 5 条历史记忆；可用 `--memory-limit 0` 禁用读取，或用 `--memory-dir` 指定目录。

赛后反思使用根目录 `config.json` 中的 `reflection.model` 配置，不跟随玩家自己的模型偏好：

```json
{
  "reflection": {
    "model": {
      "provider": "aliyun",
      "name": "qwen3.7-plus",
      "temperature": null,
      "thinking": null
    }
  }
}
```

## 语音合成

可以用阿里云百炼 Qwen3-TTS 为玩家白天公开发言生成语音：

```bash
uv run python main.py --tts aliyun-qwen --tts-include-judge
```

需要在 `.env` 中配置 `DASHSCOPE_API_KEY`。
代码入口在 `src/tts/`，由 runner 按 `--tts` 参数创建消息监听器。

推荐的 TTS 配置：

```env
DASHSCOPE_API_KEY=你的百炼 API Key
ALIYUN_TTS_MODEL=qwen3-tts-vd-2026-01-26
ALIYUN_VOICE_DESIGN_MODEL=qwen-voice-design
```
