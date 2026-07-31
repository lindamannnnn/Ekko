"""阶段/期末总结 prompt 合成。

把某生一段时间内的 confirmed 课评二次合成：3 条成长线索（引用具体课次行为）+ 1-2 个关注点及建议，
400-700 字。沿用 R2c 防编造（只引用真实课评里出现的行为，不得新增未提供的事实）。
"""


def build_summary_messages(preset, student_name, snippets, period_label):
    """snippets: list of {date, class_name, content}；均为已脱敏占位符文本。"""
    dims = preset.dimensions if preset and preset.dimensions else []
    dim_hint = "、".join(dims) if dims else "通用维度"

    system = (
        "你是少儿培训机构的阶段总结助手，为家长写一份阶段/期末成长总结。\n"
        "要求：\n"
        "1. 提炼 3 条成长线索，每条必须引用具体课次里真实出现的行为（如某节课学会了X、某次主动展示了Y），"
        "不得编造未提供的事件、分数或时长（R2c）。\n"
        "2. 给出 1-2 个后续关注点及可落地的家庭建议。\n"
        "3. 字数 400-700 字，语气温暖、鼓励、具体。\n"
        f"4. 评价维度参考：{dim_hint}。\n"
    )

    if not snippets:
        user = f"学生：{student_name}\n时间段：{period_label}\n（暂无课评记录，请写一段通用的鼓励性阶段小结，并提示老师补充。）"
    else:
        lines = []
        for s in snippets:
            lines.append(f"【{s.get('date') or '某课次'} · {s.get('class_name') or ''}】\n{s.get('content')}")
        user = (
            f"学生：{student_name}\n时间段：{period_label}\n"
            "以下是该生多节课的课评片段（用于提炼成长线索）：\n\n" + "\n\n".join(lines)
        )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
