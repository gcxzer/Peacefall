# src

`src` 是项目的 Python 源码目录。这里的代码分成三类：

- 通用基础设施：`engine/`、`model_providers/`、`prompts/`、`roles/`。
- agent 创建：`agents/`。
- 长期记忆：`memory/`。
- 可选输出：`tts/`。
- 具体游戏内容：`role_set_engines/`。

入口文件是 `runner.py`，它负责解析一局游戏所需的配置、创建 agents，并把游戏交给具体版型引擎运行。

## 本地验证

```bash
PYTHONPATH=src uv run python -m compileall main.py src
```
