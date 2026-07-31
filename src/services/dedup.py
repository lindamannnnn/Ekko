"""同班横向去重（P5c）。

全班生成完后一次性两两比对：超阈值（默认 0.35）的两份，只重写"较晚生成"的一份
（注入对方开头句，R6 触发），较早一份保持不变。重写上限 1 轮，仍超标则标黄（dedup_score 仍高）。
比较时剔除知识点(objectives)/共性(common_notes)/姓名占位符，只看实质行文。
"""
import re
from itertools import combinations

_NOISE = [
    r"\{\{STU\}\}", r"\{\{STU_NICK\}\}", r"\{\{PEER_\d+\}\}",
    r"亲爱的家长[朋友]*", r"大家好", r"各位家长",
]


def _clean(text: str) -> str:
    if not text:
        return ""
    t = text
    for pat in _NOISE:
        t = re.sub(pat, "", t)
    # 剔除常见共性短语
    t = re.sub(r"(本节课|今天|这堂课|本次课)", "", t)
    return t.strip()


def _trigram(text: str) -> set:
    t = re.sub(r"\s+", "", text)
    if len(t) < 3:
        return set(t)
    return {t[i:i + 3] for i in range(len(t) - 2)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def pairwise_scores(reviews: list, threshold: float = 0.35) -> list:
    """reviews: list of (review_id, text)。返回 [(id_a, id_b, score), ...] 超阈值的对。"""
    items = [(r[0], _trigram(_clean(r[1]))) for r in reviews if r[1]]
    out = []
    for (ia, ta), (ib, tb) in combinations(items, 2):
        s = _jaccard(ta, tb)
        if s >= threshold:
            out.append((ia, ib, round(s, 3)))
    return out


def opening_sentence(text: str) -> str:
    """取首句（用于向待重写方注入对方开头，触发 R6 差异化）。"""
    for sep in ["。", "！", "！", "\n"]:
        if sep in text:
            return text.split(sep)[0] + sep
    return text[:40]
