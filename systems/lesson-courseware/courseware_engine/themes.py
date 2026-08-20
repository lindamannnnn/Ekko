# -*- coding: utf-8 -*-
"""多主题视觉系统（吸收外部 SKILL 视觉资产）。

借鉴来源（均为"受控 + 变量化"范式，非整库照搬）：
  - next-slide      ：每套主题是一个完整"设计系统"（版式DNA/字体/配色/装饰）
  - html-ppt-skill  ：主题由 CSS token 驱动，换一组变量即整体换皮
  - guizang-ppt     ：受控配色 + 美学保护（色值全部内置合法 hex，不让模型自由发挥）
  - awesome-gpt-image2 教育课件风格：清雅中国风 / 青绿教育 / 暖黄美术 / 纸纹童趣

设计要点：
  1. 每套主题是完整 token 集（bg/surface/ink/muted/line/primary/accent/good/bad/cover/字体/圆角/装饰）。
  2. 浅色 tint 在 Python 侧预算好（不依赖浏览器 color-mix，老旧投影也稳）。
  3. pick_theme() 按 学科×学段×课型 确定性选主题——视觉多样但不随机。
"""
import re

# 字体栈（系统字体，离线课堂可用；不依赖 CDN）
SERIF = '"Noto Serif SC","Songti SC","STSong","SimSun",serif'
KAI = '"Kaiti SC","KaiTi","STKaiti","SimKai",serif'
SANS = '"PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif'


# ---------------------------------------------------------------------------
# 颜色工具：把 base 色向 surface 混出浅色 tint（预算好，不依赖 color-mix）
# ---------------------------------------------------------------------------
def _h2r(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _r2h(rgb):
    return "#%02x%02x%02x" % rgb


def _mix(a, b, t):
    """a 向 b 混入比例 t（0=纯a, 1=纯b）。"""
    ra, ga, ba = _h2r(a)
    rb, gb, bb = _h2r(b)
    return _r2h((round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t)))


def _T(id, name, bg, surface, ink, muted, line, primary, primary700, accent,
       cover1, cover2, fontHead, fontBody=SANS, radius="16px", decor="none",
       good="#15803d", bad="#dc2626"):
    return {
        "id": id, "name": name, "bg": bg, "surface": surface, "ink": ink,
        "muted": muted, "line": line, "primary": primary, "primary700": primary700,
        "accent": accent, "good": good, "bad": bad, "cover1": cover1, "cover2": cover2,
        "fontHead": fontHead, "fontBody": fontBody, "radius": radius, "decor": decor,
    }


# ---------------------------------------------------------------------------
# 主题库（14 套；色值全部内置合法 hex）
# ---------------------------------------------------------------------------
THEMES = {t["id"]: t for t in [
    # —— 语文 ——
    _T("chinese_ink", "语文·水墨赭石", "#f5efe0", "#fffdf8", "#2c3e50", "#6b6256", "#e0d6c0",
       "#9a3412", "#7c2d12", "#0f766e", "#3f3a33", "#1c1917", SERIF, decor="seal"),
    _T("chinese_celadon", "语文·青绿山水", "#eef3ee", "#fcfefc", "#243b33", "#5c6f66", "#d3e0d6",
       "#0f766e", "#115e59", "#3f6212", "#134e4a", "#082a26", SERIF, decor="branch"),
    _T("chinese_vermilion", "语文·朱砂文言", "#f7f1e8", "#fffdf8", "#3a2a26", "#6f5a52", "#e6d8c8",
       "#b91c1c", "#7f1d1d", "#9a3412", "#442626", "#1f1313", KAI, decor="seal"),
    # —— 数学 ——
    _T("math_blue", "数学·理性蓝", "#f1f5f9", "#ffffff", "#1e293b", "#64748b", "#dbe3ec",
       "#1d4ed8", "#1e40af", "#0891b2", "#1e3a8a", "#0f1f4d", SANS, decor="dots"),
    _T("math_indigo", "数学·靛青", "#f2f3fa", "#ffffff", "#23233f", "#5b5b7a", "#dcdcf0",
       "#4338ca", "#3730a3", "#0d9488", "#312e81", "#171742", SANS, decor="dots"),
    _T("math_fresh", "数学·清新(低段)", "#f3f7f2", "#ffffff", "#23402e", "#5f7a68", "#d8e6db",
       "#15803d", "#166534", "#d97706", "#14532d", "#0b2f1a", SANS, decor="wave"),
    # —— 英语 ——
    _T("english_pop", "英语·明快橙", "#fff7ef", "#ffffff", "#3a2a1a", "#8a6a4a", "#f0ddc8",
       "#ea580c", "#c2410c", "#2563eb", "#7c2d12", "#431407", SANS, decor="wave"),
    _T("english_teal", "英语·青绿(低段)", "#effaf7", "#ffffff", "#173a33", "#557a70", "#cfe8e0",
       "#0d9488", "#0f766e", "#f59e0b", "#115e59", "#06302c", SANS, decor="dots"),
    # —— 低段通用 ——
    _T("kid_warm", "低段·暖色童趣", "#fff6ea", "#fffdf7", "#4a3423", "#9a7a5a", "#f2ddc2",
       "#e0651f", "#b4530a", "#2ea36b", "#b4530a", "#7a3a06", SANS, radius="22px", decor="wave"),
    # —— 美术 / 科学 / 史地 ——
    _T("art_warm", "美术·暖黄", "#fbf3e2", "#fffdf6", "#3f3120", "#8a7350", "#ecd9b8",
       "#c8841a", "#9a6a10", "#7c5cd6", "#8a5a12", "#4a3208", SERIF, decor="branch"),
    _T("science_green", "科学·青绿", "#eff6f2", "#ffffff", "#1f3a2e", "#557a66", "#d6e6dc",
       "#15803d", "#166534", "#0369a1", "#14532d", "#0a2a18", SANS, decor="dots"),
    _T("history_sepia", "历史·赭纸", "#f5efe4", "#fffdf6", "#3a3026", "#6f6250", "#e2d7c2",
       "#92400e", "#78350f", "#57534e", "#44403c", "#221f1c", SERIF, decor="seal"),
    _T("geo_teal", "地理·青黛", "#eef4f6", "#ffffff", "#1f3338", "#55707a", "#d3e2e6",
       "#0e7490", "#155e75", "#65a30d", "#155e75", "#083344", SANS, decor="wave"),
    # —— 通用兜底 ——
    _T("general_neutral", "通用·米白", "#f4f1ea", "#fffdf8", "#26303b", "#6b6256", "#e4ddcf",
       "#b45309", "#92400e", "#0f766e", "#1f2937", "#0f172a", SERIF, decor="none"),
]}


def get_theme(tid):
    return THEMES.get(tid) or THEMES["general_neutral"]


# ---------------------------------------------------------------------------
# 学段 / 课型判定（确定性）
# ---------------------------------------------------------------------------
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def stage_of(grade):
    g = str(grade or "")
    if ("初" in g) or ("高" in g):  # 初中/高中一律按高学段（避免"初一"误判为低段）
        return "high"
    n = 0
    m = re.search(r"(\d+)", g)
    if m:
        n = int(m.group(1))
    else:
        for k, v in _CN_NUM.items():
            if k in g:
                n = v
                break
    if 0 < n <= 2:
        return "low"
    if 0 < n <= 4:
        return "mid"
    return "high"  # 5-6 及初中


def _looks_like_poem(text):
    """KB 原文若每行 2~14 字且共 2~12 行，判为诗/词（不看标题）。

    用于标题无「诗/词」字（如《山行》《静夜思》《江雪》）的古诗识别，
    与 enrich.inject_poem 的 KB 启发式同一判据，保证路由与注入一致。
    """
    if not text:
        return False
    raw = [l.strip() for l in str(text).split("\n") if l.strip()]
    if not (2 <= len(raw) <= 12):
        return False
    for l in raw:
        if not (2 <= len(l) <= 14):
            return False
    return True


def chinese_lesson_type(topic, original_text=None):
    t = str(topic or "")
    if re.search(r"识字|拼音|写字", t):
        return "识字"
    if re.search(r"诗|词|吟|赋|咏|古诗|绝句|律诗", t):
        return "古诗"
    if re.search(r"表$|说$|记$|传$|志$|序$|论$|文言", t):
        return "文言文"
    # 标题无诗/词 字时，看 KB 原文结构（每行 2~14 字、2~12 行 → 诗/词）
    if _looks_like_poem(original_text):
        return "古诗"
    return "现代文"


_MATH_STAGE = {"low": "math_fresh", "mid": "math_blue", "high": "math_indigo"}


def pick_theme(cat="general", stage="mid", lesson_type="", topic=""):
    """学科×学段×课型 → 主题 id（确定性，不随机）。"""
    if cat == "chinese":
        if lesson_type == "识字" or stage == "low":
            return "kid_warm"
        if lesson_type == "文言文":
            return "chinese_vermilion"
        if lesson_type == "古诗":
            return "chinese_celadon" if re.search(r"山|水|田园|江雪|村居|渔", str(topic)) else "chinese_ink"
        return "chinese_celadon"
    if cat == "math":
        return _MATH_STAGE.get(stage, "math_blue")
    if cat == "english":
        return "english_teal" if stage == "low" else "english_pop"
    if cat == "art":
        return "art_warm"
    if cat == "science":
        return "science_green"
    if cat == "history":
        return "history_sepia"
    if cat == "geography":
        return "geo_teal"
    if cat == "pe":
        return "kid_warm"
    return "general_neutral"


# ---------------------------------------------------------------------------
# 主题 → CSS 变量（含预算好的浅色 tint）
# ---------------------------------------------------------------------------
def theme_css_vars(th):
    sp = _mix(th["primary"], th["surface"], 0.92)
    sa = _mix(th["accent"], th["surface"], 0.90)
    sg = _mix(th["good"], th["surface"], 0.90)
    sb = _mix(th["bad"], th["surface"], 0.90)
    return (
        ":root{"
        f"--bg:{th['bg']};--surface:{th['surface']};--ink:{th['ink']};--muted:{th['muted']};--line:{th['line']};"
        f"--primary:{th['primary']};--primary700:{th['primary700']};--accent:{th['accent']};"
        f"--good:{th['good']};--bad:{th['bad']};"
        f"--primary-soft:{sp};--accent-soft:{sa};--good-soft:{sg};--bad-soft:{sb};"
        f"--cover1:{th['cover1']};--cover2:{th['cover2']};"
        f"--font-head:{th['fontHead']};--font-body:{th['fontBody']};--radius:{th['radius']};"
        "}"
    )


# ---------------------------------------------------------------------------
# 封面装饰（确定性内联 SVG，禁止模型自由画）
# ---------------------------------------------------------------------------
def decoration_svg(kind, th):
    p = th["primary"]
    a = th["accent"]
    if kind == "seal":
        return (
            f'<svg class="decor decor-seal" viewBox="0 0 120 120" width="120" height="120" aria-hidden="true">'
            f'<rect x="8" y="8" width="104" height="104" rx="14" fill="{p}" opacity="0.9"/>'
            f'<rect x="20" y="20" width="80" height="80" rx="8" fill="none" stroke="#fff" stroke-width="3" opacity="0.85"/>'
            f'<path d="M40 60 h40 M60 40 v40" stroke="#fff" stroke-width="6" opacity="0.85"/>'
            f"</svg>"
        )
    if kind == "branch":
        leaves = "".join(
            f'<ellipse cx="{40+i*16}" cy="{30+i*14}" rx="12" ry="6" fill="{a}" opacity="0.55" transform="rotate({-30+i*8} {40+i*16} {30+i*14})"/>'
            for i in range(5)
        )
        return (
            f'<svg class="decor decor-branch" viewBox="0 0 140 140" width="140" height="140" aria-hidden="true">'
            f'<path d="M20 130 Q60 80 118 22" stroke="{p}" stroke-width="3" fill="none" opacity="0.6"/>{leaves}</svg>'
        )
    if kind == "dots":
        dots = "".join(
            f'<circle cx="{20+c*26}" cy="{20+r*26}" r="5" fill="{p}" opacity="{0.25+0.12*((r+c)%3)}"/>'
            for r in range(4) for c in range(4)
        )
        return f'<svg class="decor decor-dots" viewBox="0 0 120 120" width="120" height="120" aria-hidden="true">{dots}</svg>'
    if kind == "wave":
        return (
            f'<svg class="decor decor-wave" viewBox="0 0 160 90" width="160" height="90" aria-hidden="true">'
            f'<path d="M0 30 Q40 10 80 30 T160 30" stroke="{a}" stroke-width="5" fill="none" opacity="0.5"/>'
            f'<path d="M0 55 Q40 35 80 55 T160 55" stroke="{p}" stroke-width="5" fill="none" opacity="0.45"/>'
            f'<path d="M0 78 Q40 60 80 78 T160 78" stroke="{a}" stroke-width="4" fill="none" opacity="0.3"/>'
            f"</svg>"
        )
    return ""
