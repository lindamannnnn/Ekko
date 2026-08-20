# -*- coding: utf-8 -*-
"""courseware_engine/reviewer.py —— 审核层（自审闭环）。

生成（确定性引擎 + 免费模型层 + 教学专家协议）之后，本模块按「该科教育专家」定义的
针对性标准审核生成结果，返回问题列表；问题由调用方决定：可重试的打回重生成，确定性缺陷
（分层同题/例题缺）则报告为生成器缺陷。

用法：v3 引擎在 content_fill 之前调用 review(kb)，把 issues 打进日志/返回。
"""
from .experts import get_expert


def review(kb):
    """按学科专家标准做确定性校验，返回问题列表（空=通过）。"""
    cat = kb.get("subject_cat")
    expert = get_expert(cat)
    if not expert:
        return []
    try:
        return expert.check(kb, kb.get("segments") or [])
    except Exception as e:  # 审核器自身异常不阻断生成，返回诊断
        return [f"审核器异常：{e}"]


def _segments_to_text(kb):
    """把 segments 转成「[页] 标题 + 内容」纯文本，供 LLM 专家审核。"""
    lines = []
    for i, seg in enumerate(kb.get("segments") or [], 1):
        slots = seg.get("slots") or {}
        stmt = slots.get("statement", "") or slots.get("problem", "") or slots.get("title", "")
        body = []
        for field in ("points", "steps", "items", "lines"):
            v = slots.get(field)
            if isinstance(v, list):
                body.extend(str(x) for x in v)
            elif v:
                body.append(str(v))
        for field in ("scenario", "question", "answer", "method", "theme", "rhetoric", "key_phrases"):
            v = slots.get(field)
            if v:
                body.append(str(v))
        # tiers 练习
        for tier in ("basic", "standard", "advanced"):
            for qa in slots.get(tier, []) or []:
                if isinstance(qa, dict):
                    body.append(f"{qa.get('q','')} 答:{qa.get('a','')}")
        txt = " ".join(x for x in [stmt] + body if x).strip()
        if txt:
            lines.append(f"[第{i}页] {txt[:200]}")
    return "\n".join(lines)


def llm_review(kb, client):
    """按学科教育专家标准用 LLM 审核课件内容，返回问题列表（空=通过）。"""
    cat = kb.get("subject_cat")
    expert = get_expert(cat)
    if not expert or not expert.review_prompt:
        return []
    text = _segments_to_text(kb)
    if not text:
        return []
    try:
        raw = client.complete(
            [{"role": "system", "content": expert.review_prompt},
             {"role": "user", "content": f"课题：{kb.get('topic')}\n课件内容：\n{text}"}],
            temperature=0.2, timeout=120, max_tokens=800)
        if not raw:
            return []
        if "通过" in raw and len(raw.strip()) < 10:
            return []
        issues = [ln.strip() for ln in raw.strip().split("\n") if ln.strip()]
        issues = [i for i in issues if not i.startswith("通过")]
        # 过滤「复述审核维度」的空报：真问题必须引用课件原句（含引号），否则判为清单复述丢弃
        issues = [i for i in issues if any(q in i for q in ("「", "」", '"', '"', "'", "“", "”"))]
        return issues[:12]
    except Exception:
        return []


def review_report(kb):
    """返回 (ok, issues, expert_label)。"""
    issues = review(kb)
    expert = get_expert(kb.get("subject_cat"))
    label = expert.label if expert else kb.get("subject_cat", "")
    return (len(issues) == 0, issues, label)


def expand_with_review(kb, client, max_retry=2):
    """自审闭环：生成教学展开 → LLM 专家审核 → 有问题打回重生成 → 再审核。

    只对 LLM 生成内容（品析/算理/教学展开）重试；确定性缺陷（无例题/分层同题）是生成器
    bug，重试无用，由调用方据 review(kb) 报告。
    返回 (kb, retries_used)。"""
    from .teach_expand import expand_math, expand_chinese, expand_english
    feedback = None
    for attempt in range(max_retry + 1):
        kb = expand_math(kb, client, feedback)
        kb = expand_chinese(kb, client, feedback)
        kb = expand_english(kb, client, feedback)
        llm_issues = llm_review(kb, client)
        if not llm_issues:
            return kb, attempt
        feedback = llm_issues  # 打回：把问题注入下一轮生成
    return kb, max_retry
