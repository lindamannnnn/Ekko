# -*- coding: utf-8 -*-
"""layouts/concept.py —— 知识点卡（全部适用）。"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    statement = slots.get("statement", "")
    points = slots.get("points", []) or []
    analogy = slots.get("analogy", "")
    pitfall = slots.get("pitfall", "")
    accent = theme.get("accent", "#0f766e")
    primary = theme.get("primary", "#9a3412")
    warn = "#b45309"
    points_html = ""
    if points:
        lis = "".join(f'<li>{_esc(p)}</li>' for p in points)
        points_html = f'<ul class="concept-points">{lis}</ul>'
    analogy_html = ""
    if analogy:
        analogy_html = (
            f'<div class="concept-callout concept-analogy" style="border-color:{accent}">'
            f'<span class="co-tag" style="color:{accent}">类比</span>{_esc(analogy)}</div>')
    pitfall_html = ""
    if pitfall:
        pitfall_html = (
            f'<div class="concept-callout concept-pitfall" style="border-color:{warn}">'
            f'<span class="co-tag" style="color:{warn}">易错</span>{_esc(pitfall)}</div>')
    return (
        '<div class="ly ly-concept">'
        f'<h2 class="concept-statement">{_esc(statement)}</h2>'
        f'{points_html}{analogy_html}{pitfall_html}'
        '</div>')


DEF = LayoutDef(
    layout_id="concept", label="知识点卡",
    slot_schema={
        "statement": {"type": "str", "req": True, "max_chars": 200},
        "points": {"type": "list[str]", "max_items": 5, "max_chars": 80},
        "analogy": {"type": "str", "max_chars": 90},
        "pitfall": {"type": "str", "max_chars": 90},
    },
    applicable={"cats": "*", "kinds": ["concept"], "stages": "*"},
    css=(".ly-concept{padding:6% 8%}"
         ".ly-concept .concept-statement{font-size:clamp(20px,3.6vw,32px);font-weight:800;color:var(--primary);margin:0 0 18px;line-height:1.4}"
         ".ly-concept .concept-points{margin:0 0 18px;padding-left:22px;font-size:clamp(15px,2.3vw,20px);line-height:1.7}"
         ".ly-concept .concept-points li{margin:6px 0}"
         ".ly-concept .concept-callout{border:1px dashed;padding:12px 16px;border-radius:12px;font-size:clamp(14px,2.1vw,18px);margin-top:14px;line-height:1.6}"
         ".ly-concept .co-tag{font-weight:800;margin-right:8px}"),
    _render=render,
)
