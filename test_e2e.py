# -*- coding: utf-8 -*-
"""
test_e2e.py —— 端到端数据流测试
================================
模拟一次完整的教学闭环：
    主题="分享玩具"
      → StoryGenerator 生成绘本
      → ActivityPlanner 基于绘本生成活动方案
      → DialogueAgent 基于绘本开启 3 轮幼儿对话
      → EvaluationEngine 基于对话记录生成观察记录
      → print_formatter 输出打印版
      → home_school_prompter 输出家长群话术

重点检查"模块之间的接口是否衔接得上"：
  - StoryResult.to_dict() 能否直接喂给 ActivityPlanner.plan()
  - start_session() 接受的 dict 结构和 to_dict() 输出是否一致
  - dialogue.state.observation_log 的字段是否就是 evaluate() 期望的字段

直接运行：
    python test_e2e.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.story_generator import StoryGenerator, StoryResult  # noqa: E402
from core.activity_planner import ActivityPlanner, ActivityPlan  # noqa: E402
from core.dialogue_agent import DialogueAgent, DialogueState  # noqa: E402
from core.evaluation_engine import EvaluationEngine, ObservationRecord  # noqa: E402
from core.print_formatter import format_print_version  # noqa: E402
from core.home_school_prompter import generate_home_school_script  # noqa: E402


# ---------------------------------------------------------------------- #
# 多模式 FakeLLM：按"当前阶段"返回不同结构
# ---------------------------------------------------------------------- #
class PipelineFakeLLM:
    """根据 user_message 的特征判断当前在哪个阶段，返回对应 JSON。"""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def chat_json(
        self,
        system_prompt: str = "",
        user_message: str = "",
        history: Any = None,
        temperature: float = 0.7,
        max_tokens: int = 0,
    ) -> Dict[str, Any]:
        self.calls.append({"user_message_head": user_message[:80]})

        if '"theme"' in user_message:
            return {
                "title": "小兔朵朵分享小卡车",
                "characters": [
                    {"name": "小兔朵朵", "description": "抱着胡萝卜的小兔子"},
                    {"name": "小熊壮壮", "description": "胖乎乎的小熊"},
                ],
                "story_text": (
                    "小兔朵朵有一辆红色小卡车。小熊壮壮走过来说："
                    '"我可以和你一起玩吗？"朵朵想了想，把卡车推过去。'
                    "他们你推一下我推一下，笑得真开心。"
                ),
                "scenes": [
                    {"scene_no": 1, "text": "朵朵在玩小卡车", "illustration_prompt": "草地，兔子玩红卡车", "domain_tags": ["社会"]},
                    {"scene_no": 2, "text": "壮壮走过来问", "illustration_prompt": "熊走向兔子", "domain_tags": ["语言", "社会"]},
                    {"scene_no": 3, "text": "一起推卡车", "illustration_prompt": "两个小动物一起玩", "domain_tags": ["社会"]},
                ],
                "educational_goals": {
                    "语言": ["学说短句我可以和你一起玩吗"],
                    "社会": ["愿意把玩具借给同伴"],
                },
            }
        if '"story"' in user_message and '"target_age"' in user_message:
            return {
                "activity_name": "一起玩真开心",
                "target_age": "中班 4-5 岁",
                "duration": 20,
                "goals": {
                    "语言": ["能学说我可以和你一起玩吗"],
                    "社会": ["愿意与同伴分享玩具"],
                },
                "materials": ["玩具卡车1辆", "小兔/小熊手偶各1个"],
                "process": [
                    {"step": 1, "name": "导入", "minutes": 3, "teacher_action": "出示手偶", "child_action": "观察"},
                    {"step": 2, "name": "共读绘本", "minutes": 8, "teacher_action": "讲故事", "child_action": "倾听回答"},
                    {"step": 3, "name": "角色扮演", "minutes": 7, "teacher_action": "引导分享", "child_action": "两两对玩"},
                ],
                "extension_games": ["区角分享角", "家庭分享任务"],
                "home_school_cooperation": ["本周和孩子聊聊家里哪些东西可以分享"],
            }
        if '"observation_log"' in user_message:
            return {
                "language_observation": "幼儿共发言3次，主动提问1次，平均句长约5字。",
                "social_observation": "在角色邀请下愿意说出分享短句，情绪积极。",
                "interest_level": 4,
                "teacher_note_suggestion": "可在区角继续提供分享类手偶。",
            }
        return {
            "reply": "好呀，那我们一起把小卡车推过去好不好？",
            "advance_plot": True,
            "domain_tag": "社会",
            "teacher_note": "幼儿愿意模仿分享短句",
        }

    def chat(self, *a: Any, **kw: Any) -> str:
        return "fake text"


PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  -- {detail}")


def section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _can_json(obj: Any) -> bool:
    try:
        json.dumps(obj, ensure_ascii=False)
        return True
    except Exception:
        return False


def main() -> int:
    print("童心AI绘本馆 —— 端到端数据流测试")
    print(f"Python: {sys.version.split()[0]}")

    fake = PipelineFakeLLM()

    section("Step 1：StoryGenerator 生成绘本（主题=分享玩具）")
    story_gen = StoryGenerator(llm=fake)
    story = story_gen.generate(theme="分享玩具", age_group="中班 4-5 岁", domain_tags=["语言", "社会"])
    check("绘本 title 非空", bool(story.title), repr(story.title))
    check("绘本 characters 有 2 个", len(story.characters) == 2)
    check("绘本 scenes 有 3 页", len(story.scenes) == 3)
    check("绘本 educational_goals 含五大领域",
          all(k in story.educational_goals for k in ("健康", "语言", "社会", "科学", "艺术")))
    story_dict = story.to_dict()
    check("to_dict() 可 JSON 序列化", _can_json(story_dict))

    section("Step 2：ActivityPlanner 基于绘本 dict 生成活动方案")
    planner = ActivityPlanner(llm=fake)
    plan = planner.plan(story_dict, age_group="中班 4-5 岁")
    check("plan.activity_name 非空", bool(plan.activity_name))
    check("plan.process 有 3 步", len(plan.process) == 3)
    check("plan.materials 非空", len(plan.materials) >= 1)
    check("plan.to_dict() 可 JSON 序列化", _can_json(plan.to_dict()))

    section("Step 3：DialogueAgent 基于绘本开启 3 轮对话")
    agent = DialogueAgent(llm=fake)
    state = agent.start_session(story_dict, age_group="中班 4-5 岁")
    check("start_session 拿到主角名", state.character_name == "小兔朵朵", state.character_name)
    check("start_session 拿到故事标题", state.story_title == story.title)
    child_msgs = ["我也喜欢小卡车！", "我可以和你一起玩吗？", "那我们轮流推好不好？"]
    for i, m in enumerate(child_msgs, 1):
        resp = agent.respond(state, m)
        check(f"第{i}轮 reply 非空", bool(resp.reply))
        check(f"第{i}轮 observation_log 长度={i}", len(state.observation_log) == i,
              f"actual={len(state.observation_log)}")
    required_keys = {"child_msg", "agent_reply", "advance_plot", "domain_tag", "teacher_note"}
    first = state.observation_log[0]
    check("observation_log 每条含 evaluate() 期望的字段",
          required_keys.issubset(first.keys()),
          f"missing={required_keys - first.keys()}")

    section("Step 4：EvaluationEngine 基于 observation_log 生成观察记录")
    eng = EvaluationEngine(llm=fake, use_llm=True)
    rec = eng.evaluate(state.observation_log, child_label="幼儿A")
    check("rec.message_count=3", rec.message_count == 3, str(rec.message_count))
    check("rec.interest_level 在 1-5", 1 <= rec.interest_level <= 5)
    check("rec.language_observation 非空", bool(rec.language_observation))
    table = rec.to_formatted_table()
    check("rec.to_formatted_table() 输出 Markdown 表格",
          "| 幼儿匿名ID | 日期 | 领域 | 行为表现 | 后续支持策略 |" in table)

    section("Step 5：print_formatter 生成 A4 打印版")
    print_text = format_print_version(story, age_group="中班 4-5 岁")
    check("打印版含封面", "打印版" in print_text)
    check("打印版含分镜页", "第 1 页" in print_text and "第 3 页" in print_text)
    check("打印版含提问参考", "读完后可以问问孩子" in print_text)

    section("Step 6：home_school_prompter 生成家长群话术")
    script = generate_home_school_script(theme="分享玩具", story_title=f"《{story.title}》")
    check("话术以【今日绘本分享】开头", script.startswith("【今日绘本分享】"))
    check("话术长度<=200", len(script) <= 200, f"len={len(script)}")
    check("话术含回家小问题", "聊聊" in script)

    section("端到端结果汇总")
    print(f"  通过：{PASS}")
    print(f"  失败：{FAIL}")
    print(f"  LLM 调用次数：{len(fake.calls)}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
