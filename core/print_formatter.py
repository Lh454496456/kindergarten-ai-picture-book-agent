# -*- coding: utf-8 -*-
"""
print_formatter —— 绘本 A4 打印版排版
=====================================
把 StoryResult 转成一份老师可以直接打印、照着念、照着画的 Markdown 文本。

输出结构：
  1. 封面页（标题 + 角色 + 适合年龄段）
  2. 故事正文（大字分段，按分镜切页）
  3. 每页分镜的文字 + 画面提示（老师可照着画或打印配图）
  4. 结尾：给老师的提问参考（3-5 个开放式问题）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .story_generator import StoryResult


# 给老师的开放式提问模板（按领域挑，避免变成"是不是/对不对"的封闭问题）
DEFAULT_QUESTIONS: List[str] = [
    "你最喜欢故事里的哪一段？为什么呀？",
    "如果是你，你会怎么做呢？",
    "你有没有遇到过和 XXX 一样的事情？",
    "故事里的小动物后来怎么样了？",
    "回家以后，你想把这个故事讲给谁听？",
]


def _characters_line(characters: List[Dict[str, str]]) -> str:
    if not characters:
        return "（角色由老师现场补充）"
    parts = []
    for c in characters:
        name = c.get("name", "小动物")
        desc = c.get("description", "")
        parts.append(f"{name}（{desc}）" if desc else name)
    return "、".join(parts)


def _split_story_text(story_text: str, scenes_count: int) -> List[str]:
    """把正文按句号/换行粗略切成和分镜数量匹配的小段，方便打印分页。"""
    text = (story_text or "").strip()
    if not text:
        return []
    # 按句号/感叹号/问号切，保留标点
    import re
    sentences = [s for s in re.split(r"(?<=[。！？!?])\s*", text) if s.strip()]
    if not sentences:
        return [text]
    if scenes_count <= 1:
        return [text]
    # 尽量均匀切
    per = max(1, -(-len(sentences) // scenes_count))  # 向上取整
    chunks = []
    for i in range(0, len(sentences), per):
        chunks.append("".join(sentences[i:i + per]).strip())
    return [c for c in chunks if c]


def format_print_version(
    story: StoryResult,
    age_group: str = "中班 4-5 岁",
    extra_questions: Optional[List[str]] = None,
) -> str:
    """生成 A4 打印版 Markdown 文本。

    :param story: StoryGenerator.generate() 返回的对象
    :param age_group: 用于封面"适合年龄段"
    :param extra_questions: 老师可自定义的提问参考，覆盖默认模板
    """
    characters_line = _characters_line(story.characters)
    scenes = story.scenes or []
    chunks = _split_story_text(story.story_text, len(scenes))

    out: List[str] = []
    # ---------- 封面 ---------- #
    out.append("# 📖 童心AI绘本 · 打印版")
    out.append("")
    out.append(f"## 《{story.title}》")
    out.append("")
    out.append(f"- 👧 适合年龄段：**{age_group}**")
    out.append(f"- 🐰 登场角色：{characters_line}")
    out.append(f"- 📄 分镜页数：{len(scenes)} 页")
    out.append("")
    out.append("> _（封面打印后可让孩子在右下角画自己喜欢的小动物）_")
    out.append("")
    out.append("---")
    out.append("")

    # ---------- 故事正文（按分镜分页） ---------- #
    out.append("# 一、故事正文（老师念读版）")
    out.append("")
    for i, scene in enumerate(scenes):
        page_text = chunks[i] if i < len(chunks) else (scene.text or "")
        out.append(f"## 第 {scene.scene_no} 页")
        out.append("")
        out.append(f"**{page_text or scene.text}**")
        out.append("")
        out.append(f"_画面提示（老师可照着画/打印配图）：{scene.illustration_prompt}_")
        out.append("")
        out.append("---")
        out.append("")

    # 如果正文还有剩余（分镜比正文段少），补一段
    if not scenes:
        out.append(story.story_text or "（故事正文缺失）")
        out.append("")

    # ---------- 提问参考 ---------- #
    out.append("# 二、读完后可以问问孩子")
    out.append("")
    main_char = story.characters[0].get("name", "小动物") if story.characters else "小动物"
    questions = list(extra_questions) if extra_questions else list(DEFAULT_QUESTIONS)
    # 把占位符 XXX 替换成主角名
    questions = [q.replace("XXX", main_char) for q in questions]
    for i, q in enumerate(questions[:5], 1):
        out.append(f"{i}. {q}")
    out.append("")
    out.append("---")
    out.append("")
    out.append("_本打印版由童心AI绘本馆生成，可自由复印、用于班级教学。_")

    return "\n".join(out)
