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
        # 支持多 KEY 轮询：在 .env 里用逗号分隔填入 AI_API_KEY
        raw_key = _first(api_key,
                         os.environ.get("AI_API_KEY"),
                         os.environ.get("COURSEWARE_API_KEY")) or ""
        self.api_keys = [k.strip() for k in raw_key.split(",") if k.strip()] if raw_key else []
        if not self.api_keys:
            self.api_keys = [""]
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
        self._key_index = 0

    def is_strong(self):
        """是否强模型（推理型/大模型）。含弱档标志词（flash/lite/mini/…）判为弱模型。"""
        m = (self.model or "").lower()
        return not any(k in m for k in self.WEAK_MARKS)

    def complete(self, messages, temperature=0.6, timeout=45,
                 max_tokens=1500, retries=2):
        """调用 /chat/completions，返回 content 字符串。

        多 KEY 时依次尝试，遇到限流/超时/服务端错误/鉴权失败自动切换到下一个 key。
        全部 key 失败后抛出最后一个异常。

        retries：单个 KEY 内部 HTTPError/超时按 2s/5s 指数退避重试。

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

        last_err = None
        key_count = len(self.api_keys)
        for key_offset in range(key_count):
            key = self.api_keys[(self._key_index + key_offset) % key_count]
            for attempt in range(1, max(retries, 1) + 1):
                try:
                    req = urllib.request.Request(url, data=body, method="POST")
                    req.add_header("Content-Type", "application/json")
                    req.add_header("Authorization", "Bearer " + key)
                    if self._opener:
                        with self._opener.open(req, timeout=timeout) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                    else:
                        with urllib.request.urlopen(req, timeout=timeout) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                    # 成功后将起始索引挪到下一个 key，实现简单轮询
                    self._key_index = (self._key_index + 1) % key_count
                    return data["choices"][0]["message"].get("content") or ""
                except urllib.error.HTTPError as e:
                    detail = e.read().decode("utf-8", "replace")[:300]
                    if e.code == 429:
                        # 限流：重试 + 更长退避（连续批量跑时 API 会限流）
                        last_err = RuntimeError(f"LLM 限流 429: {detail}")
                        time.sleep(min(5 * attempt, 20))
                        continue
                    # 400/422 等参数错误换 key 也没用，直接抛出
                    if 400 <= e.code < 500 and e.code not in (401,):
                        raise RuntimeError(f"LLM HTTP {e.code}: {detail}")
                    # 401/5xx 等可能为临时异常，换下一个 key
                    last_err = RuntimeError(f"LLM HTTP {e.code}: {detail}")
                    break
                except Exception as e:  # 超时 / 连接错误 → 换下一个 key
                    last_err = RuntimeError(f"LLM 调用失败: {e}")
                    break
                # 单个 key 内部成功前退避（如未被 continue/break 跳过则执行）
                if attempt < max(retries, 1):
                    time.sleep(min(2 ** attempt, 5))
        raise last_err or RuntimeError("所有 API KEY 均调用失败")


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
