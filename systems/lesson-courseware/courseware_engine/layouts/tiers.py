# -*- coding: utf-8 -*-
"""layouts/tiers.py —— 分层练习 + 分层作业（两变体同文件）。

basic 必填；standard / advanced 可选。每题含 q 与 a，答案折叠（toggleAns）。
页面标题 slots.title 由 pager 设定（练习 / 分层作业）。
"""
from ..util import _esc
from .base import LayoutDef


def _layer(name, color, items):
    if not items:
        return ""
    cards = []
    for it in items:
        q = it.get("q", "")
        a = it.get("a", "")
        cards.append(
            f'<div class="tier-item">'
            f'<div class="tier-q">{_esc(q)}</div>'
            f'<button class="ans-btn" onclick="toggleAns(this)">显示答案</button>'
            f'<div class="tier-ans" style="display:none">{_esc(a)}</div>'
            f'</div>')
    return (
        f'<div class="tier-layer" style="border-color:{color}">'
        f'<div class="tier-name" style="background:{color}">{name}</div>'
        f'<div class="tier-items">{"".join(cards)}</div></div>')


def render(slots, theme):
    title = slots.get("title", "")
    basic = slots.get("basic", []) or []
    standard = slots.get("standard", []) or []
    advanced = slots.get("advanced", []) or []
    primary = theme.get("primary", "#9a3412")
    accent = theme.get("accent", "#0f766e")
    title_html = f'<h2 class="ly-h" style="color:{primary}">{_esc(title)}</h2>' if title else ""
    basic_c = _layer("基础", primary, basic)
    std_c = _layer("提高", accent, standard)
    adv_c = _layer("拓展", "#6d28d9", advanced)
    return (
        '<div class="ly ly-tiers">'
        f'{title_html}{basic_c}{std_c}{adv_c}'
        '</div>')


DEF = LayoutDef(
    layout_id="tiers", label="分层练习/作业",
    slot_schema={
        "title": {"type": "str", "max_chars": 24},
        "basic": {"type": "list[dict]", "req": True, "min_items": 1, "max_items": 3,
                  "keys": {"q": {"type": "str", "max_chars": 120}, "a": {"type": "str", "max_chars": 400}}},
        "standard": {"type": "list[dict]", "max_items": 3,
                     "keys": {"q": {"type": "str", "max_chars": 120}, "a": {"type": "str", "max_chars": 400}}},
        "advanced": {"type": "list[dict]", "max_items": 3,
                     "keys": {"q": {"type": "str", "max_chars": 120}, "a": {"type": "str", "max_chars": 400}}},
    },
    applicable={"cats": "*", "kinds": ["practice", "homework"], "stages": "*"},
    css=(".ly-tiers{padding:5% 7%}"
         ".ly-tiers .ly-h{font-size:clamp(20px,3.2vw,28px);margin:0 0 16px}"
         ".ly-tiers .tier-layer{border:2px solid;background:var(--surface);border-radius:12px;margin-bottom:14px;overflow:hidden}"
         ".ly-tiers .tier-name{color:#fff;font-weight:800;font-size:14px;padding:6px 14px}"
         ".ly-tiers .tier-items{display:grid;gap:12px;padding:14px}"
         ".ly-tiers .tier-item{display:grid;grid-template-columns:1fr auto;grid-template-areas:'q btn' 'ans ans';gap:8px;align-items:center}"
         ".ly-tiers .tier-q{grid-area:q;font-size:clamp(15px,2.2vw,19px);line-height:1.5}"
         ".ly-tiers .ans-btn{grid-area:btn;border:1px solid var(--accent);background:#fff;color:var(--accent);border-radius:8px;padding:5px 12px;font-size:13px;cursor:pointer;font-weight:700}"
         ".ly-tiers .tier-ans{grid-area:ans;font-size:clamp(14px,2.1vw,18px);line-height:1.6;color:var(--ink);white-space:pre-wrap}"),
    _render=render,
)
