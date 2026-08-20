# -*- coding: utf-8 -*-
"""courseware_engine/render.py —— deck 装配器（非 LLM）。

build_deck(pages, recipe, identity, title, meta) → 单文件可翻页 HTML。

替代 vendor 的 15 分支 _render_slide 单体：本层只做
  CSS 变量注入 + 各版式渲染器调用（LayoutDef.render）+ deck 骨架 + 翻页 JS。
每版式渲染器是纯函数、自包含、全程 _esc，根节点 class="ly ly-<id>"。
（方案 §5：render 不新造翻页机制，沿用 vendor 的 deck JS / CSS 变量化。）
"""
from . import layouts as _layouts
from .style import recipe_to_css_vars, recipe_to_scoped_css


# ---------------------------------------------------------------------------
# deck 骨架 CSS（迁移 vendor _deck_css，色值全改 var(--*)）
# ---------------------------------------------------------------------------
_DECK_CSS = """
:root{--radius:14px;}
*{box-sizing:border-box;margin:0;padding:0;}
html,body{height:100%;font-family:var(--font-body);color:var(--ink);background:#0f172a;}
#deck{position:relative;width:100%;height:100vh;overflow:hidden;background:var(--bg);}
.slide{position:absolute;inset:0;display:none;flex-direction:column;opacity:0;
  transition:opacity .4s ease,transform .45s cubic-bezier(.16,1,.3,1);transform:translateY(14px);overflow:auto;}
.slide.active{display:flex;opacity:1;transform:none;}
.ly{width:100%;height:100%;overflow-wrap:break-word;}
/* 长英文单词/短语在 overflow:hidden 容器内（如练习卡、封面）不再被横向裁成半词，
   而是断行显示：根治 "my da"/"storyboo"/"Englis"/"be going t" 类半词截断。CJK 本就可任意断行，无副作用。 */
.ly *{overflow-wrap:break-word;word-break:break-word;}
.progress{position:fixed;left:0;top:0;height:4px;background:var(--primary);width:0;z-index:20;transition:width .3s;}
.pg{position:fixed;right:18px;bottom:16px;font-size:13px;color:#fff;background:rgba(15,23,42,.5);padding:5px 12px;border-radius:999px;z-index:20;}
.nav{position:fixed;right:18px;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;align-items:center;gap:10px;z-index:20;}
.nav button{width:42px;height:42px;border:none;border-radius:50%;background:rgba(255,255,255,.9);color:var(--ink);font-size:22px;cursor:pointer;box-shadow:0 6px 18px rgba(0,0,0,.2);}
.dots{display:flex;flex-direction:column;gap:7px;}
.dots i{width:8px;height:8px;border-radius:50%;background:rgba(15,23,42,.25);}
.dots i.on{background:var(--primary);}
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
"""


# ---------------------------------------------------------------------------
# deck JS（迁移 vendor _deck_js，含 toggleAns）
# ---------------------------------------------------------------------------
_DECK_JS = """
<script>
let i=0;const deck=document.getElementById('deck');const slides=[...deck.querySelectorAll('.slide')];
const bar=document.getElementById('bar');const pg=document.getElementById('pg');const dots=document.getElementById('dots');
slides.forEach((_,k)=>{const d=document.createElement('i');if(k===0)d.className='on';dots.appendChild(d);});
function show(k){i=Math.max(0,Math.min(slides.length-1,k));slides.forEach((s,k)=>s.classList.toggle('active',k===i));
bar.style.width=((i+1)/slides.length*100)+'%';pg.textContent=(i+1)+' / '+slides.length;
[...dots.children].forEach((d,k)=>d.classList.toggle('on',k===i));}
function go(d){show(i+d);}
function toggleAns(btn){const a=btn.nextElementSibling;a.style.display=a.style.display==='none'?'block':'none';btn.textContent=a.style.display==='none'?'显示答案':'隐藏答案';}
window.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key===' ')go(1);else if(e.key==='ArrowLeft')go(-1);});
show(0);
</script>
"""


def _theme_from_recipe(recipe):
    """构造传给布局渲染器的 theme dict（具体 hex + 字体 + 装饰 + 图示）。"""
    t = dict(recipe.palette)
    t["fontHead"] = recipe.fonts.get("head", "")
    t["fontBody"] = recipe.fonts.get("body", "")
    t["decorations"] = recipe.decorations
    t["illustration"] = recipe.illustration
    return t


def _apply_overrides(page):
    """style_overrides 仅允许 {accent, align, vertical}，转为 section 内联 style。"""
    so = getattr(page, "style_overrides", None) or {}
    css = []
    if so.get("accent"):
        css.append(f"--accent:{so['accent']}")
    if so.get("align"):
        css.append(f"text-align:{so['align']}")
    if so.get("vertical") in ("rl", "lr"):
        css.append(f"writing-mode:vertical-{so['vertical']}")
    return ";".join(css)


def build_deck(pages, recipe, identity=None, title="", meta=""):
    """装配单文件可翻页 HTML。

    pages: list[PageSpec]；recipe: StyleRecipe；identity: {subject,grade,topic,...}；
    title/meta: 用于文档标题与底部信息（布局自身内容优先）。
    """
    identity = identity or {}
    doc_title = title or identity.get("topic") or "课件"
    theme = _theme_from_recipe(recipe)

    # 收集用到的版式 scoped CSS（按 layout_id 去重）
    used_css = []
    seen = set()
    sections = []
    for idx, page in enumerate(pages, 1):
        defn = _layouts.get_layout(page.layout_id)
        if defn is None:
            html = f'<div class="ly">（未知版式 {page.layout_id}）</div>'
        else:
            if defn.layout_id not in seen and defn.css:
                used_css.append(defn.css)
                seen.add(defn.layout_id)
            html = defn.render(page.slots, theme)
        ov = _apply_overrides(page)
        attr = f' data-page="{page.page_id}" data-event="{page.event_id}" data-kind="{page.kind}"'
        sections.append(
            f'<section class="slide" data-i="{idx}"{attr} style="{ov}">{html}</section>')

    css_block = (
        recipe_to_css_vars(recipe)
        + "<style>" + _DECK_CSS + "</style>"
        + recipe_to_scoped_css(recipe)
        + ("<style>" + "\n".join(used_css) + "</style>" if used_css else "")
    )
    sections_html = "\n".join(sections)
    meta_line = meta or f'{identity.get("grade","")} · {identity.get("subject","")} · {identity.get("topic","")}'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{doc_title}</title>
{css_block}
</head>
<body>
<div class="progress" id="bar"></div>
<div id="deck">
{sections_html}
</div>
<div class="pg" id="pg">1 / {len(pages)}</div>
<div class="nav">
  <button onclick="go(-1)" aria-label="上一页">‹</button>
  <div class="dots" id="dots"></div>
  <button onclick="go(1)" aria-label="下一页">›</button>
</div>
{_DECK_JS}
</body>
</html>"""
