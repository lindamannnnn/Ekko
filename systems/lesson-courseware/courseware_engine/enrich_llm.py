# -*- coding: utf-8 -*-
"""courseware_engine/enrich_llm.py —— 免费模型层（表达/翻译/品析，弱模型擅长的部分）。

在确定性引擎（auto_kb）产出"知识准确 + 结构完整"的骨架后，本模块用免费模型
（GLM-4-Flash）补齐"表达层"：古诗逐句译文、意境赏析、作者背景。
原则：只做翻译/组织/表达，不做知识创作（知识已由确定性引擎保证）。

用法：orchestrator 在 auto_kb 之后调用 enrich_chinese/enrich_english。
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


def enrich_chinese(kb, client):
    """古诗/词：LLM 生成逐句译文、意境赏析、作者背景（表达层）。

    须在 auto_kb 之前调用——先富化 translation/imagery/author_bg，
    auto_kb 生成 segments 时才能读到这些字段产出译文/赏析页。
    """
    try:
        from courseware_engine.kb_adapter import _derive_lesson_type
        if _derive_lesson_type(kb, "chinese") != "poem":
            return kb
    except Exception:
        return kb

    missing = [k for k in ("translation", "imagery", "author_bg") if not kb.get(k)]
    if not missing:
        return kb

    topic = kb.get("topic", "")
    text = (kb.get("original_text") or "").strip()
    author = kb.get("author") or ""
    if not author:
        try:
            from courseware_engine.kb_adapter import _extract_author
            author = _extract_author(kb)
        except Exception:
            pass
    genre = kb.get("genre", "poem")
    key_phrases = ""
    for kp in (kb.get("key_points") or []):
        if "重点词句" in kp:
            key_phrases = kp.split("：", 1)[1] if "：" in kp else kp
            break

    system = (
        "你是小学语文老师，为古诗课件补充表达层内容。只输出一个 JSON 对象，不要解释。\n"
        '结构：{"translation":[["原文句","译文句"],...],"imagery":{"意象":"...","画面":"...","手法":"...","诗眼":"..."},'
        '"author_bg":"作者简介（朝代、字号、代表作、本诗背景，80字内）"}\n'
        "要求：\n"
        "1. translation 逐句翻译，一句原文对应一句译文，忠实原意，不编造。\n"
        "2. imagery 四要素：意象（诗中关键物象）、画面（一句话描述）、手法（如借景说理/白描/比喻）、诗眼（最传神的字词及理由）。\n"
        "3. author_bg 简洁介绍作者，若有不确定处写'待查'。\n"
        "4. 只做翻译与赏析，不要写教案话术、不要编造原文没有的内容。\n"
    )
    user = (
        f"课题：《{topic}》（{genre}）\n"
        + (f"作者：{author}\n" if author else "")
        + f"原文：\n{text}\n"
        + (f"重点词句：{key_phrases}\n" if key_phrases else "")
        + "\n请只输出 JSON。"
    )

    try:
        raw = client.complete([{"role": "system", "content": system},
                               {"role": "user", "content": user}],
                              temperature=0.4, timeout=90, max_tokens=1500)
        data = _extract_json(raw)
    except Exception:
        return kb

    if "translation" in missing and isinstance(data.get("translation"), list) and data["translation"]:
        kb["translation"] = data["translation"]
    if "imagery" in missing and isinstance(data.get("imagery"), dict) and data["imagery"]:
        kb["imagery"] = data["imagery"]
    if "author_bg" in missing and data.get("author_bg"):
        kb["author_bg"] = data["author_bg"]
    return kb


def enrich_english(kb, client):
    """英语：LLM 生成语法规则讲解（表达层）。词汇/音标已由确定性引擎产出。"""
    return kb
