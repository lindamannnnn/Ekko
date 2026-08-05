"""课评输出硬校验与确定性兜底修复。

背景（2026-08-03 全量走查）：模型不会稳定回显姓名占位符，30/30 份课评把学生
名字写错；同时 40% 出现「亲爱的家长」群发开头、10% 漏写【课堂内容总结】。
仅靠 prompt 软约束压不住，必须在生成后加一道确定性门禁：

    check_output()  → 找出硬伤（叫错名 / 群发开头 / 缺课堂总结 / 占位符泄漏）
    build_correction_note() → 把硬伤翻译成给模型的纠正指令，用于重生成
    patch_output()  → 重生成后仍不达标时的确定性兜底（改称呼，不编内容）

设计原则：能确定性修的（称呼）直接修；需要内容的（课堂总结）只能重生成，
修不好就如实标记在 score_json.guard 里，让老师一眼看到，绝不静默放行。
"""
import re

# 群发/对家长而非对孩子说话的开头。只在开头一小段里判定，
# 正文中间出现「建议家长陪伴练习」是正常的，不算群发。
# 覆盖三类：① 明确群发语 ② 「亲爱的X妈妈」这类错名+称家长混合形态
#          ③ 开头以「亲爱的/尊敬的/各位」起手（课评应直接称呼孩子）
_GROUP_OPEN_RE = re.compile(
    r"各位家长|亲爱的家长|尊敬的家长|家长们|家长好|各位爸爸妈妈|各位学员家长"
    r"|亲爱的[\u4e00-\u9fa5]{0,4}(?:家长|妈妈|爸爸)"
    r"|^[\s\W]{0,8}[\u4e00-\u9fa5]{1,4}(?:妈妈|爸爸)[，,：:！!]"
    r"|^[\s\W]{0,8}(?:亲爱的|尊敬的|各位)"
)

# 开头的称呼语整体（含「亲爱的小丽妈妈：」这类错名+群发混合形态）
_OPEN_ADDRESS_RE = re.compile(
    r"^([\s\W]{0,8})"
    r"(?:亲爱的|尊敬的|各位)?"
    r"[\u4e00-\u9fa5]{0,4}"
    r"(?:家长们|家长|爸爸妈妈|妈妈|爸爸)"
    r"(?:好|您好)?"
    r"[，,：:！!、\s]*"
)

# 开头「某某，」式称呼（用于错名替换）
_OPEN_NAME_RE = re.compile(r"^([\s\W]{0,8})([\u4e00-\u9fa5]{2,4})([，,：:！!])")

# 这些词出现在开头「XX，」位置时不是人名，别误替换
_NOT_NAME = {
    "今天", "本节", "这节", "这周", "本周", "首先", "最近", "同学", "小朋友",
    "孩子", "老师", "本次", "这次", "课堂", "整体", "总的来说",
}

# 花括号占位符，以及范文里常见的 XXX / xx 同学 式占位（模型会照抄）
_PLACEHOLDER_RE = re.compile(
    r"\{\{\s*(?:STU|STU_NICK|PEER_\d+)\s*\}?\}?"
    r"|[XxＸx]{2,4}(?=同学|小朋友|家长|，|,|。|！|!|的)"
)

# 课堂内容总结的标记（R3 第①段要求显式写出）
_SUMMARY_MARKERS = ("课堂内容总结", "课堂内容", "本节课内容", "课堂总结")

# 新段落结构（2026-08-04）：第 1 段＝**纯编号知识点列表**，直接以「1.」起头，
# 不再带「【课堂内容总结】」标记，也不含「本节课学习了…」这类句式。
# 若不单独识别，会被判成 missing_summary 硬伤 → 触发无谓的重生成死循环。
_NUMBERED_HEAD_RE = re.compile(r"^\s*1\s*[\.、\)]\s*\S")
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+\s*[\.、\)]\s*\S", re.MULTILINE)


def _para2_start(text) -> int:
    """第 2 段【课后评价】的起始下标；无第 2 段时返回 0。

    新结构下称呼只属于第 2 段，补称呼/改错名必须落在第 2 段，
    绝不能插到第 1 段的编号列表前面。
    """
    m = re.search(r"\n\s*\n", text or "")
    return m.end() if m else 0


def _has_numbered_summary(text) -> bool:
    """开头即为编号知识点列表（首段 ≥2 条）→ 视为【课堂内容总结】已写。"""
    t = text or ""
    if not _NUMBERED_HEAD_RE.match(t):
        return False
    first_para = re.split(r"\n\s*\n", t, maxsplit=1)[0]
    return len(_NUMBERED_ITEM_RE.findall(first_para)) >= 2

# 没打标记、但确实总结了「这节课教了什么」的写法。
# 例：「这节课我们一起学习了横竖基础笔画」——内容达标，只是格式没打标记，
# 属于格式瑕疵而非硬伤，不值得为此再烧一次生成（2026-08-03 回归验证结论）。
# 前缀放宽到「我们/你」等口语开头（2026-08-03 连续课模拟发现：重生成稿常写
# 「我们学习了…」而非「本节课学习了…」，此前被误判为硬伤 missing_summary 而无法兜底修复）。
_SUMMARY_CONTENT_RE = re.compile(
    r"(?:这节课|本节课|今天|本周|这周|我们|你)[^。！？\n]{0,14}?"
    r"(?:学习了|学了|讲了|练习了|完成了|认识了|掌握了|复习了|开始学|一起学)"
)

# 软问题：只记录、不触发重生成
SOFT_CODES = {"summary_unmarked"}


def _first_sentence(text: str, limit: int = 30) -> str:
    """取第一句（用于开头称呼判定）。正文中间出现「家长」是正常的，不能算群发。"""
    t = (text or "").lstrip()
    m = re.search(r"[，,。！!？?：:\n]", t)
    head = t[:m.start()] if m else t
    return head[:limit]


def hard_issues(issues):
    return [i for i in (issues or []) if i not in SOFT_CODES]


def _is_group_open(text, names):
    """开头是否在对「家长群体」说话，而不是对这个孩子说话。

    「亲爱的凯凯，」是完全合格的私信开头 —— 只要开头就点了该生的名、
    且没带家长/妈妈/爸爸这类称谓，就不算群发（旧版把「亲爱的」一律判为
    群发，导致 2026-08-03 回归中 2 份合格课评被误报）。

    2026-08-04 新结构：第 1 段是纯编号知识点、不含称呼，真正的称呼在第 2 段，
    因此两段的段首都要查（只要有一段是群发口吻就算问题）。
    """
    heads = [_first_sentence(text)]
    p2 = _para2_start(text)
    if p2:
        heads.append(_first_sentence(text[p2:]))
    for head in heads:
        named = any(n and n in head for n in names)
        if named and not re.search(r"家长|妈妈|爸爸", head):
            continue          # 这一段是合格的私信开头
        if _GROUP_OPEN_RE.search(head):
            return True
    return False


def check_output(text, call_name, real_name="", allow_group_open=False,
                 require_summary=True, min_len=180):
    """返回问题码列表，空列表表示通过。

    call_name: 应当使用的称呼（昵称优先，回退本名）
    real_name: 学生本名，正文用本名称呼也算合格
    allow_group_open: 托管类课评允许群发开头
    min_len: 课评字数下限（产品规定 180）。低于此值视为结构不完整
             （缺表现亮点 / 缺家庭建议），必须重生成；与上限截断（_enforce_word_limit）
             互补，堵住「首遍太短、门禁漏放」的口子（2026-08-03 连续课模拟发现：
             书法科约 1/5 概率输出仅含开头+总结、缺少表现与建议段的残稿）。
    """
    issues = []
    t = (text or "").strip()
    if not t:
        return ["empty"]

    names = [n for n in (call_name, real_name) if n]
    if names and not any(n in t for n in names):
        issues.append("name_missing")

    if not allow_group_open and _is_group_open(t, names):
        issues.append("group_open")

    if require_summary:
        if _has_numbered_summary(t) or any(m in t for m in _SUMMARY_MARKERS):
            pass
        elif _SUMMARY_CONTENT_RE.search(t):
            issues.append("summary_unmarked")   # 软问题：有内容、没打标记
        else:
            issues.append("missing_summary")

    if _PLACEHOLDER_RE.search(t):
        issues.append("placeholder_leak")

    if len(t) < min_len:
        issues.append("too_short")

    return issues


_ISSUE_TEXT = {
    "name_missing": (
        "上一稿通篇没有出现该生的正确昵称「{name}」（很可能自行编造了别的名字）。"
        "本次必须全程使用「{name}」称呼该生，第 2 段【课后评价】第一句就要点名，一字不差"
        "（第 1 段是纯知识点编号列表，不写称呼）。"
    ),
    "group_open": (
        "上一稿用了「各位家长／亲爱的家长」这类群发称呼。"
        "本次第 2 段【课后评价】第一句必须直接对「{name}」本人说话，不得出现任何群发称呼。"
    ),
    "missing_summary": (
        "上一稿缺少第①段【课堂内容总结】。本次必须把它独立成全文第 1 段，"
        "直接以「1.」开头、按 1./2./3. 编号逐条列出本节课课件里实际讲授的具体知识点／主题／活动，"
        "该段内不写称呼、不写评价。"
    ),
    "summary_unmarked": (
        "上一稿的课堂内容总结没有独立成段。本次请把它作为全文第 1 段，"
        "直接以「1.」开头按 1./2./3. 编号罗列知识点，与第 2 段课后评价之间空一行。"
    ),
    "placeholder_leak": (
        "上一稿输出了 {{STU}}／{{PEER_1}} 之类的占位符。"
        "本次禁止出现任何花括号占位符，直接写「{name}」。"
    ),
    "too_short": (
        "上一稿过于简短、结构不完整（很可能只写了课堂总结，"
        "缺少该生的具体表现/亮点描述，也缺少给家长的家庭建议）。"
        "本次必须写满完整两段：第 1 段＝1./2./3. 编号知识点；"
        "第 2 段＝专属称呼开头 + 该生具体表现与亮点 + 待改进点 + 给家长的家庭建议，字数达到要求下限。"
    ),
    "empty": "上一稿为空，请重新完整撰写。",
}


def build_correction_note(issues, call_name) -> str:
    lines = []
    for i, code in enumerate(issues, start=1):
        tpl = _ISSUE_TEXT.get(code)
        if tpl:
            lines.append(f"{i}. " + tpl.replace("{name}", call_name or "该生"))
    return "\n".join(lines)


def patch_output(text, call_name, allow_group_open=False, require_summary=True):
    """确定性兜底：只修「称呼」与「格式标记」，绝不编造内容。

    返回 (new_text, patched_codes)
    """
    t = text or ""
    patched = []
    if not call_name:
        return t, patched

    # 1) 占位符泄漏 → 直接换成正确称呼
    if _PLACEHOLDER_RE.search(t):
        t = _PLACEHOLDER_RE.sub(call_name, t)
        patched.append("placeholder_leak")

    # 2) 群发开头 → 换成「昵称，」（称呼属于第 2 段，优先在第 2 段内替换）
    if not allow_group_open and _is_group_open(t, [call_name]):
        pos = _para2_start(t)
        seg = t[pos:]
        new_seg, cnt = _OPEN_ADDRESS_RE.subn(lambda m: f"{m.group(1)}{call_name}，", seg, count=1)
        if cnt:
            t = t[:pos] + new_seg
            patched.append("group_open")
        elif pos:
            # 第 2 段没匹配到，退回全文首处（兼容模型没分段的旧形态）
            new_t, cnt2 = _OPEN_ADDRESS_RE.subn(lambda m: f"{m.group(1)}{call_name}，", t, count=1)
            if cnt2:
                t = new_t
                patched.append("group_open")

    # 3) 仍无正确姓名 → 在第 2 段段首做错名替换或补称呼。
    #    绝不能插到第 1 段编号知识点前面（会把「1. 掌握…」污染成「周野，1. 掌握…」）。
    if call_name not in t:
        pos = _para2_start(t)
        seg = t[pos:]
        m = _OPEN_NAME_RE.match(seg)
        if m and m.group(2) not in _NOT_NAME:
            new_seg = _OPEN_NAME_RE.sub(lambda mm: f"{mm.group(1)}{call_name}{mm.group(3)}", seg, count=1)
            t = t[:pos] + new_seg
            patched.append("wrong_name_replaced")
        else:
            # 跳过段首的【…】标记块，避免把称呼插进标记里（如「【课后评价】」→「【周野，课后评价】」）
            lead = re.match(r"^\s*【[^】]*】\s*", seg)
            off = lead.end() if lead else 0
            t = t[:pos + off] + f"{call_name}，" + t[pos + off:]
            patched.append("name_prepended")

    # 4) 课堂总结有内容但没打【】标记 → 确定性包成【课堂内容总结】段首。
    #    只处理「软问题 summary_unmarked」：内容确实存在，仅是格式缺标记。
    #    若正文根本无总结内容（missing_summary，硬伤）则绝不空包，留给重生成。
    if (require_summary and not _has_numbered_summary(t)
            and not any(mk in t for mk in _SUMMARY_MARKERS)):
        sm = _SUMMARY_CONTENT_RE.search(t)
        if sm:
            # 优先插在「总结句」句首（sm.start）；若其前存在句号/换行边界，则插在边界之后，
            # 避免把标记插到学生称呼之前或字符串最开头。
            seg = sm.start()
            prev = t.rfind("\n", 0, seg)
            if prev == -1:
                prev = t.rfind("。", 0, seg)
            insert_at = prev + 1 if prev != -1 else seg
            t = t[:insert_at] + "【课堂内容总结】" + t[insert_at:]
            patched.append("summary_unmarked")

    return t, patched
