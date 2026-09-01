# -*- coding: utf-8 -*-
"""layouts/timeline.py —— 时间轴（历史/语文脉络）。"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    rows = slots.get("rows", []) or []
    accent = theme.get("accent", "#0f766e")
    primary = theme.get("primary", "#9a3412")
    if not rows:
        return '<div class="ly ly-timeline"><p class="empty">（时间轴待补充）</p></div>'
    items = []
    for r in rows:
        t = r.get("time", "")
        e = r.get("event", "")
        items.append(
            f'<li class="tl-item" style="border-left-color:{accent}">'
            f'<span class="tl-dot" style="background:{primary}"></span>'
            f'<span class="tl-time" style="color:{primary}">{_esc(t)}</span>'
            f'<span class="tl-event">{_esc(e)}</span></li>')
    return (
        '<div class="ly ly-timeline">'
        f'<ul class="tl-list">{"".join(items)}</ul>'
        '</div>')


DEF = LayoutDef(
    layout_id="timeline", label="时间轴",
    slot_schema={
        "rows": {"type": "list[dict]", "req": True, "min_items": 1, "max_items": 6,
                 "keys": {"time": {"type": "str", "max_chars": 24},
                          "event": {"type": "str", "max_chars": 50}}},
    },
    applicable={"cats": "*", "kinds": ["concept", "summary"], "stages": "*"},
    css=(".ly-timeline{padding:calc(6% * var(--pad-scale,1)) calc(9% * var(--pad-scale,1))}"
         ".ly-timeline .tl-list{list-style:none;margin:0;padding:0;position:relative}"
         ".ly-timeline .tl-item{position:relative;padding:0 0 22px 28px;border-left:3px solid var(--line)}"
         ".ly-timeline .tl-dot{position:absolute;left:-7px;top:4px;width:12px;height:12px;border-radius:50%}"
         ".ly-timeline .tl-time{font-weight:800;font-size:15px;margin-right:12px}"
         ".ly-timeline .tl-event{font-size:clamp(15px,2.3vw,20px);line-height:1.5}"),
    _render=render,
)
