"""四源 prompt 合成。

最终发给模型的 messages =
  system: 类型预置(维度/语气/字数) + 风格样本 + 硬规则(R1-R7，含 R2b 防投诉、R2c 防编造)
  user:   课件/教案 + 该生历史课评 + 当前学生信息(已脱敏) + 全班共性

姓名处理：同班**其他同学**的姓名在送入前由 redact 脱敏成占位符（见 redact.Redactor）；
当前学生本人的姓名/昵称**明文传入**（占位符方案实测导致模型自行编名、100% 叫错孩子，
见 redact.py 顶部说明），并由 R13 强制模型原样使用。
"""
import os
import re
from extensions import db
from models.class_type_preset import ClassTypePreset
from models.class_student import Klass
from models.lesson import StyleSample

# 通用硬规则（所有类型共用）
BASE_RULES = (
    "【写作硬规则 · 必须严格遵守】\n"
    "R1 角色：你是一名严谨的少儿培训课评助手，面向家长写一段可直接发送的课后反馈。\n"
    "R2 防投诉：\n"
    "  · R2a 禁用绝对化用词（「最」「第一」「永远」「完全没问题」等）。\n"
    "  · R2b 禁止横向比较：不得出现「比其他同学」「班里最」「在同学中最」等与**其他学员**对比的表述（这类表述会引发家长互相比较的投诉）；允许与该生**自己过往**比较（如「比上次进步」「较之前更稳」），但不得含绝对化用词。\n"
    "  · R2c 禁止编造未提供的具体事实：不得虚构分数、排名、比赛结果、具体时长（如「用了20分钟」）、"
    "他人姓名、未见过的事件细节。只写老师真实提供的表现；信息不足时宁可简短，也不要编造。\n"
    "R3 结构（严格 2 段，缺一不可）——**知识点归知识点，课评归课评**：\n"
    "  ① 第 1 段【课堂内容总结】：**整段只写本节课的知识点**，**必须直接以「1.」开头**，"
    "使用「1. xxx  2. xxx  3. xxx」逐条编号"
    "（阿拉伯数字+半角点+空格+内容），编号项之间用**单个换行**分隔；数量 3-5 条（除非教师上传内容本身就少于 3 个要点）。\n"
    "     · **第 1 段禁止项**：禁止出现学生称呼/昵称，禁止任何铺垫叙事或引导语"
    "（如「以下是本节课的内容总结：」「在这个项目中你不仅学会了…」一律不许写），"
    "禁止夹带任何对该生表现的评价——这些一律放到第 2 段。\n"
    "     · **内容来源硬约束**：每一条都必须从【本节课课件/教案正文】里**直接抽取或紧贴其意**，**严禁添加上传文本中没有的主题、术语、活动、场景**；"
    "教师上传的是 Python 代码（如 for/range/百钱百鸡），输出里就必须出现这些关键词；完全没上传课件时，用本节课标题/知识点目标兜底，仍要编号，且不许编造教师未提的具体应用场景。\n"
    "  ② 第 2 段【课后评价】：用一段连贯文字综合写出该生的具体表现、亮点、1 个可提升点、以及 1 条家庭巩固建议——"
    "**全部作为一段**（内部用标点/换行分隔句子，不要再用空行切成多个小段）。\n"
    "     · 表现与可提升点**只能引用下方【教师点选的快捷标签】和【教师填写的一句话评语】**作为依据；若两者都为空或未提供，"
    "必须明写「老师本节课暂未提供具体表现信息」等表述，**严禁凭空编造课堂行为**（如「主动举手」「认真听讲」「积极发言」「思维得到锻炼」等若未在标签/评语中出现，一概不许写）。\n"
    "  【格式硬要求】第 1 段与第 2 段之间必须用恰好一个空行（\\n\\n）隔开；第 1 段内部的 1./2./3. 编号项之间只用一个换行；"
    "第 2 段内部不得插入空行。**严禁**把全部内容堆成一大段连写，也**严禁超过 2 段**。\n"
    "R4 字数硬上限：必须严格落在上方「字数范围」区间内，绝不可超过上限（超过上限视为不合格，家长在手机上也读不完）。"
    "写完请自查字数，若超限必须删减到区间内；宁短勿空，不要为凑结构而灌水。\n"
    "R5 emoji（硬性数量）：emoji 数量**必须达到上方「emoji 数量」区间下限**，"
    "建议在开头、亮点、建议等不同位置各点缀 1 个，总数 2-3 个最为合适；"
    "**严禁**全部堆在开头或结尾，也**严禁**全篇只用 1 个 emoji。\n"
    "R6 去重：若提供了「参考开头句」，你的开头要明显区别于它，避免同班课评开头雷同被家长横向对比发现。\n"
    "R7 具体优先：用「主动举手」「完成了X步骤」这类可观察行为，替代「表现很好」这类空话。\n"
    "R8 第 2 段【课后评价】的首句必须专属化且基于真实表现：这是老师单独发给一位家长的私信。"
    "**称呼只出现在第 2 段**——第 2 段第一句必须直接对该生说话、包含昵称（如「涵涵」），"
    "绝不可用「各位家长好」「亲爱的家长们」等群发称呼（第 1 段是纯知识点列表，不写称呼）。"
    "该首句必须紧扣该生本节课的**真实表现**来写——"
    "用教师提供的标签、一句话评语或可见行为作为切入点，禁止每篇都套「表现得非常专注/很棒/真棒/真的很棒呢」这类空泛夸法。"
    "不同学科的**语气应明显不同**（见上方【本学科写作要点】中的课评开头范例）：编程偏能力总结、书法偏平实观察、舞蹈偏身体素养、"
    "美术偏观察感知、体育偏素质提升，绝不要用同一句夸奖套所有学科。\n"
    "  · 若含待改进标签（如概念混淆/需巩固/偶尔走神），该首句必须先点出该生真实状态或具体亮点，绝不可只写「很棒/真棒/非常专注」定调；"
    "参考写法：「涵涵，今天在（具体待改进点）上还不太熟练，但你（具体亮点）做得很认真」——括号内请替换为真实内容，不要保留括号。\n"
    "  · 含正面标签（如专注/作品优秀）时，也要以【具体行为 / 作品 / 能力点】起头（见上方【本学科写作要点】中的课评开头范式），"
    "**严禁把「很棒 / 专注 / 真棒 / 表现得很出色」这类词作为第 2 段第一句**；若确需提及状态，必须紧跟具体表现，绝不可只写空泛夸奖。\n"
    "R9 结尾建议必须个性化：结尾的家庭巩固建议必须结合该生本节课的真实表现（快捷标签、一句话评语、亮点或不足）来写，"
    "严禁直接复现/照搬上方「课件/教案正文」里的通用建议原文；若参考了教案方向，也必须改写成针对该生的具体动作。\n"
    "R10 忠实反映教师标签与评语：教师点选的「快捷标签」和填写的「一句话评语」是该生本节课的真实表现，课评必须如实体现，"
    "尤其是含待改进含义的标签（如「概念混淆」「需巩固」「偶尔走神」「需纠动作」）。若标签指向不足，课评必须写出对应的具体不足与改进方向，"
    "不得用正面空话粉饰或与标签矛盾（例如标签写「概念混淆」却写「线条流畅/掌握扎实」属编造，违反 R2c）。\n"
    "R11 课堂内容总结必写且须落地：第 ① 段【课堂内容总结】必须存在且**独立成段排在全文最前**，"
    "内容须来自【本节课课件/教案正文】或【本节课知识点目标】，专门总结「这节课教了什么」，"
    "不得用该生表现段落替代、不得合并进表现段落、不得泛泛而谈。若未上传课件，则用本节课标题与知识点目标概括，但仍须具体到可辨认的主题/知识点/活动。\n"
    "  · **严禁**在第 2 段【课后评价】里再夹一整段知识点罗列或课程内容介绍（如再写一遍「本节课学习了……1. …2. …」）——"
    "知识点只允许出现在第 1 段，第 2 段只写对该生的评价。\n"
    "R12 基于真实课堂表现生成：课评的全部内容（夸奖与改进建议）都必须有教师提供的真实依据——"
    "快捷标签、一句话评语、课件内容或可见行为，禁止脱离该生实际表现的通用套话（如不分情况地写「表现优异」「进步明显」等空泛定调）。\n"
    "R13 姓名忠实（最高优先级，违反即作废）：称呼该生时**只能**使用下方【当前学生信息】里给出的「昵称」原文，一字不差。\n"
    "  · 严禁自行编造、替换、简化或美化姓名（如把「林小满」写成「涵涵」「小满」「小明」「小朋友」都属严重错误）；\n"
    "  · 严禁套用参考范文里出现的任何人名——范文里的名字与本次学生无关，只可借鉴写法，绝不可搬名字；\n"
    "  · 若看到 {{STU}}、{{STU_NICK}}、{{PEER_1}} 之类的占位符，说明那是被隐去的他人姓名，禁止在输出中出现这类花括号占位符；\n"
    "  · 全文至少出现一次该生昵称原文，且不得出现任何其他孩子的姓名。\n"
)


def _get_klass(class_id):
    return db.session.get(Klass, class_id)


def _preset_block(preset) -> str:
    if not preset:
        return "机构类型：通用。\n"
    dims = preset.dimensions or []
    block = (
        f"机构类型：【{preset.name}】。\n"
        f"评价维度：{ '、'.join(dims) if dims else '（通用维度）' }。\n"
        f"语气风格：{preset.tone or '亲切、鼓励、具体'}。\n"
        f"字数范围：{preset.length_min}-{preset.length_max} 字。\n"
        f"emoji 数量：{preset.emoji_min}-{preset.emoji_max} 个。\n"
    )
    return block


# 托管/作业辅导类：行业惯例就是「各位家长好」式的群发作业反馈，对 R8 群发称呼做豁免，
# 但 R13 姓名忠实仍然生效（提到孩子时必须用正确昵称）。
GROUP_STYLE_CODES = {"tutoring"}

_GROUP_STYLE_EXEMPTION = (
    "【本类型例外说明】托管/作业辅导课评允许使用「各位家长好」这类群发式开头（行业惯例），"
    "R8 的群发称呼禁令对本类型不适用。但 R13 姓名忠实仍然生效：正文提到该生时，"
    "必须使用【当前学生信息】给出的昵称原文，不得编造或替换姓名。\n"
)


def _is_group_style(preset) -> bool:
    return bool(preset and getattr(preset, "code", "") in GROUP_STYLE_CODES)


_TRIAL_RULES = (
    "【试听课特别提示】这是一节试听课的课评，它往往决定家长是否报名，价值最高。\n"
    "请按以下结构：① 初次上课的整体印象与专注度 ② 该生在本节课展现的潜力点（具体、可观察）\n"
    "③ 与这门课的适配度 ④ 后续学习路径建议（1-2 条）。语气温暖、建立信任，但同样遵守 R2c 不编造。\n"
)


# 各学科「课评开头范式」：用于**第 2 段【课后评价】的第一句**（第 1 段是纯知识点编号列表，不写称呼）。
# 用具体行为/能力/作品起头，禁止以「很棒/专注/真棒」起头。
# 弱模型（GLM-4-Flash）对软性「模仿风格」指令依从度低，必须用硬范式强制差异化。
#
# ⚠ 关键约束：本字典里**严禁出现英文方括号占位符**（如 [从本节课课件抽取的具体任务]）。
# 弱模型会把 [ ] 当成字面待填文本原样抄入输出（体育/美术曾 100% 泄漏）。
# 改为自然语言写法：括号内只是「举例提示」，并明确「请用课件真实内容替换示例」。
SUBJECT_OPENING = {
    # 不写死具体技术/工具（如 Scratch/Python）—— 不同老师教的语言/工具不同，
    # 必须让开头从【本节课课件/教案正文】中抽取具体任务来写。
    "coding": "XX，本次编程课你独立完成了一个具体的编程作品（示例：从课件里抽取的真实任务，如一个猜数字小游戏或成绩统计表），并在这个任务上体现出扎实的逻辑能力。请务必用本节课课件里的真实任务替换括号里的示例，禁止以空泛的「很棒/专注」开头。",
    "calligraphy": "XX，今天书法课你某个具体的笔画或字帖（示例：如「永」字八法、某首古诗的临帖）收笔顿挫明显，坐姿和握笔也一直很端正。请用课件里的真实笔画/字帖替换示例，禁止空泛夸奖。",
    "dance": "XX，今天舞蹈课你某个具体的动作或组合（示例：如地面柔韧练习、某支成品舞的片段）掌握得不错，动作连贯有表现力。请用课件里的真实动作替换示例。",
    "art": "XX，今天美术课你某个具体的作品或主题（示例：如一只陶艺杯、一幅同类色黄昏）完成度很高，能看出你对技法细节的观察。请用课件里的真实作品替换示例。",
    "sports": "XX，今天体育课你某个具体的项目或动作（示例：如立定跳远、折返跑、跳绳交替跳）完成得不错，技术动作和体能都有体现。请用课件里的真实项目替换示例。",
    "english": "XX，今天英语课你某个具体的单词、句型或对话场景（示例：如购物情景对话、过去式句型）掌握得标准，敢开口说。请用课件里的真实内容替换示例。",
    "tutoring": "XX，今天辅导课你独立完成了本节课的具体练习或题目（示例：如某套单元测试卷的错题订正），错题也及时订正了，学习态度很认真。请用课件里的真实练习替换示例。",
    "other": "XX，今天这节课你在某个具体的能力点或作品上表现不错（示例：如一次完整的小组汇报），能看出本节课的收获。请用课件里的真实内容替换示例。",
}

# 学科类型码 → 课评模板文件（src/ai/subject_templates/<file>）。
# 这些文件是「结构模板 + 学科评价角度/术语 + 语感范例」的**写作格式示范**，
# 绝不可让 AI 照抄其中的示例原句/人名/数据；详见 build_messages 的 subject_block 铁律。
_SUBJECT_TPL_FILES = {
    "coding": "coding.md",
    "art": "art.md",
    "dance": "dance.md",
    "sports": "sports.md",
    "calligraphy": "calligraphy.md",
    "english": "academic.md",
    "tutoring": "tutoring.md",
}


def load_subject_template(code: str):
    """按学科类型码加载课评模板文本；无对应文件返回 None。"""
    fn = _SUBJECT_TPL_FILES.get(code)
    if not fn:
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "subject_templates", fn)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()


# ---- 优秀历史课评 →「评价维度骨架」提取（弱模型对抽象「靠拢」指令依从度低，
#      必须给出具体可模仿的维度顺序 + 句式骨架，才能让其按范例写法产出） ----
_DIM_PATTERNS = [
    ("教学主题概述",   r"整体体系|体系教学|教学以.*为主要内容|本周.*内容|主要内容"),
    ("课堂常规/纪律", r"常规|纪律|出勤|秩序|安全|要求|习惯|身心发展"),
    ("技术动作",       r"技术|动作|示范|要领|姿势|发力|缓冲|摆臂|蹬地|起跳|运球|投篮|笔画|间架|发音|句型|构图|色彩|节奏"),
    ("学生表现/态度",  r"表现|态度|主动|积极|认真|专注|端正|参与|投入|自信|配合|活力"),
    ("问题/分层指导",  r"问题|存在|不足|个别|待改进|需加强|分层|纠正|指导|易错|混淆|不稳|不充分"),
    ("总结/家庭建议",  r"达成|建议|在家|回家|巩固|练习|希望|期待|提升|整体来看"),
]


def _split_sentences(text):
    """按句号/分号切句，返回非空句子列表。"""
    return [p.strip() for p in re.split(r"[。；;！？!?]", text) if p.strip()]


def _classify_dim(sent):
    for dim, pat in _DIM_PATTERNS:
        if re.search(pat, sent):
            return dim
    return None


def extract_template_skeleton(text, max_dims=6):
    """把优秀课评拆成「维度 → 示范句」骨架。

    返回形如 ['维度1·课堂常规/纪律：...', '维度2·技术动作：...', ...]，
    供弱模型作为第②段写法模板逐维度模仿。
    """
    sents = _split_sentences(text)
    buckets = {}
    order = []
    for s in sents:
        dim = _classify_dim(s)
        if dim:
            if dim not in buckets:
                buckets[dim] = []
                order.append(dim)
            if len(buckets[dim]) < 2:
                buckets[dim].append(s)
    fixed = ["教学主题概述", "课堂常规/纪律", "技术动作", "学生表现/态度", "问题/分层指导", "总结/家庭建议"]
    dims = [d for d in fixed if d in buckets] + [d for d in order if d not in fixed]
    skeleton = []
    for i, d in enumerate(dims[:max_dims], 1):
        sample = buckets[d][0]
        skeleton.append(f"维度{i}·{d}：{sample}")
    # 维度不足 2 个时，退化为按原始句子顺序展示，仍给模型可模仿的结构
    if len(skeleton) < 2:
        skeleton = [f"维度{i+1}：{s}" for i, s in enumerate(sents[:max_dims])]
    return skeleton


# 学科中文名（精简模板流程里给 system 用）
_SUBJ_CN = {
    "coding": "编程", "art": "美术", "dance": "舞蹈", "sports": "体育",
    "calligraphy": "书法", "english": "英语", "tutoring": "托管",
}


def _build_excellent_template_messages(preset, student_name, preferred_name, lesson_info,
                                       courseware_text, excellent_review, gender,
                                       quick_tags, one_sentence, subject_code):
    """有「班级级优秀历史课评」作主导模板时，走精简单模板流程。

    弱模型（GLM-4-Flash）对长 prompt 中多个「硬要求」约束依从度极低——把优秀课评塞进
    完整复杂 prompt（学科范式开头 + 2 段硬要求 + 多源风格等）会与「仿写优秀模板」冲突，
    模型直接忽略。本地极简实验证明：仅给「优秀课评范例 + 课件 + 标签 + 评语 + 仿写指令」
    这一单一模板时，模型能完美仿写（专业术语维度、段落结构、口吻都对齐）。故此处独立成精简流程。
    """
    call_name = preferred_name or student_name
    subj_cn = (preset.name if preset else None) or _SUBJ_CN.get(subject_code, "本学科")
    title = lesson_info.get("title") or "本节课"
    cw = (courseware_text or "").strip()
    cw_block = ("【本节课课件/教案正文】\n" + cw + "\n") if cw else f"（本节课未上传课件，请根据标题「{title}」概括课堂内容）\n"
    tags = quick_tags or []
    tag_block = ("【教师点选标签 · 该生本节课真实表现定调】" + "、".join(tags) + "\n") if tags else ""
    note_block = f"【教师一句话评语】{one_sentence}\n" if one_sentence else ""

    sys_msg = (
        f"你是一名经验丰富的少儿{subj_cn}老师，为家长撰写课后评语。"
        f"你善于用专业、有温度的语言，从课堂常规、运动负荷、技术动作、学生表现、教学目标达成、家庭巩固等维度评价学生。"
    )
    user_msg = (
        "下方是教师上传的「优秀历史课评范例」。请严格仿写它的写法——段落结构、专业术语维度"
        "（课堂常规/运动负荷/技术环节/学生表现/教学目标达成/家庭巩固）、句式口吻都向它看齐；"
        "只把内容替换为本节课该学生的真实情况，绝不照抄范例原句，不搬范例里的人名/数据/具体事件。\n\n"
        f"【优秀课评范例】\n{excellent_review}\n\n"
        f"{cw_block}"
        f"【学生昵称】{call_name}\n"
        f"【本节课标题】{title}\n"
        f"{tag_block}"
        f"{note_block}"
        "要求：\n"
        "· 保持与范例一致的自然段落（不用 #/### markdown 标题），段间恰好一个空行；\n"
        "· 必须用范例里的专业维度词（课堂常规、运动负荷、技术环节、学生表现、教学目标达成、家庭巩固等）组织，"
        "不用通用的「课堂内容总结/课后评价」框架词；\n"
        f"· 开头仿写范例开篇方式（以教学主题/体系概述起头），不以「{call_name}，你今天…」起头；\n"
        f"· emoji 数量 2-3 个，分散在亮点/建议位置。\n"
    )
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": user_msg},
    ]


def build_messages(preset, student_name, preferred_name, lesson_info,
                   courseware_text, history_reviews, style_examples,
                   trial=False, reference_opening=None,
                   excellent_review=None, gender=None,
                   quick_tags=None, one_sentence=None, library_example=None,
                   subject_template=None, subject_code=None,     correction_note=None):
    # 有「班级级优秀历史课评」作主导模板：走精简单模板流程（避免长 prompt 多约束冲突致弱模型不依从）
    if excellent_review:
        return _build_excellent_template_messages(
            preset=preset, student_name=student_name, preferred_name=preferred_name,
            lesson_info=lesson_info, courseware_text=courseware_text,
            excellent_review=excellent_review, gender=gender,
            quick_tags=quick_tags, one_sentence=one_sentence, subject_code=subject_code,
        )

    """构造发送给 LLM 的 messages 列表。

    lesson_info: dict(title, common_notes, objectives)
    所有姓名相关字段应为已脱敏的占位符。
    写法模板优先级（从高到低）：
      1. excellent_review  —— 班级级优秀历史课评（最高优先级，主导模板：开篇措辞/维度展开/术语颗粒度/收尾口吻都向其看齐）
      2. history_reviews   —— 该生历史课评（次优先级，个性化连贯）
      3. style_examples    —— StyleSample 表样本（兜底）
    若两者（excellent_review 与 history_reviews）同时存在，优先参考优秀历史课评作为写法模板。
    若两者皆无，则回落到系统本身模板（subject_template + 学科开头范式）。
    gender: 学生性别（男/女/未知），非姓名，无需脱敏
    quick_tags: 教师本节课点选的快捷标签列表
    one_sentence: 教师填写的本节课一句话评语
    library_example: 无历史/无优秀课时，同类别课评库兜底范文
    correction_note: 上一次生成不合格时的纠正指令（校验失败重生成用）
    """
    preset_block = _preset_block(preset)

    # 写法模板优先级：① 班级级优秀历史课评（最高优先 · 主导模板）② 该生历史课评（次优先 · 个性化连贯）③ StyleSample（兜底）
    style_block = ""
    segs = []
    if excellent_review:
        # 提取维度骨架（弱模型对抽象「靠拢」指令依从度低，必须给具体可模仿的维度顺序 + 句式）
        _skeleton = extract_template_skeleton(excellent_review)
        _skel_text = "\n".join(_skeleton)
        # 提取首/末句作为显式锚点
        _er_lines = [ln.strip() for ln in excellent_review.replace("\r\n", "\n").split("\n") if ln.strip()]
        _er_first = _er_lines[0] if _er_lines else ""
        _er_last = _er_lines[-1] if len(_er_lines) > 1 else ""
        _er_anchor = ""
        if _er_first:
            _er_anchor += f"  ▸ 优秀范例开篇写法（你的开篇措辞请向其看齐）：{_er_first[:120]}\n"
        if _er_last and _er_last != _er_first:
            _er_anchor += f"  ▸ 优秀范例收尾写法（你的收尾建议的详略与口吻请向其看齐）：{_er_last[:120]}\n"
        segs.append(
            "【班级级优秀历史课评 · 最高优先级 · 主导写法模板 · 必须整体仿写】\n"
            "教师已上传本班「优秀历史课评范例」，它**就是本次课评的写法模板**。请**逐段仿写**它的写法：\n"
            "  · 保留它的【段落层次与段数】（与范例一致的多个自然段，段间一个空行，不要强行压成 2 段）；\n"
            "  · 保留它的【专业维度词与句式】（如「课堂常规/纪律」「运动负荷」「技术环节/动作」「学生表现」「教学目标达成」「家庭巩固建议」等），"
            "不要用通用的「课堂内容总结/课后评价」这类框架词替代；\n"
            "  · 保留它的【专业口吻与详略】。\n"
            "① 优秀范例全文（请逐段体会其写法，本次课评要按它的结构与口吻来写）：\n" + excellent_review + "\n"
            "② 优秀范例拆出的「评价维度顺序 + 专业术语参考」：\n" + _skel_text + "\n"
            "⚠ 只把内容替换为该生本节课真实表现（来自课件/标签/评语），**绝不可照抄范例原句、不搬范例里的人名/数据/具体事件**；"
            "但段落骨架、维度词、句式口吻必须明显向范例看齐，让全班课评保持统一质感。\n"
            "⚠ 禁止在输出中使用 markdown 标题（如 # / ###），必须保持与优秀范例一致的自然段落写法。\n"
            + (_er_anchor if _er_anchor else "")
        )
    if history_reviews:
        segs.append(
            "【该生历史课评 · 次优先级 · 在跟随优秀模板基础上，保持该生个性化表现连贯】\n"
            + "\n---\n".join(history_reviews)
        )
    if style_examples:
        segs.append("【风格样本 · StyleSample · 仅在无优秀课评与历史课评时作兜底】\n" + "\n---\n".join(style_examples))
    if segs:
        style_block = "以下是本次课评的写法模板与参考（按优先级从高到低排列，优先参考排在最前的）：\n" + "\n\n".join(segs)

    # 本学科写作指南：强学科锚点，明确本学科术语与必写评价角度（始终注入）
    subject_block = ""
    if subject_template or subject_code:
        open_example = SUBJECT_OPENING.get(subject_code, SUBJECT_OPENING["other"])
        subj_name = (preset.name if preset else (subject_code or "本学科"))
        subject_block = (
            "【本学科写作要点 · 必须采纳，直接决定本文的学科味道】\n"
            f"本学科是「{subj_name}」。请严格按其中的「学科专属术语 / 评价角度 / 该突出的行为」来写，"
            "务必让课评体现出本学科的专业质感，而非放之四海皆准的通用套话。\n"
        )
        if not excellent_review:
            # 有「班级级优秀历史课评」作主导模板时，段落结构由优秀模板主导，不再强制学科范式
            subject_block += (
                "特别注意：\n"
                "① 全文严格两段，**知识点归知识点、课评归课评**："
                "第 1 段只写本节课知识点（直接以「1.」开头的编号罗列，不写称呼、不写评价、不写引导语）；"
                "第 2 段才是写给孩子/家长看的课后评价。\n"
                "② 第 2 段【课后评价】的第一句必须按下方【本学科课评开头范式】来写，用具体行为/能力/作品起头，"
                "**严禁**以「你今天表现得非常专注/很棒/真棒/表现得很出色」这类空泛夸法开头。\n"
                f"【本学科课评开头范式 · 用于第 2 段首句 · 必须模仿此句式】\n{open_example}\n"
            )
        subject_block += (
            "· 结尾家庭建议也要结合本学科具体动作（如书法的「中锋行笔/间架结构」、舞蹈的「软度/核心力量」、"
            "编程的「调试/变量」），不要泛泛写「多练习」。\n"
            + (subject_template + "\n" if subject_template else "")
        )
        if subject_template:
            # 铁律：学科模板只是「格式 + 写法示范」，严禁抄其内容（含示例原句/人名/题量/课次等具体数据）
            subject_block += (
                "\n【⚠ 课评模板使用铁律 · 违反即作废】\n"
                "上方【本学科课评模板】**仅是格式与写法示范**（结构骨架 + 学科评价角度/术语/可突出行为），"
                "**严禁照抄模板中的示例原句、人名、分数、题量、课次等任何具体数据**——"
                "模板里的「语感范例」只用来体会语气与角度，**绝不可原样搬进你的输出**。\n"
                "你写的每一句话都必须**基于本节课真实的【课件/教案正文】、【教师标签】、【一句话评语】**重新组织；"
                "若模板范例里出现了「43 道题」「5 节课」这类数字，你**绝不许沿用**，必须换成本节课实际上课内容对应的真实信息"
                "（没有真实信息时宁可省略，不许编造）。\n"
                "即：模板决定「怎么写、写哪几个角度」，内容必须来自本节课的教案/笔记/标签，**绝不能照抄模板示例**。\n"
            )

    # 同类别学科优秀课评：始终作为学科味道锚点（不再仅作无历史兜底），学习其专业词汇与评价角度
    lib_block = ""
    if library_example:
        lib_block = (
            "【同类别学科优秀课评范例 · 本学科专属，请学习其表达方式】\n"
            "⚠ 重点学习其**学科专属的表达方式、专业词汇与评价角度**"
            "（如编程的 cin/cout、整数除法、取模、AC；书法的间架结构、中锋行笔、握笔坐姿；"
            "舞蹈的软度、核心力量、脚背；美术的造型、涂色、观察力；体育的体能、技术动作、意志品质），"
            "让输出一眼就是这门课而不是通用模板；"
            "但**严禁照搬其中的人名、称呼语、具体事件或数据**，"
            "一律用下方【当前学生信息】与【教师标签/评语】的真实信息替换。\n"
            + library_example + "\n"
        )

    system = BASE_RULES + "\n" + preset_block + subject_block + style_block + lib_block
    if _is_group_style(preset):
        system += "\n" + _GROUP_STYLE_EXEMPTION
    if trial:
        system += "\n" + _TRIAL_RULES
    if correction_note:
        system += (
            "\n【⚠ 上一稿不合格，本次必须修正以下问题（最高优先级）】\n"
            + correction_note + "\n"
        )

    # —— user 侧 ——
    cw = (courseware_text or "").strip()
    cw_block = (
        "【本节课课件/教案正文（这是本节课实际讲授的内容，请在课评**第①段「课堂内容总结」**中据此按 1./2./3. 编号列出本节课教了什么；"
        "结尾家庭建议禁止照抄其中的通用建议原文，须结合该生表现个性化重写）】\n"
        + cw + "\n"
    ) if cw else "（本节课未上传课件，请根据本节课标题与知识点目标概括课堂内容总结）\n"
    objs = lesson_info.get("objectives") or []
    obj_block = f"【本节课知识点目标】\n{ '、'.join(objs) }\n" if objs else ""
    common = lesson_info.get("common_notes") or ""
    common_block = f"【全班共性表现】\n{common}\n" if common else ""
    title = lesson_info.get("title") or "本节课"

    ref_block = ""
    if reference_opening:
        ref_block = f"【参考开头句（你的开头需明显区别于它）】\n{reference_opening}\n"

    tags = quick_tags or []
    if tags:
        tag_block = (
            f"【教师点选的快捷标签 · 该生本节课真实表现定调，必须如实体现】{ '、'.join(tags) }\n"
            f"⚠ 上述标签是老师对该生本节课的真实评价，课评的【分维度表现】与【可提升点】必须明确呼应"
            f"每一个待改进标签（如含「概念混淆」「需巩固」「偶尔走神」等，必须写出对应的具体不足与改进方向，"
            f"不得用泛泛的「可提升注意力」「继续加油」之类空话替代，也不得与标签矛盾写正面空话）。\n"
        )
    else:
        tag_block = ""
    note_block = f"【教师填写的本节课一句话评语】{one_sentence}\n" if one_sentence else ""

    call_name = preferred_name or student_name
    group_style = _is_group_style(preset)

    # 本学科「开头范式」填入真实昵称，作为最高优先级硬性要求注入 user 侧（弱模型对 system 中的长指令依从度低）
    open_filled = ""
    if subject_code in SUBJECT_OPENING:
        oe = SUBJECT_OPENING[subject_code]
        open_filled = re.sub(r'^(?:[一-龥]{1,4}|XX)(?=，)', call_name, oe, count=1)
    name_warn = (
        f"⚠ 本篇课评只写给「{call_name}」一个人，全文称呼必须原样使用「{call_name}」，"
        f"禁止改成别的名字。\n"
        if group_style else
        f"⚠ 本篇课评只写给「{call_name}」一个人，全文称呼必须原样使用「{call_name}」，"
        f"禁止改成别的名字，禁止用「各位家长」「亲爱的家长」等群发称呼。\n"
    )
    student_block = (
        f"【当前学生信息】\n姓名：{student_name}\n"
        f"昵称：{call_name}\n"
        f"性别：{gender or '未提供'}\n"
        + name_warn
    )

    open_req = ""
    if open_filled and not excellent_review:
        open_req = (
            f"\n【段落职责硬性要求 · 最高优先级 · 违反即不合格】\n"
            f"· 第①段＝本节课知识点：**必须直接以「1.」开头**，整段只罗列知识点；"
            f"段内禁止出现「{call_name}」的称呼，禁止任何铺垫叙事与引导语"
            f"（「以下是本节课的内容总结：」「在这个项目中，你不仅学会了……」这类一律不许写）。\n"
            f"· 第②段＝课后评价：**它的第一句**必须严格以以下句式起头（已为你填入该生昵称「{call_name}」）：\n"
            f"　　{open_filled}\n"
            f"严禁把第②段首句写成「{call_name}，你今天表现得很棒/非常专注/非常出色/真棒」这类空泛夸法。\n"
            f"· **严禁**在第②段课后评价的中间再夹一整段知识点介绍或课程内容罗列——知识点只出现在第①段。\n"
            f"若段落职责不符合上述要求，视为不合格，会被强制重生成。\n"
        )
    elif excellent_review:
        open_req = (
            f"\n【开头硬性要求 · 最高优先级 · 对齐优秀课评模板 · 违反即不合格】\n"
            f"本文第一句必须仿写上方【班级级优秀历史课评】的开篇方式：以本节课教学主题/体系概述起头"
            f"（例如「本周/本节课…教学以…为主要内容」「本节课主要围绕…开展教学」「课前组织…环节衔接顺利」），"
            f"**严禁**以「{call_name}，你今天…」「{call_name}，今天在…课上」这种空泛称呼起头。若违反视为不合格。\n"
        )
    # 输出结构要求：有优秀课评时整体仿写其模板（多段维度化），否则严格 2 段 + 编号
    if excellent_review:
        summary_req = ""
        head_req = ""  # 有优秀时不开头硬称呼（由 open_req 要求仿写优秀开头）
        fmt_req = (
            "\n【输出格式要求 · 整体仿写优秀课评模板 · 不可违反】\n"
            "· 请整体仿写上方【班级级优秀历史课评】的写法：段落层次、段数、维度顺序、句式口吻都向它看齐"
            "（段与段之间用恰好一个空行分隔），不要强行压成 2 段。\n"
            "· 必须用优秀范例里的专业维度词（如课堂常规、运动负荷、技术环节、学生表现、教学目标达成、家庭巩固等）"
            "来组织内容，不要用「课堂内容总结/课后评价」等通用框架词。\n"
            "· 禁止 markdown 标题（# / ###），保持与优秀范例一致的自然段落写法。\n"
            f"· emoji 数量至少 {preset.emoji_min if preset else 2} 个、推荐 2-3 个，分散在亮点/建议等位置。\n"
        )
    else:
        summary_req = (
            "第 1 段＝【课堂内容总结】：**整段只写本节课的知识点**，**直接以「1.」开头**，"
            "按 1./2./3. 编号逐条列出本节课实际讲授的知识点/主题/活动，"
            "每条都必须从上方【本节课课件/教案正文】中抽取或紧贴其意，**严禁添加上传文本中没有的主题**"
            "（如教师写的是 Python 代码百钱百鸡，输出里就必须出现「百钱/鸡翁/range」等关键词；"
            "如教师未上传课件，则用本节课标题与知识点目标概括但仍要编号）。"
            f"⚠ 第 1 段里禁止出现「{call_name}」的称呼、禁止「以下是本节课的内容总结：」这类引导语、"
            "禁止任何对该生表现的评价——这些一律放到第 2 段。"
        )
        head_req = ("" if group_style else f"第 2 段【课后评价】的第一句必须直接称呼「{call_name}」本人。")
        fmt_req = (
            "\n【输出格式硬要求 · 不可违反】\n"
            "· 必须只有 2 段，且**知识点归知识点、课评归课评**：\n"
            "  第 1 段＝【课堂内容总结】——纯知识点，直接以「1.」起头的 1./2./3. 编号要点，不带称呼、不带评价、不带引导语；\n"
            f"  第 2 段＝【课后评价】——写给「{call_name}」的评价（首句点名 + 具体表现 + 亮点 + 1 个可提升点 + 1 条家庭建议，连贯一段）。\n"
            "  两段之间恰好一个空行（\\n\\n）。\n"
            "· 第 1 段内部的 1./2./3. 编号项之间只用一个换行（不要在编号项之间插空行）；第 2 段内部不得插入空行。\n"
            "· **严禁**在第 2 段课后评价中间再夹一整段知识点罗列或课程内容介绍——知识点只允许出现在第 1 段。\n"
            f"· emoji 数量至少 {preset.emoji_min if preset else 2} 个、推荐 2-3 个，分散在第 2 段的开头/亮点/建议等位置，**不要只放 1 个也不要堆在开头**。\n"
        )

    user_content = (
        f"本节课标题：{title}\n"
        + obj_block + cw_block + common_block
        + tag_block + note_block
        + student_block + ref_block + open_req
        + f"\n请基于以上为「{call_name}」撰写本节课的课评。"
        + head_req
        + summary_req
        + fmt_req
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
