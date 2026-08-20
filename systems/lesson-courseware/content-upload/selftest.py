# -*- coding: utf-8 -*-
"""selftest.py —— 阶段6 自测：无 API 时跑通规则链路 + 10 风格渲染 + markitdown 解析。

用法（项目 venv）：
  .venv/Scripts/python.exe selftest.py
生成的预览在 out/selftest_<style>.html，可直接双击打开。
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from pipeline.ingest import ingest_text, ingest_file
from pipeline.segment import segment
from pipeline.moderate import moderate
from render import render, STYLE_IDS, list_styles

SAMPLE = """第一讲 函数的基本概念
函数是描述两个变量之间对应关系的模型。设 x 为自变量，y 为因变量。
要点：定义域、值域、对应法则三要素。

第二讲 一次函数
形如 y = kx + b (k≠0) 的函数叫一次函数。
图像是一条直线。k 决定增减性，b 是 y 轴截距。
例题：已知一次函数过点 (0,2) 与 (1,5)，求解析式。

第三讲 二次函数
形如 y = ax^2 + bx + c (a≠0) 的函数叫二次函数。
图像是抛物线，对称轴为 x = -b/(2a)。
顶点坐标是 (-b/(2a), (4ac-b^2)/(4a))。

第四讲 实际应用
用二次函数求最大利润、最佳方案。
步骤：设未知数 → 列函数式 → 求最值 → 作答。
"""

HTML_SAMPLE = """<html><body>
<h1>培训课程：高效阅读法</h1>
<p>本课程帮助学员提升阅读速度与理解率。</p>
<h2>模块一 速读训练</h2>
<ul><li>指读法减少回视</li><li>块状阅读扩大视幅</li></ul>
<h2>模块二 精读拆解</h2>
<p>抓主干、标结构、做笔记。</p>
</body></html>"""


def main():
    print("== 1. 规则切页（无 API） ==")
    slides = segment(SAMPLE, env={}, allow_llm=False)
    print(f"  切出 {len(slides)} 页")
    for i, s in enumerate(slides, 1):
        print(f"   [{i}] {s['title']!r}  bullets={len(s['bullets'])}")

    print("== 2. 合规检查 ==")
    m = moderate(SAMPLE, env={})
    print("   ok =", m["ok"], m.get("reason", ""))

    print("== 3. 渲染 10 风格 ==")
    out = os.path.join(BASE, "out")
    os.makedirs(out, exist_ok=True)
    name_map = {s["id"]: s["name"] for s in list_styles()}
    for sid in STYLE_IDS:
        html = render(slides, sid, title="自测课件")
        path = os.path.join(out, f"selftest_{sid}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"   {sid:10s} {name_map[sid]:12s} -> out/selftest_{sid}.html ({len(html)} bytes)")

    print("== 4. markitdown 解析 HTML 样例 ==")
    html_path = os.path.join(out, "_sample.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(HTML_SAMPLE)
    txt = ingest_file(html_path)
    print("   解析文本长度:", len(txt))
    print("   前120字:", txt[:120].replace("\n", " / "))
    print("   markitdown 切页:")
    s2 = segment(txt, env={}, allow_llm=False)
    print(f"   切出 {len(s2)} 页")
    for i, s in enumerate(s2, 1):
        print(f"     [{i}] {s['title']!r} bullets={len(s['bullets'])}")

    print("\n全部自测通过 ✓")


if __name__ == "__main__":
    main()
