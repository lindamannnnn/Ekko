"""课评质量评分（规则化，不额外消耗 Token）。

给出 0-100 分 + 具体通过/未通过的核查项 + 改进建议。
通用化：去掉原 CSP/OJ 专属维度，改为「维度覆盖 / 字数 / 防投诉 / 具体行为」四类通用核查。
"""
import re

# R2b 防投诉：横向比较 / 绝对化 关键词
_COMPLAINT_WORDS = [
    "比其他", "比别的", "比同学", "全班最", "进步最大", "最聪明", "最优秀",
    "第一", "倒数", "垫底", "拖后腿", "最差",
]
# R2c 编造风险：未确认的数量/时长/他人姓名信号（提示老师核对，不直接判错）
_FABRICATE_HINTS = [
    r"用了\d+\s*分钟", r"花了\d+\s*分钟", r"\d+\s*次", r"\d+\s*分",
    r"第\d+\s*名", r"比赛(拿了|获得|得了)",
]


def score_review(text: str, preset=None, student_name="", peer_names=None) -> dict:
    if not text or not text.strip():
        return {
            "score": 0,
            "checks": {"length_ok": False, "no_comparison": False,
                       "has_specific": False, "dimension_ok": False},
            "suggestions": ["生成内容为空，请重试或手动撰写。"],
            "flags": [],
        }

    n = len(text)
    min_len = (preset.length_min if preset else 150) or 150
    max_len = (preset.length_max if preset else 400) or 400
    length_ok = min_len <= n <= max_len

    # R2b 防投诉
    found_complaint = [w for w in _COMPLAINT_WORDS if w in text]
    no_comparison = len(found_complaint) == 0

    # 具体行为：出现可观察动词即算有
    _SPEC_RE = re.compile(r"(完成|做到|主动|举手|展示|尝试|练习|掌握|运用了|写出了|画出了|演奏|演唱|参与了|帮助)")
    has_specific = bool(_SPEC_RE.search(text))

    # 维度覆盖：预设维度关键词命中数
    dims = preset.dimensions if preset and preset.dimensions else []
    dim_hit = 0
    for d in dims:
        if d in text:
            dim_hit += 1
    dimension_ok = (len(dims) == 0) or (dim_hit >= max(1, len(dims) // 2))

    # 打分（简单加权）
    score = 0
    if length_ok:
        score += 30
    else:
        score += max(0, 30 - abs(n - (min_len + max_len) // 2) // 20)
    if no_comparison:
        score += 30
    if has_specific:
        score += 20
    if dimension_ok:
        score += 20
    score = max(0, min(100, score))

    suggestions = []
    if not length_ok:
        suggestions.append(f"字数 {n} 不在建议区间 {min_len}-{max_len}，可增删。")
    if not no_comparison:
        suggestions.append(f"出现疑似横向比较/绝对化表述：{ '、'.join(found_complaint) }，建议改为针对该生本人的描述。")
    if not has_specific:
        suggestions.append("缺少可观察的具体行为，建议补充一个本节课真实发生的小细节。")
    if not dimension_ok and dims:
        suggestions.append(f"未覆盖评价维度（如：{ '、'.join(dims[:3]) }），建议点题。")

    # R2c 编造提示（仅提示，不扣分）
    flags = []
    for pat in _FABRICATE_HINTS:
        m = re.search(pat, text)
        if m:
            flags.append(m.group(0))
    if flags:
        suggestions.append(f"含具体数字/事件（{ '、'.join(flags[:3]) }），请核对确为真实发生，避免编造。")

    return {
        "score": score,
        "checks": {
            "length_ok": length_ok,
            "no_comparison": no_comparison,
            "has_specific": has_specific,
            "dimension_ok": dimension_ok,
        },
        "suggestions": suggestions,
        "flags": flags,
        "length": n,
    }
