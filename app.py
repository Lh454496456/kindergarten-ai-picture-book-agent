# -*- coding: utf-8 -*-
"""
童心AI绘本馆 —— Gradio Web UI 入口
====================================
启动方式：
    python app.py
然后在浏览器打开终端里提示的本地地址（默认 http://127.0.0.1:7860）。

三个 Tab：
  ① 教师端 - 生成绘本与活动方案（含打印版、家长群话术）
  ② 幼儿端 - 与 AI 角色对话
  ③ 教师端 - 查看观察记录（Markdown 表格，可直接贴到观察手册）
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

# 让 core 包可被 import
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import (  # noqa: E402
    LLMClient,
    StoryGenerator,
    DialogueAgent,
    ActivityPlanner,
    EvaluationEngine,
    format_print_version,
    generate_home_school_script,
)
from core.story_generator import StoryResult  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")


# ---------------------------------------------------------------------- #
# 主题库加载
# ---------------------------------------------------------------------- #
THEMES_FILE = ROOT / "knowledge_base" / "kindergarten_themes.json"


def load_theme_library() -> List[Dict[str, Any]]:
    """读取主题库 JSON；失败时返回空列表（不影响主流程）。"""
    try:
        data = json.loads(THEMES_FILE.read_text(encoding="utf-8"))
        return data.get("themes", [])
    except Exception as e:  # noqa: BLE001
        logger.warning("主题库加载失败：%s", e)
        return []


THEMES = load_theme_library()
THEME_CHOICES = ["（自己输入主题）"] + [t["theme_name"] for t in THEMES]


# ---------------------------------------------------------------------- #
# 全局状态
# ---------------------------------------------------------------------- #
class AppServices:
    """统一持有各模块实例；配置缺失时降级为 None，UI 仍可打开。"""

    def __init__(self) -> None:
        self.llm: Optional[LLMClient] = None
        self.story_gen: Optional[StoryGenerator] = None
        self.dialogue: Optional[DialogueAgent] = None
        self.planner: Optional[ActivityPlanner] = None
        self.evaluator: Optional[EvaluationEngine] = None
        self.init_error: str = ""
        self._init()

    def _init(self) -> None:
        try:
            self.llm = LLMClient()
            self.story_gen = StoryGenerator(self.llm)
            self.dialogue = DialogueAgent(self.llm)
            self.planner = ActivityPlanner(self.llm)
            self.evaluator = EvaluationEngine(self.llm, use_llm=True)
            logger.info("所有模块初始化成功。")
        except Exception as e:  # noqa: BLE001
            self.init_error = str(e)
            logger.warning("模块初始化失败：%s", e)

    def ready(self) -> bool:
        return self.llm is not None


SERVICES = AppServices()

# 当前会话共享数据：刚生成的绘本对象 + 年龄段 + DialogueAgent 状态
CURRENT_SESSION: Dict[str, Any] = {
    "story": None,         # StoryResult 对象（打印版要用）
    "story_dict": None,    # dict 形式（对话/活动方案要用）
    "theme": "",
    "age_group": "中班 4-5 岁",
    "state": None,
}


# ---------------------------------------------------------------------- #
# Tab ①：教师端 - 生成绘本与活动方案
# ---------------------------------------------------------------------- #
def generate_story_and_plan(
    theme_choice: str,
    theme_custom: str,
    age_group: str,
    want_language: bool,
    want_social: bool,
    want_science: bool,
    want_art: bool,
    want_health: bool,
) -> Tuple[str, str, str]:
    """返回 (绘本 Markdown, 活动方案 Markdown, 打印版占位)。"""
    # 主题：下拉选"自己输入"时用自定义框
    theme = (theme_custom or "").strip() if theme_choice == "（自己输入主题）" else (theme_choice or "").strip()

    if not SERVICES.ready():
        return (
            f"⚠️ 模型尚未配置好：{SERVICES.init_error}",
            "请先按《安装手册.md》填写 config.py。",
            "",
        )

    if not theme:
        return (
            "请先选一个主题，或者在下面的输入框里自己写一个孩子生活里的小话题哦。",
            "",
            "",
        )

    domain_tags: List[str] = []
    if want_language:
        domain_tags.append("语言")
    if want_social:
        domain_tags.append("社会")
    if want_science:
        domain_tags.append("科学")
    if want_art:
        domain_tags.append("艺术")
    if want_health:
        domain_tags.append("健康")
    if not domain_tags:
        domain_tags = ["语言", "社会"]

    try:
        story: StoryResult = SERVICES.story_gen.generate(
            theme=theme, age_group=age_group, domain_tags=domain_tags
        )
        plan = SERVICES.planner.plan(story.to_dict(), age_group=age_group)
    except ValueError as e:
        # 用户输入类问题，直接友好提示
        logger.info("生成被拦下：%s", e)
        return f"🙈 {e}", "", ""
    except Exception as e:  # noqa: BLE001
        logger.exception("生成失败")
        return f"❌ 生成失败：{e}", "", ""

    # 缓存会话数据
    CURRENT_SESSION["story"] = story
    CURRENT_SESSION["story_dict"] = story.to_dict()
    CURRENT_SESSION["theme"] = theme
    CURRENT_SESSION["age_group"] = age_group
    CURRENT_SESSION["state"] = None  # 换了新绘本，重置对话状态

    scenes_text = "\n\n".join(
        f"**场景 {s.scene_no}**｜{s.text}\n\n画面建议：{s.illustration_prompt}"
        for s in story.scenes
    )
    goals_text = "\n".join(
        f"- {k}：{'、'.join(v) if v else '（本次未重点涉及）'}"
        for k, v in story.educational_goals.items()
    )
    chars_text = "、".join(
        f"{c.get('name', '')}（{c.get('description', '')}）" for c in story.characters
    )
    story_md = (
        f"# 📖 《{story.title}》\n\n"
        f"**主题**：{theme}　**年龄段**：{age_group}\n\n"
        f"**登场角色**：{chars_text}\n\n"
        f"## 故事正文\n\n{story.story_text}\n\n"
        f"## 分镜与画面建议\n\n{scenes_text}\n\n"
        f"## 领域目标\n\n{goals_text}"
    )

    process_md = "\n".join(
        f"{p.get('step', i+1)}. **{p.get('name', '')}**（{p.get('minutes', '')} 分钟）\n"
        f"   - 教师：{p.get('teacher_action', '')}\n"
        f"   - 幼儿：{p.get('child_action', '')}"
        for i, p in enumerate(plan.process)
    )
    # 家长群话术
    script = generate_home_school_script(theme=theme, story_title=f"《{story.title}》", age_group=age_group)
    plan_md = (
        f"# 🎯 活动方案：{plan.activity_name}\n\n"
        f"- 对象：{plan.target_age}\n- 时长：{plan.duration} 分钟\n\n"
        f"## 活动目标\n"
        + "\n".join(f"- **{k}**：{'、'.join(v)}" for k, v in plan.goals.items())
        + f"\n\n## 材料准备\n- " + "\n- ".join(plan.materials)
        + f"\n\n## 活动过程\n{process_md}"
        + f"\n\n## 延伸游戏\n- " + "\n- ".join(plan.extension_games)
        + f"\n\n## 家园共育\n- " + "\n- ".join(plan.home_school_cooperation)
        + f"\n\n---\n\n## 💬 家长群话术（可直接复制）\n\n> {script}"
    )
    # 打印版先占位，等老师点按钮再生成
    print_placeholder = "_（生成成功后，点下面的「🖨️ 生成打印版」按钮，就能得到一份可打印的 A4 文本。）_"
    return story_md, plan_md, print_placeholder


def on_print_clicked() -> str:
    story = CURRENT_SESSION.get("story")
    if not story:
        return "还没有绘本可以打印哦，请先生成一本。"
    try:
        text = format_print_version(
            story,
            age_group=CURRENT_SESSION.get("age_group", "中班 4-5 岁"),
        )
        return text
    except Exception as e:  # noqa: BLE001
        logger.exception("打印版生成失败")
        return f"❌ 打印版生成失败：{e}"


# ---------------------------------------------------------------------- #
# Tab ②：幼儿端 - 与 AI 角色对话
# ---------------------------------------------------------------------- #
def tab2_welcome() -> str:
    story = CURRENT_SESSION.get("story_dict")
    if not story:
        return "（请先在【Tab①】生成一本绘本，再回到这里开始和 AI 角色对话。）"
    chars = story.get("characters", [])
    main = chars[0] if chars else {"name": "小兔朵朵"}
    return (
        f"你好呀，我是 **{main.get('name', '小兔朵朵')}**！"
        f"我们正在读《{story.get('title', '')}》。\n"
        "你想和我说点什么呢？"
    )


def tab2_respond(
    child_msg: str, chat_history: List[Dict[str, str]]
) -> Tuple[List[Dict[str, str]], str, str]:
    """Gradio 6 Chatbot 使用 messages 格式：list[{"role":..., "content":...}]。"""
    chat_history = chat_history or []
    if not SERVICES.ready():
        chat_history.append({"role": "user", "content": child_msg or "（空）"})
        chat_history.append({"role": "assistant", "content": f"模型未配置：{SERVICES.init_error}"})
        return chat_history, tab2_welcome(), ""
    story = CURRENT_SESSION.get("story_dict")
    if not story:
        chat_history.append({"role": "user", "content": child_msg or "（空）"})
        chat_history.append({"role": "assistant", "content": "请先在【Tab①】生成一本绘本哦。"})
        return chat_history, tab2_welcome(), ""

    if CURRENT_SESSION["state"] is None:
        CURRENT_SESSION["state"] = SERVICES.dialogue.start_session(
            story, age_group=CURRENT_SESSION.get("age_group", "中班 4-5 岁")
        )

    resp = SERVICES.dialogue.respond(CURRENT_SESSION["state"], child_msg)
    chat_history.append({"role": "user", "content": child_msg or "（空）"})
    chat_history.append({"role": "assistant", "content": resp.reply})
    hint = ""
    if resp.teacher_note:
        hint = f"💡 **给老师的小提示**：{resp.teacher_note}（本轮领域标签：{resp.domain_tag}）"
    return chat_history, tab2_welcome(), hint


# ---------------------------------------------------------------------- #
# Tab ③：教师端 - 查看观察记录（Markdown 表格）
# ---------------------------------------------------------------------- #
def tab3_make_observation() -> str:
    if not SERVICES.ready():
        return f"⚠️ 模型未配置：{SERVICES.init_error}"
    state = CURRENT_SESSION.get("state")
    if not state or not state.observation_log:
        return "还没有可分析的对话记录。请先在【Tab②】和孩子聊几句。"
    try:
        rec = SERVICES.evaluator.evaluate(state.observation_log)
    except ValueError as e:
        return f"🙈 {e}"
    except Exception as e:  # noqa: BLE001
        return f"❌ 分析失败：{e}"
    return rec.to_formatted_table()


# ---------------------------------------------------------------------- #
# 组装 Gradio Blocks
# ---------------------------------------------------------------------- #
def build_ui() -> gr.Blocks:
    with gr.Blocks(title="童心AI绘本馆") as demo:
        gr.Markdown(
            "# 童心AI绘本馆  \n"
            "> 面向 3-6 岁幼儿的 AI 阅读陪伴智能体  \n"
            "> 教师生成绘本 → 幼儿与角色对话 → 教师查看观察记录"
        )
        if not SERVICES.ready():
            gr.Markdown(
                f"⚠️ **当前未连接大模型**：{SERVICES.init_error}  \n"
                "请按《安装手册.md》填写 `config.py` 后重启。"
            )

        with gr.Tab("① 教师端：生成绘本与活动"):
            with gr.Row():
                with gr.Column(scale=1):
                    theme_dd = gr.Dropdown(
                        choices=THEME_CHOICES,
                        value=THEME_CHOICES[1] if len(THEME_CHOICES) > 1 else "（自己输入主题）",
                        label="选一个常用主题（20+ 个真实幼儿园话题）",
                    )
                    theme_custom = gr.Textbox(
                        label="或者自己写一个主题",
                        placeholder="例如：我敢一个人睡 / 小蚂蚁搬家",
                    )
                    age = gr.Radio(
                        ["小班 3-4 岁", "中班 4-5 岁", "大班 5-6 岁"],
                        value="中班 4-5 岁",
                        label="年龄段",
                    )
                    gr.Markdown("**希望融合的领域**（可多选）")
                    cb_lang = gr.Checkbox(value=True, label="语言")
                    cb_soc = gr.Checkbox(value=True, label="社会")
                    cb_sci = gr.Checkbox(value=False, label="科学")
                    cb_art = gr.Checkbox(value=False, label="艺术")
                    cb_hea = gr.Checkbox(value=False, label="健康")
                    btn_gen = gr.Button("✨ 生成绘本与活动方案", variant="primary")
                    btn_print = gr.Button("🖨️ 生成打印版（A4 可复印）")
                with gr.Column(scale=2):
                    story_out = gr.Markdown(label="绘本")
                    plan_out = gr.Markdown(label="活动方案")
                    print_out = gr.Markdown(label="打印版")
            btn_gen.click(
                fn=generate_story_and_plan,
                inputs=[theme_dd, theme_custom, age, cb_lang, cb_soc, cb_sci, cb_art, cb_hea],
                outputs=[story_out, plan_out, print_out],
            )
            btn_print.click(fn=on_print_clicked, outputs=print_out)

        with gr.Tab("② 幼儿端：和角色对话"):
            welcome_md = gr.Markdown(tab2_welcome())
            chatbot = gr.Chatbot(label="对话", height=400)
            teacher_hint = gr.Markdown()
            with gr.Row():
                child_input = gr.Textbox(
                    label="小朋友想说的话（由老师/家长代输入）",
                    placeholder="例如：我也喜欢小汽车！",
                    scale=4,
                )
                send_btn = gr.Button("发送", variant="primary", scale=1)
            send_btn.click(
                fn=tab2_respond,
                inputs=[child_input, chatbot],
                outputs=[chatbot, welcome_md, teacher_hint],
            )
            child_input.submit(
                fn=tab2_respond,
                inputs=[child_input, chatbot],
                outputs=[chatbot, welcome_md, teacher_hint],
            )

        with gr.Tab("③ 教师端：查看观察记录"):
            gr.Markdown(
                "下面会输出一张 Markdown 表格，**直接复制就能贴到《幼儿观察手册》里**。"
            )
            btn_eval = gr.Button("📝 生成本次活动的形成性观察记录", variant="primary")
            eval_out = gr.Markdown()
            btn_eval.click(fn=tab3_make_observation, outputs=eval_out)

    return demo


if __name__ == "__main__":
    demo = build_ui()
    try:
        import config  # type: ignore
        port = getattr(config, "GRADIO_SERVER_PORT", 7860)
        share = getattr(config, "GRADIO_SHARE", False)
    except Exception:  # noqa: BLE001
        port, share = 7860, False
    demo.launch(server_name="127.0.0.1", server_port=port, share=share)
