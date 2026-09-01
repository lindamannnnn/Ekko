# -*- coding: utf-8 -*-
"""courseware_engine/strong_gen.py —— 强模型独立生成链路（教师 AGENT 输出教学语义）。

架构（用户拍板）：
  用户表单 → 教案（k12_generate，已有）
          → 分科教师 AGENT 输出「教学语义」LessonContent（只讲"教什么"，不碰"长什么样"）
          → 程序确定性映射成 segments（layout/slots 技术结构，复用 15 个受控版式）
          → 视觉皮肤（style.py 按学科/学段套 palette/字体/装饰）

关键：教师 AGENT 的输出键名固定（objectives/lead_in/concepts/examples/practice/
summary/board/homework），不暴露渲染层细节，从根上杜绝键名漂移。
数学答案由程序验算（compute_check），错了打回重试。
"""
import json
import re

from .schemas import LessonContent


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


# ===========================================================================
# 三科教师 AGENT 协议（输出 LessonContent 语义，非 segments）
# ===========================================================================
# 通用规则（三科共用，注入每个协议尾部）
_COMMON_RULES = (
    "【通用硬性规则】\n"
    "1. 数学答案必须正确（会程序验算）；语文英语答案要真实可核对。\n"
    "2. 分层三档（basic/standard/advanced）不可同题复制，必须逐档变难。\n"
    "3. 作业（homework）必须是具体题目+具体答案，禁止「完成课本习题」「讲给家长听」「抄写生字」这类元指令。\n"
    "4. 禁止空壳（每页都要有真实内容）；禁止截断（每句写完整）。\n"
    "5. 内容只基于给定教材原料，不编造作者、公式、数据。\n"
    "6. 禁止教案话术（同学们/大家看/想一想）；每页都是可投影的教学内容。\n"
)


MATH_AGENT = (
    "你是教龄 25 年的小学数学特级教师。为一节课设计**教学内容**（只设计教什么，不设计页面排版）。\n\n"
    "【教材原料（事实，只能基于它）】\n"
    "课题：{topic}\n"
    "教材原文：{text}\n"
    "知识点：{key_points}\n"
    "公式/示例：{formulas}\n\n"
    "【你要设计的内容】\n"
    "1. objectives：3-4 条学习目标，绑定本课知识点，禁止套话。\n"
    "2. lead_in：真实生活情境（scenario）+ 一个引导问题（question），禁止照抄教材原文清单。\n"
    "3. concepts：1-2 个核心概念，每个含 statement（概念标题）、points（要点）、可选 pitfall（易错点）。\n"
    "4. examples：2-3 道例题，每道含 problem（题目）、steps（完整解题步骤，笔算必须写竖式过程）、answer（答案）、method（方法）。\n"
    "5. diagrams：1-2 个示意图（用本课真实数字画，帮助理解）。type 只能从下面 5 种选：\n"
    "   - fraction_bars（分数条）：{\"type\":\"fraction_bars\",\"bars\":[{\"num\":1,\"den\":4,\"label\":\"1/4\"}],\"caption\":\"...\"}\n"
    "   - number_line（数轴）：{\"type\":\"number_line\",\"min\":0,\"max\":1,\"min_label\":\"0\",\"max_label\":\"1\",\"marks\":[{\"value\":0.5,\"label\":\"0.5\"}],\"caption\":\"...\"}\n"
    "   - bar_model（条形图）：{\"type\":\"bar_model\",\"total\":12,\"parts\":[{\"value\":4,\"label\":\"4\"}],\"caption\":\"...\"}\n"
    "   - area_grid（方格图）：{\"type\":\"area_grid\",\"rows\":4,\"cols\":6,\"shade\":{\"r\":0,\"c\":0,\"w\":4,\"h\":2},\"title\":\"...\",\"total_label\":\"...\",\"shade_label\":\"...\",\"caption\":\"...\"}\n"
    "   - place_value（数位表）：{\"type\":\"place_value\",\"places\":[\"百\",\"十\",\"个\"],\"digits\":{\"百\":\"3\",\"十\":\"6\",\"个\":\"7\"},\"caption\":\"...\"}\n"
    "   必须用本课例题的真实数字，禁止用通用数字（如分数课不能都画 1/4）。与本课内容无关就不要 diagrams（空数组）。\n"
    "6. practice：分层练习，basic/standard/advanced 三档逐档变难，每题 {q, a}。\n"
    "7. summary：本课小结（points 3-5 条 + formula 公式/口诀）。\n"
    "8. board：板书（center 课题 + branches 2-4 个分支，每分支 label + items）。\n"
    "9. homework：分层作业，basic/standard/advanced 三档，具体题目+具体答案。\n\n"
    + _COMMON_RULES +
    "【输出格式，必须严格照抄，键名和结构一字不差】\n"
    "只输出一个 JSON 对象，键名固定为：title, objectives, lead_in, concepts, examples, diagrams, practice, summary, board, homework。\n"
    "practice 和 homework 结构：{\"basic\":[{\"q\":\"...\",\"a\":\"...\"}], \"standard\":[{\"q\":\"...\",\"a\":\"...\"}], \"advanced\":[{\"q\":\"...\",\"a\":\"...\"}]}。\n"
    "【重要】basic/standard/advanced 的值必须是**数组**（方括号），即使只有一道题也要写成 [{\"q\":...,\"a\":...}]，绝不能写成单个 {\"q\":...,\"a\":...}。\n"
    "summary 结构：{\"points\":[\"要点1\",\"要点2\"], \"formula\":\"公式\"}（键名只能是 points 和 formula）。\n"
    "board 结构：{\"center\":\"课题\", \"branches\":[{\"label\":\"分支名\",\"items\":[\"内容1\",\"内容2\"]}]}（键名只能是 center 和 branches）。\n"
    "examples 结构：[{\"problem\":\"...\",\"steps\":[\"...\",\"...\"],\"answer\":\"...\",\"method\":\"...\"}]。\n"
    "diagrams 结构见上面第 5 条。\n"
)


CHINESE_AGENT = (
    "你是教龄 25 年的小学语文特级教师。为一节课设计**教学内容**（只设计教什么，不设计页面排版）。\n\n"
    "【教材原料（事实，只能基于它）】\n"
    "课题：{topic}\n"
    "教材原文：{text}\n"
    "知识点：{key_points}\n\n"
    "【你要设计的内容】\n"
    "1. objectives：3-4 条学习目标，绑定本课，禁止套话。\n"
    "2. lead_in：真实情境（scenario）+ 引导问题（question）。\n"
    "3. concepts：按顺序放「作者/背景」（有作者才放）、「阅读提示」（本课重点）、「段落理解」（逐段首句 + 学习提示）、「重点句品析」。\n"
    "   **重点句品析这个 concept 必须含三段：意思（在文中什么意思）、手法（本句真正用的写法，判断准确）、好在哪（表达效果+换字对比），缺一不可**。\n"
    "4. practice：分层练习三档有梯度，每题 {q, a}。\n"
    "5. summary：本课小结（主旨 + 写法 + 重点词句）。\n"
    "6. board：板书（center + branches）。\n"
    "7. homework：分层作业三档，具体题目+具体答案。\n\n"
    + _COMMON_RULES +
    "【输出格式】只输出一个 JSON 对象，键名固定为：title, objectives, lead_in, concepts, practice, summary, board, homework。\n"
    "concepts 是数组，每个元素 {\"statement\":\"...\",\"points\":[\"...\",\"...\"]}。\n"
    "【环节完整性 · 最高优先级】以上 8 个键一个都不能少、一个都不能为空：\n"
    "practice 必须含 basic/standard/advanced 三档各有至少 1 题；summary.points 至少 3 条；\n"
    "board 必须有 center 和至少 2 个 branches；homework 必须含三档各有至少 1 题。\n"
    "**宁可每个环节内容少一点，也绝不允许整个环节缺失或为空对象/空数组**——缺任何一个环节这份课件就是废品。\n"
)


ENGLISH_AGENT = (
    "你是教龄 25 年的小学英语特级教师（人教 PEP）。为一节课设计**教学内容**（只设计教什么，不设计页面排版）。\n\n"
    "【教材原料（事实，只能基于它）】\n"
    "课题：{topic}\n"
    "教材原文：{text}\n"
    "知识点：{key_points}\n\n"
    "【你要设计的内容】\n"
    "1. objectives：3-4 条学习目标，绑定本课句型/词汇。\n"
    "2. lead_in：真实对话情境（scenario）+ 引导问题（question）。\n"
    "3. concepts：按顺序放「核心句型」（本课重点句型）和「词汇·句型教学」。\n"
    "   **词汇·句型教学这个 concept 必须含三段：呈现（词义+真实语境例句）、操练（可当场做的替换/问答）、应用（真实情境交流），缺一不可**。\n"
    "4. practice：分层练习三档有梯度，每题 {q, a}。\n"
    "5. summary：本课小结（句型 + 词汇 + 表达）。\n"
    "6. board：板书（center + Words/Patterns 分支）。\n"
    "7. homework：分层作业三档，具体题目+具体答案。\n\n"
    + _COMMON_RULES +
    "【输出格式】只输出一个 JSON 对象，键名固定为：title, objectives, lead_in, concepts, practice, summary, board, homework。\n"
    "concepts 是数组，每个元素 {\"statement\":\"...\",\"points\":[\"...\",\"...\"]}。\n"
    "【环节完整性 · 最高优先级】以上 8 个键一个都不能少、一个都不能为空：\n"
    "practice 必须含 basic/standard/advanced 三档各有至少 1 题；summary.points 至少 3 条；\n"
    "board 必须有 center 和至少 2 个 branches；homework 必须含三档各有至少 1 题。\n"
    "**宁可每个环节内容少一点，也绝不允许整个环节缺失或为空对象/空数组**——缺任何一个环节这份课件就是废品。\n"
)


def _agent_prompt(cat, kb):
    topic = kb.get("topic", "")
    text = (kb.get("original_text") or "").strip()
    kps = "；".join(kb.get("key_points") or [])
    formulas = "；".join(kb.get("formulas") or [])
    if cat == "math":
        p = MATH_AGENT
        return (p.replace("{topic}", topic).replace("{text}", text[:1000])
                 .replace("{key_points}", kps).replace("{formulas}", formulas))
    if cat == "chinese":
        p = CHINESE_AGENT
        return (p.replace("{topic}", topic).replace("{text}", text[:1000])
                 .replace("{key_points}", kps))
    if cat == "english":
        p = ENGLISH_AGENT
        return (p.replace("{topic}", topic).replace("{text}", text[:1000])
                 .replace("{key_points}", kps))
    return ""


def generate_content(kb, client, max_attempts=2):
    """教师 AGENT 一次调用生成 LessonContent。失败重试（含退避）。返回 LessonContent 或 None。"""
    cat = kb.get("subject_cat") or ""
    prompt = _agent_prompt(cat, kb)
    if not prompt:
        return None
    user = (
        "请为《%s》设计教学内容。\n"
        "只输出一个 JSON 对象（键名见上），不要任何解释文字、不要 markdown 代码块。"
    ) % kb.get("topic", "")
    for attempt in range(max_attempts):
        try:
            raw = client.complete(
                [{"role": "system", "content": prompt},
                 {"role": "user", "content": user}],
                temperature=0.3, timeout=300, max_tokens=16000, retries=4)
            data = _extract_json(raw)
            if isinstance(data, dict) and data.get("objectives"):
                return LessonContent.from_dict(data)
            # 解析成功但缺 objectives（结构漂移），记录后重试
            print(f"  [强模型] 第{attempt+1}次：JSON 解析失败或缺 objectives（raw_len={len(raw)}）", flush=True)
        except Exception as e:
            print(f"  [强模型] 第{attempt+1}次异常：{e}", flush=True)
        # 失败退避：推理模型偶发输出漂移/超时/限流，退避后重试更易恢复
        if attempt < max_attempts - 1:
            import time
            time.sleep(min(3 * (attempt + 1), 10))
    return None


# ===========================================================================
# 语义 → segments 映射（纯确定性，复用 15 个受控版式）
# ===========================================================================
def _qa(tier):
    """把 [{q,a}] 转成 tiers 版式的槽位（含 title 校验）。"""
    return [{"q": it.get("q", ""), "a": it.get("a", "")} for it in tier if it.get("q")]


def content_to_segments(lc, kb):
    """LessonContent → segments（list[dict]，layout/kind/slots 技术结构）。

    这是程序确定性映射，教师 AGENT 完全不碰。视觉皮肤由 style.py 决定，
    这里只决定「语义块 → 版式」的对应关系。
    """
    segs = []
    grade = kb.get("grade", "")
    subj = kb.get("subject", "")
    topic = lc.title or kb.get("topic", "")

    # 封面
    segs.append({"layout": "cover", "kind": "cover",
                 "slots": {"title": topic, "subtitle": f"{grade} · {subj}", "meta": ""}})

    # 学习目标
    if lc.objectives:
        segs.append({"layout": "objectives", "kind": "objectives",
                     "slots": {"items": lc.objectives[:4]}})

    # 情境导入
    if lc.lead_in.get("scenario") or lc.lead_in.get("question"):
        segs.append({"layout": "lead_in", "kind": "lead_in",
                     "slots": {"scenario": lc.lead_in.get("scenario", ""),
                               "question": lc.lead_in.get("question", "")}})

    # 概念页（作者/背景、阅读提示、段落理解、重点句品析、核心句型、词汇教学）
    for c in lc.concepts:
        if not c.get("statement"):
            continue
        slots = {"statement": c["statement"], "points": c.get("points") or []}
        if c.get("analogy"):
            slots["analogy"] = c["analogy"]
        if c.get("pitfall"):
            slots["pitfall"] = c["pitfall"]
        segs.append({"layout": "concept", "kind": "concept", "slots": slots})

    # 例题
    for e in lc.examples:
        if not e.get("problem"):
            continue
        segs.append({"layout": "steps", "kind": "example",
                     "slots": {"problem": e["problem"], "steps": e.get("steps") or [],
                               "answer": e.get("answer", ""), "method": e.get("method", "")}})

    # 示意图（数学，强模型用本课真实数字描述，程序画 SVG）
    if lc.diagrams:
        segs.append({"layout": "diagram", "kind": "concept",
                     "slots": {"figure": lc.diagrams}})  # diagram 版式的 figure 槽位吃 [{type, caption, ...}]

    # 分层练习
    practice = lc.practice or {}
    p_basic = _qa(practice.get("basic") or [])
    if p_basic:
        segs.append({"layout": "tiers", "kind": "practice",
                     "slots": {"title": "分层练习", "basic": p_basic,
                               "standard": _qa(practice.get("standard") or []),
                               "advanced": _qa(practice.get("advanced") or [])}})

    # 小结
    if lc.summary.get("points"):
        slots = {"points": lc.summary["points"][:5]}
        if lc.summary.get("formula"):
            slots["formula"] = lc.summary["formula"]
        segs.append({"layout": "summary", "kind": "summary", "slots": slots})

    # 板书（规范化 branches 满足 board 版式 schema：center 必填 str、
    # branches 至少 1 个 {label:str, items:list[str]}，否则 check_slots 丢页 → 产物缺板书）
    _bc = (lc.board.get("center") or "").strip() or topic
    _branches = []
    for b in (lc.board.get("branches") or []):
        if isinstance(b, dict):
            label = str(b.get("label") or "").strip()
            items = [str(x) for x in (b.get("items") or []) if isinstance(x, str) and x.strip()]
            if label or items:
                _branches.append({"label": label or "要点", "items": items or [label]})
        elif isinstance(b, str) and b.strip():  # 容错：模型把 branch 写成纯字符串
            _branches.append({"label": b.strip()[:16], "items": [b.strip()[:40]]})
    if not _branches:
        # 兜底：模型没给合法 branches，用知识点/小结造 2 个分支，绝不让板书页因格式被丢
        _src = (lc.summary.get("points") or [])[:2] or [c.get("statement","") for c in lc.concepts[:2] if c.get("statement")]
        _branches = [{"label": (s[:16] or "要点"), "items": [s[:40]]} for s in _src if s] or [{"label": "要点", "items": [topic]}]
    segs.append({"layout": "board", "kind": "board",
                 "slots": {"center": _bc[:24], "branches": _branches[:5]}})

    # 分层作业
    homework = lc.homework or {}
    h_basic = _qa(homework.get("basic") or [])
    if h_basic:
        segs.append({"layout": "tiers", "kind": "homework",
                     "slots": {"title": "分层作业", "basic": h_basic,
                               "standard": _qa(homework.get("standard") or []),
                               "advanced": _qa(homework.get("advanced") or [])}})

    return segs
