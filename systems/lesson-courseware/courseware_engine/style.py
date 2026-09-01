# -*- coding: utf-8 -*-
"""courseware_engine/style.py —— StyleRecipe → CSS 变量 + 种子化兜底。

PALETTE_SEED：≥12 套完整 10 色 palette（色值全部硬编码合法 hex），按 palette_hint 或
  f"{cat}:{stage}" 二级索引；seeded_recipe 在 LLM 风格生成失败时零依赖产出完整合法配方。
recipe_to_css_vars：输出 :root 变量（palette + 字体 + 圆角）。
recipe_to_scoped_css：输出 recipe 驱动的版式级覆盖（字体/基础排版），骨架 CSS 稳定不变。
"""
from .schemas import StyleRecipe, PALETTE_KEYS

# 字体栈白名单（与 schemas.FONT_WHITELIST 一致，避免循环 import 用本地副本）
FONT_STACKS = {
    "serif": '"Noto Serif SC","Songti SC","SimSun",serif',
    "sans": '"PingFang SC","Microsoft YaHei","Heiti SC",sans-serif',
    "kaiti": '"Kaiti SC","KaiTi","STKaiti",serif',
    "rounded": '"Yuanti SC","Hiragino Sans GB","PingFang SC",sans-serif',
}

# 学段 → 字体 / 密度 / 圆角
STAGE_SEED = {
    "low":    {"head": "rounded", "body": "rounded", "density": "sparse", "radius": 18},
    "mid":    {"head": "serif",   "body": "sans",    "density": "balanced", "radius": 12},
    "high":   {"head": "sans",    "body": "sans",    "density": "dense", "radius": 8},
    "junior": {"head": "sans",    "body": "sans",    "density": "dense", "radius": 8},
}

# 12 套硬编码合法 palette（primary,primary700,accent,bg,surface,ink,muted,line,cover1,cover2）
PALETTE_SEED = {
    "warm_ink":  {"primary": "#9a3412", "primary700": "#7c2d12", "accent": "#0f766e", "bg": "#f7f3ec", "surface": "#fffdf8", "ink": "#292524", "muted": "#78716c", "line": "#e7ddcb", "cover1": "#44403c", "cover2": "#1c1917"},
    "bamboo_green": {"primary": "#15803d", "primary700": "#166534", "accent": "#0f766e", "bg": "#f3f7f1", "surface": "#fcfffb", "ink": "#1f2937", "muted": "#6b7280", "line": "#d9e6d6", "cover1": "#1f3d2b", "cover2": "#0f2419"},
    "cinnabar":  {"primary": "#c2410c", "primary700": "#9a3412", "accent": "#0e7490", "bg": "#fbf4ef", "surface": "#fffaf6", "ink": "#292524", "muted": "#8a7f78", "line": "#f0ddd2", "cover1": "#7f1d1d", "cover2": "#450a0a"},
    "indigo":    {"primary": "#3730a3", "primary700": "#312e81", "accent": "#0f766e", "bg": "#f4f5fb", "surface": "#fdfdff", "ink": "#1e1b4b", "muted": "#6b7280", "line": "#dde0f0", "cover1": "#1e1b4b", "cover2": "#0c0a2e"},
    "paper":     {"primary": "#78716c", "primary700": "#57534e", "accent": "#0f766e", "bg": "#fafaf7", "surface": "#ffffff", "ink": "#292524", "muted": "#a8a29e", "line": "#ececec", "cover1": "#44403c", "cover2": "#1c1917"},
    "ink_black": {"primary": "#1f2937", "primary700": "#111827", "accent": "#0f766e", "bg": "#f7f7f5", "surface": "#ffffff", "ink": "#111827", "muted": "#6b7280", "line": "#e5e7eb", "cover1": "#111827", "cover2": "#000000"},
    "sky_blue":  {"primary": "#0369a1", "primary700": "#075985", "accent": "#0f766e", "bg": "#eef6fb", "surface": "#fcfeff", "ink": "#0c4a6e", "muted": "#64748b", "line": "#d4e6f1", "cover1": "#0c4a6e", "cover2": "#062c47"},
    "amber":     {"primary": "#d97706", "primary700": "#b45309", "accent": "#0f766e", "bg": "#fef7ec", "surface": "#fffdf8", "ink": "#292524", "muted": "#a16207", "line": "#f5e3c0", "cover1": "#92400e", "cover2": "#5c2e0a"},
    "plum":      {"primary": "#9d174d", "primary700": "#831843", "accent": "#0f766e", "bg": "#faf1f5", "surface": "#fffafc", "ink": "#500724", "muted": "#9f6b7d", "line": "#f2d9e4", "cover1": "#500724", "cover2": "#2e0413"},
    "mint":      {"primary": "#0f766e", "primary700": "#115e59", "accent": "#d97706", "bg": "#eef7f5", "surface": "#fcfffe", "ink": "#134e4a", "muted": "#6b8e89", "line": "#d3e8e4", "cover1": "#134e4a", "cover2": "#0a2e2b"},
    "rose":      {"primary": "#be123c", "primary700": "#9f1239", "accent": "#0369a1", "bg": "#fdf0f3", "surface": "#fffafb", "ink": "#4c0519", "muted": "#b48a93", "line": "#f5d4dc", "cover1": "#4c0519", "cover2": "#2a0410"},
    "slate":     {"primary": "#334155", "primary700": "#1e293b", "accent": "#0f766e", "bg": "#f4f6f8", "surface": "#ffffff", "ink": "#1e293b", "muted": "#64748b", "line": "#e2e8f0", "cover1": "#1e293b", "cover2": "#0f172a"},
}

# lesson_type → 装饰白名单
_DECOR_MAP = {
    "古诗": ["seal", "branch"],
    "文言文": ["seal"],
    "现代文": ["branch"],
    "识字": ["wave"],
    "grammar": ["dot_grid"],
    "reading": ["dot_grid"],
    "standard": ["none"],
    "数学": ["dot_grid"],
    "英语": ["none"],
}


def _decor_for(dna):
    lt = dna.get("lesson_type", "standard") if isinstance(dna, dict) else getattr(dna, "lesson_type", "standard")
    return _DECOR_MAP.get(lt, ["none"])


def seeded_recipe(dna, pack=None):
    """确定性兜底配方（零 LLM 依赖）。"""
    cat = dna.subject_cat if hasattr(dna, "subject_cat") else dna.get("subject_cat", "general")
    stage = dna.stage if hasattr(dna, "stage") else dna.get("stage", "mid")
    hint = dna.palette_hint if hasattr(dna, "palette_hint") else dna.get("palette_hint", "warm_ink")
    palette = (PALETTE_SEED.get(hint)
               or PALETTE_SEED.get(f"{cat}:{stage}")
               or PALETTE_SEED["warm_ink"]).copy()
    st = STAGE_SEED.get(stage, STAGE_SEED["mid"])
    fonts = {
        "head": FONT_STACKS.get(st["head"], FONT_STACKS["serif"]),
        "body": FONT_STACKS.get(st["body"], FONT_STACKS["sans"]),
    }
    decorations = _decor_for(dna)
    illustration = {
        "style": "line_art",
        "diagram_kinds": ["fraction_bars", "number_line", "bar_model"] if cat in ("math", "science") else [],
    }
    # 学科包可覆盖 style_seed（preferred/avoid/per_kind）
    layout_prefs = {"preferred": [], "avoid": [], "per_kind": {}}
    if pack is not None:
        seed = getattr(pack, "style_seed", None) or {}
        if isinstance(seed, dict):
            layout_prefs["preferred"] = list(seed.get("preferred", []))
            layout_prefs["avoid"] = list(seed.get("avoid", []))
            layout_prefs["per_kind"] = {k: list(v) for k, v in (seed.get("per_kind", {}) or {}).items()}
    recipe = StyleRecipe(
        palette=palette, fonts=fonts, layout_prefs=layout_prefs,
        illustration=illustration, decorations=decorations,
    )
    return recipe.validate()


# 密度 → padding 缩放系数（用于 layout 的 padding/margin）
DENSITY_SCALE = {"compact": 0.75, "balanced": 1.0, "spacious": 1.3}


def recipe_to_css_vars(recipe):
    p = recipe.palette
    cs = getattr(recipe, "card_style", None) or {}
    ts = getattr(recipe, "title_style", None) or {}
    density = getattr(recipe, "density", "balanced")
    dscale = DENSITY_SCALE.get(density, 1.0)
    radius = cs.get("radius", 12)
    bw = cs.get("border_width", 2)
    bs = cs.get("border_style", "solid")
    shadow = cs.get("shadow", "none")
    pad_scale = round(cs.get("padding_scale", 1.0) * dscale, 3)
    title_scale = ts.get("size_scale", 1.0)
    title_deco = ts.get("decoration", "none")
    ls = ts.get("letter_spacing", 0)
    return (
        "<style>:root{"
        f"--primary:{p['primary']};--primary700:{p['primary700']};--accent:{p['accent']};"
        f"--bg:{p['bg']};--surface:{p['surface']};--ink:{p['ink']};"
        f"--muted:{p['muted']};--line:{p['line']};--cover1:{p['cover1']};--cover2:{p['cover2']};"
        f"--font-head:{recipe.fonts.get('head', FONT_STACKS['serif'])};"
        f"--font-body:{recipe.fonts.get('body', FONT_STACKS['sans'])};"
        # 整套视觉变量（带默认值，旧配方不填时渲染不变）
        f"--radius:{radius}px;"
        f"--card-border:{bw}px {bs} var(--line);"
        f"--card-shadow:{shadow};"
        f"--pad-scale:{pad_scale};"
        f"--title-scale:{title_scale};"
        f"--title-ls:{ls}px;"
        f"--title-deco:{title_deco};"
        "}</style>"
    )


def recipe_to_scoped_css(recipe):
    """recipe 驱动的版式级覆盖：字体 + 整套视觉（背景层/卡片/标题装饰/每页装饰）。"""
    bg = getattr(recipe, "background", None) or {}
    bg_css = bg.get("css", "")
    page_decor = getattr(recipe, "page_decor", None) or []

    css = [
        ".deck,.ly{font-family:var(--font-body);color:var(--ink);}",
        ".deck h1,.deck h2,.deck h3,.ly-h{font-family:var(--font-head);"
        "letter-spacing:var(--title-ls);}",
        # 卡片统一吃变量（各 layout 写死的 border/radius 由变量覆盖）
        ".tier-layer,.concept-callout,.step-card,.obj-card,.sum-card,.hw-card{"
        "border-radius:var(--radius)!important;box-shadow:var(--card-shadow);}",
        # 标题装饰
        ".ly-h{font-size:calc(1em * var(--title-scale));}",
    ]
    # 标题装饰样式
    deco_css = {
        "underline": ".ly-h{border-bottom:3px solid var(--primary);padding-bottom:6px;display:inline-block;}",
        "side_bar": ".ly-h{border-left:6px solid var(--primary);padding-left:14px;}",
        "highlight": ".ly-h{background:linear-gradient(transparent 60%,var(--accent) 60%);padding:0 4px;}",
        "outline": ".ly-h{-webkit-text-stroke:1px var(--primary);color:transparent;}",
    }
    ts = getattr(recipe, "title_style", None) or {}
    if ts.get("decoration") in deco_css:
        css.append(deco_css[ts["decoration"]])
    # deck 背景层（纹理/渐变/点阵）
    if bg_css:
        css.append(f"#deck::before{{content:'';position:absolute;inset:0;z-index:0;pointer-events:none;{bg_css}}}")
        css.append("#deck .slide{z-index:1;}")
    # 每页装饰元素
    for d in page_decor:
        css.append(_page_decor_css(d))
    return "<style>" + "".join(x for x in css if x) + "</style>"


def _page_decor_css(name):
    """每页装饰元素的 CSS（右上角印章/侧边色带/网格线等，pointer-events:none 不挡内容）。"""
    table = {
        "seal": ".slide::after{content:'课';position:absolute;top:20px;right:22px;width:44px;height:44px;"
                "line-height:44px;text-align:center;border:2.5px solid var(--primary);border-radius:6px;"
                "color:var(--primary);font-size:22px;font-weight:800;font-family:var(--font-head);"
                "opacity:.35;pointer-events:none;z-index:5;}",
        "corner_line": ".slide::before{content:'';position:absolute;top:0;left:0;width:60px;height:60px;"
                       "border-top:4px solid var(--primary);border-left:4px solid var(--primary);"
                       "opacity:.5;pointer-events:none;z-index:5;}",
        "side_band": ".slide::before{content:'';position:absolute;top:0;left:0;bottom:0;width:8px;"
                     "background:var(--primary);opacity:.85;pointer-events:none;z-index:5;}",
        "grid_lines": ".slide::before{content:'';position:absolute;inset:0;"
                      "background:repeating-linear-gradient(0deg,transparent,transparent 39px,var(--line) 39px,var(--line) 40px),"
                      "repeating-linear-gradient(90deg,transparent,transparent 39px,var(--line) 39px,var(--line) 40px);"
                      "opacity:.35;pointer-events:none;z-index:0;}",
        "pixel_block": ".slide::after{content:'';position:absolute;bottom:18px;right:18px;width:48px;height:48px;"
                       "background:conic-gradient(var(--primary) 25%,var(--accent) 0 50%,var(--primary) 0 75%,var(--accent) 0);"
                       "background-size:24px 24px;image-rendering:pixelated;opacity:.6;pointer-events:none;z-index:5;}",
        "glow": ".slide::before{content:'';position:absolute;top:-40%;right:-20%;width:70%;height:80%;"
                "background:radial-gradient(circle,var(--accent) 0%,transparent 60%);"
                "opacity:.18;pointer-events:none;z-index:0;}",
        "thick_rule": ".slide::before{content:'';position:absolute;top:0;left:0;right:0;height:10px;"
                      "background:var(--ink);pointer-events:none;z-index:5;}",
        "gold_line": ".slide::after{content:'';position:absolute;bottom:14px;left:10%;right:10%;height:2px;"
                     "background:linear-gradient(90deg,transparent,var(--accent),transparent);"
                     "pointer-events:none;z-index:5;}",
        "wave": ".slide::after{content:'';position:absolute;bottom:0;left:0;right:0;height:6px;"
                "background:repeating-linear-gradient(90deg,var(--accent) 0 12px,transparent 12px 24px);"
                "opacity:.5;pointer-events:none;z-index:5;}",
    }
    return table.get(name, "")
