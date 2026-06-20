# memory

`memory` 负责每个数字人的长期复盘记忆。
赛后反思模型由根目录 `config.json` 的 `reflection.model` 配置统一指定。

## 文件说明

- `store.py`：按 agent 写入和读取 JSONL 记忆，并把最近记忆格式化成玩家 prompt 片段。
- `reflection.py`：游戏结束后调用专用赛后复盘 agent，生成自我反思、对手分析和证据索引。

## 设计边界

根目录 `agents/*.json` 是静态数字人设定，不写入动态对局经验。
长期记忆默认写入 `memories/{agent_id}.jsonl`，每行是一局游戏的赛后复盘。

长期记忆可以帮助玩家参考历史经验，但不能替代本局可见信息。写入内容应当是可迁移经验、行为倾向和应对策略，不应把上一局身份当成下一局事实。
