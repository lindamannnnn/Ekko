# -*- coding: utf-8 -*-
"""layouts/word_grid.py —— 词汇网格（英语词汇 / 语文识字）。

【自适应列数与字号】—— 词数决定视觉密度，不让任意词数都拉成等宽长条。
- 1 词      → 1 列（居中大卡）
- 2-3 词    → 2 列
- 4-6 词    → 3 列
- 7-12 词   → 4 列
同时按列数 scale 字号 / padding / 卡片最小宽度，避免「词越多字越小、越挤」的视觉雪崩。
"""
from ..util import _esc
from .base import LayoutDef


def _cols_for(n):
    if n <= 1:
        return 1
    if n <= 3:
        return 2
    if n <= 6:
        return 3
    return 4


def _density_for(n, cols):
    """density 越大越紧凑。3 列 6 词最紧，1 词最松。"""
    per_col = max(1, n // cols)
    # 1 词 1 列 1/列 → 密度 0
    # 6 词 3 列 2/列 → 密度 2
    return max(0, min(2, per_col - 1))


def render(slots, theme):
    words = slots.get("words", []) or []
    primary = theme.get("primary", "#9a3412")
    accent = theme.get("accent", "#0f766e")
    if not words:
        return '<div class="ly ly-word_grid"><p class="empty">（词汇待补充）</p></div>'

    n = len(words)
    cols = _cols_for(n)
    density = _density_for(n, cols)

    cards = []
    for w in words:
        wd = w.get("word", "")
        ph = w.get("phonetic", "")
        pos = w.get("pos", "")
        mg = w.get("meaning", "")
        ex = w.get("example", "")
        ex_html = f'<div class="wg-ex">{_esc(ex)}</div>' if ex else ""
        pos_html = (
            f'<span class="wg-pos" style="color:{accent}">{_esc(pos)}</span>'
            if pos else "")
        # 音标缺失（KB 无音标字段）时不显示 // 空斜杠
        phon_html = f'<div class="wg-phon">/{_esc(ph)}/</div>' if ph else ""
        # 空释义/词性不渲染 meta 行，避免空占位撑出多余空白
        meta_html = (
            f'<div class="wg-meta">{pos_html}<span class="wg-mean">{_esc(mg)}</span></div>'
            if (pos or mg) else "")
        # 生字卡（单字 + 拼音 + 无释义无例句）：居中大字布局，拼音在上、生字居中（田字格感）
        is_char = len(wd) == 1 and bool(ph) and not mg and not ex
        card_cls = "wg-card wg-char" if is_char else "wg-card"
        cards.append(
            f'<div class="{card_cls}" style="border-top:4px solid {primary}">'
            f'{phon_html}'
            f'<div class="wg-word">{_esc(wd)}</div>'
            f'{meta_html}'
            f'{ex_html}</div>')

    # --cols / --density 驱动 CSS 自适应
    style_vars = f'--cols:{cols};--density:{density}'
    return (
        '<div class="ly ly-word_grid">'
        f'<div class="wg-grid" style="{style_vars}" data-cols="{cols}">'
        f'{"".join(cards)}</div>'
        '</div>')


DEF = LayoutDef(
    layout_id="word_grid", label="词汇网格",
    slot_schema={
        "words": {"type": "list[dict]", "req": True, "min_items": 1, "max_items": 12,
                  "keys": {
                      "word": {"type": "str", "max_chars": 24},
                      "phonetic": {"type": "str", "max_chars": 30},
                      "pos": {"type": "str", "max_chars": 12},
                      "meaning": {"type": "str", "max_chars": 30},
                      "example": {"type": "str", "max_chars": 60},
                  }},
    },
    applicable={"cats": ["english", "chinese"], "kinds": ["concept", "lead_in"], "stages": "*"},
    css=(".ly-word_grid{padding:calc(5% * var(--pad-scale,1)) calc(7% * var(--pad-scale,1))}"
         # 默认 3 列；按 --cols 切换（1/2/3/4 列）
         ".ly-word_grid .wg-grid{display:grid;gap:14px;"
         "grid-template-columns:repeat(var(--cols,3),minmax(0,1fr))}"
         # 卡片基础
         ".ly-word_grid .wg-card{background:var(--surface);border-radius:var(--radius,12px);"
         "padding:calc(16px * var(--pad-scale,1)) calc(18px * var(--pad-scale,1));box-shadow:0 2px 8px rgba(0,0,0,.05)}"
         # 生字卡（单字+拼音）：居中大字，拼音在上、生字居中
         ".ly-word_grid .wg-card.wg-char{display:flex;flex-direction:column;align-items:center;"
         "justify-content:center;padding:calc(14px * var(--pad-scale,1)) calc(6px * var(--pad-scale,1));gap:3px}"
         ".ly-word_grid .wg-card.wg-char .wg-phon{font-size:12px;margin:0;color:var(--muted);line-height:1.2}"
         ".ly-word_grid .wg-card.wg-char .wg-word{font-size:clamp(26px,3.6vw,38px);line-height:1.15;margin:2px 0}"
         # 字号默认（3 列 4-6 词）
         ".ly-word_grid .wg-word{font-size:clamp(18px,2.4vw,24px);font-weight:800;color:var(--primary)}"
         ".ly-word_grid .wg-phon{color:var(--muted);font-size:13px;margin:2px 0 8px}"
         ".ly-word_grid .wg-meta{display:flex;gap:8px;align-items:baseline;font-size:15px;flex-wrap:wrap}"
         ".ly-word_grid .wg-mean{font-weight:600}"
         ".ly-word_grid .wg-ex{margin-top:8px;font-size:13px;color:var(--muted);font-style:italic;line-height:1.5}"
         # ---- 1 列（1 词）：居中大卡，字号加大 ----
         ".ly-word_grid .wg-grid[data-cols='1'] .wg-card{padding:calc(24px * var(--pad-scale,1)) calc(28px * var(--pad-scale,1))}"
         ".ly-word_grid .wg-grid[data-cols='1'] .wg-word{font-size:clamp(28px,4vw,40px)}"
         ".ly-word_grid .wg-grid[data-cols='1'] .wg-phon{font-size:16px}"
         ".ly-word_grid .wg-grid[data-cols='1'] .wg-meta{font-size:18px}"
         ".ly-word_grid .wg-grid[data-cols='1'] .wg-ex{font-size:15px}"
         # ---- 2 列（2-3 词）：舒适 ----
         ".ly-word_grid .wg-grid[data-cols='2'] .wg-card{padding:calc(18px * var(--pad-scale,1)) calc(20px * var(--pad-scale,1))}"
         ".ly-word_grid .wg-grid[data-cols='2'] .wg-word{font-size:clamp(20px,2.8vw,28px)}"
         # ---- 3 列（4-6 词）：默认 ----
         ".ly-word_grid .wg-grid[data-cols='3'] .wg-card{padding:calc(14px * var(--pad-scale,1)) calc(16px * var(--pad-scale,1))}"
         ".ly-word_grid .wg-grid[data-cols='3'] .wg-word{font-size:clamp(17px,2.2vw,22px)}"
         ".ly-word_grid .wg-grid[data-cols='3'] .wg-phon{font-size:12px}"
         ".ly-word_grid .wg-grid[data-cols='3'] .wg-meta{font-size:13px}"
         ".ly-word_grid .wg-grid[data-cols='3'] .wg-ex{font-size:12px}"
         # ---- 4 列（7-12 词）：紧凑 ----
         ".ly-word_grid .wg-grid[data-cols='4']{gap:10px}"
         ".ly-word_grid .wg-grid[data-cols='4'] .wg-card{padding:calc(12px * var(--pad-scale,1)) calc(14px * var(--pad-scale,1))}"
         ".ly-word_grid .wg-grid[data-cols='4'] .wg-word{font-size:clamp(15px,1.9vw,19px)}"
         ".ly-word_grid .wg-grid[data-cols='4'] .wg-phon{font-size:11px;margin-bottom:6px}"
         ".ly-word_grid .wg-grid[data-cols='4'] .wg-meta{font-size:12px}"
         ".ly-word_grid .wg-grid[data-cols='4'] .wg-ex{font-size:11px;margin-top:6px}"),
    _render=render,
)
