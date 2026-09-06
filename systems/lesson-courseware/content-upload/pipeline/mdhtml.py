# -*- coding: utf-8 -*-
"""行内 markdown → HTML 转换（markdown-it-py 封装）。

职责单一：把 slides 里的 title/bullets 从 markdown 原文转成 HTML。
- **加粗** → <strong>加粗</strong>
- *斜体* → <em>斜体</em>
- `代码` → <code>代码</code>
- [文字](链接) → <a href>文字</a>
- ~~删除线~~ → <del>删除线~~（markdown-it-py 默认不开 strikethrough，用插件）

代码块占位符 §§CODE_BLOCK_N§§ 不转换（render 层识别后渲染 <pre><code>）。
"""
from markdown_it import MarkdownIt

# 单例：enable strikethrough（~~删除线~~）
_MD = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("strikethrough")

# 占位符标记（segment 的代码块占位符）
_PLACEHOLDER_MARK = "§§CODE_BLOCK_"


def render_inline(text: str) -> str:
    """把单行 markdown 文本转成 HTML（行内渲染，不包 <p>）。

    - 含代码块占位符的行原样返回（render 层单独处理）
    - 其余按 markdown 语法转换，输出即合法 HTML，可直接插入模板
    """
    if not text:
        return ""
    s = str(text)
    if _PLACEHOLDER_MARK in s:
        return s
    return _MD.renderInline(s)


def render_slides(slides: list) -> list:
    """把 slides 里所有 title 和 bullets 转成 HTML（原地修改并返回）。

    code 字段不动（render 层负责 <pre><code> 渲染）。
    """
    for s in slides:
        s["title"] = render_inline(s.get("title") or "")
        s["bullets"] = [render_inline(b) for b in (s.get("bullets") or [])]
    return slides
