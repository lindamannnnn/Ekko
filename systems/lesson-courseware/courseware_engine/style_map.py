# -*- coding: utf-8 -*-
"""style_map.py —— 网页 11 种风格 id → 学科课件 StyleRecipe 整套视觉映射。

用途：课前备课「学科生成」选了风格后，orchestrator 用本模块把风格 id 映射成
courseware_engine 的 StyleRecipe（整套视觉），套到 build_deck——版式结构不变
（diagram/board/tiers 等槽位布局照常），但整套视觉跟随风格：
  palette 10 色 + fonts + card_style（圆角/边框/阴影/留白）+ background（纹理/渐变/点阵）
  + density（密度）+ title_style（字号/装饰/字距）+ page_decor（每页装饰元素）。

配色来源：content-upload/styles/<id>.css 的 CSS 变量（--bg/--fg/--accent/--muted 等），
补足 StyleRecipe 需要的 primary700/cover1/cover2（深一档主色 / 封面双色）。
字体：按风格气质映射到 schemas.FONT_WHITELIST 的 serif/sans/kaiti/rounded。

所有新字段均可缺省——缺省时走 StyleRecipe.validate() 的默认值，
渲染结果与旧版（只换配色字体）完全一致（向后兼容）。
"""
from courseware_engine.schemas import StyleRecipe, FONT_WHITELIST

_SERIF = FONT_WHITELIST["serif"]
_SANS = FONT_WHITELIST["sans"]
_KAITI = FONT_WHITELIST["kaiti"]
_ROUNDED = FONT_WHITELIST["rounded"]

# 每风格：palette 10 色 + fonts(head/body) + 整套视觉 5 字段
# palette 键 = PALETTE_KEYS = [primary, primary700, accent, bg, surface, ink, muted, line, cover1, cover2]
_STYLE_TABLE = {
    "graffiti": {  # 涂鸦像素游戏风：深空 + 金/橙霓虹 + 锐利色块 + 像素装饰
        "palette": {"primary": "#0f3460", "primary700": "#16213e", "accent": "#ffd700",
                    "bg": "#1a1a2e", "surface": "#ffffff", "ink": "#1a1a2e", "muted": "#4a4a6a",
                    "line": "#ffd700", "cover1": "#ffd700", "cover2": "#ffa502"},
        "fonts": {"head": _ROUNDED, "body": _SANS},
        "card_style": {"radius": 0, "border_width": 3, "border_style": "solid",
                       "shadow": "6px 6px 0 rgba(255,215,0,.25)", "padding_scale": 0.95},
        "background": {"type": "pattern",
                       "css": "background-image:radial-gradient(rgba(255,215,0,.08) 2px,transparent 2px);"
                              "background-size:32px 32px;"},
        "density": "compact",
        "title_style": {"size_scale": 1.1, "decoration": "highlight", "letter_spacing": 2},
        "page_decor": ["pixel_block"],
    },
    "magazine": {  # 电子杂志·电子墨水：暖纸 + 赭石 + 衬线 + 横线纹理 + 角线
        "palette": {"primary": "#b5532a", "primary700": "#8f4122", "accent": "#b5532a",
                    "bg": "#f4ecd8", "surface": "#faf5e9", "ink": "#2b2723", "muted": "#7a6f5d",
                    "line": "#d8cbb0", "cover1": "#b5532a", "cover2": "#7a6f5d"},
        "fonts": {"head": _SERIF, "body": _SERIF},
        "card_style": {"radius": 2, "border_width": 1, "border_style": "solid",
                       "shadow": "none", "padding_scale": 1.1},
        "background": {"type": "texture",
                       "css": "background:repeating-linear-gradient(0deg,transparent,transparent 28px,rgba(181,83,42,.04) 28px,rgba(181,83,42,.04) 29px);"},
        "density": "balanced",
        "title_style": {"size_scale": 1.05, "decoration": "underline", "letter_spacing": 1},
        "page_decor": ["corner_line"],
    },
    "swiss": {  # 瑞士国际主义：白底 + IKB 蓝 + 网格 + 大留白 + 无卡片边框
        "palette": {"primary": "#0061ff", "primary700": "#0049c4", "accent": "#0061ff",
                    "bg": "#ffffff", "surface": "#f5f5f5", "ink": "#111111", "muted": "#8a8a8a",
                    "line": "#e0e0e0", "cover1": "#0061ff", "cover2": "#111111"},
        "fonts": {"head": _SANS, "body": _SANS},
        "card_style": {"radius": 0, "border_width": 0, "border_style": "none",
                       "shadow": "none", "padding_scale": 1.2},
        "background": {"type": "solid", "css": ""},
        "density": "spacious",
        "title_style": {"size_scale": 1.2, "decoration": "side_bar", "letter_spacing": 0},
        "page_decor": ["grid_lines"],
    },
    "ink": {  # 水墨中国风：宣纸 + 墨色 + 印章红 + 大留白 + 楷体 + 印章装饰
        "palette": {"primary": "#9e2b25", "primary700": "#7a1f1b", "accent": "#9e2b25",
                    "bg": "#f5f0e6", "surface": "#fbf8f1", "ink": "#1c1c1c", "muted": "#6b6256",
                    "line": "#ddd3c0", "cover1": "#1c1c1c", "cover2": "#9e2b25"},
        "fonts": {"head": _KAITI, "body": _SERIF},
        "card_style": {"radius": 4, "border_width": 1, "border_style": "solid",
                       "shadow": "none", "padding_scale": 1.15},
        "background": {"type": "texture",
                       "css": "background:radial-gradient(circle at 20% 30%,rgba(28,28,28,.03) 0%,transparent 40%),"
                              "radial-gradient(circle at 80% 70%,rgba(158,43,37,.04) 0%,transparent 45%),"
                              "radial-gradient(circle at 50% 90%,rgba(28,28,28,.025) 0%,transparent 35%);"},
        "density": "spacious",
        "title_style": {"size_scale": 1.15, "decoration": "none", "letter_spacing": 6},
        "page_decor": ["seal"],
    },
    "devblue": {  # 开发者极简蓝：单一蓝 + 琥珀 + 代码感侧边带
        "palette": {"primary": "#2563eb", "primary700": "#1d4ed8", "accent": "#f59e0b",
                    "bg": "#ffffff", "surface": "#f8fafc", "ink": "#1e293b", "muted": "#64748b",
                    "line": "#e2e8f0", "cover1": "#2563eb", "cover2": "#1e293b"},
        "fonts": {"head": _SANS, "body": _SANS},
        "card_style": {"radius": 8, "border_width": 1, "border_style": "solid",
                       "shadow": "0 1px 3px rgba(30,41,59,.08)", "padding_scale": 1.0},
        "background": {"type": "solid", "css": ""},
        "density": "balanced",
        "title_style": {"size_scale": 1.0, "decoration": "side_bar", "letter_spacing": 0},
        "page_decor": ["side_band"],
    },
    "apple": {  # 苹果极简：系统灰 + 蓝 + 大圆角 + 柔阴影 + 超大留白 + 零装饰
        "palette": {"primary": "#0071e3", "primary700": "#005bb5", "accent": "#0071e3",
                    "bg": "#fbfbfd", "surface": "#ffffff", "ink": "#1d1d1f", "muted": "#86868b",
                    "line": "#e5e5e7", "cover1": "#0071e3", "cover2": "#1d1d1f"},
        "fonts": {"head": _SANS, "body": _SANS},
        "card_style": {"radius": 18, "border_width": 0, "border_style": "none",
                       "shadow": "0 4px 24px rgba(0,0,0,.08)", "padding_scale": 1.25},
        "background": {"type": "solid", "css": ""},
        "density": "spacious",
        "title_style": {"size_scale": 1.1, "decoration": "none", "letter_spacing": 0},
        "page_decor": [],
    },
    "brutalist": {  # 复古工业：粗黑边框 + 高对比橙红 + 硬投影 + 紧凑 + 顶部粗黑条
        "palette": {"primary": "#ff3b00", "primary700": "#cc2f00", "accent": "#ff3b00",
                    "bg": "#ece8dc", "surface": "#ffffff", "ink": "#0a0a0a", "muted": "#444444",
                    "line": "#0a0a0a", "cover1": "#ff3b00", "cover2": "#0a0a0a"},
        "fonts": {"head": _SANS, "body": _SANS},
        "card_style": {"radius": 0, "border_width": 3, "border_style": "solid",
                       "shadow": "8px 8px 0 #0a0a0a", "padding_scale": 0.9},
        "background": {"type": "solid", "css": ""},
        "density": "compact",
        "title_style": {"size_scale": 1.15, "decoration": "highlight", "letter_spacing": 1},
        "page_decor": ["thick_rule"],
    },
    "glass": {  # 暗色玻璃拟态：暗色渐变 + 天青/紫 + 发光 + 大圆角
        "palette": {"primary": "#38bdf8", "primary700": "#0ea5e9", "accent": "#a78bfa",
                    "bg": "#0f172a", "surface": "#1e293b", "ink": "#f1f5f9", "muted": "#94a3b8",
                    "line": "#475569", "cover1": "#38bdf8", "cover2": "#a78bfa"},
        "fonts": {"head": _SANS, "body": _SANS},
        "card_style": {"radius": 20, "border_width": 1, "border_style": "solid",
                       "shadow": "0 8px 32px rgba(56,189,248,.15)", "padding_scale": 1.1},
        "background": {"type": "gradient",
                       "css": "background:linear-gradient(160deg,#0f172a 0%,#1e1b4b 55%,#312e81 100%);"},
        "density": "balanced",
        "title_style": {"size_scale": 1.05, "decoration": "none", "letter_spacing": 1},
        "page_decor": ["glow"],
    },
    "dracula": {  # 霓虹暗夜：dracula 配色 + 紫色光晕 + 暗夜渐变
        "palette": {"primary": "#bd93f9", "primary700": "#9d6fe8", "accent": "#8be9fd",
                    "bg": "#282a36", "surface": "#44475a", "ink": "#f8f8f2", "muted": "#7a8bb5",
                    "line": "#565a6e", "cover1": "#bd93f9", "cover2": "#8be9fd"},
        "fonts": {"head": _SANS, "body": _SANS},
        "card_style": {"radius": 10, "border_width": 1, "border_style": "solid",
                       "shadow": "0 4px 20px rgba(189,147,249,.2)", "padding_scale": 1.0},
        "background": {"type": "gradient",
                       "css": "background:linear-gradient(180deg,#282a36 0%,#1e1f29 100%);"},
        "density": "balanced",
        "title_style": {"size_scale": 1.05, "decoration": "underline", "letter_spacing": 1},
        "page_decor": ["glow"],
    },
    "serif": {  # 极简衬线：经典衬线 + 橄榄棕 + 细线 + 克制 + 底部金线
        "palette": {"primary": "#8a6d3b", "primary700": "#6d5730", "accent": "#8a6d3b",
                    "bg": "#ffffff", "surface": "#fafafa", "ink": "#222222", "muted": "#9a9a9a",
                    "line": "#e5e5e5", "cover1": "#8a6d3b", "cover2": "#222222"},
        "fonts": {"head": _SERIF, "body": _SERIF},
        "card_style": {"radius": 0, "border_width": 1, "border_style": "solid",
                       "shadow": "none", "padding_scale": 1.15},
        "background": {"type": "solid", "css": ""},
        "density": "spacious",
        "title_style": {"size_scale": 1.0, "decoration": "underline", "letter_spacing": 2},
        "page_decor": ["gold_line"],
    },
    "business": {  # 商务专业：藏青 + 金 + 细金线 + 端庄
        "palette": {"primary": "#1f3a5f", "primary700": "#16293f", "accent": "#c9a227",
                    "bg": "#ffffff", "surface": "#f8f9fa", "ink": "#1f2937", "muted": "#6b7280",
                    "line": "#e5e7eb", "cover1": "#1f3a5f", "cover2": "#c9a227"},
        "fonts": {"head": _SERIF, "body": _SANS},
        "card_style": {"radius": 6, "border_width": 1, "border_style": "solid",
                       "shadow": "0 2px 8px rgba(31,58,95,.08)", "padding_scale": 1.05},
        "background": {"type": "solid", "css": ""},
        "density": "balanced",
        "title_style": {"size_scale": 1.05, "decoration": "side_bar", "letter_spacing": 1},
        "page_decor": ["gold_line"],
    },
}

# 与 content-upload/render.py 的 STYLE_IDS 保持一致（顺序即下拉顺序）
STYLE_IDS = list(_STYLE_TABLE.keys())


def recipe_for_style(style_id):
    """风格 id → StyleRecipe。未知/空 id 返回 None（调用方回退到默认取模 recipe）。

    返回的 StyleRecipe 已 .validate() 过（palette/fonts/整套视觉字段全合法）。
    """
    entry = _STYLE_TABLE.get((style_id or "").strip())
    if not entry:
        return None
    recipe = StyleRecipe(
        palette=dict(entry["palette"]),
        fonts=dict(entry["fonts"]),
        decorations=["none"],
        illustration={"style": "line_art", "diagram_kinds": []},
        layout_prefs={},
        # 整套视觉（缺省走 validate 默认值，与旧版渲染一致）
        card_style=dict(entry.get("card_style") or {}),
        background=dict(entry.get("background") or {}),
        density=str(entry.get("density", "balanced")),
        title_style=dict(entry.get("title_style") or {}),
        page_decor=list(entry.get("page_decor") or []),
    )
    return recipe.validate()
