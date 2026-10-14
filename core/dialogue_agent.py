# -*- coding: utf-8 -*-
"""
DialogueAgent —— 幼儿对话智能体
================================
让"绘本角色"（如小兔朵朵）和 3-6 岁幼儿多轮对话，
既能推进剧情，也能给出教师观察标签。

特点：
  - 用 dataclass 管理会话状态（绘本 context + 历史消息）
  - 自动截断历史，防止 token 爆炸
  - 硬编码内容安全兜底（即使模型跑偏也能拦住明显违规）
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = PROJECT_ROOT / "prompts" / "dialogue_responder.md"
SYSTEM_FILE = PROJECT_ROOT / "prompts" / "system_prompt.md"

# 安全兜底：出现这些词时，强制把对话拉回绘本主题
REDIRECT_KEYWORDS = [
    "死", "杀人", "血", "鬼", "怕", "性", "裸", "钱",
    "死了", "自杀", "妈妈死", "爸爸死",
]
SAFE_REPLY_TEMPLATE = (
    "这是个很大的问题，等你长大一点，爸爸妈妈会慢慢告诉你哦。"
    "我们还是回到故事里，看看{character}接下来要做什么吧？"
)

# 每轮最多保留多少条历史消息（user+assistant 算 2 条）
MAX_HISTORY_TURNS = 8


@dataclass
class DialogueState:
    """一次幼儿对话会话的状态。"""
    story_title: str = ""
    character_name: str = "小兔朵朵"
    character_description: str = ""
    plot_summary: str = ""           # 当前剧情梗概
    age_group: str = "中班 4-5 岁"
    history: List[Dict[str, str]] = field(default_factory=list)
    # 给 EvaluationEngine 用的观察流水
    observation_log: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DialogueResponse:
    reply: str
    advance_plot: bool
    domain_tag: str
    teacher_note: str


class DialogueAgent:
    """绘本角色对话智能体。"""

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()
        self.prompt = self._read_text(PROMPT_FILE)
        self.system_prompt = self._read_text(SYSTEM_FILE)
        # 合并：总体安全约束 + 角色应答规则
        self.system_prompt = self.system_prompt + "\n\n---\n\n" + self.prompt

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # 会话管理
    # ------------------------------------------------------------------ #
    def start_session(
        self,
        story: Dict[str, Any],
        age_group: str = "中班 4-5 岁",
    ) -> DialogueState:
        """根据一本绘本初始化一段对话会话。"""
        characters = story.get("characters", []) or []
        main_char = characters[0] if characters else {"name": "小兔朵朵", "description": "一只可爱的小兔子"}
        state = DialogueState(
            story_title=story.get("title", ""),
            character_name=main_char.get("name", "小兔朵朵"),
            character_description=main_char.get("description", ""),
            plot_summary=story.get("story_text", "")[:400],  # 只取前 400 字作为剧情锚点
            age_group=age_group,
        )
        logger.info("开启对话会话：%s / 角色=%s", state.story_title, state.character_name)
        return state

    # ------------------------------------------------------------------ #
    # 主应答
    # ------------------------------------------------------------------ #
    def respond(self, state: DialogueState, child_message: str) -> DialogueResponse:
        """让绘本角色回应小朋友的一句话。"""
        child_message = (child_message or "").strip()
        if not child_message:
            return DialogueResponse(
                reply=f"你好呀，我是{state.character_name}，你今天想和我一起做什么呢？",
                advance_plot=False,
                domain_tag="语言",
                teacher_note="",
            )

        # 1) 内容安全兜底
        if self._is_sensitive(child_message):
            logger.info("检测到敏感话题，执行兜底引导")
            reply_text = SAFE_REPLY_TEMPLATE.format(character=state.character_name)
            resp = DialogueResponse(
                reply=reply_text,
                advance_plot=False,
                domain_tag="社会",
                teacher_note="建议教师关注幼儿提问背后的情绪，必要时单独沟通。",
            )
        else:
            # 2) 调 LLM
            user_msg = self._build_user_message(state, child_message)
            try:
                raw = self.llm.chat_json(
                    system_prompt=self.system_prompt,
                    user_message=user_msg,
                    history=self._truncate_history(state.history),
                    temperature=0.85,
                )
                resp = DialogueResponse(
                    reply=str(raw.get("reply", "")).strip(),
                    advance_plot=bool(raw.get("advance_plot", False)),
                    domain_tag=str(raw.get("domain_tag", "语言")),
                    teacher_note=str(raw.get("teacher_note", "")),
                )
            except RuntimeError as e:
                logger.warning("LLM 应答失败，使用兜底话术：%s", e)
                resp = DialogueResponse(
                    reply=f"（网络好像有点小问题）我们再一起看看{state.character_name}吧。",
                    advance_plot=False,
                    domain_tag="语言",
                    teacher_note=f"系统提示：本轮应答失败，原因：{e}",
                )

        # 3) 更新状态
        state.history.append({"role": "user", "content": child_message})
        state.history.append({"role": "assistant", "content": resp.reply})
        state.observation_log.append({
            "child_msg": child_message,
            "agent_reply": resp.reply,
            "advance_plot": resp.advance_plot,
            "domain_tag": resp.domain_tag,
            "teacher_note": resp.teacher_note,
        })
        return resp

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def _build_user_message(self, state: DialogueState, child_message: str) -> str:
        """把绘本上下文 + 最新幼儿消息组装成一次 user 调用。"""
        return (
            f"【当前绘本】《{state.story_title}》\n"
            f"【你的角色】{state.character_name}：{state.character_description}\n"
            f"【剧情进展】{state.plot_summary}\n"
            f"【幼儿年龄段】{state.age_group}\n"
            f"【小朋友刚说】{child_message}\n\n"
            f"请按系统提示词要求，输出 JSON。"
        )

    @staticmethod
    def _truncate_history(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """只保留最近 MAX_HISTORY_TURNS 轮（一轮 = user+assistant）。"""
        max_msgs = MAX_HISTORY_TURNS * 2
        if len(history) <= max_msgs:
            return history
        return history[-max_msgs:]

    @staticmethod
    def _is_sensitive(text: str) -> bool:
        """轻量敏感词兜底；正式部署应替换为企业内容安全审核。"""
        return any(kw in text for kw in REDIRECT_KEYWORDS)
