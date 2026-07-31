"""四源 prompt 合成。

最终发给模型的 messages =
  system: 类型预置(维度/语气/字数) + 风格样本 + 硬规则(R1-R7，含 R2b 防投诉、R2c 防编造)
  user:   课件/教案 + 该生历史课评 + 当前学生信息(已脱敏) + 全班共性

姓名脱敏在送入前由 redact 处理（见 redact.Redactor），本模块收到的 student_name
已是占位符（如 {{STU}}），还原在生成返回后做。
"""
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
    "  · R2b 禁止横向比较（不得出现「比其他同学」「比上次进步最大」等任何与其他学员对比的表述）。\n"
    "  · R2c 禁止编造未提供的具体事实：不得虚构分数、排名、比赛结果、具体时长（如「用了20分钟」）、"
    "他人姓名、未见过的事件细节。只写老师真实提供的表现；信息不足时宁可简短，也不要编造。\n"
    "R3 结构：开头一句整体肯定 → 分维度写具体表现 → 结尾给 1 条可落地的家庭巩固建议。\n"
    "R4 字数：按机构类型要求控制在给定区间内，宁短勿空。\n"
    "R5 emoji：按机构类型要求在开头/结尾点缀，数量达标即可，不要堆砌。\n"
    "R6 去重：若提供了「参考开头句」，你的开头要明显区别于它，避免同班课评开头雷同被家长横向对比发现。\n"
    "R7 具体优先：用「主动举手」「完成了X步骤」这类可观察行为，替代「表现很好」这类空话。\n"
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


_TRIAL_RULES = (
    "【试听课特别提示】这是一节试听课的课评，它往往决定家长是否报名，价值最高。\n"
    "请按以下结构：① 初次上课的整体印象与专注度 ② 该生在本节课展现的潜力点（具体、可观察）\n"
    "③ 与这门课的适配度 ④ 后续学习路径建议（1-2 条）。语气温暖、建立信任，但同样遵守 R2c 不编造。\n"
)


def build_messages(preset, student_name, preferred_name, lesson_info,
                   courseware_text, history_reviews, style_examples,
                   trial=False, reference_opening=None):
    """构造发送给 LLM 的 messages 列表。

    lesson_info: dict(title, common_notes, objectives)
    所有姓名相关字段（student_name/preferred_name/history/style）应为已脱敏的占位符。
    """
    preset_block = _preset_block(preset)
    style_block = ""
    if style_examples:
        style_block = "以下是该老师过往课评范文，请严格模仿其行文风格：\n" + "\n---\n".join(style_examples)

    system = BASE_RULES + "\n" + preset_block + style_block
    if trial:
        system += "\n" + _TRIAL_RULES

    # —— user 侧 ——
    cw = (courseware_text or "").strip()
    cw_block = f"【本节课课件/教案正文】\n{cw}\n" if cw else "（本节课未上传课件）\n"
    hist = "\n".join(history_reviews) if history_reviews else ""
    hist_block = f"【该生历史课评（用于保持风格连贯，注意是同一学生）】\n{hist}\n" if hist else ""
    objs = lesson_info.get("objectives") or []
    obj_block = f"【本节课知识点目标】\n{ '、'.join(objs) }\n" if objs else ""
    common = lesson_info.get("common_notes") or ""
    common_block = f"【全班共性表现】\n{common}\n" if common else ""
    title = lesson_info.get("title") or "本节课"

    ref_block = ""
    if reference_opening:
        ref_block = f"【参考开头句（你的开头需明显区别于它）】\n{reference_opening}\n"

    student_block = (
        f"【当前学生信息】\n姓名：{student_name}\n"
        f"昵称：{preferred_name or student_name}\n"
    )

    user_content = (
        f"本节课标题：{title}\n"
        + obj_block + cw_block + hist_block + common_block
        + student_block + ref_block
        + "\n请基于以上为这名学生撰写本节课的课评。"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
