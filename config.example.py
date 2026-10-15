# -*- coding: utf-8 -*-
"""
童心AI绘本馆 —— 配置示例文件
使用方法：cp config.example.py config.py，填入自己的 Key。
"""

# 一、大模型接入（OpenAI 兼容协议）
API_KEY = "在这里填你的-火山方舟-API-Key"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
MODEL_NAME = "doubao-seed-1-6-250615"

# 二、可选：模型生成参数
TEMPERATURE = 0.7
MAX_TOKENS = 2000
REQUEST_TIMEOUT = 60

# 三、应用运行配置
GRADIO_SERVER_PORT = 7860
GRADIO_SHARE = False

# 四、可选：幼儿语音输入 / 语音播报（ASR + TTS）
# 不配也能正常用，幼儿对话仍可由老师代打字。
# 申请：https://console.volcengine.com/speech/overview → 创建应用 → 勾选一句话识别+语音合成
VOICE_APP_ID = ""
VOICE_ACCESS_TOKEN = ""
ASR_MODEL_NAME = "bigmodel"
TTS_VOICE_TYPE = "BV700_streaming"

# 五、可选：本地兜底 ASR（faster-whisper，免费离线）
# pip install faster-whisper 后自动启用，不用改配置。
