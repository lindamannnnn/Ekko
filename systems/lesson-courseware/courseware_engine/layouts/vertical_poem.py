# -*- coding: utf-8 -*-
"""layouts/vertical_poem.py —— 竖排古诗/词（行业标准版式）。

设计原则（参考线装书 / 古籍竖排排版规范）：
· 每列 = 原文中的一个自然短语（"，"/"、" 间内容），不截断、不丢字；
· 列与列之间等距，列内字符上下排列（writing-mode: vertical-rl）；
· 阕与阕之间用竖虚线 + 较宽间距分隔；
· 楷体（KaiTi）+ 墨色字，左侧朱红装饰条；
· 标题居中、作者·朝代（byline）放底部。
"""
from ..util import _esc
from .base import LayoutDef


def render(slots, theme):
    title = slots.get("title", "")
    subtitle = slots.get("subtitle", "")
    lines = slots.get("lines", []) or []
    byline = slots.get("byline", "")
    rhythm = slots.get("rhythm", "")
    note = slots.get("note", "")
    primary = theme.get("primary", "#9a3412")
    muted = theme.get("muted", "#78716c")

    vlines = []
    for ln in lines:
        if not ln:
            continue
        if ln == "§":
            vlines.append('<div class="vp-stanza-sep" aria-hidden="true"></div>')
        else:
            vlines.append(f'<div class="vline">{_esc(ln)}</div>')
    poem_html = "".join(vlines)

    title_html = f'<h2 class="vp-title" style="color:{primary}">{_esc(title)}</h2>' if title else ""
    sub_html = f'<div class="vp-sub" style="color:{muted}">{_esc(subtitle)}</div>' if subtitle else ""
    byline_html = f'<div class="vp-byline" style="color:{muted}">{_esc(byline)}</div>' if byline else ""
    rhythm_html = f'<div class="vp-rhythm" style="color:{muted}">朗读：{_esc(rhythm)}</div>' if rhythm else ""
    note_html = f'<div class="vp-note" style="color:{muted}">{_esc(note)}</div>' if note else ""

    return (
        '<div class="ly ly-vertical_poem">'
        '<div class="vp-deco-left" aria-hidden="true"></div>'
        f'<div class="vp-head">{title_html}{sub_html}</div>'
        f'<div class="vp-poem">{poem_html}</div>'
        f'<div class="vp-foot">{byline_html}{rhythm_html}{note_html}</div>'
        '</div>')


DEF = LayoutDef(
    layout_id="vertical_poem", label="竖排古诗/词",
    slot_schema={
        "title": {"type": "str", "req": True, "max_chars": 16},
        "subtitle": {"type": "str", "max_chars": 32},
        "lines": {"type": "list[str]", "req": True, "min_items": 2, "max_items": 24, "max_chars": 12},
        "byline": {"type": "str", "max_chars": 40},
        "rhythm": {"type": "str", "max_chars": 60},
        "note": {"type": "str", "max_chars": 80},
    },
    applicable={"cats": ["chinese"], "kinds": ["concept", "lead_in"], "stages": "*"},
    css=(
        # 主容器：米白宣纸底
        ".ly-vertical_poem{padding:calc(5% * var(--pad-scale,1)) calc(8% * var(--pad-scale,1));display:flex;flex-direction:column;height:100%;"
        "background:linear-gradient(180deg,#fdfaf4 0%,#f9f3e8 100%);"
        "position:relative;overflow:hidden}"
        # 左侧朱红竖条（线装书版心装饰）
        ".ly-vertical_poem .vp-deco-left{position:absolute;left:22px;top:18%;bottom:18%;width:3px;"
        "background:linear-gradient(180deg,transparent 0%,#c0392b 12%,#c0392b 88%,transparent 100%);opacity:0.55}"
        # 标题区
        ".ly-vertical_poem .vp-head{text-align:center;margin-bottom:18px;position:relative;z-index:1}"
        ".ly-vertical_poem .vp-title{font-family:'KaiTi','STKaiti','楷体',serif;"
        "font-size:clamp(22px,3.4vw,32px);margin:0;font-weight:600;letter-spacing:8px;color:#2c1f15}"
        ".ly-vertical_poem .vp-sub{font-size:13px;margin-top:6px;letter-spacing:2px;font-family:'KaiTi','楷体',serif}"
        # 诗版主体：列从右到左
        ".ly-vertical_poem .vp-poem{display:flex;flex-direction:row-reverse;justify-content:center;"
        "align-items:center;flex:1;gap:clamp(10px,1.4vw,18px);position:relative;z-index:1}"
        # 单列（一个自然短语）：楷体上下排列
        ".ly-vertical_poem .vline{writing-mode:vertical-rl;text-orientation:upright;"
        "font-family:'KaiTi','STKaiti','楷体',serif;"
        "font-size:clamp(22px,3.4vw,32px);font-weight:500;"
        "letter-spacing:10px;line-height:1.18;color:#2c1f15;min-width:1em}"
        # 阕分隔：竖虚线 + 较宽占位
        ".ly-vertical_poem .vp-stanza-sep{width:18px;height:60%;flex:0 0 18px;"
        "border-right:2px dotted rgba(154,52,18,0.45);margin:0 6px}"
        # 底部
        ".ly-vertical_poem .vp-foot{text-align:center;margin-top:18px;position:relative;z-index:1;"
        "font-family:'KaiTi','楷体',serif}"
        ".ly-vertical_poem .vp-byline{font-size:13px;margin-bottom:6px;letter-spacing:2px;color:#7a5b3a}"
        ".ly-vertical_poem .vp-rhythm{font-size:13px;letter-spacing:1px}"
        ".ly-vertical_poem .vp-note{font-size:13px;margin-top:4px;color:#78716c}"
    ),
    _render=render,
)