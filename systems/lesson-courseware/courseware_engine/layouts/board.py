# -*- coding: utf-8 -*-
"""layouts/board.py —— 中心辐射板书 / 思维导图。"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    center = slots.get("center", "")
    branches = slots.get("branches", []) or []
    primary = theme.get("primary", "#9a3412")
    accent = theme.get("accent", "#0f766e")
    if not branches:
        return ('<div class="ly ly-board">'
                f'<div class="board-center" style="background:{primary}">{_esc(center)}</div>'
                '<p class="empty">（分支待补充）</p></div>')
    cols = "".join(
        f'<div class="board-branch" style="border-top:4px solid {accent}">'
        f'<div class="board-label" style="color:{primary}">{_esc(b.get("label",""))}</div>'
        f'<ul class="board-items">{"".join("<li>"+_esc(it)+"</li>" for it in b.get("items",[]))}</ul>'
        f'</div>' for b in branches)
    return (
        '<div class="ly ly-board">'
        f'<div class="board-center" style="background:{primary}">{_esc(center)}</div>'
        f'<div class="board-grid">{cols}</div>'
        '</div>')


DEF = LayoutDef(
    layout_id="board", label="中心辐射板书",
    slot_schema={
        "center": {"type": "str", "req": True, "max_chars": 24},
        "branches": {"type": "list[dict]", "req": True, "min_items": 1, "max_items": 5,
                     "keys": {"label": {"type": "str", "max_chars": 16},
                              "items": {"type": "list[str]", "max_items": 4, "max_chars": 40}}},
    },
    applicable={"cats": "*", "kinds": ["board", "summary"], "stages": "*"},
    css=(".ly-board{padding:calc(5% * var(--pad-scale,1)) calc(7% * var(--pad-scale,1));display:flex;flex-direction:column;height:100%}"
         ".ly-board .board-center{align-self:center;color:#fff;font-weight:800;font-size:clamp(18px,2.8vw,26px);padding:calc(12px * var(--pad-scale,1)) calc(28px * var(--pad-scale,1));border-radius:var(--radius,999px);margin-bottom:22px}"
         ".ly-board .board-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;flex:1;align-content:center}"
         ".ly-board .board-branch{background:var(--surface);border-radius:var(--radius,12px);padding:calc(14px * var(--pad-scale,1)) calc(16px * var(--pad-scale,1))}"
         ".ly-board .board-label{font-weight:800;font-size:16px;margin-bottom:8px}"
         ".ly-board .board-items{list-style:none;margin:0;padding:0;display:grid;gap:6px}"
         ".ly-board .board-items li{font-size:clamp(14px,2.1vw,18px);line-height:1.5;padding-left:14px;position:relative}"
         ".ly-board .board-items li::before{content:'';position:absolute;left:0;top:9px;width:6px;height:6px;border-radius:50%;background:var(--accent)}"),
    _render=render,
)
