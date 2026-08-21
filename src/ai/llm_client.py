"""通用 LLM 客户端（OpenAI 兼容）。

支持任意 OpenAI-compatible 端点（智谱 GLM-4-Flash / OpenAI / 本地 vLLM 等）。
支持单 KEY 或多 KEY 轮询：在 .env 中把多个 key 用逗号分隔填入 AI_API_KEY，
当某个 key 限流、失败或异常时自动切换到下一个 key。
"""
import os

import requests
from flask import current_app


class LLMClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        raw_key = api_key or current_app.config.get("AI_API_KEY", "")
        self.api_keys = [k.strip() for k in raw_key.split(",") if k.strip()] if raw_key else []
        if not self.api_keys:
            self.api_keys = [""]
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
        # 轮询起始索引，Flask 多线程下用实例级索引已足够（每个请求独立 client）
        self._key_index = 0

    @property
    def api_key(self):
        """兼容单 KEY 读取场景。"""
        return self.api_keys[0] if self.api_keys else ""

    @classmethod
    def for_user(cls, user):
        """优先使用用户自定义 API；未配置则回退平台默认。"""
        if user is None:
            return cls()
        return cls(
            api_key=user.ai_api_key or None,
            base_url=user.ai_base_url or None,
            model=user.ai_model or None,
        )

    def complete(self, messages, temperature=0.7, timeout=120, max_tokens=None):
        """同步调用，返回纯文本。

        多 KEY 时依次尝试，遇到限流/超时/服务端错误/鉴权失败自动切换到下一个 key。
        全部 key 失败后抛出最后一个异常。
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        last_err = None
        key_count = len(self.api_keys)
        for offset in range(key_count):
            key = self.api_keys[(self._key_index + offset) % key_count]
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
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
                # 成功后把起始索引挪到下一个 key，实现简单轮询
                self._key_index = (self._key_index + 1) % key_count
                return data["choices"][0]["message"]["content"]
            except requests.HTTPError as e:
                last_err = e
                code = e.response.status_code
                # 400/422 等参数错误换 key 也没用，直接抛出
                if 400 <= code < 500 and code not in (401, 429):
                    raise
                # 401/429/5xx 以及网络异常继续尝试下一个 key
                continue
            except requests.RequestException as e:
                last_err = e
                continue

        if last_err is not None:
            raise last_err
        raise RuntimeError("所有 API KEY 均调用失败")
