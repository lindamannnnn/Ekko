# -*- coding: utf-8 -*-
"""layouts/poem_thinking.py —— 诗词赏析/笺注页（古文风）。

设计为 古诗/词 课件第二张 concept 页：呈现"上下阕对比 + 主旨 + 修辞/写法"。
风格继承 vertical_poem：宣纸底 + 朱红装饰条 + 楷体。
"""
from ..util import _esc
from .base import LayoutDef


_STANZA_LABELS = ["第一句", "第二句", "第三句", "第四句"]


def render(slots, theme):
    title = slots.get("title") or "笺注 · 赏析"
    stanzas = slots.get("stanzas") or []
    theme_text = (slots.get("theme") or "").strip()
    rhetoric = (slots.get("rhetoric") or "").strip()
    key_phrases = (slots.get("key_phrases") or "").strip()
    primary = theme.get("primary", "#9a3412")
    muted = theme.get("muted", "#78716c")

    # 阕（2 列；只有 1 段时占满；>2 段时横向排 + 自动换行）
    blocks = []
    n = min(len(stanzas), 4)
    grid_cols = "1fr 1fr" if n == 2 else ("1fr" if n == 1 else "1fr 1fr")
    labels = slots.get("stanza_labels") or _STANZA_LABELS
    for i, st in enumerate(stanzas[:4]):
        label = labels[i] if i < len(labels) else f"第{i+1}段"
        if n == 1:
            label = "原 文"
        blocks.append(
            f'<div class="pt-stanza">'
            f'<div class="pt-stanza-head" style="color:{primary}">{_esc(label)}</div>'
            f'<div class="pt-stanza-body">{_esc(st)}</div>'
            f'</div>')
    stanza_html = (f'<div class="pt-stanzas" style="grid-template-columns:{grid_cols}">'
                   + "".join(blocks) + '</div>') if blocks else ""

    def row(label, body, with_sep=True):
        if not body:
            return ""
        sep = '<div class="pt-sep"></div>' if with_sep else ""
        return (
            f'<div class="pt-row">{sep}'
            f'<div class="pt-row-head" style="color:{primary}">{_esc(label)}</div>'
            f'<div class="pt-row-body">{_esc(body)}</div>'
            f'</div>')

    rows_html = (
        row("主旨", theme_text) +
        row("重点词句", key_phrases, with_sep=False) +
        row("修辞 · 写法", rhetoric, with_sep=False))

    title_html = (f'<h2 class="pt-title" style="color:{primary}">{_esc(title)}</h2>'
                  if title else "")

    return (
        '<div class="ly ly-poem_thinking">'
        '<div class="pt-deco-left" aria-hidden="true"></div>'
        f'<div class="pt-head">{title_html}</div>'
        f'{stanza_html}'
        f'<div class="pt-rows">{rows_html}</div>'
        '</div>')


DEF = LayoutDef(
    layout_id="poem_thinking", label="诗词赏析/笺注",
    slot_schema={
        "title": {"type": "str", "max_chars": 16},
        "stanzas": {"type": "list[str]", "min_items": 1, "max_items": 4, "max_chars": 240},
        "theme": {"type": "str", "max_chars": 240},
        "key_phrases": {"type": "str", "max_chars": 240},
        "rhetoric": {"type": "str", "max_chars": 240},
    },
    applicable={"cats": ["chinese"], "kinds": ["concept"], "stages": "*"},
    css=(
        ".ly-poem_thinking{padding:calc(4% * var(--pad-scale,1)) calc(7% * var(--pad-scale,1));display:flex;flex-direction:column;height:100%;"
        "background:linear-gradient(180deg,#fdfaf4 0%,#f9f3e8 100%);"
        "position:relative;overflow:hidden}"
        # 左侧朱红装饰
        ".ly-poem_thinking .pt-deco-left{position:absolute;left:18px;top:14%;bottom:14%;width:3px;"
        "background:linear-gradient(180deg,transparent 0%,#c0392b 12%,#c0392b 88%,transparent 100%);opacity:0.5}"
        # 标题
        ".ly-poem_thinking .pt-head{text-align:center;margin-bottom:14px;position:relative;z-index:1}"
        ".ly-poem_thinking .pt-title{font-family:'KaiTi','STKaiti','楷体',serif;"
        "font-size:clamp(20px,2.8vw,26px);margin:0;font-weight:600;letter-spacing:8px;color:#2c1f15}"
        # 阕网格
        ".ly-poem_thinking .pt-stanzas{display:grid;gap:12px;margin-bottom:12px;position:relative;z-index:1}"
        ".ly-poem_thinking .pt-stanza{background:rgba(255,253,248,0.7);border-radius:var(--radius,8px);"
        "padding:calc(12px * var(--pad-scale,1)) calc(16px * var(--pad-scale,1));border-left:3px solid #c0392b66;}"
        ".ly-poem_thinking .pt-stanza-head{font-family:'KaiTi','楷体',serif;font-size:13px;"
        "font-weight:700;letter-spacing:6px;margin-bottom:6px;display:inline-block;"
        "border-bottom:2px solid currentColor;padding-bottom:2px}"
        ".ly-poem_thinking .pt-stanza-body{font-family:'KaiTi','STKaiti','楷体',serif;"
        "font-size:clamp(15px,2.1vw,18px);line-height:1.95;color:#2c1f15;letter-spacing:1px}"
        # 底部行（主旨/修辞）
        ".ly-poem_thinking .pt-rows{display:flex;flex-direction:column;gap:8px;position:relative;z-index:1;margin-top:auto}"
        ".ly-poem_thinking .pt-row{display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:baseline;"
        "background:rgba(255,253,248,0.6);border-radius:var(--radius,8px);padding:calc(8px * var(--pad-scale,1)) calc(14px * var(--pad-scale,1))}"
        ".ly-poem_thinking .pt-row-head{font-family:'KaiTi','楷体',serif;font-size:13px;"
        "font-weight:700;letter-spacing:4px;flex:0 0 auto;min-width:96px}"
        ".ly-poem_thinking .pt-row-body{font-family:'KaiTi','楷体',serif;font-size:14px;"
        "line-height:1.7;color:#2c1f15;letter-spacing:0.5px}"
        ".ly-poem_thinking .pt-sep{display:none}"),
    _render=render,
)
