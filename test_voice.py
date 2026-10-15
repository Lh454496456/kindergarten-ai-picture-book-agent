# -*- coding: utf-8 -*-
"""
test_voice.py —— 语音模块降级逻辑测试
"""

from __future__ import annotations

import sys
import os
import wave
import io
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.voice_assistant import VoiceAssistant, _make_silence_wav

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} :: {detail}")
        print(f"  ❌ {name}  -- {detail}")


def test_mock_fallback():
    os.environ["VOICE_MOCK"] = "1"
    empty_cfg = SimpleNamespace(VOICE_APP_ID="", VOICE_ACCESS_TOKEN="", ASR_MODEL_NAME="", TTS_VOICE_TYPE="")
    va = VoiceAssistant(config=empty_cfg)
    check("backend=mock", va.backend_name() == "mock", va.backend_name())
    check("available()=False", va.available() is False)
    text = va.transcribe(b"fake-audio")
    check("mock transcribe 返回固定句", text == VoiceAssistant.MOCK_TRANSCRIPT, repr(text))
    wav_bytes = va.synthesize("你好呀小兔")
    check("synthesize 返回 wav", isinstance(wav_bytes, bytes) and len(wav_bytes) > 44)
    os.environ.pop("VOICE_MOCK", None)


def test_volc_backend():
    volc_cfg = SimpleNamespace(
        VOICE_APP_ID="1234567890", VOICE_ACCESS_TOKEN="fake-token",
        ASR_MODEL_NAME="bigmodel", TTS_VOICE_TYPE="BV700_streaming",
    )
    os.environ.pop("VOICE_MOCK", None)
    va = VoiceAssistant(config=volc_cfg)
    check("backend=volc", va.backend_name() == "volc", va.backend_name())
    check("available()=True", va.available() is True)
    check("volc transcribe 占位不崩", isinstance(va.transcribe(b"x"), str))
    check("volc synthesize 返回 wav", len(va.synthesize("你好")) > 44)


def test_edge():
    os.environ["VOICE_MOCK"] = "1"
    va = VoiceAssistant(config=SimpleNamespace())
    check("空音频返回空串", va.transcribe(b"") == "")
    check("超大音频不崩", va.transcribe(b"\x00" * (11 * 1024 * 1024)) == "")
    check("超长文本 synthesize 不崩", len(va.synthesize("你好" * 500)) > 44)
    os.environ.pop("VOICE_MOCK", None)


def test_silence_wav():
    wav = _make_silence_wav(0.5)
    with wave.open(io.BytesIO(wav), "rb") as wf:
        check("静音 wav 采样率 16000", wf.getframerate() == 16000)
        check("静音 wav 单声道", wf.getnchannels() == 1)
        check("静音 wav 16bit", wf.getsampwidth() == 2)


def main():
    print("语音模块降级测试")
    test_mock_fallback()
    test_volc_backend()
    test_edge()
    test_silence_wav()
    print(f"\n通过：{PASS}  失败：{FAIL}")
    for f in FAILURES:
        print(f"  - {f}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
