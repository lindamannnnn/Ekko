# -*- coding: utf-8 -*-
"""layouts/steps.py —— 例题步骤（数学/科学）。"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    problem = slots.get("problem", "")
    steps = slots.get("steps", []) or []
    answer = slots.get("answer", "")
    method = slots.get("method", "")
    accent = theme.get("accent", "#0f766e")
    primary = theme.get("primary", "#9a3412")
    prob_html = f'<div class="step-problem" style="border-left:6px solid {primary}">{_esc(problem)}</div>' if problem else ""
    step_html = ""
    if steps:
        lis = "".join(
            f'<li><span class="step-no" style="background:{accent}">{i}</span>'
            f'<span class="step-txt">{_esc(s)}</span></li>'
            for i, s in enumerate(steps, 1))
        step_html = f'<ol class="step-list">{lis}</ol>'
    ans_html = f'<div class="step-answer" style="color:{primary}">答：{_esc(answer)}</div>' if answer else ""
    method_html = ""
    if method:
        method_html = (
            f'<div class="step-method" style="border-color:{accent}">'
            f'<span class="sm-tag" style="color:{accent}">方法</span>{_esc(method)}</div>')
    return (
        '<div class="ly ly-steps">'
        f'{prob_html}{step_html}{ans_html}{method_html}'
        '</div>')


DEF = LayoutDef(
    layout_id="steps", label="例题步骤",
    slot_schema={
        "problem": {"type": "str", "req": True, "max_chars": 160},
        "steps": {"type": "list[str]", "req": True, "min_items": 1, "max_items": 8, "max_chars": 60},
        "answer": {"type": "str", "req": True, "max_chars": 120},
        "method": {"type": "str", "max_chars": 120},
    },
    applicable={"cats": ["math", "science"], "kinds": ["example"], "stages": "*"},
    css=(".ly-steps{padding:calc(5% * var(--pad-scale,1)) calc(7% * var(--pad-scale,1))}"
         ".ly-steps .step-problem{background:var(--surface);border-radius:var(--radius,12px);padding:calc(14px * var(--pad-scale,1)) calc(18px * var(--pad-scale,1));font-size:clamp(16px,2.6vw,22px);font-weight:600;margin-bottom:18px}"
         ".ly-steps .step-list{list-style:none;margin:0;padding:0;counter-reset:none;display:grid;gap:12px}"
         ".ly-steps .step-list li{display:flex;gap:12px;align-items:flex-start}"
         ".ly-steps .step-no{flex:0 0 auto;width:26px;height:26px;border-radius:50%;color:#fff;font-weight:800;font-size:14px;display:flex;align-items:center;justify-content:center;margin-top:2px}"
         ".ly-steps .step-txt{font-size:clamp(15px,2.3vw,20px);line-height:1.6}"
         ".ly-steps .step-answer{font-size:clamp(16px,2.6vw,22px);font-weight:800;margin-top:16px}"
         ".ly-steps .step-method{border:1px dashed;padding:calc(10px * var(--pad-scale,1)) calc(14px * var(--pad-scale,1));border-radius:var(--radius,10px);font-size:clamp(14px,2.1vw,18px);margin-top:12px}"
         ".ly-steps .sm-tag{font-weight:800;margin-right:8px}"),
    _render=render,
)
