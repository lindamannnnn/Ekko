# -*- coding: utf-8 -*-
"""courseware_engine/util.py —— 与 LLM/解析相关的通用工具（从 vendor 迁移，纯标准库）。

迁移自 vendor/scripts/courseware_gen.py：
  - _esc / clean_control（HTML 转义 + 控制字符清理，render 与所有 layout 渲染器共用）
  - extract_json（稳健 JSON 解析：标准 → 截取 {…}/[…] → json5 兜底；不做激进字符串改写）
  - classify_subject（从表单判定学科 category）

这些函数是 T0 基建，不依赖任何下游模块（schemas/agents/layouts）。
"""
import os
import re
import json


# ---------------------------------------------------------------------------
# 1) HTML 转义 + 控制字符清理
# ---------------------------------------------------------------------------
def clean_control(s):
    """去掉字符串内部的裸控制字符（弱模型偶尔吐出的 \\r/\\t/裸换行会破坏 JSON）。"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s)


def _esc(s):
    """HTML 转义，供所有版式渲染器调用（全程 _esc，防注入/破坏布局）。"""
    return ("" if s is None else str(s)) \
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# 2) 稳健 JSON 解析
# ---------------------------------------------------------------------------
def extract_json(text, max_retry=3):
    """尽力从模型输出里解析出 JSON。优先标准解析，回退到截取 + 可选 json5。

    弱模型（如 GLM-4-Flash）输出通常已是合法 JSON（可能包在 ``` 里），
    标准解析 + 截取 {…} 已验证足够；不采用激进的字符串改写，避免破坏嵌套结构。
    """
    if not text:
        raise ValueError("模型返回为空")
    t = clean_control(text.strip())
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    # 1) 标准
    try:
        return json.loads(t)
    except Exception:
        pass
    # 2) 截取首个 {...} 或 [...]
    m = re.search(r"\{.*\}|\[.*\]", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # 3) 尝试 json5（若环境有安装）
    try:
        import json5  # type: ignore
        return json5.loads(t)
    except Exception:
        pass
    raise ValueError("模型未返回可解析的 JSON")


# ---------------------------------------------------------------------------
# 3) 学科分类（从表单判定 category）
# ---------------------------------------------------------------------------
def classify_subject(form):
    """从输入判定学科 category。mode=art 时按 category 判，否则按 subject 判。"""
    if not isinstance(form, dict):
        return "general"
    mode = form.get("mode", "subject")
    if mode == "art":
        cat = (form.get("category") or "").strip()
    else:
        cat = (form.get("subject") or "").strip()
    c = cat.replace("（", "(").replace("）", ")")
    if any(k in c for k in ["数学", "算术"]):
        return "math"
    if any(k in c for k in ["语文", "文言", "阅读", "作文"]):
        return "chinese"
    if any(k in c for k in ["英语", "English", "eng"]):
        return "english"
    if any(k in c for k in ["物理", "化学", "生物", "科学", "理化"]):
        return "science"
    if any(k in c for k in ["历史"]):
        return "history"
    if any(k in c for k in ["地理"]):
        return "geography"
    if any(k in c for k in ["道法", "政治", "思政"]):
        return "politics"
    if any(k in c for k in ["美术", "书法", "绘画"]):
        return "art"
    if any(k in c for k in ["舞蹈", "体育", "运动"]):
        return "pe"
    return "general"
