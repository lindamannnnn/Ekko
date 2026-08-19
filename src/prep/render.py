# -*- coding: utf-8 -*-
"""render.py —— 渲染核心：slides → 单文件 index.html（离线、横向翻页）。

设计：
  - 一个健壮的通用引擎（布局/导航/键盘/触摸/进度条，纯内联、无 CDN），
  - 10 种风格 = 10 套主题 CSS（视觉灵感来自 guizang / primary-chinese / teaching /
    frontend-dev / Slidev / reveal.js，已沉淀为独立可改的 styles/<id>.css）；
  - 输出为完全自包含的单文件 HTML，可直接双击打开或部署。
风格选择（v3 计划：风格要多、跨不同 skill 也行）：
  1 graffiti 涂鸦像素游戏风      （默认：深空渐变+像素网格+金/霓虹，提取自《涂鸦PK》课件）
  2 magazine 电子杂志·电子墨水  3 swiss 瑞士国际主义  4 ink 水墨中国风
  5 devblue 开发者极简蓝         6 apple 苹果极简      7 brutalist 复古工业
  8 glass 暗色玻璃拟态           9 dracula 霓虹暗夜   10 serif 极简衬线
 11 business 商务专业
"""
import os
import re
import html

# 风格注册表（顺序即 1~10）
STYLES = [
    ("graffiti",  "涂鸦像素游戏风",     "深空渐变 + 像素网格 + 金/霓虹强调，玻璃卡（默认）"),
    ("magazine",  "电子杂志·电子墨水", "衬线 + 暖纸 + 赭石，流体排版"),
    ("swiss",     "瑞士国际主义",       "无衬线 + 网格 + IKB蓝/柠檬黄/安全橙"),
    ("ink",       "水墨中国风",         "宣纸 + 墨色 + 印章红，书法感"),
    ("devblue",   "开发者极简蓝",       "单一蓝 #2563eb + 琥珀 #f59e0b，非对称"),
    ("apple",     "苹果极简",           "系统字体 + 大量留白 + 居中大标题"),
    ("brutalist", "复古工业",           "等宽 + 粗黑边框 + 高对比，无圆角"),
    ("glass",     "暗色玻璃拟态",       "暗色渐变 + 毛玻璃卡片 + 霓虹"),
    ("dracula",   "霓虹暗夜",           "dracula 配色 + 发光文字"),
    ("serif",     "极简衬线",           "经典衬线 + 细分割线，优雅"),
    ("business",  "商务专业",           "藏青 #1f3a5f + 金 #c9a227，企业感"),
]

STYLE_IDS = [s[0] for s in STYLES]

_BASE_CSS = """
:root{
  --bg:#ffffff; --fg:#1a1a1a; --muted:#666; --accent:#2563eb; --accent2:#f59e0b;
  --font: -apple-system, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
  --serif: Georgia, "Times New Roman", "Songti SC", "SimSun", serif;
  --mono: "JetBrains Mono", "Courier New", Consolas, monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;}
body{
  background:var(--bg); color:var(--fg); font-family:var(--font);
  overflow:hidden; -webkit-font-smoothing:antialiased;
}
.deck{display:flex; height:100vh; width:100%; overflow-x:auto; overflow-y:hidden;
  scroll-snap-type:x mandatory; scroll-behavior:smooth;}
.deck::-webkit-scrollbar{display:none;}
.deck{scrollbar-width:none;}
.slide{
  scroll-snap-align:start; flex:0 0 100vw; height:100vh; position:relative;
  display:flex; flex-direction:column; overflow-y:auto;
  padding:9vh 11vw;
}
.slide-inner{max-width:1100px; width:100%; margin:auto;}
.title{font-size:clamp(28px,5vw,56px); line-height:1.15; font-weight:800;
  letter-spacing:-.5px; margin-bottom:.6em; color:var(--fg);}
.bullets{list-style:none; margin-top:.4em;}
.bullets li{font-size:clamp(17px,2.4vw,26px); line-height:1.5; margin:.5em 0;
  padding-left:1.4em; position:relative; color:var(--fg);}
.bullets li::before{content:""; position:absolute; left:0; top:.62em;
  width:.55em; height:.55em; background:var(--accent); border-radius:2px;}
.kicker{font-size:clamp(12px,1.4vw,15px); letter-spacing:.18em; text-transform:uppercase;
  color:var(--accent); font-weight:700; margin-bottom:1em;}
.slide-num{position:absolute; right:5vw; bottom:4vh; font-size:13px; color:var(--muted);
  font-variant-numeric:tabular-nums;}
/* 封面 */
.cover .title{font-size:clamp(34px,7vw,80px);}
.cover .sub{font-size:clamp(15px,2vw,22px); color:var(--muted); margin-top:.6em;}
/* 导航 */
.nav-btn{position:fixed; top:50%; transform:translateY(-50%); z-index:50;
  width:46px; height:46px; border:none; border-radius:50%; cursor:pointer;
  background:rgba(128,128,128,.18); color:#fff; font-size:22px; display:flex;
  align-items:center; justify-content:center; backdrop-filter:blur(6px);
  transition:background .2s, opacity .2s; user-select:none;}
.nav-btn:hover{background:rgba(128,128,128,.4);}
.nav-prev{left:2vw;} .nav-next{right:2vw;}
.nav-btn[disabled]{opacity:.25; cursor:default;}
.progress{position:fixed; left:0; top:0; height:4px; background:var(--accent);
  width:0; z-index:60; transition:width .3s ease;}
@media (max-width:640px){ .slide{padding:8vh 7vw;} .nav-btn{display:none;} }
"""

_ENGINE_JS = """
(function(){
  var deck=document.getElementById('deck');
  var slides=deck.children;
  var total=slides.length, idx=0;
  var prev=document.getElementById('prev'), next=document.getElementById('next');
  var bar=document.getElementById('bar'), counter=document.getElementById('counter');
  function update(){
    deck.scrollTo({left:idx*window.innerWidth, behavior:'smooth'});
    if(prev) prev.disabled = idx<=0;
    if(next) next.disabled = idx>=total-1;
    if(bar) bar.style.width = ((idx+1)/total*100)+'%';
    if(counter) counter.textContent = (idx+1)+' / '+total;
    for(var i=0;i<slides.length;i++){
      var n=slides[i].querySelector('.slide-num');
      if(n) n.textContent=(i+1)+' / '+total;
    }
  }
  function go(d){ idx=Math.max(0,Math.min(total-1, idx+d)); update(); }
  if(prev) prev.onclick=function(){go(-1);};
  if(next) next.onclick=function(){go(1);};
  window.addEventListener('keydown',function(e){
    if(e.key==='ArrowRight'||e.key==='PageDown'||e.key===' '){go(1);}
    else if(e.key==='ArrowLeft'||e.key==='PageUp'){go(-1);}
    else if(e.key==='Home'){idx=0;update();} else if(e.key==='End'){idx=total-1;update();}
  });
  // 触摸滑动
  var sx=0;
  deck.addEventListener('touchstart',function(e){sx=e.touches[0].clientX;},{passive:true});
  deck.addEventListener('touchend',function(e){
    var dx=e.changedTouches[0].clientX-sx;
    if(Math.abs(dx)>50){ go(dx<0?1:-1); }
  },{passive:true});
  // 点击左右半屏
  deck.addEventListener('click',function(e){
    if(e.target.closest('.nav-btn')) return;
    var r=deck.getBoundingClientRect();
    if(e.clientX < r.left + r.width*0.3) go(-1);
    else if(e.clientX > r.right - r.width*0.3) go(1);
  });
  window.addEventListener('resize',update);
  update();
})();
"""


def _esc(s):
    return html.escape(str(s), quote=True)


# ---- 涂鸦默认风格：标题自动配 emoji 锚点（仅 graffiti 生效）----
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9, "十": 10}
_KEYCAP = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣",
           6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}


def _num_emoji(numstr: str) -> str:
    s = (numstr or "").strip()
    if s.isdigit():
        n = int(s)
    else:
        n = _CN_NUM.get(s, 0)
    return _KEYCAP.get(n, "🔢")


def _match_step(title: str):
    m = re.search(r"第([一二三四五六七八九十\d]+)", title)
    if m:
        return _num_emoji(m.group(1))
    m = re.search(r"任务([一二三四五六七八九十\d]+)", title)
    if m:
        return _num_emoji(m.group(1))
    return None


_EMOJI_RULES = [
    (re.compile(r"不一样|区别|对比|差异|vs|VS"), "⚡"),
    (re.compile(r"豆包|对话|聊天|问答|动嘴"), "💬"),
    (re.compile(r"认识|开场|我们要|做什么|开始|欢迎|新朋友"), "🚀"),
    (re.compile(r"五步|步骤|方法|流程|怎么用|怎么做|法："), "🪜"),
    (re.compile(r"壁纸|桌面|图片|下载|搜索|上网|素材|换"), "🖼️"),
    (re.compile(r"资料|角色|收集|动漫|游戏|兴趣|喜欢|主题"), "🎮"),
    (re.compile(r"猜数字|代码|程序|运行|python|Python|小程序"), "💻"),
    (re.compile(r"发现|问题|目标|解决"), "💡"),
    (re.compile(r"拆解|拆分|分[解步]"), "🧩"),
    (re.compile(r"审查|检查|核对|确认|看清"), "🔍"),
    (re.compile(r"迭代|改进|优化|修改|提升|继续"), "🔄"),
    (re.compile(r"安全|规矩|提醒|禁止|注意|红线|失控"), "⚠️"),
    (re.compile(r"总结|学到了|回顾|收尾|展示"), "🏆"),
    (re.compile(r"作业|提交|交|截图|留痕|总结话术"), "📝"),
    (re.compile(r"成功|胜利|恭喜|完成|做到|跑通"), "🎉"),
    (re.compile(r"小龙虾|AI|助手|人工智能|电脑|操作"), "🦞"),
]


def _with_emoji(title: str, is_cover: bool = False) -> str:
    """为涂鸦风格标题按语义自动配 emoji 锚点，不改写正文文字。"""
    if not title or not title.strip():
        return title
    if is_cover:
        return "🦞 " + title.strip()
    step = _match_step(title)
    if step:
        return step + " " + title.strip()
    for rx, em in _EMOJI_RULES:
        if rx.search(title):
            return em + " " + title.strip()
    return "✨ " + title.strip()


def _slide_html(slide: dict, cover: bool = False, title: str = "",
                style_id: str = "") -> str:
    if cover:
        t = _with_emoji(title, is_cover=True) if style_id == "graffiti" else title
        inner = f'<h1 class="title">{_esc(t)}</h1>'
        return (f'<section class="slide cover"><div class="slide-inner">{inner}'
                f'<div class="sub">内容上传 · 课件预览</div></div>'
                f'<div class="slide-num"></div></section>')
    raw = slide.get("title") or ""
    if style_id == "graffiti":
        raw = _with_emoji(raw)
    t = _esc(raw)
    bullets = slide.get("bullets") or []
    lis = "".join(f"<li>{_esc(b)}</li>" for b in bullets if str(b).strip())
    body = f'<ul class="bullets">{lis}</ul>' if lis else ""
    return (f'<section class="slide"><div class="slide-inner">'
            f'<h2 class="title">{t}</h2>{body}</div>'
            f'<div class="slide-num"></div></section>')


def list_styles():
    return [{"id": i, "name": n, "desc": d} for (i, n, d) in STYLES]


def render(slides: list, style_id: str, title: str = "课件",
           styles_dir: str = None, with_cover: bool = True) -> str:
    """生成单文件 HTML 字符串。"""
    if style_id not in STYLE_IDS:
        style_id = STYLE_IDS[0]
    if styles_dir is None:
        styles_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles")
    css_path = os.path.join(styles_dir, style_id + ".css")
    theme_css = ""
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            theme_css = f.read()

    slides = [s for s in (slides or []) if s.get("title") or s.get("bullets")]
    parts = []
    if with_cover:
        parts.append(_slide_html({}, cover=True, title=title, style_id=style_id))
    for s in slides:
        parts.append(_slide_html(s, style_id=style_id))

    deck = "\n".join(parts)
    counter = f'<div class="slide-num" id="counter">1 / {len(slides)+ (1 if with_cover else 0)}</div>' \
        if not with_cover else ""
    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>{_esc(title)}</title>
<style>{_BASE_CSS}\n{theme_css}</style>
</head>
<body class="theme-{style_id}">
<div class="progress" id="bar"></div>
<button class="nav-btn nav-prev" id="prev" aria-label="上一页">&#10094;</button>
<button class="nav-btn nav-next" id="next" aria-label="下一页">&#10095;</button>
<div class="deck" id="deck">
{deck}
</div>
<script>{_ENGINE_JS}</script>
</body>
</html>"""
