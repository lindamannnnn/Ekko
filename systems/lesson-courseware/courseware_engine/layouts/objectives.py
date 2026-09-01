# -*- coding: utf-8 -*-
"""layouts/objectives.py —— 学习目标（全部适用）。"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    items = slots.get("items", [])
    accent = theme.get("accent", "#0f766e")
    primary = theme.get("primary", "#9a3412")
    if not items:
        return '<div class="ly ly-objectives"><p class="empty">（本课学习目标待补充）</p></div>'
    cards = []
    for i, it in enumerate(items, 1):
        cards.append(
            f'<li class="obj-card" style="border-left:5px solid {accent}">'
            f'<span class="obj-no" style="color:{primary}">{i}</span>'
            f'<span class="obj-text">{_esc(it)}</span></li>')
    return (
        '<div class="ly ly-objectives">'
        '<h2 class="ly-h">学习目标</h2>'
        f'<ul class="obj-list">{"".join(cards)}</ul>'
        '</div>')


DEF = LayoutDef(
    layout_id="objectives", label="学习目标",
    slot_schema={
        "items": {"type": "list[str]", "req": True, "min_items": 1, "max_items": 6, "max_chars": 56},
    },
    applicable={"cats": "*", "kinds": ["objectives"], "stages": "*"},
    css=(".ly-objectives{padding:calc(6% * var(--pad-scale,1)) calc(8% * var(--pad-scale,1))}"
         ".ly-objectives .ly-h{font-size:clamp(20px,3.4vw,30px);margin:0 0 18px;color:var(--primary)}"
         ".ly-objectives .obj-list{list-style:none;margin:0;padding:0;display:grid;gap:14px}"
         ".ly-objectives .obj-card{background:var(--surface);border-radius:var(--radius,12px);padding:calc(14px * var(--pad-scale,1)) calc(18px * var(--pad-scale,1));display:flex;gap:14px;align-items:flex-start;box-shadow:0 2px 10px rgba(0,0,0,.05)}"
         ".ly-objectives .obj-no{font-size:22px;font-weight:800;flex:0 0 auto}"
         ".ly-objectives .obj-text{font-size:clamp(15px,2.2vw,19px);line-height:1.55}"),
    _render=render,
)
