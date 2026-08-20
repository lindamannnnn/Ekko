# -*- coding: utf-8 -*-
"""pipeline/llm.py —— 轻量 OpenAI 兼容 LLM 客户端（纯标准库，无第三方依赖）。

复刻系统 B（lesson-courseware/courseware_engine/llm.py）的成熟写法：
代理支持 + 限流/超时指数退避重试 + 弱模型适配。但本文件为「内容上传功能」独立维护，
不 import 系统 B 任何代码，符合两条红线（A/B 代码冻结、只读复用）。

环境变量（AI_* 优先）：
  AI_API_KEY / AI_BASE_URL / AI_MODEL / AI_PROXY
"""
import os
import time
import json
import urllib.request
import urllib.error


def _first(*vals):
    for v in vals:
        if v:
            return v
    return None


class LLMClient:
    # 弱模型（快速便宜档）标志词：含这些词判为弱模型，走小 max_tokens 路径。
    WEAK_MARKS = ("flash", "lite", "mini", "turbo", "air", "tiny")

    def __init__(self, api_key=None, base_url=None, model=None, proxy=None):
        self.api_key = _first(api_key, os.environ.get("AI_API_KEY")) or ""
        self.base_url = (_first(base_url, os.environ.get("AI_BASE_URL"))
                         or "https://api.openai.com/v1").rstrip("/")
        self.model = _first(model, os.environ.get("AI_MODEL")) or "gpt-4o-mini"
        self.proxy = _first(proxy, os.environ.get("AI_PROXY"),
                            os.environ.get("HTTPS_PROXY"),
                            os.environ.get("HTTP_PROXY"))
        self._opener = None
        if self.proxy:
            self._opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}))

    def is_strong(self):
        """是否强模型（推理型/大模型）。含弱档标志词（flash/lite/mini…）判为弱模型。"""
        m = (self.model or "").lower()
        return not any(k in m for k in self.WEAK_MARKS)

    def complete(self, messages, temperature=0.6, timeout=45,
                 max_tokens=1500, retries=2):
        """调用 /chat/completions，返回 content 字符串。

        retries：HTTPError/超时按 2s/5s 指数退避重试；非网络错误（鉴权失败）立即抛出。
        弱模型保持原 max_tokens；强模型自动抬到下限避免思考截断。
        """
        url = self.base_url + "/chat/completions"
        if self.is_strong():
            max_tokens = max(int(max_tokens), 8000)
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        last_err = None
        for attempt in range(1, max(retries, 1) + 1):
            try:
                req = urllib.request.Request(url, data=body, method="POST")
                req.add_header("Content-Type", "application/json")
                req.add_header("Authorization", "Bearer " + self.api_key)
                if self._opener:
                    with self._opener.open(req, timeout=timeout) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                else:
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"].get("content") or ""
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code == 429:
                    last_err = RuntimeError(f"LLM 限流 429: {detail}")
                    time.sleep(min(5 * attempt, 20))
                    continue
                if 400 <= e.code < 500:
                    raise RuntimeError(f"LLM HTTP {e.code}: {detail}")
                last_err = RuntimeError(f"LLM HTTP {e.code}: {detail}")
            except Exception as e:
                last_err = RuntimeError(f"LLM 调用失败: {e}")
            if attempt < max(retries, 1):
                time.sleep(min(2 ** attempt, 5))
        raise last_err or RuntimeError("LLM 调用失败（未知错误）")


def make_client(env=None):
    """从 env dict 或 os.environ 构造 LLMClient。env 优先，缺失回退 os.environ。"""
    env = env or {}
    get = lambda k: env.get(k) or os.environ.get(k)
    return LLMClient(
        api_key=get("AI_API_KEY"),
        base_url=get("AI_BASE_URL"),
        model=get("AI_MODEL"),
        proxy=get("AI_PROXY"),
    )
