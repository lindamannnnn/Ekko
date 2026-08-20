# -*- coding: utf-8 -*-
"""layouts/diagram.py —— 内联 SVG 示意图（数学/科学）。

整体迁移自 vendor/scripts/courseware_gen.py:1271-1379 的 fraction_bars / number_line / bar_model
渲染器（理科课件质量核心资产），改写为吃 theme dict（含 primary）+ 全程 _esc，并收敛调色板。
figure 槽位走 DIAGRAM_RENDERERS 白名单，禁止 LLM 自由写 SVG。
"""
from ..util import _esc
from .base import LayoutDef

_COLORS = ["#9a3412", "#0f766e", "#1d4ed8", "#b45309", "#6d28d9", "#0e7490"]


def _sint(x):
    try:
        return int(float(x))
    except Exception:
        return 0


def _sfloat(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def _c(th, idx):
    return _COLORS[idx % len(_COLORS)]


def _bar_row(x, y, w, h, num, den, color, label):
    bar_w = w - 100
    num = _sint(num)
    den = _sint(den)
    if den <= 0:
        den = 1
    cell = bar_w / den
    out = [f'<rect x="{x}" y="{y}" width="{bar_w}" height="{h}" rx="7" fill="#f4f1ea" stroke="#e4ddcf"/>']
    for i in range(den):
        cx = x + i * cell
        fill = color if i < num else "#ffffff"
        out.append(f'<rect x="{cx+1.5:.1f}" y="{y+1.5:.1f}" width="{cell-3:.1f}" height="{h-3:.1f}" fill="{fill}" stroke="#fff" stroke-width="1"/>')
    if label:
        out.append(f'<text x="{x+bar_w+12:.0f}" y="{y+h/2+5:.0f}" font-size="15" font-weight="700" fill="#26303b">{_esc(label)}</text>')
    return "".join(out)


def _fig_fraction_bars(spec, th):
    bars = spec.get("bars") or []
    if not bars:
        return ""
    common = spec.get("common")
    W = 640
    pad = 16
    bw = W - pad * 2
    rh = 46
    rg = 16
    rows = len(bars) + ((1 + len(common.get("parts", []))) if common else 0)
    H = pad * 2 + rows * (rh + rg)
    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:640px" role="img">']
    y = pad
    for idx, b in enumerate(bars):
        num = _sint(b.get("num", 0))
        den = max(1, _sint(b.get("den", 1)))
        svg.append(_bar_row(pad, y, bw, rh, num, den, _c(th, idx), b.get("label", "")))
        y += rh + rg
    if common:
        den = max(1, _sint(common.get("den", 1)))
        col = "#15803d"
        svg.append(f'<text x="{pad}" y="{y+rh-14}" font-size="12" fill="#6b6256">（公分母 {den} 对齐）：</text>')
        y += rg
        for p in common.get("parts", []) or []:
            num = _sint(p.get("num", 0))
            svg.append(_bar_row(pad, y, bw, rh, num, den, col, p.get("label", "")))
            y += rh + rg
        res = common.get("result", "")
        if res:
            svg.append(f'<text x="{pad}" y="{y+rh-16}" font-size="16" font-weight="700" fill="{th.get("primary","#9a3412")}">结果：{_esc(res)}</text>')
    svg.append('</svg>')
    return "".join(svg)


def _fig_number_line(spec, th):
    mn = _sfloat(spec.get("min", 0))
    mx = _sfloat(spec.get("max", 1))
    span = (mx - mn) or 1
    W = 640
    H = 120
    x0 = 40
    x1 = W - 40
    y = 60

    def X(v):
        return x0 + (v - mn) / span * (x1 - x0)

    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:640px" role="img">']
    svg.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#6b6256" stroke-width="2"/>')
    for v, lab in [(mn, spec.get("min_label", "")), (mx, spec.get("max_label", ""))]:
        xx = X(v)
        svg.append(f'<line x1="{xx:.1f}" y1="{y-8}" x2="{xx:.1f}" y2="{y+8}" stroke="#6b6256" stroke-width="2"/>')
        if lab:
            svg.append(f'<text x="{xx:.1f}" y="{y+26}" font-size="13" text-anchor="middle" fill="#6b6256">{_esc(lab)}</text>')
    for m in spec.get("marks", []) or []:
        v = _sfloat(m.get("value", 0))
        xx = X(v)
        col = m.get("color", th.get("primary", "#9a3412"))
        svg.append(f'<line x1="{xx:.1f}" y1="{y-12}" x2="{xx:.1f}" y2="{y+12}" stroke="{col}" stroke-width="3"/>')
        if m.get("label"):
            svg.append(f'<text x="{xx:.1f}" y="{y-18}" font-size="13" font-weight="700" text-anchor="middle" fill="{col}">{_esc(m["label"])}</text>')
    svg.append('</svg>')
    return "".join(svg)


def _fig_bar_model(spec, th):
    total = _sint(spec.get("total", 0))
    parts = spec.get("parts", []) or []
    if not total or not parts:
        return ""
    W = 640
    H = 70
    pad = 12
    y = pad
    bw = W - pad * 2
    svg = [f'<svg viewBox="0 0 {W} {H+34}" width="100%" style="max-width:640px" role="img">']
    svg.append(f'<rect x="{pad}" y="{y}" width="{bw}" height="{H}" rx="8" fill="#f4f1ea" stroke="#e4ddcf"/>')
    cx = pad
    for i, p in enumerate(parts):
        v = _sint(p.get("value", 0))
        pw = bw * v / total
        col = _c(th, i)
        svg.append(f'<rect x="{cx:.1f}" y="{y}" width="{pw:.1f}" height="{H}" fill="{col}" opacity="0.85"/>')
        if p.get("label"):
            svg.append(f'<text x="{(cx+pw/2):.1f}" y="{y+H/2+5:.0f}" font-size="13" font-weight="700" text-anchor="middle" fill="#fff">{_esc(p["label"])}</text>')
        cx += pw
    svg.append('</svg>')
    return "".join(svg)


def _fig_place_value(spec, th):
    """数位顺序表：用于大数认识/计数单位/数位顺序等课题。
    places 为从高位到低位的数位名；digits 可选，把某个具体数字的每位映射到格子里。"""
    places = spec.get("places") or ["亿", "千万", "百万", "十万", "万", "千", "百", "十", "个"]
    digits = spec.get("digits") or {}
    primary = th.get("primary", "#9a3412")
    n = max(1, len(places))
    W = 640
    pad = 12
    gap = 4
    cell_w = (W - pad * 2 - gap * (n - 1)) / n
    cell_h = 54
    y0 = 22
    H = cell_h + 78
    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:640px" role="img">']
    for i, p in enumerate(places):
        x = pad + i * (cell_w + gap)
        # 每级（个/万/亿）四位的分隔可用颜色区分，但为通用简洁统一浅底
        svg.append(f'<rect x="{x:.1f}" y="{y0}" width="{cell_w:.1f}" height="{cell_h}" rx="6" fill="#f7f3ec" stroke="#d9cfbe" stroke-width="1.5"/>')
        d = digits.get(p, "")
        if d:
            svg.append(f'<text x="{x + cell_w/2:.1f}" y="{y0 + cell_h/2 + 6:.0f}" font-size="20" font-weight="800" text-anchor="middle" fill="{primary}">{_esc(str(d))}</text>')
        svg.append(f'<text x="{x + cell_w/2:.1f}" y="{y0 + cell_h + 20:.0f}" font-size="13" font-weight="700" text-anchor="middle" fill="#5f5a50">{_esc(p)}</text>')
    svg.append('</svg>')
    return "".join(svg)


def _fig_area_grid(spec, th):
    """方格图：用于面积/周长/长方形/正方形等课题，直观呈现"每行几个×几行=总数"。"""
    rows = max(1, _sint(spec.get("rows", 4)))
    cols = max(1, _sint(spec.get("cols", 6)))
    shade = spec.get("shade") or {}
    sr, sc = _sint(shade.get("r", 0)), _sint(shade.get("c", 0))
    sw = max(1, _sint(shade.get("w", min(cols, 3))))
    sh = max(1, _sint(shade.get("h", min(rows, 2))))
    primary = th.get("primary", "#9a3412")
    W = 640
    pad = 20
    cell = min(70, int((W - pad * 2) / cols))
    gw, gh = cell * cols, cell * rows
    H = gh + 84
    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:640px" role="img">']
    if spec.get("title"):
        svg.append(f'<text x="{pad}" y="{pad-4}" font-size="15" font-weight="700" fill="{primary}">{_esc(spec["title"])}</text>')
    y0 = pad + (16 if spec.get("title") else 0)
    # 格子
    for r in range(rows):
        for c in range(cols):
            x = pad + c * cell
            y = y0 + r * cell
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" fill="#ffffff" stroke="#d9cfbe" stroke-width="1.5"/>')
    # 涂色矩形（叠在格子之上，低透明着色，避免被白色格子盖住看不见）
    if sw > 0 and sh > 0:
        sx = pad + sc * cell
        sy = y0 + sr * cell
        svg.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{sw*cell:.1f}" height="{sh*cell:.1f}" fill="{primary}" opacity="0.20" stroke="{primary}" stroke-width="2"/>')
    svg.append(f'<rect x="{pad}" y="{y0}" width="{gw}" height="{gh}" fill="none" stroke="#6b6256" stroke-width="2"/>')
    # 标注
    ty = y0 + gh + 26
    if spec.get("total_label"):
        svg.append(f'<text x="{pad}" y="{ty}" font-size="14" font-weight="700" fill="#26303b">{_esc(spec["total_label"])}</text>')
    if spec.get("shade_label"):
        svg.append(f'<text x="{pad}" y="{ty+20}" font-size="13" fill="{primary}">{_esc(spec["shade_label"])}</text>')
    svg.append('</svg>')
    return "".join(svg)


DIAGRAM_RENDERERS = {
    "fraction_bars": _fig_fraction_bars,
    "number_line": _fig_number_line,
    "bar_model": _fig_bar_model,
    "area_grid": _fig_area_grid,
    "place_value": _fig_place_value,
}


def _render_figure(spec, th):
    if not isinstance(spec, dict):
        return ""
    fn = DIAGRAM_RENDERERS.get(spec.get("type"))
    if not fn:
        return ""
    try:
        svg = fn(spec, th)
    except Exception:
        return ""
    if not svg:
        return ""
    cap = spec.get("caption")
    cap_html = f'<div class="figcap">{_esc(cap)}</div>' if cap else ""
    return f'<div class="figure">{svg}{cap_html}</div>'


def render(slots, theme):
    figures = slots.get("figure", []) or []
    caption = slots.get("caption", "")
    side_text = slots.get("side_text", "")
    figs = "".join(_render_figure(f, theme) for f in figures)
    side_html = f'<div class="diag-side">{_esc(side_text)}</div>' if side_text else ""
    cap_html = f'<div class="diag-cap">{_esc(caption)}</div>' if caption else ""
    return (
        '<div class="ly ly-diagram">'
        f'<div class="diag-main">{figs}{cap_html}</div>'
        f'{side_html}'
        '</div>')


DEF = LayoutDef(
    layout_id="diagram", label="内联SVG示意图",
    slot_schema={
        "figure": {"type": "list[dict]", "req": True, "min_items": 1, "max_items": 4,
                   "keys": {
                       "type": {"type": "str", "max_chars": 24},
                       "caption": {"type": "str", "max_chars": 60},
                       # 嵌套渲染数据：raw 透传，保留 bars/common/marks/min/max 等结构
                       "bars": {"type": "raw"},
                       "common": {"type": "raw"},
                       "marks": {"type": "raw"},
                       "min": {"type": "raw"},
                       "max": {"type": "raw"},
                       "min_label": {"type": "raw"},
                       "max_label": {"type": "raw"},
                       "total": {"type": "raw"},
                       "parts": {"type": "raw"},
                       # area_grid 嵌套字段
                       "rows": {"type": "raw"},
                       "cols": {"type": "raw"},
                       "shade": {"type": "raw"},
                       "title": {"type": "raw"},
                       "total_label": {"type": "raw"},
                       "shade_label": {"type": "raw"},
                       "places": {"type": "raw"},
                       "digits": {"type": "raw"},
                       "note": {"type": "raw"},
                   }},
        "caption": {"type": "str", "max_chars": 80},
        "side_text": {"type": "str", "max_chars": 200},
    },
    applicable={"cats": ["math", "science"], "kinds": ["concept", "example"], "stages": "*"},
    css=(".ly-diagram{padding:5% 7%;display:flex;flex-direction:column;height:100%;justify-content:center}"
         ".ly-diagram .diag-main{display:flex;flex-direction:column;gap:14px;align-items:center}"
         ".ly-diagram .figure{width:100%;display:flex;flex-direction:column;align-items:center}"
         ".ly-diagram .figcap{font-size:14px;color:var(--muted);margin-top:4px;text-align:center}"
         ".ly-diagram .diag-cap{font-size:clamp(15px,2.3vw,19px);color:var(--ink);text-align:center;margin-top:8px}"
         ".ly-diagram .diag-side{font-size:clamp(14px,2.1vw,18px);color:var(--muted);text-align:center;margin-top:10px;line-height:1.6}"),
    _render=render,
)
