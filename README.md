# 童心AI绘本馆

> 面向 3-6 岁幼儿的 AI 阅读陪伴智能体 —— 教师一键生成绘本、幼儿与角色对话、系统自动生成形成性观察记录。

![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![LLM](https://img.shields.io/badge/LLM-豆包%20%2F%20DeepSeek-orange.svg)
![UI](https://img.shields.io/badge/UI-Gradio-ff69b4.svg)
![Status](https://img.shields.io/badge/Status-%E5%8F%AF%E8%BF%90%E8%A1%8C-success.svg)

---

## 项目简介

"童心AI绘本馆"是一套面向幼儿园教师与 3-6 岁幼儿的本地化 AI 应用：

- **对教师**：输入一个主题（如"分享玩具"），几秒钟生成一本符合《3-6 岁儿童学习与发展指南》的绘本脚本 + 一份配套的集体教学活动方案。
- **对幼儿**：绘本中的小动物角色（如小兔朵朵）用短句、口语化的方式和孩子多轮对话，自然推进剧情。
- **对教研**：系统自动汇总本次活动中幼儿的发言、提问、情绪，输出一份可直接抄到观察手册上的形成性记录。

所有大模型调用走 OpenAI 兼容协议，默认接入 **豆包 / 火山方舟**，也兼容 **DeepSeek**。

---

## 功能特性

- 📚 **绘本生成**：按小班 / 中班 / 大班自动调节字数与句式，输出分镜 + 画面建议 + 五大领域目标。
- 🐰 **角色对话**：AI 角色每次回应不超过 3 句、主动提一个开放性小问题，推进剧情节奏可控。
- 🎯 **活动方案**：5 步教学过程 + 材料清单 + 延伸游戏 + 家园共育，直接可用。
- 📝 **观察记录**：规则统计（发言次数 / 提问次数 / 情绪词）+ LLM 教师视角评语双引擎。
- 🛡️ **内容安全**：系统提示词 + 关键字兜底双重约束，敏感话题自动温和引导回绘本。
- 🧩 **模块化**：StoryGenerator / DialogueAgent / ActivityPlanner / EvaluationEngine 各自独立，可单独调用。

---

## 快速开始（5 步）

```bash
# 1. 进入项目目录
cd 03_代码与应用文档

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate        # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt

# 3. 填入 API Key
cp config.example.py config.py
# 用编辑器打开 config.py，填入火山方舟（或 DeepSeek）的 API Key

# 4. 启动
python app.py

# 5. 浏览器打开
# 终端会提示 http://127.0.0.1:7860
```

> 详细图文步骤见 [`安装手册.md`](安装手册.md)。

---

## 界面截图（占位）

![截图占位：教师端界面](screenshots/teacher_ui.png)
![截图占位：幼儿对话界面](screenshots/child_chat.png)
![截图占位：观察记录界面](screenshots/observation.png)

---

## 目录结构

```
03_代码与应用文档/
├── README.md                   # 本文件
├── 安装手册.md
├── 使用手册.md
├── 开发记录.md
├── requirements.txt
├── config.example.py          # 复制为 config.py 后填写
├── app.py                      # Gradio Web UI 入口
├── core/
│   ├── __init__.py
│   ├── llm_client.py           # OpenAI 兼容 API 统一封装
│   ├── story_generator.py     # StoryGenerator
│   ├── dialogue_agent.py       # DialogueAgent
│   ├── activity_planner.py     # ActivityPlanner
│   └── evaluation_engine.py   # EvaluationEngine
├── prompts/
│   ├── system_prompt.md        # 总体安全与风格约束
│   ├── story_generator.md      # 绘本生成提示词
│   ├── dialogue_responder.md   # 幼儿对话提示词
│   └── activity_planner.md     # 活动方案提示词
└── knowledge_base/
    ├── five_domains_guide.md   # 《指南》五大领域要点
    └── activity_examples.md    # 典型活动案例
```

---

## 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 语言 | Python 3.9+ | 类型提示 + dataclass |
| 大模型 SDK | openai >= 1.0 | 兼容豆包 / 火山方舟 / DeepSeek |
| Web UI | Gradio >= 4.0 | 三 Tab 中文界面 |
| 配置 | 纯 Python + .env | 非技术教师友好 |

---

## 常见问题

**Q1：启动时报"未检测到完整的模型配置"？**
A：没有把 `config.example.py` 复制成 `config.py`，或没填 API_KEY / BASE_URL / MODEL_NAME。详见安装手册。

**Q2：生成绘本时报"模型返回的内容不是合法 JSON"？**
A：偶发的模型输出异常，点一次"重新生成"即可；如果连续 3 次都失败，建议换更低温度或换模型。

**Q3：幼儿对话里 AI 角色突然说奇怪的话？**
A：检查 prompts/dialogue_responder.md 是否被改过；系统已对敏感词做了兜底，但仍建议教师在现场陪同。

**Q4：能不能离线用？**
A：不能。本项目所有"智能"都来自云端大模型，必须能访问火山方舟或 DeepSeek。

---

## 致谢

- 教育部《3-6 岁儿童学习与发展指南》（2012）—— 全部领域目标的依据。
- 火山方舟、DeepSeek —— 提供 OpenAI 兼容的中文大模型能力。
- Gradio 社区 —— 让非技术教师也能用上现代 Web UI。

---

License: MIT
