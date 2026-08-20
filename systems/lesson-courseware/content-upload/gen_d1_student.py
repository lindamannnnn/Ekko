# -*- coding: utf-8 -*-
"""把「学生向」D1 内容跑通完整流水线，生成多风格课件。

流程：读 out/_d1_student.md → ingest(纯文本) → moderate(合规) → segment(切页) → render(多风格)
与教师手册版的区别：本文件内容是【学生上课用】，已剔除老师专属章节
（课前准备 / 老师话术 / 家长群 / 主管验收 / 复盘表），保留课堂流程与学生要打的提示词。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.ingest import ingest_text
from pipeline.moderate import moderate
from pipeline.segment import segment
from render import render

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "out", "_d1_student.md")
TITLE = "小龙虾启蒙营 · 第一天"


def load_env():
    env = {}
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main():
    env = load_env()
    text = ingest_text(open(SRC, encoding="utf-8").read())

    # 1) 合规
    res = moderate(text, env)
    if not res.get("ok"):
        raise SystemExit("合规未通过：" + str(res))
    print("[moderate] ok")

    # 2) 切页（已配置智谱 GLM-4-Flash，优先走 LLM 分段；异常自动回退规则）
    slides = segment(text, env=env, allow_llm=True)
    print(f"[segment] {len(slides)} 张内容页（封面另加）")

    # 3) 多风格渲染
    styles = ["magazine", "swiss", "ink", "devblue", "business", "apple"]
    for st in styles:
        html = render(slides, st, TITLE, os.path.join(HERE, "styles"))
        out = os.path.join(HERE, "out", f"d1_student_{st}.html")
        open(out, "w", encoding="utf-8").write(html)
        print(f"[render] {st:9s} -> {os.path.basename(out)}  ({len(html)//1024}KB)")


if __name__ == "__main__":
    main()
