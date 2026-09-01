# -*- coding: utf-8 -*-
"""layouts/compare.py —— 对比（正误 / 易混）。"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    right = slots.get("right", "")
    wrong = slots.get("wrong", "")
    why = slots.get("why", "")
    ok_c = "#15803d"
    bad_c = "#b91c1c"
    primary = theme.get("primary", "#9a3412")
    return (
        '<div class="ly ly-compare">'
        f'<div class="cmp-block cmp-right" style="border-color:{ok_c}">'
        f'<div class="cmp-tag" style="background:{ok_c}">正确</div>'
        f'<div class="cmp-text">{_esc(right)}</div></div>'
        f'<div class="cmp-block cmp-wrong" style="border-color:{bad_c}">'
        f'<div class="cmp-tag" style="background:{bad_c}">错误</div>'
        f'<div class="cmp-text">{_esc(wrong)}</div></div>'
        f'<div class="cmp-block cmp-why" style="border-color:{primary}">'
        f'<div class="cmp-tag" style="background:{primary}">为何错</div>'
        f'<div class="cmp-text">{_esc(why)}</div></div>'
        '</div>')


DEF = LayoutDef(
    layout_id="compare", label="对比（正误/易混）",
    slot_schema={
        "right": {"type": "str", "req": True, "max_chars": 120},
        "wrong": {"type": "str", "req": True, "max_chars": 120},
        "why": {"type": "str", "req": True, "max_chars": 120},
    },
    applicable={"cats": "*", "kinds": ["concept", "example", "practice"], "stages": "*"},
    css=(".ly-compare{padding:calc(5% * var(--pad-scale,1)) calc(7% * var(--pad-scale,1));display:flex;flex-direction:column;gap:14px;height:100%;justify-content:center}"
         ".ly-compare .cmp-block{border:2px solid;background:var(--surface);border-radius:var(--radius,12px);padding:calc(14px * var(--pad-scale,1)) calc(18px * var(--pad-scale,1));display:flex;gap:14px;align-items:flex-start}"
         ".ly-compare .cmp-tag{flex:0 0 auto;color:#fff;font-weight:800;font-size:13px;padding:calc(4px * var(--pad-scale,1)) calc(10px * var(--pad-scale,1));border-radius:var(--radius,8px);margin-top:2px}"
         ".ly-compare .cmp-text{font-size:clamp(15px,2.3vw,20px);line-height:1.6}"),
    _render=render,
)
