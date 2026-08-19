# -*- coding: utf-8 -*-
"""KB 课程树读取 + KB 条目转 slides（content-upload 分支内，不依赖 mainline 代码）。

- list_kb_courses()：扫描 vendor/kb，返回 {科目: {年级: [课程...]}} 供前端三级联下拉。
- get_entry(subject, grade, topic)：按 (科目,年级,课程) 精确读文件；找不到退回 topic 子串匹配。
- kb_to_slides(entry)：把 KB 条目（原文/知识点/公式/易错点）转成 render 需要的
  [{"title":..., "bullets":[...]}] 结构。
"""
import os
import re
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# KB 知识库是系统 B（lesson-courseware）的只读数据，课前系统复用同一份。
# prep 位于 class-review-system/src/prep，向上三级到 E:/001 再进 lesson-courseware。
# 用候选回退，避免目录结构调整后直接崩。
_KB_CANDIDATES = [
    os.path.normpath(os.path.join(BASE_DIR, "..", "..", "..", "lesson-courseware", "vendor", "kb")),
    os.path.normpath(os.path.join(BASE_DIR, "..", "..", "lesson-courseware", "vendor", "kb")),
    os.path.normpath(os.path.join(BASE_DIR, "kb")),
]
KB_ROOT = None
for _c in _KB_CANDIDATES:
    if os.path.isdir(_c):
        KB_ROOT = _c
        break
if KB_ROOT is None:
    KB_ROOT = _KB_CANDIDATES[0]

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

_GRADE_KEY = re.compile(r"(\d+)\s*年级([上下])?")


def _grade_key(g: str):
    m = _GRADE_KEY.match(g or "")
    if m:
        return (int(m.group(1)), 0 if m.group(2) == "上" else 1)
    return (99, 0)


def list_kb_courses():
    """返回 {subject: {grade: [topic, ...]}}，按文件扫描，跳过 bundle 总览文件。"""
    tree = {}
    if not os.path.isdir(KB_ROOT):
        return tree
    for sub in sorted(os.listdir(KB_ROOT)):
        sdir = os.path.join(KB_ROOT, sub)
        if not os.path.isdir(sdir):
            continue
        tree[sub] = {}
        for fn in sorted(os.listdir(sdir)):
            if not fn.endswith(".json"):
                continue
            try:
                j = json.load(open(os.path.join(sdir, fn), encoding="utf-8"))
            except Exception:
                continue
            if "bundle" in j:
                continue
            grade = j.get("grade") or ""
            topic = j.get("topic") or fn[:-5]
            tree[sub].setdefault(grade, []).append(topic)
    # 年级排序
    for sub in tree:
        tree[sub] = {g: sorted(topics) for g, topics in
                     sorted(tree[sub].items(), key=lambda kv: _grade_key(kv[0]))}
    return tree


def get_entry(subject, grade, topic):
    """按 (subject, grade, topic) 精确读文件；找不到则退回 topic 子串匹配。"""
    if not subject or not topic:
        return None
    sdir = os.path.join(KB_ROOT, subject)
    if not os.path.isdir(sdir):
        return None
    exact = (os.path.join(sdir, f"{grade}_{topic}.json")
             if grade else os.path.join(sdir, f"{topic}.json"))
    if os.path.exists(exact):
        return json.load(open(exact, encoding="utf-8"))
    for fn in os.listdir(sdir):
        if fn.endswith(".json") and topic in fn[:-5]:
            return json.load(open(os.path.join(sdir, fn), encoding="utf-8"))
    return None


def _to_bullets(v):
    """把 list / str 统一成非空字符串列表。str 优先按换行切；若仍是整段且含 ①②③ 则按编号切。"""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        parts = [p.strip() for p in v.split("\n") if p.strip()]
        if len(parts) <= 1 and re.search("[" + _CIRCLED + "]", v):
            parts = re.split(r"(?=[" + _CIRCLED + "])", v)
            parts = [p.strip(" ；;，。") for p in parts if p.strip()]
        return parts
    return []


def kb_to_slides(entry: dict):
    """KB 条目 → slides 列表（封面由 render 生成，此处不含封面）。"""
    if not entry:
        return []
    slides = []
    ot = _to_bullets(entry.get("original_text"))
    if ot:
        slides.append({"title": "教材原文", "bullets": ot})
    kp = _to_bullets(entry.get("key_points"))
    if kp:
        slides.append({"title": "知识点", "bullets": kp})
    fm = _to_bullets(entry.get("formulas"))
    if fm:
        slides.append({"title": "公式与示例", "bullets": fm})
    ca = _to_bullets(entry.get("cautions"))
    if ca:
        slides.append({"title": "易错点与易混警示", "bullets": ca})
    return slides


if __name__ == "__main__":
    t = list_kb_courses()
    print("科目:", list(t.keys()))
    for s, g in t.items():
        print(f"  {s}: {len(g)} 个年级")
    e = get_entry("数学", "五年级下", "同分母分数加减法")
    print("\n抽样 get_entry:", e.get("topic") if e else None)
    print("slides 数:", len(kb_to_slides(e)) if e else 0)
