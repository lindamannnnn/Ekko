# -*- coding: utf-8 -*-
"""layouts/cover.py —— 封面（全部适用）。"""
from ..util import _esc
from .base import LayoutDef


def _decor(name, theme):
    c1 = theme.get("cover2", "#1c1917")
    c2 = theme.get("accent", "#0f766e")
    if name == "seal":
        return ('<div class="decor decor-seal" aria-hidden="true">'
                f'<span style="border-color:{c2};color:{c2};font-size:18px">课例</span></div>')
    if name == "branch":
        return ('<svg class="decor decor-branch" viewBox="0 0 120 120" aria-hidden="true">'
                f'<path d="M10 110 C40 80 50 40 110 20" stroke="{c2}" stroke-width="3" fill="none" opacity=".7"/>'
                f'<circle cx="110" cy="20" r="6" fill="{c2}" opacity=".7"/>'
                f'<circle cx="70" cy="55" r="5" fill="{c2}" opacity=".55"/></svg>')
    if name == "dot_grid":
        dots = "".join(
            f'<circle cx="{20 + (i % 6) * 16}" cy="{20 + (i // 6) * 16}" r="2.2" fill="{c2}" opacity=".5"/>'
            for i in range(36))
        return f'<svg class="decor decor-dots" viewBox="0 0 120 120" aria-hidden="true">{dots}</svg>'
    if name == "wave":
        return ('<svg class="decor decor-wave" viewBox="0 0 200 40" preserveAspectRatio="none" aria-hidden="true">'
                f'<path d="M0 20 Q25 4 50 20 T100 20 T150 20 T200 20" stroke="{c2}" stroke-width="3" fill="none" opacity=".6"/></svg>')
    return ""


def render(slots, theme):
    title = slots.get("title", "未命名课题")
    subtitle = slots.get("subtitle", "")
    meta = slots.get("meta", "")
    kick = slots.get("kick", "")
    ribbon = slots.get("ribbon", "")
    c1 = theme.get("cover1", "#44403c")
    c2 = theme.get("cover2", "#1c1917")
    accent = theme.get("accent", "#0f766e")
    decos = [d for d in theme.get("decorations", []) if d != "none"][:2]
    deco_html = "".join(_decor(d, theme) for d in decos)
    kick_html = f'<div class="cover-kick" style="background:{accent}">{_esc(kick)}</div>' if kick else ""
    ribbon_html = f'<div class="cover-ribbon">{_esc(ribbon)}</div>' if ribbon else ""
    sub_html = f'<div class="cover-sub">{_esc(subtitle)}</div>' if subtitle else ""
    meta_html = f'<div class="cover-meta">{_esc(meta)}</div>' if meta else ""
    return (
        f'<div class="ly ly-cover" style="background:linear-gradient(135deg,{c1},{c2})">'
        f'{deco_html}{kick_html}{ribbon_html}'
        f'<div class="cover-body">'
        f'<h1 class="cover-title">{_esc(title)}</h1>'
        f'{sub_html}{meta_html}'
        f'</div></div>'
    )


DEF = LayoutDef(
    layout_id="cover", label="封面",
    slot_schema={
        "title": {"type": "str", "req": True, "max_chars": 40},
        "subtitle": {"type": "str", "max_chars": 30},
        "meta": {"type": "str", "max_chars": 40},
        "kick": {"type": "str", "max_chars": 16},
        "ribbon": {"type": "str", "max_chars": 24},
    },
    applicable={"cats": "*", "kinds": ["cover"], "stages": "*"},
    css=(".ly-cover{position:relative;height:100%;display:flex;flex-direction:column;"
         "justify-content:center;align-items:center;color:#fff;text-align:center;overflow:hidden}"
         ".ly-cover .cover-body{z-index:2;padding:0 8%}"
         ".ly-cover .cover-title{font-size:clamp(30px,6vw,64px);font-weight:800;margin:0;letter-spacing:2px;text-shadow:0 2px 12px rgba(0,0,0,.35)}"
         ".ly-cover .cover-sub{font-size:clamp(15px,2.4vw,22px);opacity:.92;margin-top:10px}"
         ".ly-cover .cover-meta{font-size:14px;opacity:.78;margin-top:8px}"
         ".ly-cover .cover-kick{position:absolute;top:26px;left:26px;color:#fff;font-size:13px;padding:5px 12px;border-radius:999px;font-weight:700;z-index:3}"
         ".ly-cover .cover-ribbon{position:absolute;top:0;right:0;background:rgba(255,255,255,.16);color:#fff;font-size:13px;padding:8px 22px;border-bottom-left-radius:14px;z-index:3}"
         ".ly-cover .decor{position:absolute;opacity:.9;z-index:1}"
         ".ly-cover .decor-seal{top:24px;right:26px}"
         ".ly-cover .decor-seal span{display:inline-block;width:52px;height:52px;line-height:52px;border:3px solid;border-radius:8px;font-size:26px;font-weight:800}"
         ".ly-cover .decor-branch{bottom:0;right:0;width:42%;height:60%}"
         ".ly-cover .decor-dots{top:18px;left:18px;width:120px;height:120px}"
         ".ly-cover .decor-wave{bottom:0;left:0;width:100%;height:40px}"),
    _render=render,
)
