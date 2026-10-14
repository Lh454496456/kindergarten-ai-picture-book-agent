# -*- coding: utf-8 -*-
"""
StoryGenerator —— 绘本故事生成器
================================
根据教师输入的主题、年龄段、希望融合的领域标签，调用大模型生成结构化绘本脚本。
输出为 JSON：{title, characters, story_text, scenes, educational_goals}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient

logger = logging.getLogger(__name__)

# 项目根目录（core/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = PROJECT_ROOT / "prompts" / "story_generator.md"
GUIDE_FILE = PROJECT_ROOT / "knowledge_base" / "five_domains_guide.md"

VALID_AGE_GROUPS = {"小班 3-4 岁", "中班 4-5 岁", "大班 5-6 岁"}
VALID_DOMAINS = {"健康", "语言", "社会", "科学", "艺术"}


@dataclass
class Scene:
    scene_no: int
    text: str
    illustration_prompt: str
    domain_tags: List[str] = field(default_factory=list)


@dataclass
class StoryResult:
    title: str
    characters: List[Dict[str, str]]
    story_text: str
    scenes: List[Scene]
    educational_goals: Dict[str, List[str]]
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "characters": self.characters,
            "story_text": self.story_text,
            "scenes": [s.__dict__ for s in self.scenes],
            "educational_goals": self.educational_goals,
        }


class StoryGenerator:
    """根据主题与年龄段生成绘本脚本。"""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()
        self.system_prompt = self._read_text(PROMPT_FILE)
        # 把五大领域指南作为参考资料拼在系统提示词后面
        guide = self._read_text(GUIDE_FILE, optional=True)
        if guide:
            self.system_prompt += "\n\n## 附：五大领域发展目标速查（生成时请对齐年龄段）\n\n" + guide

    @staticmethod
    def _read_text(path: Path, optional: bool = False) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if optional:
                logger.warning("知识库文件缺失：%s", path)
                return ""
            raise

    def generate(
        self,
        theme: str,
        age_group: str = "中班 4-5 岁",
        domain_tags: Optional[List[str]] = None,
    ) -> StoryResult:
        """
        生成绘本脚本。

        :param theme: 教育主题，如"分享玩具"
        :param age_group: 小班 3-4 岁 / 中班 4-5 岁 / 大班 5-6 岁
        :param domain_tags: 希望融合的领域标签，默认 ["语言", "社会"]
        """
        # 参数校验
        theme = (theme or "").strip()
        if not theme:
            raise ValueError("主题不能为空，请填写例如'分享玩具'。")
        if age_group not in VALID_AGE_GROUPS:
            raise ValueError(f"年龄段必须是 {sorted(VALID_AGE_GROUPS)} 之一，收到：{age_group}")
        domain_tags = domain_tags or ["语言", "社会"]
        bad = [d for d in domain_tags if d not in VALID_DOMAINS]
        if bad:
            raise ValueError(f"领域标签必须来自 {sorted(VALID_DOMAINS)}，收到非法值：{bad}")

        user_msg = json.dumps(
            {"theme": theme, "age_group": age_group, "domain_tags": domain_tags},
            ensure_ascii=False,
        )
        logger.info("开始生成绘本：theme=%s, age=%s, tags=%s", theme, age_group, domain_tags)

        raw = self.llm.chat_json(
            system_prompt=self.system_prompt,
            user_message=user_msg,
            temperature=0.8,
        )
        return self._parse_result(raw)

    @staticmethod
    def _parse_result(raw: Dict[str, Any]) -> StoryResult:
        """把模型返回的 dict 整理成 StoryResult，做基础字段校验。"""
        try:
            title = raw["title"]
            story_text = raw["story_text"]
        except KeyError as e:
            raise RuntimeError(f"绘本结果缺少必要字段：{e}") from e

        characters = raw.get("characters", []) or []
        scenes_raw = raw.get("scenes", []) or []
        scenes = [
            Scene(
                scene_no=s.get("scene_no", i + 1),
                text=s.get("text", ""),
                illustration_prompt=s.get("illustration_prompt", ""),
                domain_tags=s.get("domain_tags", []) or [],
            )
            for i, s in enumerate(scenes_raw)
        ]
        goals = raw.get("educational_goals", {}) or {}
        # 保证五大领域 key 都存在
        for k in ("健康", "语言", "社会", "科学", "艺术"):
            goals.setdefault(k, [])

        return StoryResult(
            title=title,
            characters=characters,
            story_text=story_text,
            scenes=scenes,
            educational_goals=goals,
            raw=raw,
        )
