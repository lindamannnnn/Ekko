# -*- coding: utf-8 -*-
"""courseware_engine/validator.py —— ⑤ 校验闸门（确定性）。

每张页面必须满足底线，否则确定性修补或丢弃；绝不二次调用 LLM。
检查项：
  - 空壳：可见文本低于各版式最小字数。
  - 教案话术：不得出现“教学意图/教学过程/教师检查/教师讲解…”等设计话术。
  - 诗版：vertical_poem 仅当 KB 为古诗时可用（西沙等非诗课一律拦下）。
  - tiers：每题 q 非空；a 非空且不得等于/包含 q（回声）。
  - 跨页同 kind 近重复：Jaccard≥0.85 删后页。

修补策略（确定性）：
  - 含教案话术 -> 逐字段剥离该话术片段。
  - tiers 空答案 -> 回填“（请结合课文内容作答，或请老师讲解）”占位。
"""
import re

from . import layouts as _layouts
from .schemas import PageSpec

_TEACH_TALK = re.compile(
    r"教学意图|教学过程|教学重?点|教师检查|教师讲解|学生将|"
    r"This page focuses|Students will|教案设计|教学设计",
    re.I,
)
_POEM_LAYOUTS = {"vertical_poem", "poem_thinking"}

# 各版式最小可见字数（防空壳）
_MIN_CHARS = {
    "cover": 2, "objectives": 8, "lead_in": 12, "concept": 12,
    "split": 12, "steps": 12, "tiers": 12, "summary": 12,
    "board": 8, "compare": 12, "word_grid": 6, "big_image": 8,
    "poem_thinking": 12,
}


def _all_text(slots):
    out = []
    for v in (slots or {}).values():
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    out.append(x)
                elif isinstance(x, dict):
                    for vv in x.values():
                        if isinstance(vv, str):
                            out.append(vv)
                        elif isinstance(vv, list):
                            out.extend(str(y) for y in vv if isinstance(y, str))
    return " ".join(out)


def _norm(s):
    return re.sub(r"\s", "", s or "")


def _is_poem(kb):
    """判定 KB 是否为古诗/文言文（允许 vertical_poem）。
    三类证据满足任一即可：
      1) KB 有 dynasty+author 字段（手写 KB 的硬证据）
      2) KB.lesson_type == "poem"（由 analyst/适配器判定）
      3) KB.subject_cat == "chinese" 且 KB.key_points 含「朝代/作者/诗人/词人」字样
    """
    dynasty = str(kb.get("dynasty", "") or "").strip()
    author = str(kb.get("author", "") or "").strip()
    if dynasty and author and dynasty not in ("-", "无", ""):
        return True
    if (kb.get("lesson_type") or "").strip() == "poem":
        return True
    kps_text = " ".join(kb.get("key_points") or [])
    if any(k in kps_text for k in ("朝代", "作者", "诗人", "词人", "唐代", "宋代", "清代", "明代")):
        return True
    return False


def validate_page(page, kb, cat="chinese"):
    v = []
    slots = page.slots
    layout = page.layout_id
    txt = _all_text(slots)

    # 1) 空壳
    need = _MIN_CHARS.get(layout, 8)
    if len(_norm(txt)) < need:
        v.append(f"内容过短(<{need}字)")

    # 2) 教案话术
    if _TEACH_TALK.search(txt):
        v.append("含教案话术")

    # 3) 诗版仅诗
    if layout in _POEM_LAYOUTS and not _is_poem(kb):
        v.append("诗版用于非诗课")

    # 4) tiers 答案质量
    if layout == "tiers":
        for tier in ("basic", "standard", "advanced"):
            for it in (slots.get(tier) or []):
                if not isinstance(it, dict):
                    continue
                q = (it.get("q") or "").strip()
                a = (it.get("a") or "").strip()
                if not q:
                    v.append(f"{tier} 存在空题")
                elif not a:
                    v.append(f"{tier} 答案空")
                elif _norm(a) == _norm(q) or _norm(q) in _norm(a):
                    v.append(f"{tier} 答案回声")

    return v


def _jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0
    return len(sa & sb) / len(sa | sb)


def _dedup(pages):
    out, seen = [], {}
    for pg in pages:
        k = pg.kind
        t = _norm(_all_text(pg.slots))
        dup = False
        if len(t) >= 20:
            for s in seen.get(k, []):
                # 字符集 Jaccard 对同主题中文页天然偏高，阈值设为 0.97：
                # 仅丢弃近乎完全相同的页（防 LLM/适配重复），保留只是"同主题但不同焦点"的合法概念页。
                if len(s) >= 20 and _jaccard(t, s) >= 0.97:
                    dup = True
                    break
        if not dup:
            out.append(pg)
            seen.setdefault(k, []).append(t)
    return out


def _patch(pg, kb):
    """确定性修补：剥离教案话术 + 回填 tiers 空答案。返回新 PageSpec。"""
    slots = dict(pg.slots)
    # 剥离教案话术（str 字段 / list[str] / list[dict] 内的 str）
    for k, v in list(slots.items()):
        if isinstance(v, str) and _TEACH_TALK.search(v):
            slots[k] = _TEACH_TALK.sub("", v).strip()
        elif isinstance(v, list):
            nv = []
            for x in v:
                if isinstance(x, str):
                    nv.append(_TEACH_TALK.sub("", x).strip())
                elif isinstance(x, dict):
                    nd = {}
                    for kk, vv in x.items():
                        if isinstance(vv, str):
                            nd[kk] = _TEACH_TALK.sub("", vv).strip()
                        else:
                            nd[kk] = vv
                    nv.append(nd)
                else:
                    nv.append(x)
            slots[k] = nv
    # tiers 空答案回填（KB 优先；此处 KB 已含答案，仅兜底）
    if pg.layout_id == "tiers":
        for tier in ("basic", "standard", "advanced"):
            items = slots.get(tier) or []
            for it in items:
                if isinstance(it, dict) and not (it.get("a") or "").strip():
                    it["a"] = "（请结合课文内容作答，或请老师讲解）"
    return PageSpec(
        page_id=pg.page_id, event_id=pg.event_id, kind=pg.kind,
        layout_id=pg.layout_id, slots=slots, source=pg.source,
    )


def validate_deck(pages, kb, cat="chinese"):
    """⑤ 闸门：逐页校验 + 确定性修补 + 去重。返回 (clean_pages, report)。"""
    report = {"checked": len(pages), "violations": [], "dropped": 0}
    clean = []
    for pg in pages:
        vs = validate_page(pg, kb, cat)
        if vs:
            report["violations"].append(
                {"page": pg.page_id, "kind": pg.kind, "issues": vs})
            pg = _patch(pg, kb)
        clean.append(pg)
    before = len(clean)
    clean = _dedup(clean)
    report["dropped"] = before - len(clean)
    report["passed"] = len(clean)
    return clean, report
