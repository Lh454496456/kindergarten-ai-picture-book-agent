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

# 主题长度上限（字符数）：超过视为输入异常
MAX_THEME_LEN = 120

# 主题级敏感词：出现这些词时直接拒绝生成，引导老师换一个更适合 3-6 岁的主题
THEME_BLOCK_KEYWORDS = [
    "暴力", "恐怖", "杀人", "自杀", "色情", "赌博", "毒品",
    "妈妈死", "爸爸死", "葬礼", "自杀式",
]

# 年龄段差异化提示词文件
AGE_DIFF_FILE = PROJECT_ROOT / "prompts" / "story_generator_age_diff.md"


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
        # 年龄段差异化提示词（按 age_group 取用）
        self.age_diff_text = self._read_text(AGE_DIFF_FILE, optional=True)

    def _age_diff_fragment(self, age_group: str) -> str:
        """从 age_diff 文件里抽出对应年龄段的片段。

        文件格式约定：用 ``## 小班`` / ``## 中班`` / ``## 大班`` 三个二级标题分段。
        找不到就返回空串，不影响主流程。
        """
        if not self.age_diff_text:
            return ""
        head_map = {
            "小班 3-4 岁": ("## 小班", "## 中班"),
            "中班 4-5 岁": ("## 中班", "## 大班"),
            "大班 5-6 岁": ("## 大班", None),
        }
        start_marker, end_marker = head_map.get(age_group, (None, None))
        if not start_marker or start_marker not in self.age_diff_text:
            return ""
        start = self.age_diff_text.find(start_marker)
        if end_marker:
            end = self.age_diff_text.find(end_marker, start + len(start_marker))
            if end == -1:
                end = len(self.age_diff_text)
        else:
            end = len(self.age_diff_text)
        return self.age_diff_text[start:end].strip()

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
            raise ValueError("主题还空着呢，请写一个孩子生活里的小话题，比如'分享玩具''好好午睡'。")
        if len(theme) > MAX_THEME_LEN:
            raise ValueError(
                f"主题太长啦（{len(theme)} 字），我们建议一句话说清楚就好，"
                f"控制在 {MAX_THEME_LEN} 字以内哦。"
            )
        if age_group not in VALID_AGE_GROUPS:
            raise ValueError(f"年龄段必须是 {sorted(VALID_AGE_GROUPS)} 之一，收到：{age_group}")
        domain_tags = domain_tags or ["语言", "社会"]
        bad = [d for d in domain_tags if d not in VALID_DOMAINS]
        if bad:
            raise ValueError(f"领域标签必须来自 {sorted(VALID_DOMAINS)}，收到非法值：{bad}")

        # 主题级安全兜底：明显不适合 3-6 岁的主题直接拦下
        hit = [kw for kw in THEME_BLOCK_KEYWORDS if kw in theme]
        if hit:
            raise ValueError(
                f"「{theme}」这个主题不太适合给 3-6 岁的孩子读哦。"
                f"我们换成贴近孩子日常生活的话题吧，比如'我敢一个人睡''想妈妈了怎么办'。"
            )

        user_msg = json.dumps(
            {"theme": theme, "age_group": age_group, "domain_tags": domain_tags},
            ensure_ascii=False,
        )
        logger.info("开始生成绘本：theme=%s, age=%s, tags=%s", theme, age_group, domain_tags)

        # 按年龄段拼差异化提示词
        system_prompt = self.system_prompt
        fragment = self._age_diff_fragment(age_group)
        if fragment:
            system_prompt += "\n\n## 本段年龄段写作要求（必须严格遵守）\n\n" + fragment

        raw = self.llm.chat_json(
            system_prompt=system_prompt,
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
