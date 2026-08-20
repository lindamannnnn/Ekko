# -*- coding: utf-8 -*-
"""courseware_engine/teach_expand.py —— 教学专家协议（"经验丰富的教师 agent"）。

用户方案：固定一个教学经验丰富的 agent，专门指导弱模型「如何生成教学层」，
不让弱模型自由发挥。本模块就是那个"专家"——把三科的"教学展开方法"沉淀成固定协议，
弱模型只按协议填充具体内容。

三科协议：
  数学例题 = 算理(为什么) + 过程(分步+依据) + 易错(哪里会错)
  语文品析 = 意思 + 手法 + 好在哪(表达效果/换字对比)
  英语词汇/句型 = 呈现(音形义+例句) + 操练(替换/问答) + 应用(情境)

用法：v3 引擎在确定性引擎产出"知识骨架"后，调本模块让弱模型按协议展开教学层。
"""
import json
import re

# ---------------------------------------------------------------------------
# 三科协议（固定，一次写好长期复用）
# ---------------------------------------------------------------------------
MATH_PROTOCOL = (
    "你是教龄 25 年的小学数学特级教师。为一节课的例题写「教学展开」，直接可投影给学生，不要写教案。\n\n"
    "【例题】{problem}\n"
    "【必须包含三段，缺一不可】\n"
    "1. 算理（为什么）：这一步背后的数学道理，用一句话讲清（如「小数点要对齐，因为相同数位才能相减」）。\n"
    "2. 过程（怎么做）：分步写，每步一个动作 + 一句依据，直到得出答案。\n"
    "3. 易错（哪里会错）：学生最容易错的一处 + 提醒。\n\n"
    "【禁止】只写「公式→代入→答案」三个词；禁止「同学们」「想一想」「大家看」；禁止布置作业；每个字都要有教学价值。\n"
    "【示例】\n"
    "例题：3.25 - 2.35 = ？\n"
    "1. 算理：小数相减，小数点要对齐——只有相同数位上的数才能直接相减。\n"
    "2. 过程：① 小数点上下对齐；② 从百分位减起 5-5=0；③ 十分位 2-3 不够减，向个位借 1 变 12-3=9；④ 个位 3 借走 1 剩 2，2-2=0；⑤ 结果 0.90，去末尾 0 得 0.9。\n"
    "3. 易错：竖式没对齐小数点导致数位错位。提醒：先对齐小数点再落笔。\n"
)

CHINESE_PROTOCOL = (
    "你是教龄 25 年的小学语文特级教师。为课文的一句话/一个词写「品析」，直接可投影给学生，不要写教案。\n\n"
    "【课文/诗句】{text}\n"
    "【品析对象】{target}\n"
    "【必须包含三段，缺一不可】\n"
    "1. 意思：这个字/词/句在文中是什么意思。\n"
    "2. 手法：用了什么写法（比喻/拟人/反复/对比/借景说理等，只写本句真正用的）。\n"
    "3. 好在哪：它的表达效果——写出了什么、让人感受到什么；可加一句「换成别的字/词行不行」。\n\n"
    "【禁止】只贴原文；术语堆砌（不要罗列一堆手法名字）；禁止「体会情感」空话；每个字都要有教学价值。\n"
    "【示例】\n"
    "品析「一簇堆在另一簇上面」的「堆」字：\n"
    "1. 意思：「堆」是一层一层往上叠放。\n"
    "2. 手法：用动作写叶子，把静态的叶子写活了。\n"
    "3. 好在哪：一个「堆」字写出榕树叶又多又密、挤在一起的生命力；换成「长」就平淡了，没有这份旺盛。\n"
)

ENGLISH_PROTOCOL = (
    "你是教龄 25 年的小学英语特级教师（人教 PEP）。为一组词汇/句型写「教学展开」，直接可投影给学生，不要写教案。\n\n"
    "【词汇/句型】{target}\n"
    "【必须包含三段，缺一不可】\n"
    "1. 呈现：音、形、义 + 一句真实语境的例句。\n"
    "2. 操练：设计一个可当场做的替换/问答操练（给出具体替换词或问句）。\n"
    "3. 应用：设计一个真实情境，让学生用这个词汇/句型交流。\n\n"
    "【禁止】只列词表；禁止「跟读」「抄写」套话；禁止布置作业；每个环节都要学生真实开口/动手。\n"
    "【示例】\n"
    "词汇：pear 梨\n"
    "1. 呈现：/peə(r)/ pear 梨。Do you like pears? 你喜欢梨吗？\n"
    "2. 操练：替换水果名——把 pear 换成 apple/orange/banana 各说一遍：Do you like apples?\n"
    "3. 应用：同桌互相问「你最喜欢什么水果」：What fruit do you like? I like ...\n"
)


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


def _with_feedback(prompt, feedback):
    """把上一轮审核问题注入 prompt，让 LLM 针对性修正。"""
    if not feedback:
        return prompt
    return prompt + "\n\n【上一轮审核发现的问题，必须修正，不得再犯】\n" + "\n".join("- " + str(f) for f in feedback)


def expand_math(kb, client, feedback=None):
    """数学：对 segments 里的例题页（layout=steps），用算理协议生成教学展开，替换模板 steps。"""
    if kb.get("subject_cat") != "math":
        return kb
    segs = kb.get("segments") or []
    for seg in segs:
        if seg.get("layout") != "steps":
            continue
        slots = seg.get("slots") or {}
        problem = (slots.get("problem") or "").strip()
        # 只对计算/求解类例题展开（概念理解题的 problem 是"XX指的是什么"，不展开）
        if not problem or not any(k in problem for k in ("计算", "求", "解", "=？", "多少", "比较", "改写", "读出", "近似")):
            continue
        prompt = _with_feedback(MATH_PROTOCOL.replace("{problem}", problem), feedback)
        try:
            raw = client.complete([{"role": "system", "content": prompt},
                                   {"role": "user", "content": f"为「{problem}」写出教学展开。"}],
                                  temperature=0.4, timeout=90, max_tokens=600)
            if raw and len(raw.strip()) > 30:
                steps = [ln.strip() for ln in raw.strip().split("\n") if ln.strip()]
                # 过滤 LLM 复述的「【例题】xxx」标记行（题目本身已在 problem 字段）
                steps = [s for s in steps if not s.startswith("【例题】") and not s.startswith("例题：")][:8]
                seg["slots"]["steps"] = steps
        except Exception:
            pass
    return kb


def expand_chinese(kb, client, feedback=None):
    """语文：对「重点词句」生成品析（意思/手法/好在哪），在练习前插入品析页。"""
    if kb.get("subject_cat") != "chinese":
        return kb
    segs = kb.get("segments") or []
    kps = kb.get("key_points") or []
    text = (kb.get("original_text") or "").strip()

    # 品析对象：key_points 里的「重点词句/重点句」
    target = ""
    for kp in kps:
        if "重点词句" in kp or "重点句" in kp:
            target = (kp.split("：", 1)[1] if "：" in kp else (kp.split(":", 1)[1] if ":" in kp else kp)).strip()
            break
    if not target or len(target) > 60:
        return kb

    prompt = _with_feedback(CHINESE_PROTOCOL.replace("{text}", text[:300]).replace("{target}", target), feedback)
    try:
        raw = client.complete([{"role": "system", "content": prompt},
                               {"role": "user", "content": f"为「{target}」写出品析。"}],
                              temperature=0.4, timeout=90, max_tokens=600)
        if raw and len(raw.strip()) > 30:
            pts = [ln.strip() for ln in raw.strip().split("\n") if ln.strip()][:8]
            # 覆盖旧品析页（重试时替换，而非重复插入）
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
    except Exception:
        pass
    return kb


def expand_english(kb, client, feedback=None):
    """英语：对词汇/句型生成教学展开（呈现/操练/应用），在练习前插入。"""
    if kb.get("subject_cat") != "english":
        return kb
    segs = kb.get("segments") or []

    # 教学对象：优先词卡，否则核心句型
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

    prompt = _with_feedback(ENGLISH_PROTOCOL.replace("{target}", target), feedback)
    try:
        raw = client.complete([{"role": "system", "content": prompt},
                               {"role": "user", "content": f"为「{target}」写教学展开。"}],
                              temperature=0.4, timeout=90, max_tokens=600)
        if raw and len(raw.strip()) > 30:
            pts = [ln.strip() for ln in raw.strip().split("\n") if ln.strip()][:8]
            # 覆盖旧教学页（重试时替换，而非重复插入）
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
    except Exception:
        pass
    return kb
