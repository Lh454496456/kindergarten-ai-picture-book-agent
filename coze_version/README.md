# 童心AI绘本馆 · Coze 零代码版

> 给**不会写代码**的一线老师准备的版本。
> 不用装 Python、不用开命令行，注册一个 Coze 账号，照着点鼠标就能搭出来。

## 两种版本对比

| 对比项 | 本地代码版（Python） | Coze 零代码版（本目录） |
|--------|---------------------|------------------------|
| 适合谁 | 会 Python 的老师 / 信息老师 | 不会写代码的一线老师 |
| 安装 | 需装 Python + 依赖 | 注册 Coze 账号即可 |
| 数据隐私 | 全本地 | 存 Coze 云端 |
| 功能 | 全功能（含语音、打印版、家长群话术） | 对齐 Python 版 4 大能力 |
| 成本 | 自己的 API Key | Coze 免费额度 + API Key |

## 目录结构

```
coze_version/
├── README.md
├── 01_创建Bot与人设提示词.md
├── 02_工作流配置.md
├── prompts/
│   ├── bot_system_prompt.md
│   ├── wf_story_generator.md
│   ├── wf_dialogue.md
│   ├── wf_activity_planner.md
│   └── wf_observation.md
└── knowledge_base_upload/
    ├── five_domains_guide.md
    └── kindergarten_themes.json
```

## 搭建顺序

1. 看 `01_创建Bot与人设提示词.md`：注册 Coze → 建 Bot → 贴人设 → 上传知识库。
2. 看 `02_工作流配置.md`：搭 4 个工作流。
3. 把工作流挂到 Bot 上，发布。
