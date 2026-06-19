# src

`src` 是项目的 Python 源码目录。这里的代码分成三类：

- 通用基础设施：`engine/`、`model_providers/`、`prompts/`、`roles/`。
- agent 创建：`agents/`。
- 具体游戏内容：`role_set_engines/`。

入口文件是 `runner.py`，它负责解析一局游戏所需的配置、创建 agents，并把游戏交给具体版型引擎运行。

## 模块边界

- `runner.py` 不写具体狼人杀流程。
- `agents/` 不写游戏规则，只负责数字人配置、模型和 LangChain agent 创建。
- `engine/` 只放跨版型可复用的组件。
- `role_set_engines/` 才放具体版型的阶段流程和规则结算。

## 本地验证

```bash
PYTHONPATH=src uv run python -m compileall main.py src
```
