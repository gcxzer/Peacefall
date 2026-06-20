# agents

这个目录负责把根目录 `agents/*.json` 里的数字人配置转成运行时可用的 LangChain agents。

## 文件说明

- `profiles.py`：读取和校验数字人 JSON 配置，生成 `AgentProfile`。
- `factory.py`：根据版型、身份分配和数字人配置创建法官 agent 与玩家 agents。

## 职责边界

这里不负责：

- 身份随机分配。
- 游戏阶段推进。
- 狼人杀规则结算。
- prompt 文档内容本身。

这里只负责：

- 加载玩家和法官数字人配置。
- 从数字人池中选择本局需要的玩家；可以全随机，也可以先指定一部分再随机补齐。
- 把选中的数字人重新映射成本局座位号。
- 读取 `kind: judge` 的法官配置；法官不进入玩家池，也不会被 `--list-agents` 列出。
- 根据数字人 JSON 配置创建聊天模型；如果模型名、temperature 或 thinking 没写，就交给环境变量和 provider 默认值决定。
- 把数字人的新版分块人设（核心身份、行为特征、语言风格、局内策略、思考流程与示例）接入玩家 prompt。
- 读取该数字人的长期复盘记忆，并以“历史经验，不代表本局事实”的形式接入玩家 prompt。
- 调用 `create_agent` 创建 LangChain agent。
- 把玩家 prompt 和法官 prompt 接入 agent。

根目录的 `agents/` 是数字人配置数据；`src/agents/` 是读取配置并创建运行时 agent 的代码。
JSON 里的 `seat` 是数字人池里的默认编号，不等于每局实际座位；实际座位由当局抽取结果决定。
法官配置使用 `kind: judge`，`seat` 固定为 `0`，只用于满足统一 JSON 结构，不参与玩家入座。
