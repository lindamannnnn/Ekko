# -*- coding: utf-8 -*-
"""layouts/big_image.py —— 大字意象页（语文意象 / 低段导入）。

背景为确定性内联 SVG 简笔画（由 svg_hint 枚举选取：mountain/river/moon/leaf/star），
禁止 LLM 写自由 SVG（防注入/版式崩坏）。
"""
from ..util import _esc
from .base import LayoutDef

# 确定性简笔画库：每个返回一个 SVG 字符串（viewBox 0 0 200 200，充满背景）
_SVG_LIB = {
    "mountain": ('<svg class="bi-svg" viewBox="0 0 200 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
                 '<rect width="200" height="200" fill="currentColor" opacity=".10"/>'
                 '<path d="M0 160 L60 70 L100 130 L150 50 L200 160 Z" fill="currentColor" opacity=".45"/>'
                 '<circle cx="160" cy="45" r="18" fill="currentColor" opacity=".55"/></svg>'),
    "river": ('<svg class="bi-svg" viewBox="0 0 200 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
              '<rect width="200" height="200" fill="currentColor" opacity=".10"/>'
              '<path d="M0 80 Q50 60 100 80 T200 80 V200 H0 Z" fill="currentColor" opacity=".4"/>'
              '<path d="M0 120 Q50 100 100 120 T200 120" stroke="currentColor" stroke-width="3" fill="none" opacity=".5"/></svg>'),
    "moon": ('<svg class="bi-svg" viewBox="0 0 200 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
             '<rect width="200" height="200" fill="currentColor" opacity=".10"/>'
             '<circle cx="100" cy="100" r="55" fill="currentColor" opacity=".5"/>'
             '<circle cx="120" cy="85" r="55" fill="#fff" opacity=".9"/></svg>'),
    "leaf": ('<svg class="bi-svg" viewBox="0 0 200 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
             '<rect width="200" height="200" fill="currentColor" opacity=".10"/>'
             '<path d="M100 30 C150 60 150 140 100 175 C50 140 50 60 100 30 Z" fill="currentColor" opacity=".45"/>'
             '<line x1="100" y1="40" x2="100" y2="170" stroke="currentColor" stroke-width="3" opacity=".5"/></svg>'),
    "star": ('<svg class="bi-svg" viewBox="0 0 200 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
             '<rect width="200" height="200" fill="currentColor" opacity=".10"/>'
             '<path d="M100 35 L118 80 L166 82 L128 112 L142 158 L100 130 L58 158 L72 112 L34 82 L82 80 Z" fill="currentColor" opacity=".5"/></svg>'),
}


def render(slots, theme):
    # 防御性截断：即便上游未走 check_slots，也不让超长文本撑破大字版式
    headline = (slots.get("headline", "") or "")[:14]
    body = (slots.get("body", "") or "")[:120]
    image_desc = (slots.get("image_desc", "") or "")[:120]
    hint = slots.get("svg_hint", "mountain")
    accent = theme.get("accent", "#0f766e")
    svg = _SVG_LIB.get(hint, _SVG_LIB["mountain"])
    body_html = f'<p class="bi-body">{_esc(body)}</p>' if body else ""
    desc_html = f'<div class="bi-desc">{_esc(image_desc)}</div>' if image_desc else ""
    return (
        f'<div class="ly ly-big_image" style="color:{accent}">'
        f'{svg}'
        f'<div class="bi-content">'
        f'<h1 class="bi-headline">{_esc(headline)}</h1>'
        f'{body_html}{desc_html}'
        f'</div></div>')


DEF = LayoutDef(
    layout_id="big_image", label="大字意象页",
    slot_schema={
        "headline": {"type": "str", "req": True, "max_chars": 14},
        "body": {"type": "str", "max_chars": 160},
        "image_desc": {"type": "str", "max_chars": 120},
        "svg_hint": {"type": "str", "max_chars": 16},
    },
    applicable={"cats": "*", "kinds": ["lead_in", "concept"], "stages": "*"},
    css=(".ly-big_image{position:relative;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;padding:0 8%"
         ".ly-big_image .bi-svg{position:absolute;inset:0;width:100%;height:100%}"
         ".ly-big_image .bi-content{position:relative;z-index:2;text-align:center;color:var(--ink)}"
         ".ly-big_image .bi-headline{font-size:clamp(28px,6vw,60px);font-weight:800;margin:0;color:var(--primary);text-shadow:0 2px 10px rgba(255,255,255,.4)}"
         ".ly-big_image .bi-body{font-size:clamp(16px,2.6vw,22px);margin-top:14px;line-height:1.6}"
         ".ly-big_image .bi-desc{font-size:14px;color:var(--muted);margin-top:8px}"),
    _render=render,
)
