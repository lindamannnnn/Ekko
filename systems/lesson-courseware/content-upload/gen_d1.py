# -*- coding: utf-8 -*-
"""gen_d1.py —— 用内容上传功能流水线，把 D1 教师手册做成课件。

流水线：ingest(粘贴文本) → moderate(合规) → segment(切页) → render(单文件HTML)
产物：out/d1_courseware_<风格>.html
"""
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from pipeline.ingest import ingest_text
from pipeline.moderate import moderate
from pipeline.segment import segment
import render


def main():
    src = os.path.join(BASE, "out", "_d1_manual.md")
    raw = open(src, encoding="utf-8").read()

    # [1] ingest：已是纯文本/ markdown
    text = ingest_text(raw)

    # [2] moderate：合规兜底
    m = moderate(text, {})
    print("== 合规检查 ==", m)

    # [3] segment：规则切页（无 API key 走规则；本仓库 .env 未配 key）
    slides = segment(text, env={}, allow_llm=False)
    print(f"== 切页 == 共 {len(slides)} 页（不含封面）")

    # 封面标题取文档首个 # 行
    cover = "小龙虾启蒙营 D1 教师执行手册"
    mm = re.search(r"^#\s+(.+)$", text, re.M)
    if mm:
        cover = mm.group(1).strip()

    out = os.path.join(BASE, "out")
    for sid in ["business", "magazine"]:
        html = render.render(slides, sid, cover, with_cover=True)
        path = os.path.join(out, f"d1_courseware_{sid}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  {sid:10s} -> {path}  ({len(html)} bytes, {len(slides)+1} 页含封面)")

    print("完成。")


if __name__ == "__main__":
    main()
