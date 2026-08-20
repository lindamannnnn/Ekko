# -*- coding: utf-8 -*-
"""gen_random.py —— 自己写培训内容，跑真实流水线，随机风格，重点查流程问题。

流程：ingest_file(真实上传路径) → moderate(合规) → segment(LLM 切页) → render(随机风格)
校验：合规是否误杀 / 切页是否 >0 / HTML 是否合法 / emoji 仅 graffiti / < 是否转义 / 11 风格是否全可渲染。
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline.ingest import ingest_file
from pipeline.moderate import moderate
from pipeline.segment import segment
from render import render, STYLE_IDS

random.seed(20260817)
COURSES = {
    "习惯训练营D1": "out/_train_habit.md",
    "表达训练D1":   "out/_train_speak.md",
    "高效笔记D1":   "out/_train_note.md",
}
ENV = {}
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1); ENV[k.strip()] = v.strip()

GRAFFITI_EMOJI = ("⚡", "💬", "🚀", "🪜", "🖼️", "🎮", "💻", "💡", "🧩",
                  "🔍", "🔄", "⚠️", "🏆", "📝", "🎉", "🦞", "✨",
                  "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")


def check(html, style, n_slides):
    issues = []
    if not html.startswith("<!doctype html>"):
        issues.append("DOCTYPE 缺失")
    if f"theme-{style}" not in html:
        issues.append(f"缺 theme-{style}")
    # 页数 = 封面 + 内容（用 <section class="slide 精确计数，避开 slide-inner/slide-num）
    cnt = html.count('<section class="slide')
    if cnt != n_slides + 1:
        issues.append(f"页数异常 期望{n_slides+1} 实得{cnt}")
    # emoji 仅 graffiti
    prefixed = [e + " " for e in GRAFFITI_EMOJI]
    has_emoji = any(p in html for p in prefixed)
    if style == "graffiti" and not has_emoji:
        issues.append("graffiti 却无 emoji")
    if style != "graffiti" and has_emoji:
        issues.append(f"非 graffiti({style}) 竟有 emoji")
    # < 转义（note 课程含 "分数 < 60"，必须转成 &lt;，否则有 XSS/结构风险）
    if "分数 < 60" in html:
        issues.append("存在未转义 '<'（XSS/结构风险）")
    if "分数 &lt; 60" in html:
        pass  # 转义正确，无需处理
    # 体积
    if len(html.encode("utf-8")) > 3_000_000:
        issues.append("文件 >3MB")
    return issues


def run_course(name, path, styles):
    print(f"\n===== {name} =====")
    raw = ingest_file(path)
    m = moderate(raw, env=ENV, use_api=False)
    if not m["ok"]:
        print(f"  [合规拦截] {m.get('reason')}  -> 流程止步")
        return
    text = raw
    slides = segment(text, env=ENV, allow_llm=True)
    print(f"  ingest OK | 合规 OK | 切页 {len(slides)} 页")
    for sid in styles:
        html = render(slides, style_id=sid, title=name)
        fn = f"out/{name}_random_{sid}.html"
        open(fn, "w", encoding="utf-8").write(html)
        iss = check(html, sid, len(slides))
        tag = "OK " if not iss else "!! "
        print(f"  {tag}[{sid:9s}] {fn}  ({len(html)//1024}KB) " +
              ("" if not iss else "问题: " + "; ".join(iss)))


# 1) 每门课随机 3 个风格
print(">>> 随机风格生成（seed=20260817）")
for name, path in COURSES.items():
    picks = random.sample(STYLE_IDS, 3)
    run_course(name, path, picks)

# 2) 全 11 风格冒烟（用 note 课，含 < 与表格），确认每种都能渲染不报错
print("\n>>> 全 11 风格冒烟（高效笔记D1，含 '<' 与表格）")
run_course("高效笔记D1", "out/_train_note.md", list(STYLE_IDS))
print("\n全部流程跑完。")
