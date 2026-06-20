# prompts

`prompts` 负责 prompt 模板和 prompt 组装。这里放代码，不放 Markdown prompt 文档。

## 文件说明

- `templates.py`：短模板字符串，例如玩家基础 prompt、法官基础 prompt、私有身份上下文模板。
- `builder.py`：读取 `docs/` 和数字人配置，把多个 prompt 片段组装成最终 system prompt。

## Prompt 来源

玩家 prompt 当前由以下内容组成：

- `docs/common/background-knowledge.md`
- `docs/role-sets/{role_set_id}.md`
- 玩家数字人设定
- 玩家本局私有身份信息
- 玩家基础任务模板

法官 prompt 当前由以下内容组成：

- `docs/common/background-knowledge.md`
- `docs/role-sets/{role_set_id}.md`
- `docs/judge-flows/{role_set_id}.md`
- 法官完整身份信息
- 法官基础任务模板