# -*- coding: utf-8 -*-
"""
EvaluationEngine —— 形成性观察记录引擎
======================================
对一次活动中的幼儿对话记录做分析：
  - 不调用 LLM 时：用规则统计（发言次数、主动提问次数、情绪词等）；
  - 调用 LLM 时：让模型从教师视角生成观察评语。

设计目标：给老师一份"可直接抄到观察手册上"的简短记录。
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_FILE = PROJECT_ROOT / "prompts" / "system_prompt.md"

# 简单的情绪词表（规则统计用）
POSITIVE_WORDS = ["开心", "高兴", "喜欢", "好玩", "笑", "棒", "可爱", "想要", "好"]
NEGATIVE_WORDS = ["害怕", "怕", "不喜欢", "讨厌", "难过", "哭", "不要", "不想"]
QUESTION_HINTS = ("吗", "呢", "为什么", "怎么", "什么", "？", "?")


@dataclass
class ObservationRecord:
    child_anonymous_id: str
    message_count: int
    question_count: int
    positive_count: int
    negative_count: int
    interest_level: int            # 1-5
    language_observation: str
    social_observation: str
    teacher_note_suggestion: str
    extra_stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class EvaluationEngine:
    """对话记录 → 形成性观察记录。"""

    def __init__(self, llm: Optional[LLMClient] = None, use_llm: bool = True) -> None:
        """
        :param llm: 大模型客户端；use_llm=False 时可不传。
        :param use_llm: True=用 LLM 写教师评语；False=纯规则统计。
        """
        self.use_llm = use_llm and llm is not None
        self.llm = llm
        self.system_prompt = self._read_text(SYSTEM_FILE, optional=True) + (
            "\n\n你现在是一位有经验的幼儿园主班老师，正在为一次活动写形成性观察记录。"
            "请用教师视角、客观、具体的语言，不要夸大、不要贴标签。"
        )

    @staticmethod
    def _read_text(path: Path, optional: bool = False) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if optional:
                return ""
            raise

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        observation_log: List[Dict[str, Any]],
        child_label: Optional[str] = None,
    ) -> ObservationRecord:
        """
        :param observation_log: DialogueAgent.state.observation_log
                                每条形如 {"child_msg": "...", "agent_reply": "...",
                                          "advance_plot": bool, "domain_tag": "...", ...}
        :param child_label: 指定匿名 ID，否则随机生成"幼儿A/B/C"
        """
        if not observation_log:
            raise ValueError("观察记录为空，无法评估。")

        stats = self._rule_based_stats(observation_log)
        child_id = child_label or self._random_label()

        language_obs = self._rule_language_observation(stats)
        social_obs = self._rule_social_observation(observation_log, stats)
        interest = self._guess_interest(stats)
        note = self._rule_teacher_note(stats)

        if self.use_llm:
            try:
                llm_note = self._llm_synthesize(observation_log, stats)
                language_obs = llm_note.get("language_observation", language_obs) or language_obs
                social_obs = llm_note.get("social_observation", social_obs) or social_obs
                note = llm_note.get("teacher_note_suggestion", note) or note
                interest = int(llm_note.get("interest_level", interest)) or interest
            except RuntimeError as e:
                logger.warning("LLM 评语生成失败，回退到规则结果：%s", e)

        return ObservationRecord(
            child_anonymous_id=child_id,
            message_count=stats["message_count"],
            question_count=stats["question_count"],
            positive_count=stats["positive_count"],
            negative_count=stats["negative_count"],
            interest_level=max(1, min(5, interest)),
            language_observation=language_obs,
            social_observation=social_obs,
            teacher_note_suggestion=note,
            extra_stats=stats,
        )

    # ------------------------------------------------------------------ #
    # 规则统计
    # ------------------------------------------------------------------ #
    def _rule_based_stats(self, log: List[Dict[str, Any]]) -> Dict[str, Any]:
        messages = [item.get("child_msg", "") for item in log if item.get("child_msg")]
        text = " ".join(messages)
        message_count = len(messages)
        question_count = sum(1 for m in messages if any(h in m for h in QUESTION_HINTS))
        positive_count = sum(text.count(w) for w in POSITIVE_WORDS)
        negative_count = sum(text.count(w) for w in NEGATIVE_WORDS)
        advance_count = sum(1 for item in log if item.get("advance_plot"))
        domain_tags = [item.get("domain_tag", "") for item in log if item.get("domain_tag")]
        return {
            "message_count": message_count,
            "question_count": question_count,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "advance_count": advance_count,
            "domain_tags": domain_tags,
            "avg_msg_len": round(sum(len(m) for m in messages) / max(message_count, 1), 1),
        }

    @staticmethod
    def _rule_language_observation(stats: Dict[str, Any]) -> str:
        if stats["message_count"] == 0:
            return "本轮活动中幼儿未主动发言。"
        parts = [f"全程共发言 {stats['message_count']} 次"]
        if stats["question_count"] > 0:
            parts.append(f"主动提问 {stats['question_count']} 次")
        parts.append(f"平均句长约 {stats['avg_msg_len']} 字")
        return "，".join(parts) + "。"

    @staticmethod
    def _rule_social_observation(log: List[Dict[str, Any]], stats: Dict[str, Any]) -> str:
        tags = stats.get("domain_tags", [])
        if not tags:
            return "对话中主要涉及语言领域的回应。"
        # 统计最常见的标签
        from collections import Counter
        top = Counter(tags).most_common(1)[0]
        return f"本轮对话中，AI 角色主要支持的领域为「{top[0]}」（共出现 {top[1]} 次）。"

    @staticmethod
    def _guess_interest(stats: Dict[str, Any]) -> int:
        """基于发言次数 / 提问次数 / 正负情绪粗估兴趣度（1-5）。"""
        score = 3
        score += min(stats["message_count"], 5) // 3
        score += min(stats["question_count"], 3)
        score += 1 if stats["positive_count"] > stats["negative_count"] else -1
        return max(1, min(5, score))

    @staticmethod
    def _rule_teacher_note(stats: Dict[str, Any]) -> str:
        notes = []
        if stats["question_count"] >= 3:
            notes.append("幼儿好奇心强，可在区角继续延伸。")
        if stats["negative_count"] > stats["positive_count"]:
            notes.append("幼儿情绪偏消极，建议课后单独关心。")
        if stats["message_count"] <= 2:
            notes.append("幼儿参与度较低，建议下次用手偶或游戏单独邀请。")
        if not notes:
            notes.append("幼儿参与稳定，可继续保持当前活动节奏。")
        return " ".join(notes)

    @staticmethod
    def _random_label() -> str:
        return f"幼儿{random.choice(['A', 'B', 'C', 'D', 'E'])}"

    # ------------------------------------------------------------------ #
    # LLM 综合评语
    # ------------------------------------------------------------------ #
    def _llm_synthesize(
        self,
        log: List[Dict[str, Any]],
        stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        """让 LLM 在规则统计基础上，生成教师视角的、更具体的观察评语。"""
        user_msg = json.dumps(
            {
                "observation_log": log,
                "rule_based_stats": stats,
            },
            ensure_ascii=False,
        )
        system = (
            self.system_prompt
            + "\n\n请只输出合法 JSON，结构如下：\n"
            + '{"language_observation": "...", "social_observation": "...", '
            + '"interest_level": 1-5 的整数, "teacher_note_suggestion": "..."}'
        )
        raw = self.llm.chat_json(system_prompt=system, user_message=user_msg, temperature=0.3)
        return {
            "language_observation": raw.get("language_observation", ""),
            "social_observation": raw.get("social_observation", ""),
            "interest_level": int(raw.get("interest_level", 3)),
            "teacher_note_suggestion": raw.get("teacher_note_suggestion", ""),
        }
