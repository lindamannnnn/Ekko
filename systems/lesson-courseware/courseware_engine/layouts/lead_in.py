# -*- coding: utf-8 -*-
"""layouts/lead_in.py —— 情境导入（全部适用）。"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    scenario = slots.get("scenario", "")
    question = slots.get("question", "")
    qtag = slots.get("qtag", "想一想")
    accent = theme.get("accent", "#0f766e")
    primary = theme.get("primary", "#9a3412")
    scen_html = f'<p class="lead-scenario">{_esc(scenario)}</p>' if scenario else ""
    q_html = ""
    if question:
        q_html = (
            f'<div class="lead-question" style="border-left:6px solid {accent};background:color-mix(in srgb, var(--accent) 8%, var(--bg))">'
            f'<span class="lead-qtag" style="color:{primary}">{_esc(qtag)}</span>'
            f'<span class="lead-qtext">{_esc(question)}</span></div>')
    return (
        '<div class="ly ly-lead_in">'
        '<h2 class="ly-h">情境导入</h2>'
        f'{scen_html}{q_html}'
        '</div>')


DEF = LayoutDef(
    layout_id="lead_in", label="情境导入",
    slot_schema={
        "scenario": {"type": "str", "req": True, "max_chars": 160},
        "question": {"type": "str", "req": True, "max_chars": 50},
        "qtag": {"type": "str", "req": False, "max_chars": 8},
    },
    applicable={"cats": "*", "kinds": ["lead_in"], "stages": "*"},
    css=(".ly-lead_in{padding:calc(6% * var(--pad-scale,1)) calc(8% * var(--pad-scale,1))}"
         ".ly-lead_in .ly-h{font-size:clamp(20px,3.4vw,30px);margin:0 0 18px;color:var(--primary)}"
         ".ly-lead_in .lead-scenario{font-size:clamp(16px,2.4vw,21px);line-height:1.7;color:var(--ink);margin:0 0 22px}"
         ".ly-lead_in .lead-question{padding:calc(18px * var(--pad-scale,1)) calc(22px * var(--pad-scale,1));border-radius:var(--radius,14px);display:flex;gap:14px;align-items:center;flex-wrap:wrap}"
         ".ly-lead_in .lead-qtag{font-weight:800;font-size:15px;flex:0 0 auto}"
         ".ly-lead_in .lead-qtext{font-size:clamp(18px,3vw,26px);font-weight:700}"),
    _render=render,
)
