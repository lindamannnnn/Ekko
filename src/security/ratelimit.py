"""简单内存级登录失败限流（防暴力破解）。

- 基于 (key_prefix, 客户端 IP) 在滑动窗口内统计「失败次数」，超限即拦截。
- 仅统计失败尝试；一次成功登录即清空该 IP 计数 —— 正常用户永远不会被误伤。
- 内存存储：进程重启即清空；多进程/多实例不共享，仅适合单实例部署。
  生产若多实例，请改用 Redis 等共享存储。
"""
import time
from collections import defaultdict, deque

from flask import request

_WINDOW = 300   # 窗口秒数（5 分钟）
_MAX = 10      # 窗口内最大失败次数（含密码错 / 表单格式错）
_FAILS = defaultdict(deque)


def _key(key_prefix):
    ip = request.remote_addr or "0.0.0.0"
    return f"{key_prefix}:{ip}"


def check_rate_limit(key_prefix, max_count=_MAX, window=_WINDOW):
    """返回该 IP 在窗口内失败次数是否已超限（True=超限）。不主动 abort。"""
    now = time.time()
    dq = _FAILS[_key(key_prefix)]
    while dq and dq[0] < now - window:
        dq.popleft()
    return len(dq) >= max_count


def hit_rate_limit(key_prefix, max_count=_MAX, window=_WINDOW):
    """记录一次失败的登录尝试。"""
    now = time.time()
    dq = _FAILS[_key(key_prefix)]
    while dq and dq[0] < now - window:
        dq.popleft()
    dq.append(now)


def reset_rate_limit(key_prefix):
    """登录成功后清空该 IP 的失败计数。"""
    _FAILS.pop(_key(key_prefix), None)
