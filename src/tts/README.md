# tts

`tts` 负责可选的文字转语音输出，目前接入阿里云百炼 Qwen3-TTS，并维护音色缓存和音频 manifest。

`factory.py` 创建 TTS 消息监听器，`aliyun_qwen.py` 处理阿里云请求、音色生成和音频文件写入。
