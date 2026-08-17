"""通用 LLM 客户端（OpenAI 兼容）。

支持任意 OpenAI-compatible 端点（智谱 GLM-4-Flash / OpenAI / 本地 vLLM 等）。
单 Key 走同步请求；多 Key 轮询在 channel.py 里做容量扩容。
"""
import os

import requests
from flask import current_app


class LLMClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or current_app.config.get("AI_API_KEY", "")
        self.base_url = base_url or current_app.config.get(
            "AI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
        )
        self.model = model or current_app.config.get("AI_MODEL", "glm-4-flash")
        # 代理策略：默认直连，不继承系统 HTTP(S)_PROXY，避免开发机/部署机的代理环境干扰。
        # 若部署环境需经代理才能访问大模型（如部分海外服务器），在 .env 设 AI_PROXY=http://host:port 即可。
        proxy_url = current_app.config.get("AI_PROXY") or os.environ.get("AI_PROXY")
        self.proxies = (
            {"http": proxy_url, "https": proxy_url} if proxy_url else {"http": None, "https": None}
        )

    def complete(self, messages, temperature=0.7, timeout=120, max_tokens=None):
        """同步调用，返回纯文本。失败时抛异常交由调用方处理。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        try:
            r = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
                proxies=self.proxies,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            # 把底层错误原样上抛，调用方记录到 reviews.error_msg
            raise
