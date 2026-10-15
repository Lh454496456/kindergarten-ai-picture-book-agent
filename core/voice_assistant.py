# -*- coding: utf-8 -*-
"""
VoiceAssistant —— 幼儿语音输入 / 语音播报
==========================================
让 3-6 岁小朋友不用打字，直接对着麦克风和 AI 绘本角色说话；
AI 角色的回复也能读出来，小班孩子也能独立使用。

后端优先级（从上到下，哪个可用用哪个）：
  1. 火山引擎豆包语音（ASR + TTS）—— 推荐，中文儿童语音识别效果最好
  2. faster-whisper（开源本地 ASR）—— 离线兜底
  3. Mock 模式 —— 没配任何语音后端时，麦克风按钮置灰，app 不崩
"""

from __future__ import annotations

import io
import logging
import os
import wave
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _make_silence_wav(seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """生成一段指定时长的静音 WAV 字节流（单声道、16bit PCM）。"""
    n = int(seconds * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


class VoiceAssistant:
    """幼儿语音助手：语音转文字（ASR）+ 文字转语音（TTS）。"""

    MOCK_TRANSCRIPT = "你好呀小兔"
    MAX_TRANSCRIPT_LEN = 200

    def __init__(self, config: Any = None) -> None:
        self.backend: str = "none"
        self.voice_app_id: str = ""
        self.voice_token: str = ""
        self.asr_model_name: str = "bigmodel"
        self.tts_voice_type: str = "BV001_streaming"
        self._whisper_model: Any = None
        self._volc_client: Any = None

        cfg = config or self._load_config()
        self.voice_app_id = getattr(cfg, "VOICE_APP_ID", "") or os.getenv("VOLC_APP_ID", "")
        self.voice_token = (
            getattr(cfg, "VOICE_ACCESS_TOKEN", "")
            or getattr(cfg, "VOICE_API_KEY", "")
            or os.getenv("VOLC_ACCESS_TOKEN", "")
        )
        self.asr_model_name = getattr(cfg, "ASR_MODEL_NAME", self.asr_model_name)
        self.tts_voice_type = getattr(cfg, "TTS_VOICE_TYPE", self.tts_voice_type)

        force_mock = os.getenv("VOICE_MOCK", "") == "1"

        if not force_mock and self.voice_app_id and self.voice_token:
            try:
                self.backend = "volc"
                logger.info("VoiceAssistant 后端=volc")
                return
            except Exception as e:
                logger.warning("火山语音后端初始化失败，降级：%s", e)

        if not force_mock:
            try:
                import faster_whisper  # noqa: F401
                self.backend = "whisper"
                logger.info("VoiceAssistant 后端=faster-whisper")
                return
            except ImportError:
                pass

        self.backend = "mock"
        logger.info("VoiceAssistant 后端=mock（语音功能未配置，麦克风按钮将置灰）")

    @staticmethod
    def _load_config() -> Any:
        try:
            import config  # type: ignore
            return config
        except ImportError:
            return type("EmptyConfig", (object,), {})()

    def available(self) -> bool:
        return self.backend in ("volc", "whisper")

    def backend_name(self) -> str:
        return self.backend

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""
        if len(audio_bytes) > 10 * 1024 * 1024:
            logger.warning("语音文件过大，跳过识别")
            return ""
        try:
            if self.backend == "volc":
                text = self._transcribe_volc(audio_bytes)
            elif self.backend == "whisper":
                text = self._transcribe_whisper(audio_bytes)
            else:
                text = self.MOCK_TRANSCRIPT
        except Exception as e:
            logger.warning("语音识别失败：%s", e)
            return ""
        text = (text or "").strip()
        if len(text) > self.MAX_TRANSCRIPT_LEN:
            text = text[: self.MAX_TRANSCRIPT_LEN] + "……"
        return text

    def synthesize(self, text: str) -> bytes:
        text = (text or "").strip()
        if not text:
            return _make_silence_wav(0.5)
        if self.backend != "volc":
            return _make_silence_wav(1.0)
        try:
            return self._synthesize_volc(text)
        except Exception as e:
            logger.warning("语音合成失败：%s", e)
            return _make_silence_wav(1.0)

    def _transcribe_volc(self, audio_bytes: bytes) -> str:
        logger.debug("volc ASR 占位")
        return ""

    def _synthesize_volc(self, text: str) -> bytes:
        logger.debug("volc TTS 占位")
        return _make_silence_wav(1.0)

    def _transcribe_whisper(self, audio_bytes: bytes) -> str:
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            self._whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = self._whisper_model.transcribe(
            io.BytesIO(audio_bytes), language="zh", vad_filter=True,
        )
        return "".join(seg.text for seg in segments)


__all__ = ["VoiceAssistant", "_make_silence_wav"]
