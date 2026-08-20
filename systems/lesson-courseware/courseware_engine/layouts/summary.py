# -*- coding: utf-8 -*-
"""layouts/summary.py —— 总结卡片（全部适用）。"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    points = slots.get("points", []) or []
    formula = slots.get("formula", "")
    primary = theme.get("primary", "#9a3412")
    accent = theme.get("accent", "#0f766e")
    pts_html = ""
    if points:
        lis = "".join(f'<li>{_esc(p)}</li>' for p in points)
        pts_html = f'<ul class="sum-points">{lis}</ul>'
    formula_html = ""
    if formula:
        formula_html = (
            f'<div class="sum-formula" style="border-left:6px solid {accent};background:var(--surface)">'
            f'<span class="sf-tag" style="color:{accent}">口诀 / 公式</span>'
            f'<span class="sf-text">{_esc(formula)}</span></div>')
    return (
        '<div class="ly ly-summary">'
        '<h2 class="ly-h" style="color:var(--primary)">本课小结</h2>'
        f'{pts_html}{formula_html}'
        '</div>')


DEF = LayoutDef(
    layout_id="summary", label="总结卡片",
    slot_schema={
        "points": {"type": "list[str]", "req": True, "min_items": 1, "max_items": 5, "max_chars": 60},
        "formula": {"type": "str", "max_chars": 80},
    },
    applicable={"cats": "*", "kinds": ["summary"], "stages": "*"},
    css=(".ly-summary{padding:6% 8%}"
         ".ly-summary .ly-h{font-size:clamp(20px,3.4vw,30px);margin:0 0 18px}"
         ".ly-summary .sum-points{list-style:none;margin:0 0 18px;padding:0;display:grid;gap:12px}"
         ".ly-summary .sum-points li{background:var(--surface);border-radius:10px;padding:12px 16px;font-size:clamp(15px,2.3vw,20px);line-height:1.6}"
         ".ly-summary .sum-formula{padding:14px 18px;border-radius:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}"
         ".ly-summary .sf-tag{font-weight:800;font-size:14px;flex:0 0 auto}"
         ".ly-summary .sf-text{font-size:clamp(16px,2.6vw,22px);font-weight:700}"),
    _render=render,
)
