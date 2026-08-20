# -*- coding: utf-8 -*-
"""courseware_engine/strong_expand.py —— 强模型路径（与弱模型路径分离）。

背景：弱模型路径（teach_expand.py + reviewer.expand_with_review）是为 GLM-4-Flash
这种「便宜但笨」的模型设计的——多次小调用（每例题一次、max_tokens=600）+ 自审打回重试。
这对推理型强模型（deepseek-v4-pro 等）是灾难：强模型每次调用都先花大量 token 在
reasoning_content（思考）上，600 token 全耗在思考、content 为空；多次调用 + 自审重试
让时间和 token 指数爆炸。

强模型「贵但聪明」，正确用法是：**一次大调用产出该课全部教学层，免自审闭环**。
本模块只做这一件事——把整节课的例题/品析/教学展开合并成一次调用，max_tokens 给足。

与弱模型路径的关系：二者互斥，由 orchestrator 按模型判定选其一；确定性引擎（auto_kb）
与知识/答案/结构部分完全不受影响。
"""
import json
import re


def _extract_json(text):
    if not text:
        return {}
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    s, e = t.find("{"), t.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(t[s:e + 1])
        except Exception:
            return {}
    return {}


# ---------------------------------------------------------------------------
# 三科「一次性全部产出」协议（强模型版：一次调用覆盖整课，不再逐例题调用）
# ---------------------------------------------------------------------------
MATH_ONCE = (
    "你是教龄 25 年的小学数学特级教师。为一节课的**所有例题**一次性写出教学展开，直接可投影给学生。\n\n"
    "【例题列表】\n{problems}\n\n"
    "对每道例题各写三段，缺一不可：\n"
    "1. 算理（为什么）：这一步背后的数学道理，禁止用公式本身当算理（面积课的算理是「数格子」不是「面积=长×宽」）。\n"
    "2. 过程（怎么做）：分步写，每步一个动作 + 依据，直到得出答案。\n"
    "3. 易错（哪里会错）：学生最容易错的一处 + 提醒。\n\n"
    "只输出 JSON，格式：\n"
    '{"examples":[{"index":0,"steps":["算理：…","过程：…","易错：…"]}, …]}\n'
    "index 对应例题列表的序号；steps 是三段的完整文字，每段一句话到两句话，可投影。\n"
)

CHINESE_ONCE = (
    "你是教龄 25 年的小学语文特级教师。为课文的关键句/词写「品析」，直接可投影给学生。\n\n"
    "【课文/诗句】{text}\n"
    "【品析对象】{target}\n\n"
    "必须包含三段，缺一不可：\n"
    "1. 意思：这个字/词/句在文中是什么意思。\n"
    "2. 手法：只写本句真正用的写法，判断要准确（'耷拉'是状态描写不是拟人，'借景说理'≠'借景抒情'）。\n"
    "3. 好在哪：表达效果 + 换成别的字/词行不行。\n\n"
    "只输出 JSON，格式：\n"
    '{"points":["意思：…","手法：…","好在哪：…"]}\n'
)

ENGLISH_ONCE = (
    "你是教龄 25 年的小学英语特级教师（人教 PEP）。为词汇/句型写教学展开，直接可投影。\n\n"
    "【词汇/句型】{target}\n\n"
    "必须包含三段，缺一不可：\n"
    "1. 呈现：词义 + 一句真实语境例句（不要写音标，音标在词卡页）。\n"
    "2. 操练：一个可当场做的替换/问答操练（给具体替换词或问句）。\n"
    "3. 应用：一个真实情境，让学生用这个词汇/句型交流。\n\n"
    "只输出 JSON，格式：\n"
    '{"points":["呈现：…","操练：…","应用：…"]}\n'
)


def expand_all(kb, client):
    """强模型一次调用产出该课全部教学展开，直接填回 kb。返回 kb。

    与弱模型路径（teach_expand 逐页多次 + 自审打回）互斥，二选一。
    """
    cat = kb.get("subject_cat")
    try:
        if cat == "math":
            return _math_once(kb, client)
        if cat == "chinese":
            return _chinese_once(kb, client)
        if cat == "english":
            return _english_once(kb, client)
    except Exception:
        pass  # 强模型单次失败不阻塞（确定性骨架仍在）
    return kb


def _math_once(kb, client):
    """数学：收集所有计算类例题，一次调用产出各例题的算理/过程/易错。"""
    segs = kb.get("segments") or []
    problems = []
    for seg in segs:
        if seg.get("layout") != "steps":
            continue
        p = (seg.get("slots") or {}).get("problem", "").strip()
        if not p or not any(k in p for k in ("计算", "求", "解", "=？", "多少", "比较", "改写", "读出", "近似", "用字母", "简写", "表示")):
            continue
        problems.append(p)
    if not problems:
        return kb

    problem_list = "\n".join(f"{i}. {p}" for i, p in enumerate(problems))
    prompt = MATH_ONCE.replace("{problems}", problem_list)
    raw = client.complete(
        [{"role": "system", "content": prompt},
         {"role": "user", "content": "为上面所有例题一次性写出教学展开，只输出 JSON。"}],
        temperature=0.3, timeout=180, max_tokens=8000)
    data = _extract_json(raw)
    exs = data.get("examples") or []
    # 按 index 填回对应例题的 steps
    by_index = {e.get("index", -1): (e.get("steps") or []) for e in exs if isinstance(e, dict)}
    k = 0
    for seg in segs:
        if seg.get("layout") != "steps":
            continue
        p = (seg.get("slots") or {}).get("problem", "").strip()
        if not p or not any(x in p for x in ("计算", "求", "解", "=？", "多少", "比较", "改写", "读出", "近似", "用字母", "简写", "表示")):
            continue
        if k in by_index and by_index[k]:
            steps = [s for s in by_index[k] if isinstance(s, str) and s.strip()][:8]
            if steps:
                seg["slots"]["steps"] = steps
        k += 1
    return kb


def _chinese_once(kb, client):
    """语文：一次产出品析（意思/手法/好在哪），插入品析页。"""
    segs = kb.get("segments") or []
    kps = kb.get("key_points") or []
    text = (kb.get("original_text") or "").strip()

    target = ""
    for kp in kps:
        if "重点词句" in kp or "重点句" in kp:
            target = (kp.split("：", 1)[1] if "：" in kp else (kp.split(":", 1)[1] if ":" in kp else kp)).strip()
            break
    if not target or len(target) > 60:
        return kb

    prompt = CHINESE_ONCE.replace("{text}", text[:300]).replace("{target}", target)
    raw = client.complete(
        [{"role": "system", "content": prompt},
         {"role": "user", "content": f"为「{target}」写出品析，只输出 JSON。"}],
        temperature=0.3, timeout=180, max_tokens=4000)
    data = _extract_json(raw)
    pts = data.get("points") or []
    pts = [p for p in pts if isinstance(p, str) and p.strip()][:8]
    if not pts:
        return kb
    for s in segs:
        if (s.get("slots") or {}).get("statement") == "重点句 · 品析":
            s["slots"]["points"] = pts
            break
    else:
        insert_at = len(segs)
        for i, s in enumerate(segs):
            if s.get("kind") == "practice":
                insert_at = i
                break
        segs.insert(insert_at, {"kind": "concept", "layout": "concept",
                                "slots": {"statement": "重点句 · 品析", "points": pts}})
    return kb


def _english_once(kb, client):
    """英语：一次产出词汇/句型教学展开（呈现/操练/应用），插入教学页。"""
    segs = kb.get("segments") or []
    target = ""
    for s in segs:
        if s.get("layout") == "word_grid":
            ws = (s.get("slots") or {}).get("words") or []
            if ws:
                target = "、".join(w.get("word", "") for w in ws[:3])
                break
    if not target:
        for s in segs:
            if (s.get("slots") or {}).get("statement") == "核心句型 · Key patterns":
                pts = (s.get("slots") or {}).get("points") or []
                if pts:
                    target = pts[0]
                    break
    if not target or len(target) > 60:
        return kb

    prompt = ENGLISH_ONCE.replace("{target}", target)
    raw = client.complete(
        [{"role": "system", "content": prompt},
         {"role": "user", "content": f"为「{target}」写教学展开，只输出 JSON。"}],
        temperature=0.3, timeout=180, max_tokens=4000)
    data = _extract_json(raw)
    pts = data.get("points") or []
    pts = [p for p in pts if isinstance(p, str) and p.strip()][:8]
    if not pts:
        return kb
    for s in segs:
        if (s.get("slots") or {}).get("statement") == "词汇 · 句型教学":
            s["slots"]["points"] = pts
            break
    else:
        insert_at = len(segs)
        for i, s in enumerate(segs):
            if s.get("kind") == "practice":
                insert_at = i
                break
        segs.insert(insert_at, {"kind": "concept", "layout": "concept",
                                "slots": {"statement": "词汇 · 句型教学", "points": pts}})
    return kb
