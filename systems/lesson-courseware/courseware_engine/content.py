# -*- coding: utf-8 -*-
"""courseware_engine/content.py —— ④ 内容填充器（确定性，KB 驱动）。

重设计核心：教材 KB 是内容主笔。本模块不做任何 LLM 自由生成，
只把结构化 KB 的 segments 确定性地映射成 PageSpec（版式 slots 由
编写期 KB 直接给定）。LLM 仅在可选 polish 分支使用，且 fallback 到
KB 原文——demo 默认关闭，故本模块运行时零 LLM。

对比旧 pager：旧版让 LLM「写整页文字」，弱模型随机崩；本版内容来自
KB，弱模型不在正确路径上。
"""
import os
import sys

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from .schemas import PageSpec, TeachingEvent, TeachingScript, DesignDNA
from . import layouts as _layouts


# ---------------------------------------------------------------------------
# ② analyst 等价物：从结构化 KB 的 segments 确定性产出 TeachingScript
# ---------------------------------------------------------------------------
def build_script(kb):
    """KB.segments -> TeachingScript（每段即一个 TeachingEvent）。"""
    segs = kb.get("segments") or []
    events = []
    for i, seg in enumerate(segs, 1):
        ev = TeachingEvent(
            event_id=f"e{i}",
            kind=seg.get("kind", "concept"),
            title=seg.get("title", ""),
            content_brief=seg.get("title", ""),
        )
        events.append(ev)
    dna = DesignDNA(
        subject_cat=kb.get("subject_cat", "chinese"),
        stage=kb.get("stage", "mid"),
        lesson_type=kb.get("lesson_type", "standard"),
    )
    return TeachingScript(
        identity={
            "subject": kb.get("subject", ""),
            "grade": kb.get("grade", ""),
            "topic": kb.get("topic", ""),
            "duration": kb.get("duration", 40),
        },
        events=events,
        dna=dna,
    )


# ---------------------------------------------------------------------------
# ④ 核心：单个 segment -> PageSpec（确定性，经 layout.check_slots 校验）
# ---------------------------------------------------------------------------
def _fill_one(seg, idx):
    layout_id = seg.get("layout")
    if not layout_id or layout_id not in _layouts.LAYOUTS:
        print(f"  [content_fill] 第{idx}段版式未注册（{layout_id}），丢页", flush=True)
        return None
    defn = _layouts.LAYOUTS[layout_id]
    slots = defn.check_slots(seg.get("slots") or {})
    if slots is None:
        # 丢页告警：slots 不满足版式 schema（如 board branches 空/格式错）会被静默丢页，
        # 必须打日志——否则产物缺环节时无法定位是哪页被丢、为什么丢。
        print(f"  [content_fill] 第{idx}段（kind={seg.get('kind')}/layout={layout_id}）"
              f"slots 不满足版式 schema，丢页。slots 键={list((seg.get('slots') or {}).keys())}", flush=True)
        return None
    return PageSpec(
        page_id=f"p{idx:02d}",
        event_id=f"e{idx}",
        kind=seg.get("kind", defn.layout_id),
        layout_id=layout_id,
        slots=slots,
        source="kb",
    )


def content_fill(kb):
    """④ 确定性填充：KB.segments -> PageSpec[]。零 LLM。"""
    segs = kb.get("segments") or []
    pages = []
    for i, seg in enumerate(segs, 1):
        pg = _fill_one(seg, i)
        if pg is not None:
            pages.append(pg)
    return pages


# ---------------------------------------------------------------------------
# 可选 LLM 窄润色（默认不调用；接回弱模型时的唯一入口）
# 失败/超时 -> 返回原页（KB 原文兜底），绝不空、绝不回声。
# ---------------------------------------------------------------------------
def polish_page(page, kb, client, max_tokens=400):
    return page
