"""通用 LLM 客户端（OpenAI 兼容）。

支持任意 OpenAI-compatible 端点（智谱 GLM-4-Flash / OpenAI / 本地 vLLM 等）。
单 Key 走同步请求；多 Key 轮询在 channel.py 里做容量扩容。
"""
import requests
from flask import current_app


class LLMClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or current_app.config.get("AI_API_KEY", "")
        self.base_url = base_url or current_app.config.get(
            "AI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
        )
        self.model = model or current_app.config.get("AI_MODEL", "glm-4-flash")

    def complete(self, messages, temperature=0.7, timeout=120):
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
        try:
            r = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            # 把底层错误原样上抛，调用方记录到 reviews.error_msg
            raise
