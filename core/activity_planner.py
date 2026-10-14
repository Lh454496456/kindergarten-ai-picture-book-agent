# -*- coding: utf-8 -*-
"""
ActivityPlanner —— 活动方案生成器
==================================
输入一本绘本 JSON + 年龄段，输出一份符合幼儿园集体教学规范的活动方案。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = PROJECT_ROOT / "prompts" / "activity_planner.md"
EXAMPLES_FILE = PROJECT_ROOT / "knowledge_base" / "activity_examples.md"


@dataclass
class ActivityPlan:
    activity_name: str
    target_age: str
    duration: int
    goals: Dict[str, List[str]]
    materials: List[str]
    process: List[Dict[str, Any]]
    extension_games: List[str]
    home_school_cooperation: List[str]
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity_name": self.activity_name,
            "target_age": self.target_age,
            "duration": self.duration,
            "goals": self.goals,
            "materials": self.materials,
            "process": self.process,
            "extension_games": self.extension_games,
            "home_school_cooperation": self.home_school_cooperation,
        }


class ActivityPlanner:
    """根据绘本生成集体教学活动方案。"""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()
        self.system_prompt = self._read_text(PROMPT_FILE)
        examples = self._read_text(EXAMPLES_FILE, optional=True)
        if examples:
            self.system_prompt += "\n\n## 附：典型活动案例参考（请保持相同结构与颗粒度）\n\n" + examples

    @staticmethod
    def _read_text(path: Path, optional: bool = False) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if optional:
                logger.warning("案例库缺失：%s", path)
                return ""
            raise

    def plan(self, story: Dict[str, Any], age_group: str = "中班 4-5 岁") -> ActivityPlan:
        """
        根据绘本生成活动方案。

        :param story: StoryGenerator 输出的 dict（或 StoryResult.to_dict()）
        :param age_group: 目标年龄段
        """
        if not story or not story.get("title"):
            raise ValueError("绘本内容不完整，无法生成活动方案。")

        user_msg = json.dumps(
            {"story": story, "target_age": age_group},
            ensure_ascii=False,
        )
        logger.info("开始为绘本《%s》生成活动方案（%s）", story.get("title"), age_group)

        raw = self.llm.chat_json(
            system_prompt=self.system_prompt,
            user_message=user_msg,
            temperature=0.6,
        )
        return self._parse(raw)

    @staticmethod
    def _parse(raw: Dict[str, Any]) -> ActivityPlan:
        try:
            return ActivityPlan(
                activity_name=raw["activity_name"],
                target_age=raw.get("target_age", ""),
                duration=int(raw.get("duration", 20)),
                goals=raw.get("goals", {}) or {},
                materials=raw.get("materials", []) or [],
                process=raw.get("process", []) or [],
                extension_games=raw.get("extension_games", []) or [],
                home_school_cooperation=raw.get("home_school_cooperation", []) or [],
                raw=raw,
            )
        except KeyError as e:
            raise RuntimeError(f"活动方案结果缺少必要字段：{e}") from e
