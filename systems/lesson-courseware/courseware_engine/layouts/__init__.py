# -*- coding: utf-8 -*-
"""courseware_engine/layouts/__init__.py —— 版式注册表 + 目录文本。

LAYOUTS：layout_id → LayoutDef（15 个受控版式，替代 vendor 的 15 分支 _render_slide 单体）。
layout_catalog_text()：给 pager / stylist 注入的「版式目录」，每行 ≤60 字，
  含 id | 适用场景 | 槽位摘要（方案 §4 prompt 设计）。
"""
from .base import LayoutDef, check_slots
from .cover import DEF as cover
from .objectives import DEF as objectives
from .lead_in import DEF as lead_in
from .concept import DEF as concept
from .split import DEF as split
from .vertical_poem import DEF as vertical_poem
from .poem_thinking import DEF as poem_thinking
from .steps import DEF as steps
from .compare import DEF as compare
from .timeline import DEF as timeline
from .word_grid import DEF as word_grid
from .tiers import DEF as tiers
from .board import DEF as board
from .summary import DEF as summary
from .diagram import DEF as diagram
from .big_image import DEF as big_image

LAYOUTS = {
    d.layout_id: d for d in (
        cover, objectives, lead_in, concept, split, vertical_poem, poem_thinking,
        steps, compare, timeline, word_grid, tiers, board, summary, diagram, big_image,
    )
}

# 目录文本摘要（id | 适用 | 槽位）
_CATALOG = [
    ("cover", "全部·封面", "title,subtitle,meta,kick,ribbon"),
    ("objectives", "全部·学习目标", "items[3-4条]"),
    ("lead_in", "全部·情境导入", "scenario,question"),
    ("concept", "全部·知识点卡", "statement,points,analogy,pitfall"),
    ("split", "细读/概念+图", "head_l,body_l,head_r,body_r"),
    ("vertical_poem", "语文·古诗文言", "title,lines[2-24,逗号自然短语],byline,rhythm,note"),
    ("poem_thinking", "语文·诗词赏析", "title,stanzas[2-4段],theme,key_phrases,rhetoric"),
    ("steps", "数学/科学·例题", "problem,steps[3-8],answer,method"),
    ("compare", "正误/易混对比", "right,wrong,why"),
    ("timeline", "脉络/时间轴", "rows[{time,event}]"),
    ("word_grid", "英语/识字·词汇", "words[{word,phonetic,pos,meaning,example}]"),
    ("tiers", "分层练习/作业", "basic,standard,advanced[{q,a}]"),
    ("board", "板书/思维导图", "center,branches[{label,items}]"),
    ("summary", "总结卡片", "points[3-5],formula"),
    ("diagram", "数学·SVG图", "figure[fraction_bars/number_line/bar_model]"),
    ("big_image", "意象/低段导入", "headline,body,svg_hint"),
]


def layout_catalog_text() -> str:
    lines = ["版式目录（id | 适用 | 槽位）："]
    for lid, scene, slots in _CATALOG:
        lines.append(f"- {lid} | {scene} | {slots}")
    return "\n".join(lines)


def get_layout(layout_id):
    return LAYOUTS.get(layout_id)


__all__ = ["LAYOUTS", "LayoutDef", "check_slots", "layout_catalog_text", "get_layout"]
