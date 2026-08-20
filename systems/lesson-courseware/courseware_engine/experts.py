# -*- coding: utf-8 -*-
"""courseware_engine/experts.py —— 三个学科的教育专家 agent（针对性判断标准）。

用户架构：每科一个教育专家，各自有「针对性的判断标准」。本模块定义：
  - guide：生成指导（教弱模型"这科的好内容该怎么生成"，比通用三段式更针对）
  - check：审核规则（确定性校验，审核层据此判断生成结果是否符合该科标准）

三个专家的 check 是从三轮教师 agent 审核报告中提炼的、可程序化判断的硬标准。
"""


class SubjectExpert:
    def __init__(self, cat, label, guide, check, review_prompt):
        self.cat = cat
        self.label = label
        self.guide = guide
        self.check = check
        self.review_prompt = review_prompt


# ===========================================================================
# 通用确定性门禁（三科共用）：答案复述、文本截断、模板套话
# ===========================================================================
import re as _re

_STRIP = "，。！？、；：\"\"''（）()【】[]·…"


def _norm(s):
    return _re.sub(r"[\s" + _STRIP + "]", "", s or "")


def _answer_duplicates_question(seg):
    """练习答案是否复述题目（答案含题目大部分原文 → 空转，未真正作答）。"""
    for tier in ("basic", "standard", "advanced"):
        for qa in (seg.get("slots") or {}).get(tier, []) or []:
            if not isinstance(qa, dict):
                continue
            q = _norm(qa.get("q", ""))
            a = _norm(qa.get("a", ""))
            if q and a and len(q) >= 8 and q in a and len(a) <= len(q) + 30:
                return f"答案复述题目（空转）：{qa.get('q','')[:30]}"
    return None


def _truncated(text):
    """文本是否被截断：中文以虚词结尾（句子没说完）。英文截断交给 LLM 审核（程序易误报）。"""
    t = (text or "").strip()
    if not t:
        return False
    # 完整的口诀/固定短语虽以「一/之/而」结尾，但不是截断（如"满十进一""不够退一"）
    if t.endswith(("进一", "退一", "借一", "添一", "得一")):
        return False
    # 完整的口语词/翻译（"是的""好的""对了"等）虽以「的/了」结尾，但不是截断
    if t.endswith(("是的", "好的", "对了", "不是", "就是", "完了", "好了", "真的", "对的")):
        return False
    # 中文：只保留最明确的截断虚词（的/了/在/是/和/与/把/被/从/对/个），
    # 去掉"一/些/就/都/还/更/很/而/之"等易误报的（口诀"进一"、文言"之/而"结尾多为完整）
    return t[-1] in "的了在是和与把被从对个"


# 教学页模板套话黑名单：LLM 生成的教学展开若落在这些「每课都能说」的空话上，
# 说明弱模型没绑本课内容、在背教案模板（审核层据此打回/标记）。
_TEMPLATE_BLACKLIST = ("同学们", "大家看", "大家想一想", "想一想", "布置作业",
                       "认读字母", "跟读", "齐读", "今天我们来", "这节课我们",
                       "我们一起来")


def _template_phrases(text):
    """返回文本中命中的模板套话列表（教学页专用，不查作业/练习）。"""
    hits = []
    for ph in _TEMPLATE_BLACKLIST:
        if ph in (text or ""):
            hits.append(ph)
    return hits


def _seg_text(segs):
    """汇总所有 segments 的可见文本（用于核心句型/课题覆盖等跨页检测）。"""
    parts = []
    for s in segs:
        slots = s.get("slots") or {}
        for f in ("statement", "problem", "answer", "method", "scenario", "question", "center", "caption"):
            v = slots.get(f)
            if isinstance(v, str):
                parts.append(v)
        for f in ("points", "steps", "items", "lines", "words"):
            v = slots.get(f)
            if isinstance(v, list):
                parts.extend(str(x) if not isinstance(x, dict) else (x.get("word", "") + " " + x.get("meaning", "")) for x in v)
            elif isinstance(v, str):
                parts.append(v)
        for tier in ("basic", "standard", "advanced"):
            for qa in slots.get(tier, []) or []:
                if isinstance(qa, dict):
                    parts.append(str(qa.get("q", "")))
    return " ".join(parts)


def _common_check(kb, segs):
    """通用门禁：答案复述 + 文本截断 + 教学页模板套话，三科共用。返回问题列表。"""
    issues = []
    for i, seg in enumerate(segs, 1):
        slots = seg.get("slots") or {}
        # 练习答案复述
        if seg.get("kind") == "practice" or seg.get("kind") == "homework":
            d = _answer_duplicates_question(seg)
            if d:
                issues.append(f"[第{i}页] {d}")
        # 文本截断：points/steps 每行
        for field in ("points", "steps"):
            for t in slots.get(field, []) or []:
                if isinstance(t, str) and _truncated(t):
                    issues.append(f"[第{i}页] 文本疑似截断：{t[:40]}")
        # 教学页模板套话（只查 steps/品析/词汇教学等展开页，不查作业/练习）
        if seg.get("layout") == "steps" or seg.get("kind") == "concept":
            body = " ".join(str(x) for x in (slots.get("points") or slots.get("steps") or []))
            hits = _template_phrases(body)
            if hits:
                issues.append(f"[第{i}页] 模板套话未绑本课：{'、'.join(hits)}")
    return issues


# ===========================================================================
# 数学教育专家
# ===========================================================================
MATH_GUIDE = (
    "你是教龄 25 年的小学数学特级教师。为例题写教学展开，直接可投影给学生。\n\n"
    "【必须三段】\n"
    "1. 算理（为什么）：这一步背后的数学道理。**禁止用公式本身当算理**——\n"
    "   面积课的算理是「数格子」（一行几个 × 几行 = 总个数），不是「面积=长×宽」；\n"
    "   方程课的算理是「等式性质」，不是「移项」；进率课的算理是「10×10=100」。\n"
    "2. 过程（怎么做）：分步写，每步一个动作 + 依据。\n"
    "3. 易错（哪里会错）：学生最可能错的一处 + 提醒。\n\n"
    "【禁止】公式→代入→答案三词；教案话术；布置作业。\n"
)

MATH_REVIEW = (
    "你是小学数学教研员，审核一份课件的**教学法**是否合格（不做数学计算，计算另有程序校验）。\n"
    "审核维度：\n"
    "1. 算理：例题的「算理」是不是用公式复述当理由（循环论证，如用「面积=长×宽」当面积的算理）？\n"
    "2. 例题-课题：例题是否覆盖本课核心知识？有没有例题与课题错位（如「用字母表示数」课只出解方程题）？\n"
    "3. 分层：基础/提高/拓展三档是否同题复制、没有梯度？\n"
    "4. 模板套话：学习目标/情境导入/作业是否三课通用模板（没绑本课内容）？\n"
    "输出规则：\n"
    "- 只报你**在课件正文里实际看到**的问题，每条必须引用课件里的原句（用引号括起）。\n"
    "- 没有发现问题时，只输出两个字「通过」，不要输出任何其它文字。\n"
    "- 禁止把上面 4 条审核维度复述一遍当问题（那是清单，不是发现）。\n"
    "输出：每处问题一行「[页] 问题（引用原句）」；没问题输出「通过」。\n"
)


def math_check(kb, segs):
    """数学审核规则：例题覆盖课题、分层去重、算理非公式复述。"""
    issues = _common_check(kb, segs)
    topic = kb.get("topic", "")
    # 1) 例题存在且非概念题（problem 是计算/求解，不是"XX指的是什么"）
    steps_segs = [s for s in segs if s.get("layout") == "steps"]
    calc_examples = [s for s in steps_segs
                     if any(k in (s.get("slots") or {}).get("problem", "") for k in ("计算", "求", "解", "=？", "多少", "比较", "改写", "读出", "近似", "用字母", "简写", "表示"))]
    if not calc_examples:
        # 只对「计算类」课题要求必有例题；概念课（运动现象/认识图形/分类/位置/观察）本无算术例题
        if _expects_calculation(topic, kb):
            issues.append("无计算类例题：本课没有真实例题，学生无从学起")
    # 2) 例题覆盖课题：本课核心知识应在例题题干中出现（否则例题与课题错位/漏核心）
    if calc_examples:
        probs = " ".join((s.get("slots") or {}).get("problem", "") for s in calc_examples)
        anchor = _topic_anchor(topic)
        if anchor and not any(a in probs for a in anchor[1]):
            issues.append(f"例题未覆盖课题核心「{anchor[0]}」：{probs[:40]}")
    # 3) 分层练习去重：三档题目不得同题
    for s in segs:
        if s.get("kind") != "practice":
            continue
        tiers = (s.get("slots") or {}).get("basic", []), (s.get("slots") or {}).get("standard", []), (s.get("slots") or {}).get("advanced", [])
        qs = [t.get("q", "") for tier in tiers for t in tier]
        if len(qs) != len(set(qs)):
            issues.append("分层练习存在同题复制：基础/提高/拓展三档题目重复")
    # 4) 算理非公式复述（"算理：面积=长×宽"这种用公式当算理）
    for s in calc_examples:
        steps = (s.get("slots") or {}).get("steps", [])
        for st in steps:
            if st.startswith("算理") or st.startswith("1. 算理") or st.startswith("1.算理"):
                if "=" in st and ("×" in st or "*" in st or "÷" in st):
                    issues.append(f"算理疑似公式复述（用结论当理由）：{st[:40]}")
    return issues


def _expects_calculation(topic, kb):
    """本课是否应含算术例题：计算类课题=是；概念/几何认识/运动/分类类=否。

    依据 formulas 里是否出现数字算式（+ - × ÷ = 数字）判定，比主题词更可靠。
    """
    for fm in (kb.get("formulas") or []):
        if _re.search(r"\d\s*[+\-−×xX*÷]\s*\d|\d+\s*[=＝]", fm or ""):
            return True
    # 课题词兜底：明显计算类课题
    for kw in ("计算", "加减", "乘除", "方程", "除法", "乘法", "加法", "减法", "运算",
               "分数", "小数", "百分数", "面积", "周长", "体积", "平均数", "比例", "解"):
        if kw in (topic or ""):
            return True
    return False


def _topic_anchor(topic):
    """从课题抽「核心词 → 例题题干必须出现的关键词（至少一个）」。

    只对确定性可判的课题词做校验；无匹配返回 None（放行，不误报）。
    """
    _TOPIC_ANCHOR = {
        "用字母表示": ("用字母表示", ("字母", "表示", "a×b", "ab", "a+b", "含字母")),
        "简易方程": ("简易方程", ("方程", "x", "未知数", "解")),
        "解方程": ("解方程", ("方程", "x", "未知数")),
        "百分数": ("百分数", ("%", "百分之", "折", "成数", "税率", "利率", "折扣", "优惠")),
        "小数": ("小数", (".", "小数点", "十分位")),
        "面积": ("面积", ("面积", "平方")),
        "周长": ("周长", ("周长", "周")),
        "体积": ("体积", ("体积", "立方")),
        "平均数": ("平均数", ("平均", "÷", "总数")),
        "集合": ("集合", ("集合", "圈", "交集")),
    }
    for kw, anchor in _TOPIC_ANCHOR.items():
        if kw in (topic or ""):
            return anchor
    return None


# ===========================================================================
# 语文教育专家
# ===========================================================================
CHINESE_GUIDE = (
    "你是教龄 25 年的小学语文特级教师。为课文的关键句写品析，直接可投影给学生。\n\n"
    "【必须三段】\n"
    "1. 意思：这个字/词/句在文中是什么意思。\n"
    "2. 手法：只写本句真正用的写法，**判断要准确**（'耷拉'是状态描写不是拟人，'借景说理'≠'借景抒情'）。\n"
    "3. 好在哪：表达效果 + 换成别的字/词行不行。\n\n"
    "【禁止】只贴原文；罗列一堆手法名字；用词义解释冒充句子品析（品的是句子，不是孤立的词义）。\n"
)

CHINESE_REVIEW = (
    "你是小学语文教研员，审核一份课件是否能直接上课。逐页看，只报硬问题。\n"
    "审核维度：\n"
    "1. 品析：品析的是不是真正的重点句（不是词义解释冒充）？手法判断对不对（拟人/比喻/借景说理别判错）？有没有空白品析？\n"
    "2. 古诗五件套：作者背景/逐句译文/意境赏析/生字词/朗读节奏齐不齐？\n"
    "3. 生字词：有没有音形义组词？还是残缺/选字错误？\n"
    "4. 练习答案：答案是否真的回答问题（情感题给情感、词义题给词义）？还是复述题目/串句/答非所问？\n"
    "5. 知识性错误：作者署名、译文、赏析、写法有没有错？\n"
    "输出规则：\n"
    "- 只报你**在课件正文里实际看到**的问题，每条必须引用课件里的原句（用引号括起）。\n"
    "- 没有发现问题时，只输出两个字「通过」，不要输出任何其它文字。\n"
    "- 禁止把上面 5 条审核维度复述一遍当问题（那是清单，不是发现）。\n"
    "输出：每处问题一行「[页] 问题（引用原句）」；没问题输出「通过」。\n"
)


def chinese_check(kb, segs):
    """语文审核规则：古诗五件套、品析对象是真句、无英文串扰。"""
    issues = _common_check(kb, segs)
    statements = " ".join((s.get("slots") or {}).get("statement", "") for s in segs)
    # 1) 古诗五件套
    if kb.get("lesson_type") == "poem":
        for need in ("诗意译文", "意境赏析", "朗读指导"):
            if need not in statements:
                issues.append(f"古诗缺「{need}」页")
    # 2) 无英文串扰（英语教学页不该出现在语文课）
    if "词汇 · 句型教学" in statements or "词汇 · 句型教学" in " ".join((s.get("slots") or {}).get("statement", "") for s in segs):
        issues.append("语文课混入「词汇·句型教学」英文页")
    # 3) 品析对象是"真重点句"而非词义堆砌（品析页 points 里若全是"词（释）"式，则判不合格）
    for s in segs:
        if (s.get("slots") or {}).get("statement") == "重点句 · 品析":
            pts = (s.get("slots") or {}).get("points", [])
            joined = " ".join(pts)
            # 品析正文若含「意思：」且对象是词义列表（如"西林（西林寺）、岭、峰"）则提示
            if "、" in joined and "意思" in joined and "手法" not in joined:
                issues.append("品析页疑似用词义解释冒充句子品析（缺手法/好在哪）")
            # 三要素齐全：意思 + 手法 + 好在哪（表达效果），缺任一即不合格
            missing = []
            if "意思" not in joined:
                missing.append("意思")
            if "手法" not in joined:
                missing.append("手法")
            if not any(k in joined for k in ("好在", "效果", "表达", "换成", "换作")):
                missing.append("好在哪")
            if missing:
                issues.append(f"品析页缺三要素：{'、'.join(missing)}")
    return issues


# ===========================================================================
# 英语教育专家
# ===========================================================================
ENGLISH_GUIDE = (
    "你是教龄 25 年的小学英语特级教师（人教 PEP）。为词汇/句型写教学展开，直接可投影。\n\n"
    "【必须三段，缺一不可】\n"
    "1. 呈现：词义 + 一句真实语境例句。**不要写音标**（音标已在词卡页，本页重复写音标会造成跨页不一致）。\n"
    "2. 操练：一个可当场做的替换/问答操练（给具体替换词或问句）。\n"
    "3. 应用：一个真实情境，让学生用这个词汇/句型交流。\n\n"
    "【禁止】只列词表；只写'呈现'一段；写音标；'跟读''抄写'套话；布置作业。\n"
)

ENGLISH_REVIEW = (
    "你是小学英语教研员（人教 PEP），审核一份课件是否能直接上课。逐页看，只报硬问题。\n"
    "审核维度：\n"
    "1. 音标：英式音标对不对？同一词跨页音标是否一致？\n"
    "2. 核心句型：单元标题句（如 What's he like?）有没有出现在句型页/对话/练习？\n"
    "3. 教学展开：词汇教学有没有「呈现/操练/应用」三环节？还是只有词表罗列？\n"
    "4. 练习答案：'显示答案'给的是英文参考答案，还是中文指令/套话？\n"
    "5. 文本截断/目标套话：有没有半词截断、'认读字母'类模板残留？\n"
    "输出规则：\n"
    "- 只报你**在课件正文里实际看到**的问题，每条必须引用课件里的原句（用引号括起）。\n"
    "- 没有发现问题时，只输出两个字「通过」，不要输出任何其它文字。\n"
    "- 禁止把上面 5 条审核维度复述一遍当问题（那是清单，不是发现）。\n"
    "输出：每处问题一行「[页] 问题（引用原句）」；没问题输出「通过」。\n"
)


def english_check(kb, segs):
    """英语审核规则：教学展开三环节齐全、核心句型出现、音标跨页一致。"""
    issues = _common_check(kb, segs)
    # 1) 词汇教学页三环节齐全
    for s in segs:
        if (s.get("slots") or {}).get("statement") == "词汇 · 句型教学":
            pts = " ".join((s.get("slots") or {}).get("points", []))
            for need in ("呈现", "操练", "应用"):
                if need not in pts:
                    issues.append(f"词汇教学页缺「{need}」环节")
    # 2) 核心句型出现：单元标题句（如 What's he like?）必须出现在课件正文
    title_sent = _english_title_sentence(kb)
    if title_sent:
        all_text = _seg_text(segs)
        if title_sent.lower() not in all_text.lower():
            issues.append(f"核心句型未出现：单元标题句「{title_sent}」")
    return issues


def _english_title_sentence(kb):
    """提取英语单元标题句：topic「Unit 1 What's he like」→「What's he like」。

    只对「Unit N + 英文句」类课题提取；语法/功能课题（无 Unit 前缀）返回空，不误报。
    """
    topic = (kb.get("topic") or "").strip()
    m = _re.search(r"Unit\s*\d+\s*([A-Za-z][A-Za-z'?!. ]*)$", topic)
    if m:
        s = m.group(1).strip().strip("?!. ")
        return s if s and " " in s else ""
    return ""


EXPERTS = {
    "math": SubjectExpert("math", "数学", MATH_GUIDE, math_check, MATH_REVIEW),
    "chinese": SubjectExpert("chinese", "语文", CHINESE_GUIDE, chinese_check, CHINESE_REVIEW),
    "english": SubjectExpert("english", "英语", ENGLISH_GUIDE, english_check, ENGLISH_REVIEW),
}


def get_expert(cat):
    return EXPERTS.get(cat)
