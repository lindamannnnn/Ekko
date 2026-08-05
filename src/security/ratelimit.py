"""简单内存级登录失败限流（防暴力破解）。

- 基于 (key_prefix, 客户端 IP) 在滑动窗口内计数，超限即拒绝（429）。
- 内存存储：进程重启即清空；多进程/多实例不共享，仅适合单实例部署。
  生产若多实例，请改用 Redis 等共享存储。
"""
import time
from collections import defaultdict, deque

from flask import abort, request

_WINDOW = 60   # 窗口秒数
_MAX = 10      # 窗口内最大尝试次数（含成功）
_FAILS = defaultdict(deque)


def check_rate_limit(key_prefix, max_count=_MAX, window=_WINDOW):
    """在登录 POST 处理开头调用；超限抛 429。"""
    ip = request.remote_addr or "0.0.0.0"
    key = f"{key_prefix}:{ip}"
    now = time.time()
    dq = _FAILS[key]
    while dq and dq[0] < now - window:
        dq.popleft()
    if len(dq) >= max_count:
        abort(429, description="登录尝试过于频繁，请稍后再试（约 1 分钟后）")
    dq.append(now)
