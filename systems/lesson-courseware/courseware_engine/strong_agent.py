# -*- coding: utf-8 -*-
"""courseware_engine/strong_agent.py —— 强模型链路的 agent 化改造（生产版）。

相对 strong_gen.generate_content()（一次 complete 大 prompt）的升级：
  原：KB 原文塞进 prompt → 一次 complete → LessonContent（模型闭门造车，易张冠李戴）
  本：发送 tools → 模型**自主决策**检索教材(retrieve_kb)/查课标(query_syllabus)/
      核对事实(check_fact) → 工具结果回灌 → 产出 LessonContent（grounded 真实事实）

成本不翻倍：工具轮次模型只发函数名+参数（极短输出），只有最后一步才吐完整课件 JSON，
≈ 一次完整生成的成本。render/validate 段完全不动（确定性）。

对外接口（与 strong_gen.generate_content 对齐）：
  - generate_content_agent(kb, client, ...) → LessonContent | None
  - generate_recipe_agent(dna, kb, client, ...) → StyleRecipe（可选；失败/缺 tool-calling 走确定性兜底）
"""
import os
import re
import json

from .strong_gen import (
    MATH_AGENT, CHINESE_AGENT, ENGLISH_AGENT, _extract_json, generate_content,
)
from .schemas import LessonContent, StyleRecipe, DesignDNA
from .style import seeded_recipe
from . import kb as _kb_mod


def _extract_json_lenient(text):
    """比 strong_gen._extract_json 更宽容的 JSON 提取：多起点重试 + 截断修复。

    针对 deepseek 等模型在 tool-calling 模式下反复在同一处截断输出（notepad 现象）：
      1) 先试整体 / 去 markdown 围栏后的整体；
      2) 失败则尝试多个 `{` 起点（可能前面夹带说明文字）；
      3) 仍失败则尝试「截断修复」——把尾部不完整的字符串/数组/对象补全后再解析。
    """
    if not text:
        return {}
    t = text.strip()
    # 去 markdown 围栏（宽容版：头尾的 ``` / ```json 都剥掉，模型常顺手在 JSON 末尾补围栏）
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```+\s*$", "", t)
    t = t.rstrip("`").rstrip()  # 兜底：尾部残留的孤立反引号
    try:
        return json.loads(t)
    except Exception:
        pass
    # 多起点：从每个 '{' 尝试，终点用「去围栏后」的最后一个 '}'
    for m in re.finditer(r"\{", t):
        s = m.start()
        e = t.rfind("}")
        if e > s:
            try:
                return json.loads(t[s:e + 1])
            except Exception:
                pass
    # 截断修复：补全未闭合的字符串/数组/对象
    fixed = _fix_truncated_json(t)
    if fixed:
        try:
            return json.loads(fixed)
        except Exception:
            pass
    return {}


def _fix_truncated_json(t):
    """修复被截断的 JSON：闭合未完成的字符串、补齐未闭合的 ] 和 }。

    策略：找到最后一个「完整元素边界」（最后一个合法逗号或开括号），
    截到那里，再按括号栈补 ]/}。仅作为兜底，可能丢最后一个元素，但能保住整体结构。
    注意：若整串本来就完整可解析，调用方应先直接 json.loads，本函数只在截断时兜底。
    """
    s = t.find("{")
    if s < 0:
        return ""
    sub = t[s:]
    # 先确认确实截断（直接能解析就原样返回，避免误伤完整 JSON）
    try:
        json.loads(sub)
        return sub
    except Exception:
        pass
    # 逐字符扫描，维护括号栈与字符串状态
    stack = []
    in_str = False
    esc = False
    last_good = s  # 最后一个「可安全截断」的位置（完整元素结束处）
    for i, ch in enumerate(sub):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                last_good = i  # 完整字符串结束
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            if stack:
                stack.pop()
            last_good = i
        elif ch == ",":
            last_good = i
    # 截到最后一个完整边界，再补闭合
    core = sub[:last_good + 1].rstrip().rstrip(",")
    # 重新扫描 core 得到真实未闭合栈
    stack = []
    in_str = False
    esc = False
    for ch in core:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            if stack:
                stack.pop()
    # 补闭合（倒序）
    closers = {"[": "]", "{": "}"}
    tail = "".join(closers[c] for c in reversed(stack))
    return core + tail


# ===========================================================================
# 课标（2022 义务教育）核心素养——防超纲（query_syllabus 工具返回）
# ===========================================================================
_SYLLABUS = {
    "math": (
        "数学核心素养：会用数学的眼光观察现实世界（数感、量感、符号意识、几何直观、"
        "空间观念、创新意识），会用数学的思维思考现实世界（运算能力、推理意识/能力、"
        "模型意识/数据意识），会用数学的语言表达现实世界。小学三四五六年级以具体运算、"
        "直观几何为主，不要求严格形式化证明。"
    ),
    "chinese": (
        "语文核心素养：文化自信、语言运用、思维能力、审美创造。阅读重在整体感知、"
        "提取信息、形成解释、做出评价；习作重观察、想象、表达。小学以识字写字、阅读、"
        "口语交际、习作/写话为主，不超纲引入语法术语。"
    ),
    "english": (
        "英语核心素养：语言能力、文化意识、思维品质、学习能力。小学以听说为主、"
        "读写跟上，重语境、语用与兴趣；句型操练以替换、问答、真实情境交流为主，"
        "不超前讲复杂语法规则。"
    ),
}


def _syllabus(subject):
    s = (subject or "").strip()
    if "数" in s:
        return _SYLLABUS["math"]
    if "语" in s:
        return _SYLLABUS["chinese"]
    if "英" in s:
        return _SYLLABUS["english"]
    return "通用：依据 2022 义务教育课程标准，聚焦本学段核心素养，不超纲。"


# ===========================================================================
# 工具 schema（OpenAI function-calling）
# ===========================================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_kb",
            "description": (
                "检索教材知识库，获取指定学科/年级/课题的原文、知识点、公式与易混警示。"
                "生成任何教学内容前必须先调用，严禁凭记忆编造作者、公式、数据或串台到其他篇目。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "grade": {"type": "string"},
                    "topic": {"type": "string"},
                    "subject_cat": {"type": "string"},
                },
                "required": ["subject", "grade", "topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_syllabus",
            "description": "查询 2022 义务教育课程标准的学科核心素养与教学提示，用于校准内容不超纲。",
            "parameters": {
                "type": "object",
                "properties": {"subject": {"type": "string"}},
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_fact",
            "description": (
                "核对一条事实陈述（作者/人物/公式/数字）是否与已检索的教材原文一致。"
                "返回 consistent（一致）或 conflict（原文未出现该事实，可能编造）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {"claim": {"type": "string"}},
                "required": ["claim"],
            },
        },
    },
]


# 保存最近一次检索到的 KB 原文，供 check_fact 核对
_LAST_KB_TEXT = ""


def _tool_retrieve_kb(args):
    global _LAST_KB_TEXT
    form = {
        "subject": args.get("subject", ""),
        "grade": args.get("grade", ""),
        "topic": args.get("topic", ""),
        "subject_cat": args.get("subject_cat", ""),
    }
    entry = _kb_mod.retrieve_kb(form)
    if not entry:
        return {"ok": False,
                "grounding": f"（未命中 KB：{form.get('subject')}/{form.get('grade')}/{form.get('topic')}，请检查课题）"}
    _LAST_KB_TEXT = entry.get("original_text") or ""
    return {
        "ok": True,
        "topic": entry.get("topic", ""),
        "source": entry.get("source", ""),
        "grounding": _kb_mod.kb_block(entry),
    }


def _tool_query_syllabus(args):
    return {"subject": args.get("subject", ""), "syllabus": _syllabus(args.get("subject", ""))}


def _tool_check_fact(args):
    """事实核对：聚焦『作者/人物张冠李戴』（用户真实硬伤：语文作者错写鲁迅）。

    设计原则：宁可漏报也不误报——只对『明确断言了某作者/人物』且『该人未出现在
    教材原文』判 conflict；公式/数字/通用表述宽松处理（以 retrieve_kb 原文为准）。
    """
    claim = (args.get("claim") or "").strip()
    if not claim:
        return {"status": "skip", "reason": "空陈述"}
    if not _LAST_KB_TEXT:
        return {"status": "unknown", "reason": "尚未检索 KB，请先调用 retrieve_kb"}
    name_patterns = [
        r"作者[是为:：]?\s*([一-龿]{2,4})",
        r"《[^》]{1,20}》[的]?作者[是为]?\s*([一-龿]{2,4})",
        r"([一-龿]{2,3})[（(][^）)]{1,6}[）)][的]?人",
        r"([一-龿]{2,3})[先生|居士|诗人|作家]",
    ]
    asserted = []
    for pat in name_patterns:
        for m in re.finditer(pat, claim):
            nm = m.group(1)
            if nm and len(nm) >= 2:
                asserted.append(nm)
    if asserted:
        conflicts = [a for a in asserted if a not in _LAST_KB_TEXT]
        if conflicts:
            return {"status": "conflict", "missing_authors": conflicts,
                    "detail": "以下作者/人物未在已检索教材原文中出现，极可能张冠李戴，请复核：" + "、".join(conflicts)}
        return {"status": "consistent", "detail": f"作者/人物出现在教材原文：{asserted}"}
    return {"status": "unverified",
            "detail": "未断言具体作者/人物，工具不做硬性核对（公式与数字以 retrieve_kb 原文为准）"}


def dispatch_tool(name, args):
    try:
        if name == "retrieve_kb":
            return _tool_retrieve_kb(args)
        if name == "query_syllabus":
            return _tool_query_syllabus(args)
        if name == "check_fact":
            return _tool_check_fact(args)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": f"未知工具: {name}"}


# ===========================================================================
# 内容 agent：ReAct 工具调用 → LessonContent（分学科契约）
# ===========================================================================
# 每学科一份专属输出契约 + 学科教师角色 + 学科结构要求。
# 学科 agent 之间互不串扰：数学强约束 examples/diagrams，语文强约束 concepts 四类，
# 英语强约束核心句型/词汇教学。subject_cat 不在三科内回退 math 通用契约。
_SCHEMAS = {
    "math": (
        "你是一位教龄 25 年的小学数学特级教师，独立为《{topic}》设计一节课的课件内容。\n\n"
        "【数学课件结构 · 必须完整】\n"
        "1. objectives：3-4 条学习目标，绑定本课知识点。\n"
        "2. lead_in：真实生活情境（scenario）+ 引导问题（question）。\n"
        "3. concepts：1-2 个核心概念，每个含 statement、points、可选 pitfall（易错点）。\n"
        "4. examples：2-3 道例题，每道含 problem、steps（完整解题步骤）、answer、method。\n"
        "5. diagrams：1-2 个示意图。**每种图有固定适用场景和必填参数，选错图或缺参数会渲染成空白/错图，"
        "必须严格对照下表**（与本课无关就省略 diagrams 字段，宁缺毋滥）：\n"
        "   ① fraction_bars（分数条）：**仅用于分数课**。必填 bars=[{\"num\":分子,\"den\":分母,\"label\":\"1/4\"}]。\n"
        "      通分对比再加 common={\"den\":公分母,\"parts\":[{\"num\":..,\"label\":..}],\"result\":\"3/4\"}。\n"
        "      例（异分母加法 1/4+1/2）：bars=[{\"num\":1,\"den\":4,\"label\":\"1/4\"},{\"num\":1,\"den\":2,\"label\":\"1/2\"}],\n"
        "      common={\"den\":4,\"parts\":[{\"num\":1,\"label\":\"1/4\"},{\"num\":2,\"label\":\"2/4\"}],\"result\":\"3/4\"}。\n"
        "      **bars 绝不能为空数组**，否则图渲染空白。\n"
        "   ② circle（圆）：**仅用于圆的认识**。标圆心O/半径r/直径d。例：{\"type\":\"circle\",\"caption\":\"圆心O、半径r、直径d=2r\"}。\n"
        "   ③ number_line（数轴）：**仅用于数的顺序/大小/分数小数在数轴上的位置**。必填 min/max/marks。\n"
        "      例：{\"type\":\"number_line\",\"min\":0,\"max\":1,\"marks\":[{\"value\":0.5,\"label\":\"1/2\"}]}。\n"
        "   ④ bar_model（条形模型）：**用于整体与部分、倍数关系、加减乘除意义**。必填 total + parts。\n"
        "      例（小数乘法 2.4×3，把 7.2 拆成 6+1.2）：{\"type\":\"bar_model\",\"total\":72,\"parts\":[{\"value\":60,\"label\":\"2×3=6\"},{\"value\":12,\"label\":\"0.4×3=1.2\"}]}。\n"
        "      **小数乘法/除法用 bar_model 表示拆分，绝不用 place_value**。\n"
        "   ⑤ area_grid（方格面积）：**仅用于长方形正方形面积/周长**（rows×cols 个格子 + shade 涂色）。\n"
        "      必填 rows/cols/shade={\"r\",\"c\",\"w\",\"h\"}。**不能表示小数**（小数格无法涂），小数课禁用。\n"
        "      例（3×4 面积）：{\"type\":\"area_grid\",\"rows\":3,\"cols\":4,\"shade\":{\"r\":0,\"c\":0,\"w\":4,\"h\":3},\"shade_label\":\"3×4=12\"}。\n"
        "      **平行四边形/三角形/梯形面积课禁用 area_grid（那是方格图不是割补图），用 parallelogram**。\n"
        "   ⑥ parallelogram（平行四边形割补）：**仅用于平行四边形面积**（左画平行四边形标底高，右画割补后的长方形）。\n"
        "      必填 base（底）+ height（高）。例（底6高4）：{\"type\":\"parallelogram\",\"base\":6,\"height\":4,\"caption\":\"割补后长方形面积=底×高\"}。\n"
        "   ⑦ place_value（数位表）：**仅用于大数认识/数位顺序/计数单位**（亿/万/个级）。\n"
        "      必填 places=[\"千\",\"百\",\"十\",\"个\"] + digits={\"千\":\"3\",..}。**小数/分数课禁用**（那是整数数位表）。\n"
        "      例（认识 3456）：{\"type\":\"place_value\",\"places\":[\"千\",\"百\",\"十\",\"个\"],\"digits\":{\"千\":\"3\",\"百\":\"4\",\"十\":\"5\",\"个\":\"6\"}}。\n"
        "6. practice：分层练习 basic/standard/advanced 三档，每题 {\"q\":\"题\",\"a\":\"答\"}。\n"
        "7. summary：{\"points\":[\"要点1\",\"要点2\"], \"formula\":\"公式\"}。\n"
        "8. board：{\"center\":\"课题\", \"branches\":[{\"label\":\"分支\",\"items\":[\"内容\"]}]}。\n"
        "9. homework：分层作业三档，具体题目+答案。\n\n"
        "【输出 JSON 契约 · 键名固定】\n"
        '{"title":"课题","objectives":["..."],"lead_in":{"scenario":"...","question":"..."},'
        '"concepts":[{"statement":"...","points":["..."],"pitfall":"..."}],'
        '"examples":[{"problem":"...","steps":["..."],"answer":"...","method":"..."}],'
        '"diagrams":[{"type":"按上表选+带该图必填参数(bars/shade/places/total/parts等)","caption":"图注"}],'
        '"practice":{"basic":[{"q":"...","a":"..."}],"standard":[...],"advanced":[...]},'
        '"summary":{"points":["..."],"formula":"..."},'
        '"board":{"center":"...","branches":[{"label":"...","items":["..."]}]},'
        '"homework":{"basic":[{"q":"...","a":"..."}],"standard":[...],"advanced":[...]}}'
    ),
    "chinese": (
        "你是一位教龄 25 年的小学语文特级教师，独立为《{topic}》设计一节课的课件内容。\n\n"
        "【语文课件结构 · 必须完整，缺一不可】\n"
        "1. objectives：3-4 条学习目标，绑定本课（识字/阅读/习作）。\n"
        "2. lead_in：真实情境（scenario）+ 引导问题（question）。\n"
        "3. concepts：按顺序放 4 个概念（这是语文课件的核心，**4 个都必须有**）：\n"
        "   ① 作者/背景（statement 写作者名+年代/背景，有作者才放；古诗/文言文必须放）；\n"
        "   ② 阅读提示（本课学习重点/方法）；\n"
        "   ③ 段落理解（逐段首句 + 学习提示）；\n"
        "   ④ 重点句品析（**必须含三段：意思（在文中什么意思）、手法（本句真正用的写法）、好在哪（表达效果+换字对比），缺一不可**）。\n"
        "4. practice：分层练习 basic/standard/advanced 三档，每题 {\"q\":\"题\",\"a\":\"答\"}。\n"
        "5. summary：本课小结（主旨 + 写法 + 重点词句），points 3-5 条。\n"
        "6. board：板书（center 课题 + branches 2-4 个分支，每分支 label + items）。\n"
        "7. homework：分层作业三档，具体题目+具体答案。\n\n"
        "【语文课不填的字段】examples/diagrams 一般不需要（除非识字课配笔顺），省略即可。\n\n"
        "【输出 JSON 契约 · 键名固定】\n"
        '{"title":"课题","objectives":["..."],"lead_in":{"scenario":"...","question":"..."},'
        '"concepts":[{"statement":"作者/背景","points":["..."]},{"statement":"阅读提示","points":["..."]},'
        '{"statement":"段落理解","points":["..."]},{"statement":"重点句品析","points":["意思：...","手法：...","好在哪：..."]}],'
        '"practice":{"basic":[{"q":"...","a":"..."}],"standard":[...],"advanced":[...]},'
        '"summary":{"points":["主旨...","写法...","重点词句..."],"formula":""},'
        '"board":{"center":"课题","branches":[{"label":"...","items":["..."]}]},'
        '"homework":{"basic":[{"q":"...","a":"..."}],"standard":[...],"advanced":[...]}}'
    ),
    "english": (
        "你是一位教龄 25 年的小学英语特级教师（人教 PEP），独立为《{topic}》设计一节课的课件内容。\n\n"
        "【英语课件结构 · 必须完整，缺一不可】\n"
        "1. objectives：3-4 条学习目标，绑定本课句型/词汇。\n"
        "2. lead_in：真实对话情境（scenario）+ 引导问题（question）。\n"
        "3. concepts：按顺序放 2 个概念（**2 个都必须有**）：\n"
        "   ① 核心句型（本课重点句型，statement 写句型本身）；\n"
        "   ② 词汇·句型教学（**必须含三段：呈现（词义+真实语境例句）、操练（可当场做的替换/问答）、应用（真实情境交流），缺一不可**）。\n"
        "4. practice：分层练习 basic/standard/advanced 三档，每题 {\"q\":\"题\",\"a\":\"答\"}。\n"
        "5. summary：本课小结（句型 + 词汇 + 表达），points 3-5 条。\n"
        "6. board：板书（center 课题 + branches：Words 分支 + Patterns 分支）。\n"
        "7. homework：分层作业三档，具体题目+具体答案。\n\n"
        "【英语课不填的字段】examples/diagrams 一般不需要，省略即可。\n\n"
        "【输出 JSON 契约 · 键名固定】\n"
        '{"title":"课题","objectives":["..."],"lead_in":{"scenario":"...","question":"..."},'
        '"concepts":[{"statement":"核心句型","points":["..."]},'
        '{"statement":"词汇·句型教学","points":["呈现：...","操练：...","应用：..."]}],'
        '"practice":{"basic":[{"q":"...","a":"..."}],"standard":[...],"advanced":[...]},'
        '"summary":{"points":["句型...","词汇...","表达..."],"formula":""},'
        '"board":{"center":"课题","branches":[{"label":"Words","items":["..."]},{"label":"Patterns","items":["..."]}]},'
        '"homework":{"basic":[{"q":"...","a":"..."}],"standard":[...],"advanced":[...]}}'
    ),
}


def _subject_cat(cat, subject):
    """归一化 subject_cat：兼容 cat 字段为空时从 subject 推断。"""
    c = (cat or "").strip().lower()
    if c in _SCHEMAS:
        return c
    s = subject or ""
    if "数" in s:
        return "math"
    if "语" in s:
        return "chinese"
    if "英" in s:
        return "english"
    return "math"  # 兜底走数学通用契约


def _build_system_prompt(cat, topic, kb=None):
    """全自主内容 agent 的 system prompt：分学科契约 + 不预填 KB，agent 自己 retrieve_kb。

    每学科一份专属契约：注入学科教师角色 + 学科结构硬约束（语文 concepts 4 类、
    数学 examples+diagrams、英语核心句型/词汇教学），杜绝「通用契约导致学科环节缺失」。
    """
    subject = (kb or {}).get("subject", "")
    key = _subject_cat(cat, subject)
    schema = _SCHEMAS[key].replace("{topic}", topic)
    return (
        schema + "\n\n"
        "【agent 工作流程 · 必须遵守】\n"
        "1. 先检索：调用 retrieve_kb 拿到本课题真实教材原文/知识点/公式/易混警示，"
        "严禁凭记忆编造作者、公式、数据、课文内容。\n"
        "2. 再规划：根据检索到的教材，自主决定讲哪些内容、出什么分层练习。"
        "拿不准是否超纲时调用 query_syllabus 校准。\n"
        "3. 写内容时自检：写到作者/人物/年代/具体数字时，调用 check_fact 核对是否与教材原文一致。\n"
        "4. 最后产出：把内容组织成一个 JSON 对象输出。\n\n"
        "【铁律】所有内容基于 retrieve_kb 返回的真实教材；禁止编造、禁止串台；"
        "最终只输出一个完整可解析的 JSON 对象，不要解释文字、不要 markdown 代码块。"
    )


def generate_content_agent(kb, client, tools=None, max_rounds=12, max_tokens=24000,
                           feedback=""):
    """全自主内容 agent（ReAct / tool-calling）。返回 LessonContent 或 None。

    agent 自主完成：retrieve_kb 检索课文 → 规划 → 生成 → check_fact 自检 → 产出。
    feedback：审核 agent 打回时给出的修改意见，内容 agent 据此重做（闭环）。

    治 deepseek 截断：给足轮次，拿到合法 JSON 立即收尾；连续失败回退单次大调用。
    kb 需含 subject / grade / topic / subject_cat（orchestrator 已补全）。
    """
    if not hasattr(client, "complete_with_tools"):
        return generate_content(kb, client)
    tools = tools or TOOLS
    cat = kb.get("subject_cat") or ""
    topic = kb.get("topic", "")
    subject = kb.get("subject", "")
    grade = kb.get("grade", "")
    system = _build_system_prompt(cat, topic, kb)
    user = (
        f"请为《{topic}》（{subject}·{grade}）设计课件内容。"
        "请先调用 retrieve_kb 检索本课题真实教材，再规划并生成。"
    )
    if feedback:
        user += ("\n\n【审核打回 · 必须修正以下问题后重新生成】\n" + feedback +
                 "\n请针对上述问题逐一修正，其余可保留。")
    user += "\n最后只输出一个 JSON 对象（键名见系统说明）。"
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    last_tool_names = []  # 防死循环：跟踪最近几轮调用的工具名
    for r in range(max_rounds):
        try:
            content, tool_calls = client.complete_with_tools(
                messages, tools=tools, temperature=0.3, timeout=300,
                max_tokens=max_tokens, retries=4)
        except Exception as e:
            print(f"  [内容agent] 第{r+1}轮调用异常：{e}", flush=True)
            break
        if tool_calls:
            names = [tc["name"] for tc in tool_calls]
            last_tool_names.append(names)
            # 防死循环：连续 3 轮重复调同一工具（retrieve_kb 反复检索不产出）→ 强制收尾
            if (len(last_tool_names) >= 3
                    and all(n == last_tool_names[-1] for n in last_tool_names[-3:])):
                repeated = last_tool_names[-1][0]
                print(f"  [内容agent] 检测到连续 3 轮重复调用 {repeated}，强制要求产出 JSON", flush=True)
                messages.append({
                    "role": "assistant", "content": content,
                    "tool_calls": [{
                        "id": tc["id"], "type": "function",
                        "function": {"name": tc["name"], "arguments": tc.get("_raw_args", "{}")},
                    } for tc in tool_calls],
                })
                for tc in tool_calls:
                    result = dispatch_tool(tc["name"], tc["arguments"])
                    messages.append({"role": "tool",
                                     "content": json.dumps(result, ensure_ascii=False),
                                     "tool_call_id": tc["id"]})
                messages.append({"role": "user", "content": (
                    "你已经检索了足够多的教材信息，**不要再调用任何工具**。"
                    "请立即基于已检索到的内容，直接输出一个完整可解析的 JSON 对象"
                    "（键名见系统说明：objectives/lead_in/concepts/practice/summary/board/homework 等全部环节）。"
                    "不要解释文字、不要 markdown 代码块、不要再调用工具。")})
                # 下一轮若还调工具，跳出回退单次调用
                if len(last_tool_names) >= 5 and all(
                        n == last_tool_names[-1] for n in last_tool_names[-5:]):
                    print(f"  [内容agent] 连续 5 轮重复调用 {repeated}，放弃 ReAct 回退单次调用", flush=True)
                    break
                continue
            messages.append({
                "role": "assistant", "content": content,
                "tool_calls": [{
                    "id": tc["id"], "type": "function",
                    "function": {"name": tc["name"], "arguments": tc.get("_raw_args", "{}")},
                } for tc in tool_calls],
            })
            for tc in tool_calls:
                result = dispatch_tool(tc["name"], tc["arguments"])
                messages.append({"role": "tool",
                                 "content": json.dumps(result, ensure_ascii=False),
                                 "tool_call_id": tc["id"]})
            print(f"  [内容agent] 第{r+1}轮：调用工具 -> {[tc['name'] for tc in tool_calls]}", flush=True)
            continue
        last_tool_names.append([])  # 本轮没调工具（在尝试产出 JSON）
        data = _extract_json_lenient(content)
        if isinstance(data, dict) and data.get("objectives"):
            print(f"  [内容agent] 第{r+1}轮：产出 LessonContent", flush=True)
            return LessonContent.from_dict(data)
        _ln = len(content or "")
        _tail = (content or "")[-60:].replace("\n", " ")
        print(f"  [内容agent] 第{r+1}轮：文本非合法 JSON（len={_ln} 尾部='{_tail}'），重试", flush=True)
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": (
            "输出不是合法 JSON 或缺 objectives（可能被截断/夹带说明）。"
            "请严格只输出一个完整可解析的 JSON 对象，所有数组与字符串闭合，不要解释文字。")})
    print(f"  [内容agent] 超 {max_rounds} 轮未产出，回退单次调用", flush=True)
    return generate_content(kb, client, max_attempts=2)


# ===========================================================================
# 审核 agent：独立 LLM 审核 segments（课件内容结构），返回 通过/打回+理由
# 与 validate_deck（确定性规则）互补：agent 管语义质量，规则管硬伤。
# ===========================================================================
_REVIEW_VERDICT_TOOL = [{
    "type": "function",
    "function": {
        "name": "submit_review",
        "description": "提交课件审核结论：通过(approve) 或 打回(reject 并给具体修改意见)。",
        "parameters": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "description": "approve 或 reject"},
                "issues": {"type": "array", "items": {"type": "string"},
                           "description": "打回时的具体问题清单（哪页、什么问题、怎么改）；approve 时可为空"},
                "score": {"type": "integer", "description": "0-100 质量分"},
            },
            "required": ["verdict"],
        },
    },
}]


def _segs_to_text(segs):
    """把 segments 转成可读的纯文本大纲，供审核 agent 阅读。"""
    lines = []
    # diagram 版式可渲染的图形 type 白名单（与 layouts/diagram.py 的 DIAGRAM_RENDERERS 对齐）
    from .layouts.diagram import DIAGRAM_RENDERERS
    renderable = set(DIAGRAM_RENDERERS.keys())
    for i, s in enumerate(segs, 1):
        kind = s.get("kind", "")
        layout = s.get("layout", "")
        slots = s.get("slots") or {}
        parts = []
        for k, v in slots.items():
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, str):
                        parts.append(x)
                    elif isinstance(x, dict):
                        parts.append(" ".join(str(vv) for vv in x.values() if isinstance(vv, str)))
        body = " | ".join(p for p in parts if p)[:400]
        # diagram 页：显式标注图形 type 是否可渲染，让审核 agent 能发现「不可渲染的空图页」
        if layout == "diagram":
            figs = slots.get("figure") or []
            types = [f.get("type") for f in figs if isinstance(f, dict)]
            bad = [t for t in types if t not in renderable]
            if bad:
                body += f" 【警告：图形 type={bad} 不可渲染，将显示为空白，请改用概念文字页或可渲染图形】"
        lines.append(f"[第{i}页 {kind}/{layout}] {body}")
    return "\n".join(lines)


# 审核 agent 的学科专属审核维度（生成 agent 分学科后，审核也分学科）
_REVIEW_DIMS = {
    "math": (
        "【数学学科专属审核维度】\n"
        "A. 例题（steps 页）必须有完整解题步骤，不能只给答案；\n"
        "B. diagram 页的图形 type 必须可渲染（circle/fraction_bars/number_line/bar_model/area_grid/place_value），"
        "且用本课真实数字（如分数课不能都画 1/4）；\n"
        "C. 分层练习三档必须有梯度（basic→standard→advanced 逐档变难）；\n"
        "D. 公式/计算结果必须正确（可用教材原文核对）。"
    ),
    "chinese": (
        "【语文学科专属审核维度】\n"
        "A. concepts 必须含 4 类（缺一类即 reject）：作者/背景、阅读提示、段落理解、重点句品析；\n"
        "B. 重点句品析页必须含三段：意思、手法、好在哪（缺一不可）；\n"
        "C. 作者必须正确（对照教材原文，张冠李戴立即 reject）；\n"
        "D. 分层练习必须含 basic/standard/advanced 三档；homework 必须存在；\n"
        "E. 段落理解必须真的分段（逐段首句+提示），不能一段话概括全文。"
    ),
    "english": (
        "【英语学科专属审核维度】\n"
        "A. concepts 必须含 2 类（缺一类即 reject）：核心句型、词汇·句型教学；\n"
        "B. 词汇·句型教学页必须含三段：呈现、操练、应用（缺一不可）；\n"
        "C. 句型/词汇必须与教材原文一致（不能超纲引入复杂语法术语）；\n"
        "D. 分层练习必须含 basic/standard/advanced 三档；homework 必须存在。"
    ),
}


# 各学科课件必须出现的环节 kind（结构完整性硬校验，先于 LLM 审核）
# 防 LLM 审核误判：代码先数 segments 缺不缺环节，缺了直接 reject。
_REQUIRED_KINDS = {
    "math": ["objectives", "lead_in", "concept", "example", "practice", "summary", "board", "homework"],
    "chinese": ["objectives", "lead_in", "concept", "practice", "summary", "board", "homework"],
    "english": ["objectives", "lead_in", "concept", "practice", "summary", "board", "homework"],
}


# diagram 各图必填参数（数据有效性硬校验：缺了渲染成空白/错图，必须打回）
_DIAGRAM_REQUIRED = {
    "fraction_bars": lambda f: bool(f.get("bars")),
    "bar_model": lambda f: bool(f.get("total") and f.get("parts")),
    "area_grid": lambda f: bool(f.get("rows") and f.get("cols") and f.get("shade")),
    "place_value": lambda f: bool(f.get("places")),
    "number_line": lambda f: f.get("min") is not None and f.get("max") is not None,
    "parallelogram": lambda f: bool(f.get("base") and f.get("height")),
    "parallelogram_area": lambda f: bool(f.get("base") and f.get("height")),
    "平行四边形": lambda f: bool(f.get("base") and f.get("height")),
    "circle": lambda f: True,
}


def _check_diagram_data(segs):
    """diagram 数据有效性硬校验：检查每个 figure 的关键参数是否有效。返回问题清单。"""
    problems = []
    for i, s in enumerate(segs, 1):
        if s.get("layout") != "diagram":
            continue
        figs = (s.get("slots") or {}).get("figure") or []
        for f in figs:
            if not isinstance(f, dict):
                continue
            t = f.get("type")
            chk = _DIAGRAM_REQUIRED.get(t)
            if chk is None:
                problems.append(f"第{i}页 diagram 图形 type={t!r} 不在白名单（将渲染成占位框）")
            elif not chk(f):
                # 缺关键参数
                keys = [k for k in ("bars", "total", "parts", "rows", "cols", "shade", "places", "min", "max") if f.get(k)]
                problems.append(f"第{i}页 diagram 图形 type={t!r} 缺关键参数（仅有 {keys or '无'}），将渲染成空白")
    return problems


def _check_structure(segs, key):
    """结构完整性硬校验：数 segments 里必要环节 kind 是否齐全 + diagram 数据是否有效。返回缺失清单。"""
    present = set()
    for s in segs:
        k = s.get("kind", "")
        if k:
            present.add(k)
    required = _REQUIRED_KINDS.get(key, _REQUIRED_KINDS["math"])
    missing = [k for k in required if k not in present]
    # concept 页语文至少要 3 个（作者背景/阅读提示/段落理解/重点句品析 至少出 3 个才算合格）
    if key == "chinese":
        n_concept = sum(1 for s in segs if s.get("kind") == "concept")
        if n_concept < 3:
            missing.append(f"concept 仅 {n_concept} 个（语文至少 3 个：阅读提示/段落理解/重点句品析）")
    # diagram 数据有效性（缺关键参数会渲染空白/错图）
    missing.extend(_check_diagram_data(segs))
    return missing


def review_segments_agent(kb, segs, client):
    """审核 agent：独立审核 segments。返回 (approved:bool, feedback:str, score:int)。

    两道防线：① 结构完整性硬校验（代码数环节，缺了直接 reject 不问 LLM）；
    ② LLM 语义审核（扣题/事实/套话/学段 + 学科专属维度）。
    """
    if not hasattr(client, "complete_with_tools"):
        return True, "", 0  # 不支持 tool-calling 时跳过 agent 审核（走确定性门禁兜底）
    topic = kb.get("topic", "")
    subject = kb.get("subject", "")
    grade = kb.get("grade", "")
    text = (kb.get("original_text") or "")[:800]
    deck_text = _segs_to_text(segs)
    key = _subject_cat(kb.get("subject_cat"), subject)
    subj_dims = _REVIEW_DIMS.get(key, _REVIEW_DIMS["math"])
    # 第一道防线：结构完整性硬校验（代码判断，不给 LLM 误判机会）
    missing = _check_structure(segs, key)
    if missing:
        fb = "课件结构不完整，缺少以下必要环节，请补全：\n" + "\n".join(f"- {m}" for m in missing)
        print(f"  [审核agent] 结构硬校验不通过，缺 {len(missing)} 环节：{missing}（直接打回，不经 LLM）", flush=True)
        return False, fb, 0
    sys_p = (
        "你是一位严格的课件审核专家（教研组长），审核一份"
        + {"math": "数学", "chinese": "语文", "english": "英语"}.get(key, "") +
        "课件的页面内容大纲，判断能否交付给学生使用。\n"
        "【通用审核维度】\n"
        "1. 内容是否紧扣本课教材（对照下面给出的教材原文），有没有张冠李戴/串台；\n"
        "2. 作者/公式/数字等事实是否正确；\n"
        "3. 是否有「每课都能说」的空话套话（如光说'大家想一想'却没具体内容）；\n"
        "4. 是否适合该学段学生（不超纲也不太浅）。\n"
        + subj_dims + "\n"
        "【打回标准 · 极其重要】只打回以下 4 类**硬伤**，缺一不可忍：\n"
        "  ① 张冠李戴/串台（内容与本课教材不符，如把别的课文/别的单元的知识点当本课）；\n"
        "  ② 事实错误（作者写错、公式算错、数字错、知识点讲错）；\n"
        "  ③ 缺环节（该类的必备 concept/练习/小结/作业缺失或为空）；\n"
        "  ④ 超纲（远超该学段，如小学讲中学公式）。\n"
        "【以下情况必须 approve，不得打回】\n"
        "  - 「建议/可以更好/可优化/标注一下/略显简单/可增加」这类**优化建议**，不是硬伤；\n"
        "  - 内容正确但表述可更精炼、练习可更多样、难度可再微调——这些都是可交付的，approve；\n"
        "  - 教材原文的合理扩展（句型/例题在原文基础上换数字换情境），只要不错不超纲，approve。\n"
        "  判断口诀：**这份课件能不能直接拿去上课？能→approve；有①②③④硬伤才→reject。**\n"
        "【结论】approve 或 reject。reject 时逐条给出「哪页+什么硬伤（必须属①②③④）+怎么改」，\n"
        "不要把优化建议写进 issues。只通过 submit_review 工具返回结论，不要输出任何文字。"
    )
    user = (
        f"课题：《{topic}》（{subject}·{grade}）\n\n"
        f"【教材原文（前800字）】\n{text}\n\n"
        f"【课件页面内容大纲】\n{deck_text}\n\n"
        "请审核并提交结论。"
    )
    messages = [{"role": "system", "content": sys_p},
                {"role": "user", "content": user}]
    try:
        content, tool_calls = client.complete_with_tools(
            messages, tools=_REVIEW_VERDICT_TOOL, temperature=0.2, timeout=180,
            max_tokens=3000, retries=3)
        for tc in tool_calls:
            if tc["name"] != "submit_review":
                continue
            a = tc["arguments"]
            verdict = (a.get("verdict") or "").lower()
            issues = [str(x) for x in (a.get("issues") or [])]
            score = int(a.get("score") or 0)
            approved = verdict == "approve"
            feedback = "" if approved else "\n".join(f"- {x}" for x in issues)
            print(f"  [审核agent] verdict={verdict} score={score}"
                  + (f" 打回{len(issues)}条" if not approved else " 通过"), flush=True)
            if not approved:
                for _i, _x in enumerate(issues, 1):
                    print(f"      打回{_i}: {_x}", flush=True)
            return approved, feedback, score
        # 模型没调工具，兜底按通过（避免死循环）
        print("  [审核agent] 未返回工具结论，按通过放行（兜底）", flush=True)
        return True, "", 0
    except Exception as e:
        print(f"  [审核agent] 审核异常（{e}），按通过放行（兜底）", flush=True)
        return True, "", 0


# ===========================================================================
# 样式 agent：出 StyleRecipe（调色板/字体/装饰/版式偏好）
# 设计为可选增强：失败或客户端不支持 tool-calling 时回退确定性 seeded_recipe。
# ===========================================================================
_STYLE_TOOL = [{
    "type": "function",
    "function": {
        "name": "set_style",
        "description": "设定课件视觉风格（调色板/字体/装饰/版式偏好）。仅可调用一次，作为最终风格决策。",
        "parameters": {
            "type": "object",
            "properties": {
                "palette_hint": {"type": "string",
                                 "description": "warm_ink/bamboo_green/cinnabar/indigo/paper/ink_black/sky_blue/amber/plum/mint/rose/slate"},
                "mood": {"type": "string",
                         "description": "沉静典雅/活泼童趣/理性严谨/温润质朴/明快清朗/古雅厚重/清新自然/端庄大气"},
                "density": {"type": "string", "description": "sparse/balanced/dense"},
                "decorations": {"type": "array", "items": {"type": "string"},
                                "description": "seal/branch/dot_grid/wave/none 至多 2 个"},
                "preferred_layouts": {"type": "array", "items": {"type": "string"}},
                "avoid_layouts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["palette_hint", "mood", "density"],
        },
    },
}]


def generate_recipe_agent(dna, kb, client):
    """样式 agent：据课型/学段/主题出 StyleRecipe。失败回退 seeded_recipe（确定性）。"""
    fallback = seeded_recipe(dna)
    if not hasattr(client, "complete_with_tools"):
        return fallback
    topic = kb.get("topic", "")
    subject = kb.get("subject", "")
    grade = kb.get("grade", "")
    cat = dna.subject_cat if hasattr(dna, "subject_cat") else dna.get("subject_cat", "general")
    stage = dna.stage if hasattr(dna, "stage") else dna.get("stage", "mid")
    sys_prompt = (
        "你是资深课件视觉设计师。根据学科/学段/课题气质，决定一套视觉风格。"
        "规则：低学段活泼、高学段理性；古雅课题用 warm_ink/cinnabar+seal；"
        "数学/科学偏理性（indigo/slate/sky_blue）；语文现代文明快清朗。"
        "只通过 set_style 工具返回风格决策，不要输出任何文字。"
    )
    user = f"学科={subject} 类别={cat} 学段={stage} 年级={grade} 课题=《{topic}》。请定风格。"
    messages = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": user}]
    try:
        content, tool_calls = client.complete_with_tools(
            messages, tools=_STYLE_TOOL, temperature=0.3, timeout=120,
            max_tokens=2000, retries=2)
        for tc in tool_calls:
            if tc["name"] != "set_style":
                continue
            a = tc["arguments"]
            from .schemas import PALETTE_HINTS, MOODS, DENSITIES
            hint = a.get("palette_hint") if a.get("palette_hint") in PALETTE_HINTS else getattr(dna, "palette_hint", "warm_ink")
            mood = a.get("mood") if a.get("mood") in MOODS else getattr(dna, "mood", "温润质朴")
            density = a.get("density") if a.get("density") in DENSITIES else getattr(dna, "density", "balanced")
            # 构造一个带 hint 的 dna 副本走 seeded_recipe 拿合法 palette，再叠加 agent 的装饰/版式偏好
            dna_kwargs = {
                "subject_cat": getattr(dna, "subject_cat", "general"),
                "stage": getattr(dna, "stage", "mid"),
                "lesson_type": getattr(dna, "lesson_type", "standard"),
                "mood": mood, "density": density,
                "palette_hint": hint,
                "content_form": getattr(dna, "content_form", "mixed"),
            }
            recipe = seeded_recipe(DesignDNA(**dna_kwargs))
            decos = a.get("decorations") or []
            if decos:
                recipe.decorations = [str(x) for x in decos][:2]
            lp = recipe.layout_prefs or {"preferred": [], "avoid": [], "per_kind": {}}
            lp["preferred"] = [str(x) for x in (a.get("preferred_layouts") or [])]
            lp["avoid"] = [str(x) for x in (a.get("avoid_layouts") or [])]
            recipe.layout_prefs = lp
            print(f"  [agent] 样式 agent：palette_hint={hint} mood={mood} density={density}", flush=True)
            return recipe.validate()
    except Exception as e:
        print(f"  [agent] 样式 agent 失败（{e}），回退确定性 recipe", flush=True)
    return fallback
