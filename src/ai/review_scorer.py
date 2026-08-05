"""课评质量评分（规则化，不额外消耗 Token）。

给出 0-100 分 + 具体通过/未通过的核查项 + 改进建议。
通用化：去掉原 CSP/OJ 专属维度，改为「维度覆盖 / 字数 / 防投诉 / 具体行为」四类通用核查。
"""
import re

# R2b 防投诉：横向比较 / 绝对化
# 注意：只判「与其他学员横向比较」和「排名式绝对化」。
# 允许自比（「比上次进步」）；「第一次接触」「第一步」这类不是排名，不得误判
# ——旧版把裸「第一」列为关键词，导致「第一次接触编程」被误报（2026-08-03 走查发现）。
_COMPLAINT_PATTERNS = [
    r"比其他(?:同学|孩子|学员|小朋友)?",
    r"比别的(?:同学|孩子|学员|小朋友)",
    r"比同(?:学|班同学)",
    r"(?:全班|班里|班上|同学中|所有人中)最",
    r"进步最(?:大|快|明显)",
    r"最(?:聪明|优秀|差|棒的一个|好的一个)",
    r"(?:全班|班级|年级)第一",
    r"第一名",
    r"排名第[一二三1-3]",
    r"数一数二",
    r"倒数", r"垫底", r"拖后腿",
]
_COMPLAINT_RE = [re.compile(p) for p in _COMPLAINT_PATTERNS]
# R2c 编造风险：未确认的数量/时长/他人姓名信号（提示老师核对，不直接判错）
_FABRICATE_HINTS = [
    r"用了\d+\s*分钟", r"花了\d+\s*分钟", r"\d+\s*次", r"\d+\s*分",
    r"第\d+\s*名", r"比赛(拿了|获得|得了)",
]


# 维度关键词同义词：key 为维度名里的 2 字核心词
_DIM_SYNONYMS = {
    "专注": ("认真", "投入", "注意力", "专心", "聚精会神"),
    "纪律": ("守规则", "听指令", "秩序"),
    "逻辑": ("思路", "条理", "推理"),
    "思维": ("思路", "想法", "思考"),
    "创意": ("创造", "想象", "点子", "巧思"),
    "表达": ("讲述", "描述", "说出", "分享"),
    "动作": ("姿势", "体式", "招式"),
    "节奏": ("拍子", "律动", "节拍"),
    "力量": ("力气", "发力", "力度"),
    "柔韧": ("拉伸", "软开度"),
    "笔画": ("运笔", "笔法", "落笔"),
    "结构": ("间架", "布局", "章法"),
    "坐姿": ("握笔", "姿势"),
    "代码": ("程序", "编程", "脚本"),
    "调试": ("排错", "找错", "改错", "debug"),
    "色彩": ("颜色", "配色", "上色"),
    "构图": ("布局", "画面", "取景"),
    "配合": ("合作", "协作", "团队"),
    "耐力": ("体能", "坚持", "持久"),
    "作业": ("练习", "题目", "习题"),
    "订正": ("改错", "纠正", "订错"),
    "参与": ("举手", "回答", "互动", "发言"),
    "完成": ("做完", "完成度", "交付"),
}


def _dim_hit(dim: str, text: str) -> bool:
    """维度是否被覆盖：整词 → 2 字子串 → 同义词，逐级放宽。"""
    if not dim:
        return False
    if dim in text:
        return True
    grams = {dim[i:i + 2] for i in range(len(dim) - 1)} if len(dim) >= 2 else {dim}
    for g in grams:
        if g in text:
            return True
        for syn in _DIM_SYNONYMS.get(g, ()):
            if syn in text:
                return True
    return False


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
    found_complaint = []
    for rx in _COMPLAINT_RE:
        m = rx.search(text)
        if m:
            found_complaint.append(m.group(0))
    no_comparison = len(found_complaint) == 0

    # 具体行为：出现可观察动词即算有
    _SPEC_RE = re.compile(r"(完成|做到|主动|举手|展示|尝试|练习|掌握|运用了|写出了|画出了|演奏|演唱|参与了|帮助)")
    has_specific = bool(_SPEC_RE.search(text))

    # 维度覆盖：宽松匹配（整词 → 2 字子串 → 同义词）
    # 旧版要求维度名整词命中且覆盖半数以上，实测大量误判（课评明明写了「很专注」，
    # 却因维度名是「课堂专注度」而判未覆盖）。字数限制下也不可能覆盖全部维度，
    # 因此阈值改为「至少点到 2 个维度（维度不足 2 个时按实际数）」。
    dims = preset.dimensions if preset and preset.dimensions else []
    hit_dims = [d for d in dims if _dim_hit(d, text)]
    dim_hit = len(hit_dims)
    dimension_ok = (len(dims) == 0) or (dim_hit >= min(2, len(dims)))

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
        missed = [d for d in dims if d not in hit_dims]
        suggestions.append(f"评价维度覆盖不足（未提及：{ '、'.join(missed[:3]) }），建议点题。")

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
