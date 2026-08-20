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


def recipe_to_css_vars(recipe):
    p = recipe.palette
    return (
        "<style>:root{"
        f"--primary:{p['primary']};--primary700:{p['primary700']};--accent:{p['accent']};"
        f"--bg:{p['bg']};--surface:{p['surface']};--ink:{p['ink']};"
        f"--muted:{p['muted']};--line:{p['line']};--cover1:{p['cover1']};--cover2:{p['cover2']};"
        f"--font-head:{recipe.fonts.get('head', FONT_STACKS['serif'])};"
        f"--font-body:{recipe.fonts.get('body', FONT_STACKS['sans'])};--radius:14px;"
        "}</style>"
    )


def recipe_to_scoped_css(recipe):
    """recipe 驱动的版式级覆盖（字体/基础排版）；具体版式差异由各 LayoutDef.css 提供。"""
    return (
        "<style>"
        ".deck,.ly{font-family:var(--font-body);color:var(--ink);}"
        ".deck h1,.deck h2,.deck h3,.ly-h{font-family:var(--font-head);}"
        "</style>"
    )
