# -*- coding: utf-8 -*-
"""共享文本/解析工具（自 vendor/scripts/courseware_gen.py 迁移，行为保持一致）。

包含：弱模型容错 JSON 解析、HTML 转义、学科分类、数字容忍抽取、文本压缩。
这些函数是引擎各模块（agents/layouts/subjects/render）的公共依赖。
"""
import json
import re


# ---------------------------------------------------------------------------
# HTML 转义（渲染层全程使用，杜绝把模型原文直接拼进 HTML）
# ---------------------------------------------------------------------------
def _esc(s):
    return ("" if s is None else str(s)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# 弱模型容错 JSON 解析（无第三方依赖；不采用激进字符串改写，避免破坏嵌套结构）
# ---------------------------------------------------------------------------
def _clean_control(s):
    """去掉字符串内部的裸控制字符（弱模型偶尔吐出的 \r/\t/裸换行会破坏 JSON）。"""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s)


def extract_json(text, max_retry=3):
    """尽力从模型输出里解析出 JSON。优先标准解析，回退到截取 + 可选 json5。"""
    if not text:
        raise ValueError("模型返回为空")
    t = _clean_control(text.strip())
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}|\[.*\]", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    try:
        import json5  # type: ignore
        return json5.loads(t)
    except Exception:
        pass
    raise ValueError("模型未返回可解析的 JSON")


# ---------------------------------------------------------------------------
# 学科分类（自 vendor classify_subject 迁移，原样保留）
# ---------------------------------------------------------------------------
def classify_subject(form):
    """从输入判定学科 category。"""
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


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------
def _one_line(x):
    if isinstance(x, list):
        return "；".join(str(i) for i in x)
    return str(x)


def _sint(v, d=0):
    """容忍弱模型把数字写成 '6格'/'约3' 等，强制抽成 int。"""
    if v is None:
        return d
    try:
        return int(float(str(v).strip().split()[0]))
    except Exception:
        m = re.search(r"-?\d+", str(v))
        return int(m.group()) if m else d


def _sfloat(v, d=0.0):
    if v is None:
        return d
    try:
        return float(str(v).strip().split()[0])
    except Exception:
        m = re.search(r"-?\d+(?:\.\d+)?", str(v))
        return float(m.group()) if m else d


def truncate(s, n):
    """超长截断（用于 slot 厚度约束）。"""
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n] + "…"
