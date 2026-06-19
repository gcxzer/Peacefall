# model_providers

`model_providers` 负责把不同 LLM provider 包装成 LangChain 可用的聊天模型。

## 支持的 provider

- `codex`：读取 Codex 本地认证信息。
- `openai`：使用 OpenAI API key。
- `deepseek`：使用 DeepSeek API key。

## 文件说明

- `config.py`：provider 名称归一化、默认模型、环境变量读取。
- `factory.py`：根据 `ModelProviderConfig` 创建对应聊天模型。
- `codex_provider.py`：Codex 模型接入。
- `codex_auth.py`：Codex 本地认证信息读取。
- `openai_provider.py`：OpenAI 模型接入。
- `deepseek_provider.py`：DeepSeek 模型接入。

## 配置优先级

玩家模型配置通常来自根目录 `agents/*.json`。如果某个字段没有写，才会回落到环境变量或 provider 默认值。

模型配置通常按这个顺序生效：

1. 数字人 JSON 里的模型偏好。
2. 环境变量。
3. provider 默认模型。

默认 provider 是 `deepseek`。