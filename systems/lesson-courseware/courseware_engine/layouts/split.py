# -*- coding: utf-8 -*-
"""layouts/split.py —— 左右分栏（文本细读+批注 / 概念+图示）。"""
from ..util import _esc
from .base import LayoutDef


def _col(head, body):
    lis = "".join(f'<li>{_esc(b)}</li>' for b in (body or []))
    return (f'<div class="split-col">'
            f'<h3 class="split-head">{_esc(head)}</h3>'
            f'<ul class="split-body">{lis}</ul></div>')


def render(slots, theme):
    hl = slots.get("head_l", "")
    bl = slots.get("body_l", []) or []
    hr = slots.get("head_r", "")
    br = slots.get("body_r", []) or []
    accent = theme.get("accent", "#0f766e")
    return (
        '<div class="ly ly-split">'
        f'<div class="split-grid">'
        f'{_col(hl, bl)}'
        f'<div class="split-divider" style="background:{accent}"></div>'
        f'{_col(hr, br)}'
        '</div></div>')


DEF = LayoutDef(
    layout_id="split", label="左右分栏",
    slot_schema={
        "head_l": {"type": "str", "req": True, "max_chars": 24},
        "body_l": {"type": "list[str]", "req": True, "min_items": 1, "max_items": 6, "max_chars": 80},
        "head_r": {"type": "str", "req": True, "max_chars": 24},
        "body_r": {"type": "list[str]", "req": True, "min_items": 1, "max_items": 6, "max_chars": 80},
    },
    applicable={"cats": "*", "kinds": ["concept", "example", "activity"], "stages": "*"},
    css=(".ly-split{padding:calc(5% * var(--pad-scale,1)) calc(7% * var(--pad-scale,1))}"
         ".ly-split .split-grid{display:grid;grid-template-columns:1fr 4px 1fr;gap:18px;align-items:stretch;height:100%}"
         ".ly-split .split-col{display:flex;flex-direction:column}"
         ".ly-split .split-head{font-size:clamp(17px,2.6vw,23px);margin:0 0 12px;color:var(--primary)}"
         ".ly-split .split-body{list-style:none;margin:0;padding:0;display:grid;gap:10px}"
         ".ly-split .split-body li{background:var(--surface);border-radius:var(--radius,10px);padding:calc(12px * var(--pad-scale,1)) calc(14px * var(--pad-scale,1));font-size:clamp(14px,2.1vw,18px);line-height:1.6}"
         ".ly-split .split-divider{width:4px;border-radius:var(--radius,2px)}"),
    _render=render,
)
