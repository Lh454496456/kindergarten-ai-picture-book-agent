# -*- coding: utf-8 -*-
"""
test_extreme.py —— 极端输入与异常场景测试
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.voice_assistant import VoiceAssistant, _make_silence_wav
from core.dialogue_agent import DialogueAgent, DialogueState

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  -- {detail}")


class FakeLLMTimeout:
    def chat_json(self, *a, **kw):
        raise RuntimeError("模拟网络超时")


class FakeLLM:
    def chat_json(self, *a, **kw):
        return {"reply": "好呀", "advance_plot": False, "domain_tag": "语言", "teacher_note": ""}


def test_repeated_mic():
    os.environ["VOICE_MOCK"] = "1"
    va = VoiceAssistant(config=type("C", (), {})())
    texts = [va.transcribe(b"audio") for _ in range(10)]
    check("连续点麦克风 10 次都返回固定句", all(t == VoiceAssistant.MOCK_TRANSCRIPT for t in texts))
    os.environ.pop("VOICE_MOCK", None)


def test_oversized_transcript():
    va = VoiceAssistant.__new__(VoiceAssistant)
    va.backend = "whisper"
    va.voice_app_id = ""
    va.voice_token = ""
    va.asr_model_name = ""
    va.tts_voice_type = ""
    va._whisper_model = None
    va._volc_client = None
    va._transcribe_whisper = lambda audio_bytes: "你好呀" * 500
    truncated = va.transcribe(b"audio")
    check("超长识别文本被截断到 ≤202 字", len(truncated) <= 202, f"len={len(truncated)}")
    check("截断后末尾有省略号", truncated.endswith("……"), truncated[-10:])


def test_silent_audio():
    os.environ["VOICE_MOCK"] = "1"
    va = VoiceAssistant(config=type("C", (), {})())
    silent = _make_silence_wav(0.3)
    check("静音 wav 在 mock 模式返回固定句", va.transcribe(silent) == VoiceAssistant.MOCK_TRANSCRIPT)
    check("空 bytes 返回空串", va.transcribe(b"") == "")
    os.environ.pop("VOICE_MOCK", None)


def test_llm_timeout():
    agent = DialogueAgent(llm=FakeLLMTimeout())
    state = DialogueState(story_title="测试", character_name="小兔")
    resp = agent.respond(state, "你好呀")
    check("LLM 超时后返回兜底话术", "网络" in resp.reply or "问题" in resp.reply, repr(resp.reply))
    check("兜底话术写进 observation_log", len(state.observation_log) == 1)


def test_oversized_child_msg():
    agent = DialogueAgent(llm=FakeLLM())
    state = agent.start_session({"title": "测试", "characters": [{"name": "小兔"}]})
    resp = agent.respond(state, "我喜欢小汽车" * 200)
    check("超长消息不崩", bool(resp.reply))
    check("teacher_note 提示已截断", "截断" in resp.teacher_note, resp.teacher_note)


def main():
    print("极端输入测试")
    test_repeated_mic()
    test_oversized_transcript()
    test_silent_audio()
    test_llm_timeout()
    test_oversized_child_msg()
    print(f"\n通过：{PASS}  失败：{FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
