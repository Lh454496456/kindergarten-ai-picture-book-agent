# -*- coding: utf-8 -*-
"""
统一的 OpenAI 兼容 API 封装
==========================
同时兼容：
  - 豆包 / 火山方舟（https://ark.cn-beijing.volces.com/api/v3）
  - DeepSeek（https://api.deepseek.com）
  - 任何实现 OpenAI Chat Completions 协议的服务

设计要点：
  - 所有模块只依赖 LLMClient，不直接 import openai，便于未来替换后端
  - 统一日志、超时、重试与错误提示（面向非技术教师友好）
  - 提供 chat() 与 chat_json() 两种调用方式
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI, APIError, APITimeoutError, AuthenticationError, RateLimitError

logger = logging.getLogger(__name__)


class LLMClient:
    """对 OpenAI 兼容端点的轻量封装。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: int = 60,
    ) -> None:
        """
        参数留空时自动从 config.py 读取（若存在），否则回退到环境变量。

        优先级：显式传入 > config.py > 环境变量（ARK_API_KEY / OPENAI_BASE_URL 等）。
        """
        # 尝试加载项目配置
        cfg = self._load_config()

        self.api_key = api_key or getattr(cfg, "API_KEY", None) or os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or getattr(cfg, "BASE_URL", None) or os.getenv("OPENAI_BASE_URL")
        self.model_name = model_name or getattr(cfg, "MODEL_NAME", None) or os.getenv("OPENAI_MODEL")
        self.temperature = temperature if temperature != 0.7 else getattr(cfg, "TEMPERATURE", temperature)
        self.max_tokens = max_tokens if max_tokens != 2000 else getattr(cfg, "MAX_TOKENS", max_tokens)
        self.timeout = timeout if timeout != 60 else getattr(cfg, "REQUEST_TIMEOUT", timeout)

        if not self.api_key or not self.base_url or not self.model_name:
            raise RuntimeError(
                "未检测到完整的模型配置。请复制 config.example.py 为 config.py，"
                "并填入 API_KEY / BASE_URL / MODEL_NAME。"
            )

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        logger.info("LLMClient 初始化完成：model=%s, base_url=%s", self.model_name, self.base_url)

    @staticmethod
    def _load_config() -> Any:
        """动态导入项目根目录下的 config.py；若不存在则返回空对象。"""
        try:
            import config  # type: ignore
            return config
        except ImportError:
            logger.warning("未找到 config.py，将使用环境变量或默认值。")
            return type("EmptyConfig", (object,), {})()

    # ------------------------------------------------------------------ #
    # 核心调用
    # ------------------------------------------------------------------ #
    def chat(
        self,
        system_prompt: str,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        retries: int = 2,
    ) -> str:
        """
        普通对话调用，返回模型文本。

        :param system_prompt: 系统提示词（角色设定 / 安全约束 / 输出格式）
        :param user_message: 本轮用户消息
        :param history: 历史消息列表，元素为 {"role": "user"/"assistant", "content": "..."}
        :param temperature: 覆盖默认温度
        :param max_tokens: 覆盖默认最大 token
        :param retries: 网络错误 / 限流时的重试次数
        :return: 模型返回的文本内容
        """
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                logger.debug("LLM 请求第 %d 次，message 长度=%d", attempt + 1, len(user_message))
                resp = self._client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature if temperature is not None else self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                )
                content = resp.choices[0].message.content or ""
                return content.strip()
            except AuthenticationError as e:
                # Key 错误不要重试
                logger.error("API Key 无效：%s", e)
                raise RuntimeError("API Key 不正确，请检查 config.py 中的 API_KEY。") from e
            except RateLimitError as e:
                logger.warning("触发限流，第 %d 次等待后重试：%s", attempt + 1, e)
                time.sleep(2 * (attempt + 1))
                last_err = e
            except (APITimeoutError, APIError) as e:
                logger.warning("网络异常，第 %d 次重试：%s", attempt + 1, e)
                time.sleep(1.5 * (attempt + 1))
                last_err = e
            except Exception as e:  # noqa: BLE001
                logger.exception("未预期的调用错误")
                raise RuntimeError(f"调用大模型时出错：{e}") from e

        raise RuntimeError(f"多次重试后仍失败，请检查网络或模型配置。最后错误：{last_err}")

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        要求模型返回合法 JSON，并自动做解析与容错：
          - 剥离 ```json ... ``` 代码块
          - 截取第一个 { 到最后一个 } 之间的内容
        解析失败时抛出带原文的 RuntimeError，便于上层提示教师重试。
        """
        raw = self.chat(
            system_prompt=system_prompt,
            user_message=user_message,
            history=history,
            temperature=temperature if temperature is not None else 0.3,  # JSON 用更低温度
            max_tokens=max_tokens or self.max_tokens,
        )
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """从模型输出中尽量稳健地提取 JSON 对象。"""
        t = text.strip()
        # 去掉 ```json ... ``` 包裹
        if t.startswith("```"):
            t = t.strip("`")
            # 去掉开头可能的 json 字样
            if t.lower().startswith("json"):
                t = t[4:]
        # 截取 {...}
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1 and end > start:
            t = t[start:end + 1]
        try:
            return json.loads(t)
        except json.JSONDecodeError as e:
            logger.error("JSON 解析失败，原文前 500 字：%s", text[:500])
            raise RuntimeError(
                f"模型返回的内容不是合法 JSON，请重试或换一个说法。解析错误：{e}"
            ) from e
