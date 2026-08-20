# -*- coding: utf-8 -*-
"""K12 SKILL 教案(lesson.json) → class-course-content SKILL 课件(form["plan"]) 适配器。

K12 `k12-lesson-planning` SKILL 产出 lesson.json：
  shared{grade,subject,duration,standard_code,standard_text,...}
  documents[].sections[].blocks[]  （paragraph/labeled/list/callout/from_shared/data_table/phase_header...）

class-course-content 课件端的生成读 form["plan"]，且只认这 4 个键（_one_line 兼容 list/str）：
  objectives (教学目标) / keypoints 或 重难点 (重难点)
  practice   或 分层练习 (分层练习要点)
  process    或 教学过程 (教学过程要点)

本适配器把 K12 的 lesson_plan 文档抽取成这 4 个字段，供课件端做 grounded 上下文。
"""
import json, re, os


# ---------------------------------------------------------------------------
# 1) block → 可读文本（递归解析 from_shared）
# ---------------------------------------------------------------------------
def block_to_text(block, shared):
    if block is None:
        return ""
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return str(block)

    btype = block.get("type")
    if btype == "from_shared":
        key = block.get("key")
        val = shared.get(key) if isinstance(shared, dict) else None
        if val is None:
            return ""
        if isinstance(val, str):
            return val
        if isinstance(val, list):
            return "\n".join(block_to_text(b, shared) for b in val)
        # 单个 block 或分面对象
        if isinstance(val, dict):
            # 分面 {teacher, student, stimulus}：课件面向教师，取 teacher 或合并
            if "teacher" in val or "student" in val:
                parts = []
                if val.get("teacher") is not None:
                    parts.append(block_to_text(val["teacher"], shared))
                if val.get("student") is not None:
                    parts.append(block_to_text(val["student"], shared))
                return "\n".join(p for p in parts if p)
            return block_to_text(val, shared)
        return str(val)

    if btype in ("paragraph", "h2", "h3"):
        return (block.get("text") or "").strip()

    if btype == "labeled":
        label = block.get("label", "")
        text = block.get("text", "")
        return f"{label}：{text}".strip("：") if label else text

    if btype == "callout":
        label = block.get("label", "")
        text = block.get("text", "")
        return f"{label}：{text}".strip("：") if label else text

    if btype == "list":
        items = block.get("items", []) or []
        prefix = (block.get("label") or "") + ("：" if block.get("label") else "")
        return prefix + "；".join(str(i) for i in items)

    if btype == "data_table":
        headers = block.get("headers", []) or []
        rows = block.get("rows", []) or []
        lines = ["　".join(str(h) for h in headers)]
        for r in rows:
            lines.append("　".join(str(c) for c in r))
        return "\n".join(lines)

    if btype == "phase_header":
        name = block.get("name", "")
        minutes = block.get("minutes", "")
        return f"{name}（{minutes}分钟）" if minutes else name

    if btype in ("fill_table", "workspace", "number_line", "page_break", "cards", "checklist", "group", "columns"):
        # 这些对课件 grounded 上下文价值低，跳过（但 group/columns 展开子块）
        if btype == "group":
            return "\n".join(block_to_text(b, shared) for b in block.get("blocks", []) or [])
        if btype == "columns":
            return "\n".join(
                block_to_text(b, shared) for b in (block.get("left", []) or []) + (block.get("right", []) or [])
            )
        return ""

    # 兜底：能拿 text 就拿
    if "text" in block:
        return str(block["text"]).strip()
    return ""


def section_texts(section, shared):
    """返回该 section 所有 block 的文本列表（每项一块）。"""
    out = []
    for b in section.get("blocks", []) or []:
        t = block_to_text(b, shared).strip()
        if t:
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# 2) 从 lesson_plan 文档抽取 4 字段
# ---------------------------------------------------------------------------
PHASE_KEYWORDS = ("导入", "新授", "探究", "练习", "巩固", "应用", "拓展", "小结", "总结", "作业", "检测", "复习", "展示", "交流")
_MINUTES_RE = re.compile(r"[（(]?\s*(\d+)\s*分钟\s*[)）]?")


def _heading_minutes(heading):
    m = _MINUTES_RE.search(heading)
    return int(m.group(1)) if m else None


def _is_phase_section(heading):
    if _MINUTES_RE.search(heading):
        return True
    return any(heading.strip().startswith(k) for k in PHASE_KEYWORDS)


def _fmt_phase(cur):
    name = cur.get("name", "")
    mins = cur.get("minutes", "")
    line = f"{name}（{mins}分钟）" if mins else name
    act = "；".join(cur.get("act", []))
    if len(act) > 140:
        act = act[:140] + "…"
    if act:
        line += "：" + act
    return line


def extract_plan(lesson):
    shared = lesson.get("shared", {}) or {}
    docs = lesson.get("documents", []) or []
    lp = next((d for d in docs if d.get("id") == "lesson_plan"), None)
    if lp is None:
        # 退化：取第一个文档
        lp = docs[0] if docs else {"sections": []}
    sections = lp.get("sections", []) or []

    objectives, keypoints, process, practice_parts = [], [], [], []

    for sec in sections:
        heading = (sec.get("heading") or "").strip()
        texts = section_texts(sec, shared)

        # 教学目标
        if "目标" in heading and ("学习" in heading or "教学" in heading or "课时" in heading):
            objectives.extend(texts)
            continue

        # 教学重难点
        if "重难点" in heading or heading in ("教学重点", "教学难点", "重点难点"):
            keypoints.extend(texts)
            continue

        # 教学过程：优先从 phase_header 块抽环节（含分钟数与活动）
        if "过程" in heading or "环节" in heading:
            cur = None
            for b in sec.get("blocks", []) or []:
                if isinstance(b, dict) and b.get("type") == "phase_header":
                    if cur:
                        process.append(_fmt_phase(cur))
                    cur = {"name": b.get("name", ""), "minutes": b.get("minutes", ""), "act": []}
                else:
                    t = block_to_text(b, shared).strip()
                    if t and cur is not None:
                        cur["act"].append(t)
            if cur:
                process.append(_fmt_phase(cur))
            continue

        # 兜底：整段 section 标题本身是环节（如"导入（6分钟）"）也按环节处理
        if _is_phase_section(heading):
            mins = _heading_minutes(heading)
            phase_name = _MINUTES_RE.sub("", heading).strip("（）() ").strip()
            summary = "；".join(texts)
            if len(summary) > 120:
                summary = summary[:120] + "…"
            line = f"{phase_name}（{mins}分钟）" if mins else phase_name
            if summary:
                line += "：" + summary
            process.append(line)
            continue

        # 分层练习 / 差异化 / 作业
        if any(k in heading for k in ("分层", "差异化", "练习", "作业")):
            practice_parts.extend(texts)
            continue

    # 兜底：没抽到重难点时用课标原文充作重难点
    if not keypoints:
        st = shared.get("standard_text")
        if st:
            keypoints = [st]

    plan = {
        "objectives": objectives,
        "keypoints": keypoints,
        "practice": "\n".join(practice_parts) if practice_parts else "",
        "process": process,
    }
    return plan


# ---------------------------------------------------------------------------
# 3) 顶层身份（给 orchestrator 填 form 的 subject/grade/topic/duration）
# ---------------------------------------------------------------------------
def extract_identity(lesson):
    shared = lesson.get("shared", {}) or {}
    lp = next((d for d in lesson.get("documents", []) or [] if d.get("id") == "lesson_plan"), None)
    title = lp.get("title", "") if lp else ""
    topic = title.split("——")[0].split("——")[0].strip() if title else ""
    # title 可能含副标题，取主标题
    if "——" in title:
        topic = title.split("——")[0].strip()
    return {
        "subject": shared.get("subject", ""),
        "grade": shared.get("grade", ""),
        "duration": shared.get("duration", 40),
        "topic": topic,
        "standard_code": shared.get("standard_code", ""),
        "standard_text": shared.get("standard_text", ""),
    }


# ---------------------------------------------------------------------------
# 4) 一体化入口
# ---------------------------------------------------------------------------
def k12_lesson_to_form(lesson_path):
    """读 lesson.json，返回 (identity, plan)。"""
    with open(lesson_path, "r", encoding="utf-8") as f:
        lesson = json.load(f)
    identity = extract_identity(lesson)
    plan = extract_plan(lesson)
    return identity, plan


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "out/lesson_k12_分数的初步认识.json"
    ident, plan = k12_lesson_to_form(p)
    print("=== identity ===")
    print(json.dumps(ident, ensure_ascii=False, indent=2))
    print("\n=== plan(objectives/keypoints/practice/process) ===")
    print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))
