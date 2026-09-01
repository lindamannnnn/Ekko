# -*- coding: utf-8 -*-
"""courseware_engine/llm.py —— 增强 LLM 客户端（OpenAI 兼容，纯标准库）。

相对 vendor 的 LLMClient 改进：
  - 统一读取 AI_* 与 COURSEWARE_* 两套环境变量（AI_* 优先），解决「两套变量」坑；
  - proxy 支持 AI_PROXY / COURSEWARE_PROXY / HTTPS_PROXY / HTTP_PROXY 四来源；
  - complete() 新增 retries：HTTPError/超时按 2s→5s 指数退避重试（弱模型兜底第一层）。
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
    # 强模型（推理型）自动抬 max_tokens 的下限：推理模型先花 token 在 reasoning_content
    # （思考）上，长协议（含禁止项+示例）会让推理暴涨到 3000+ token，600/4000 都不够，
    # content 会为空。凡 max_tokens 小于此值的调用，直接抬到下限。
    STRONG_MIN_TOKENS = 8000
    # 弱模型（快速便宜档）标志词：含这些词判为弱模型，走小 max_tokens 多次调用路径。
    WEAK_MARKS = ("flash", "lite", "mini", "turbo", "air", "tiny")

    def __init__(self, api_key=None, base_url=None, model=None, proxy=None):
        # 统一读取 AI_* 与 COURSEWARE_*（AI_* 优先）
        self.api_key = _first(api_key,
                              os.environ.get("AI_API_KEY"),
                              os.environ.get("COURSEWARE_API_KEY")) or ""
        self.base_url = (_first(base_url,
                                os.environ.get("AI_BASE_URL"),
                                os.environ.get("COURSEWARE_BASE_URL"))
                         or "https://api.openai.com/v1").rstrip("/")
        self.model = _first(model,
                            os.environ.get("AI_MODEL"),
                            os.environ.get("COURSEWARE_MODEL")) or "gpt-4o-mini"
        # proxy：四来源优先级
        self.proxy = (_first(proxy,
                             os.environ.get("AI_PROXY"),
                             os.environ.get("COURSEWARE_PROXY"),
                             os.environ.get("HTTPS_PROXY"),
                             os.environ.get("HTTP_PROXY")))
        self._opener = None
        if self.proxy:
            self._opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}))

    def is_strong(self):
        """是否强模型（推理型/大模型）。含弱档标志词（flash/lite/mini/…）判为弱模型。"""
        m = (self.model or "").lower()
        return not any(k in m for k in self.WEAK_MARKS)

    def complete(self, messages, temperature=0.6, timeout=45,
                 max_tokens=1500, retries=2):
        """调用 /chat/completions，返回 content 字符串。

        retries：HTTPError/超时按 2s/5s 指数退避重试；非网络错误（如鉴权失败）立即抛出。

        强模型适配：强模型（推理型）在调用前就把 max_tokens 抬到下限（避免思考未完成
        就截断导致 content 为空）；弱模型保持原 max_tokens 不变。
        """
        url = self.base_url + "/chat/completions"
        if self.is_strong():
            max_tokens = max(int(max_tokens), self.STRONG_MIN_TOKENS)
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        data = self._post(url, body, timeout, retries)
        return data["choices"][0]["message"].get("content") or ""

    def complete_with_tools(self, messages, tools, temperature=0.3,
                            timeout=300, max_tokens=16000, retries=4):
        """带 function-calling 的调用（agent 核心）。返回 (content, tool_calls)。

        - content: 模型文本（工具轮次通常为空字符串）
        - tool_calls: list[dict]，每项 {id, name, arguments(dict), _raw_args(str)}
                      arguments 已从 JSON 字符串反序列化为 dict
        若模型直接返回文本（未调用任何工具），tool_calls 为空列表。
        """
        url = self.base_url + "/chat/completions"
        if self.is_strong():
            max_tokens = max(int(max_tokens), self.STRONG_MIN_TOKENS)
        body = {
            "model": self.model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        raw = self._post(url, json.dumps(body).encode("utf-8"), timeout, retries)
        msg = raw["choices"][0]["message"]
        content = msg.get("content") or ""
        tool_calls = []
        for tc in (msg.get("tool_calls") or []):
            if tc.get("type") != "function":
                continue
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            tool_calls.append({
                "id": tc.get("id", ""), "name": fn.get("name", ""),
                "arguments": args, "_raw_args": fn.get("arguments") or "{}",
            })
        return content, tool_calls

    # ------------------------------------------------------------------
    # 内部：POST + 指数退避重试（complete 与 complete_with_tools 共用）
    # ------------------------------------------------------------------
    def _post(self, url, body, timeout, retries):
        last_err = None
        for attempt in range(1, max(retries, 1) + 1):
            try:
                req = urllib.request.Request(url, data=body, method="POST")
                req.add_header("Content-Type", "application/json")
                req.add_header("Authorization", "Bearer " + self.api_key)
                if self._opener:
                    with self._opener.open(req, timeout=timeout) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                else:
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code == 429:
                    # 限流：重试 + 更长退避（连续批量跑时 API 会限流）
                    last_err = RuntimeError(f"LLM 限流 429: {detail}")
                    time.sleep(min(5 * attempt, 20))
                    continue
                # 其它 4xx（鉴权/参数错误）不重试，立即抛出
                if 400 <= e.code < 500:
                    raise RuntimeError(f"LLM HTTP {e.code}: {detail}")
                last_err = RuntimeError(f"LLM HTTP {e.code}: {detail}")
            except Exception as e:  # 超时 / 连接错误 → 重试
                last_err = RuntimeError(f"LLM 调用失败: {e}")
            # 退避：1→2s, 2→5s（指数，封顶 5s）
            if attempt < max(retries, 1):
                time.sleep(min(2 ** attempt, 5))
        raise last_err or RuntimeError("LLM 调用失败（未知错误）")


def make_client(env=None):
    """从 orchestrator.load_env 返回的 dict 或 os.environ 构造 LLMClient。

    env 优先（网页/测试注入），缺失时回退 os.environ。AI_*/COURSEWARE_* 内部再统一读取。
    """
    env = env or {}
    get = lambda k: env.get(k) or os.environ.get(k)
    return LLMClient(
        api_key=get("AI_API_KEY") or get("COURSEWARE_API_KEY"),
        base_url=get("AI_BASE_URL") or get("COURSEWARE_BASE_URL"),
        model=get("AI_MODEL") or get("COURSEWARE_MODEL"),
        proxy=get("AI_PROXY") or get("COURSEWARE_PROXY"),
    )
