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


def _fig_parallelogram(spec, th):
    """平行四边形面积推导图：左侧平行四边形（标底 a、高 h），右侧割补成的长方形（标注 长=a 宽=h），中间箭头表示割补变换。

    spec 字段：
      base  底的数字（如 6）       height 高的数字（如 4）
      base_label  底标注（默认 "底"）   height_label 高标注（默认 "高"）
      cut_label   割补箭头文字（默认 "割补 → 变长方形"）
      result_label 结果标注（默认 "面积 = 底 × 高"）
    """
    primary = (th or {}).get("primary", "#9a3412")
    base = _sfloat(spec.get("base", 6))
    height = _sfloat(spec.get("height", 4))
    bl = _esc(spec.get("base_label", "底 a"))
    hl = _esc(spec.get("height_label", "高 h"))
    cl = _esc(spec.get("cut_label", "割补 → 变长方形"))
    rl = _esc(spec.get("result_label", "面积 = 底 × 高"))
    W, H = 640, 380
    pad = 30
    # 左图：平行四边形
    par_w, par_h = 240, 160
    par_x, par_y = pad + 20, pad + 20
    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:640px" role="img">']
    # 平行四边形（斜边倾斜）
    skew = 50  # 倾斜量
    pts = f"{par_x+skew},{par_y} {par_x+par_w+skew},{par_y} {par_x+par_w},{par_y+par_h} {par_x},{par_y+par_h}"
    svg.append(f'<polygon points="{pts}" fill="none" stroke="{primary}" stroke-width="3"/>')
    # 底边标注
    bx, by = par_x + par_w/2, par_y + par_h + 24
    svg.append(f'<text x="{bx:.0f}" y="{by}" font-size="16" font-weight="700" text-anchor="middle" fill="{primary}">{bl} = {base}</text>')
    # 高线（虚线，从顶点到底边垂线）
    hx = par_x + par_w + skew
    svg.append(f'<line x1="{hx}" y1="{par_y}" x2="{hx}" y2="{par_y+par_h}" stroke="#b45309" stroke-width="2" stroke-dasharray="6,4"/>')
    svg.append(f'<text x="{hx+8}" y="{par_y+par_h/2}" font-size="14" fill="#b45309" font-weight="700">{hl} = {height}</text>')
    # 割补箭头（右侧）
    arrow_x = par_x + par_w + skew + 40
    ay = par_y + par_h/2
    svg.append(f'<text x="{arrow_x}" y="{ay}" font-size="13" fill="#6b6256" text-anchor="middle" font-size="14">{cl}</text>')
    svg.append(f'<line x1="{arrow_x+8}" y1="{ay+8}" x2="{arrow_x+88}" y2="{ay+8}" stroke="#6b6256" stroke-width="2" marker-end="url(#arrowhead)"/>')
    # 右图：割补后的长方形
    rect_x = arrow_x + 100
    rect_w, rect_h = 160, 120
    rect_y = par_y + (par_h - rect_h)/2
    svg.append(f'<rect x="{rect_x}" y="{rect_y}" width="{rect_w}" height="{rect_h}" fill="none" stroke="#0f766e" stroke-width="3"/>')
    # 长方形标注
    svg.append(f'<text x="{rect_x+rect_w/2}" y="{rect_y+rect_h+24}" font-size="15" font-weight="700" text-anchor="middle" fill="#0f766e">长 = 底</text>')
    svg.append(f'<text x="{rect_x+rect_w+14}" y="{rect_y+rect_h/2}" font-size="15" fill="#0f766e" text-anchor="start" font-weight="700">宽 = 高</text>')
    # 结果公式
    svg.append(f'<text x="{W/2}" y="{H-20}" font-size="17" font-weight="800" text-anchor="middle" fill="{primary}">{rl}</text>')
    # 箭头标记定义
    svg.insert(1, '<defs><marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="#6b6256"/></defs>')
    svg.append('</svg>')
    return "".join(svg)


def _fig_circle(spec, th):
    """圆示意图：画圆，可标注圆心 O、半径 r、直径 d。

    spec 字段（均可选，缺省画一个带圆心+半径的圆）：
      show_center  是否标圆心（默认 True）
      show_radius  是否画半径并标 r（默认 True）
      show_diameter 是否画直径并标 d（默认 False，与半径二选一避免杂乱）
      radius_label 半径标注文字（默认 "r"）
      diameter_label 直径标注文字（默认 "d"）
      center_label 圆心标注文字（默认 "O"）
    """
    primary = (th or {}).get("primary", "#1d4ed8")
    show_center = spec.get("show_center", True)
    show_radius = spec.get("show_radius", True)
    show_diameter = spec.get("show_diameter", False)
    rl = _esc(spec.get("radius_label", "r"))
    dl = _esc(spec.get("diameter_label", "d"))
    cl = _esc(spec.get("center_label", "O"))

    W, H = 640, 420
    cx, cy, r = W // 2, H // 2, 150
    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:520px" role="img">']
    # 圆
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{primary}" stroke-width="3"/>')
    # 直径（穿过圆心的水平线）
    if show_diameter:
        svg.append(f'<line x1="{cx-r}" y1="{cy}" x2="{cx+r}" y2="{cy}" stroke="#0f766e" stroke-width="2.5"/>')
        svg.append(f'<text x="{cx}" y="{cy-12}" font-size="18" font-weight="700" fill="#0f766e" text-anchor="middle">{dl}</text>')
    # 半径（圆心到圆周右上）
    if show_radius:
        import math
        ex = cx + r * math.cos(math.radians(-35))
        ey = cy + r * math.sin(math.radians(-35))
        svg.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#b45309" stroke-width="2.5"/>')
        mx, my = (cx + ex) / 2, (cy + ey) / 2
        svg.append(f'<text x="{mx+8:.1f}" y="{my-6:.1f}" font-size="18" font-weight="700" fill="#b45309">{rl}</text>')
    # 圆心点 + 标注
    if show_center:
        svg.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="{primary}"/>')
        svg.append(f'<text x="{cx-22}" y="{cy+22}" font-size="18" font-weight="700" fill="{primary}">{cl}</text>')
    svg.append('</svg>')
    return "".join(svg)


DIAGRAM_RENDERERS = {
    "fraction_bars": _fig_fraction_bars,
    "number_line": _fig_number_line,
    "bar_model": _fig_bar_model,
    "area_grid": _fig_area_grid,
    "place_value": _fig_place_value,
    "parallelogram": _fig_parallelogram,
    "parallelogram_area": _fig_parallelogram,
    "平行四边形": _fig_parallelogram,
    # 圆/几何图形（含 agent 可能给的别名），解决《圆的认识》等课 diagram 空白
    "circle": _fig_circle,
    "circle_diagram": _fig_circle,
    "annulus": _fig_circle,
    "圆": _fig_circle,
}


# 各图渲染非空的关键参数（丢图告警用：缺了 svg 必为空）
_FIG_REQUIRED = {
    "fraction_bars": ["bars"],
    "bar_model": ["total", "parts"],
    "area_grid": ["rows", "cols", "shade"],
    "place_value": ["places"],
    "number_line": ["min", "max"],
    "parallelogram": ["base", "height"],
    "parallelogram_area": ["base", "height"],
    "平行四边形": ["base", "height"],
}


def _render_figure(spec, th):
    if not isinstance(spec, dict):
        return ""
    cap = spec.get("caption")
    cap_html = f'<div class="figcap">{_esc(cap)}</div>' if cap else ""
    ftype = spec.get("type")
    fn = DIAGRAM_RENDERERS.get(ftype)
    if not fn:
        # 未知图形 type：不再静默吞掉。打日志 + 出占位框（至少显示 caption），避免整页空白。
        print(f"  [diagram] 未注册的图形 type={ftype!r}，用占位框兜底", flush=True)
        ph = (f'<div style="padding:22px;border:2px dashed #cbd5e1;border-radius:10px;'
              f'color:#64748b;font-size:15px;text-align:center">示意图：{_esc(str(ftype or "未指定"))}</div>')
        return f'<div class="figure">{ph}{cap_html}</div>'
    try:
        svg = fn(spec, th)
    except Exception as e:
        print(f"  [diagram] 渲染 type={ftype!r} 异常：{e}，用占位框兜底", flush=True)
        ph = (f'<div style="padding:22px;border:2px dashed #cbd5e1;border-radius:10px;'
              f'color:#64748b;font-size:15px;text-align:center">示意图渲染失败</div>')
        return f'<div class="figure">{ph}{cap_html}</div>'
    if not svg:
        # 丢图告警：svg 为空说明关键参数缺失（fraction_bars 无 bars 等），不再静默只显示 caption。
        req = _FIG_REQUIRED.get(ftype, [])
        missing = [k for k in req if not spec.get(k)]
        print(f"  [diagram] 图形 type={ftype!r} 渲染为空"
              + (f"——缺关键参数 {missing}（agent 给了 type 但没填数据）" if missing else "——参数无效"),
              flush=True)
        return f'<div class="figure">{cap_html}</div>' if cap else ""
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
                       # parallelogram（平行四边形/三角形/梯形割补图）嵌套字段
                       "base": {"type": "raw"},
                       "height": {"type": "raw"},
                       "base_label": {"type": "raw"},
                       "height_label": {"type": "raw"},
                       "cut_label": {"type": "raw"},
                       "result_label": {"type": "raw"},
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
