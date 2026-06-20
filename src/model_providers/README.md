# model_providers

`model_providers` 负责把不同 LLM provider 包装成 LangChain 可用的聊天模型。

## 支持的 provider

- `codex`：读取 Codex 本地认证信息。
- `aliyun`：使用阿里云百炼 OpenAI 兼容接口，默认模型 `qwen3.7-plus`。
- `openai`：使用 OpenAI API key。
- `deepseek`：使用 DeepSeek API key。

## 文件说明

- `config.py`：provider 名称归一化、默认模型、环境变量读取。
- `factory.py`：根据 `ModelProviderConfig` 创建对应聊天模型。
- `aliyun_provider.py`：阿里云百炼千问模型接入。
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

默认 provider 是 `aliyun`。

## 阿里云超时配置

阿里云百炼偶发响应较慢时，可能出现 `APITimeoutError: Request timed out`。阿里云 provider
默认 timeout 是 180 秒，默认重试 3 次；也可以在 `.env` 里单独调整：

```env
ALIYUN_LLM_TIMEOUT=240
ALIYUN_LLM_MAX_RETRIES=4
```

通用变量 `PINGAN_YE_LLM_TIMEOUT` 和 `PINGAN_YE_LLM_MAX_RETRIES` 仍然可用；如果同时设置了
阿里云专用变量和通用变量，阿里云专用变量优先生效。
