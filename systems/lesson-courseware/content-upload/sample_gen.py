# -*- coding: utf-8 -*-
"""sample_gen.py —— 生成示例课件 HTML，演示成品效果。

用法：
  ./.venv/Scripts/python.exe sample_gen.py
产物：
  out/sample_<style>.html  （10 套风格各一份，可直接双击打开）
"""
import os
import sys

# 让本脚本能 import 同目录的 render.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import render  # noqa: E402

# 示例：一份用户上传的「编程入门」课程内容（纯演示，非真实教学承诺）
SAMPLE_TITLE = "Python 入门：变量与数据类型"
SAMPLE_SLIDES = [
    {
        "title": "什么是变量",
        "bullets": [
            "变量是程序中用来存放数据的「名字」",
            "a = 10 把数字 10 存到名字 a 里",
            "变量的值可以随时修改：a = a + 1",
        ],
    },
    {
        "title": "常见数据类型",
        "bullets": [
            "整数 int：1、42、-7",
            "浮点数 float：3.14、0.5",
            "字符串 str：'hello'、\"你好\"",
            "布尔 bool：True / False",
        ],
    },
    {
        "title": "命名规则",
        "bullets": [
            "只能含字母、数字、下划线，且不能以数字开头",
            "区分大小写：Age 与 age 是两个变量",
            "避免使用内置关键字（如 if、for）",
        ],
    },
    {
        "title": "动手练习",
        "bullets": [
            "把你的名字存进变量 name 并打印",
            "计算 半径=5 的圆的周长，存进变量 c",
            "判断 10 是否大于 3，结果存进变量 flag",
        ],
    },
]


def main():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out_dir, exist_ok=True)
    styles = render.list_styles()
    print(f"渲染 {len(styles)} 套风格到 {out_dir}/")
    for st in styles:
        sid = st["id"]
        html = render.render(
            SAMPLE_SLIDES, style_id=sid, title=SAMPLE_TITLE, with_cover=True)
        path = os.path.join(out_dir, f"sample_{sid}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✓ {sid:10s} {st['name']:8s} -> {os.path.basename(path)}")
    print("完成。打开 out/sample_<风格>.html 即可预览。")


if __name__ == "__main__":
    main()
