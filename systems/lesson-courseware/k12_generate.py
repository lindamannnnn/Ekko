# -*- coding: utf-8 -*-
"""脚本化 K12 教案生成（等价「基于 k12-lesson-planning SKILL」）。

把 K12 SKILL 的「路由 → 课标锚定 → 构建 lesson.json」流程固化为可直接调用的函数，
使网页后台 / orchestrator 无需 agent 在线即可产出 lesson.json。

- 课标 grounding：运行时读取 k12-lesson-planning 的 curriculum/<学科>.md，按年级 band 抽取对应学段内容要求，注入 prompt，根治"教案超纲"。
- 结构：lesson.json（shared + documents[lesson_plan]），与 K12 SKILL 的 schema 一致。
- 复用 courseware_engine.textutil.extract_json 做稳健 JSON 解析。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from courseware_engine.textutil import extract_json  # noqa: E402
from courseware_engine.kb import retrieve_kb  # noqa: E402

# 课标 references 目录：
# 1) 环境变量 K12_SKILL_DIR 优先级最高（可覆盖任何路径）
# 2) 开发机优先用本地安装的 k12-lesson-planning SKILL
# 3) 生产/Docker 回退到项目内置的 references/ 目录（已随仓库/镜像打包）
_LOCAL_SKILL_DIR = os.path.expanduser(r"~/.workbuddy/skills/k12-lesson-planning/references")
_BUNDLED_SKILL_DIR = os.path.join(HERE, "references")
SKILL_DIR = os.environ.get("K12_SKILL_DIR")
if SKILL_DIR is None:
    SKILL_DIR = _LOCAL_SKILL_DIR if os.path.isdir(_LOCAL_SKILL_DIR) else _BUNDLED_SKILL_DIR

# 学科 → (课标文件, 学科指令文件)
SUBJECT_FILES = {
    "数学": ("curriculum/math.md", "math.md"),
    "语文": ("curriculum/yuwen.md", "ela.md"),
    "英语": ("curriculum/english.md", "english.md"),
}

_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


# ---------------------------------------------------------------------------
# 年级 → 学段 band
# ---------------------------------------------------------------------------
def _band(grade):
    s = str(grade or "")
    if "初" in s:
        return "第四学段"
    num = None
    for ch, v in _CN.items():
        if ch in s:
            num = v
            break
    if num is None:
        m = re.search(r"\d+", s)
        if m:
            num = int(m.group())
    if num is None:
        num = 5  # 默认高段
    if num <= 2:
        return "第一学段"
    if num <= 4:
        return "第二学段"
    if num <= 6:
        return "第三学段"
    return "第四学段"


# ---------------------------------------------------------------------------
# 课标抽取：按 band 切出对应学段内容要求
# ---------------------------------------------------------------------------
def _load_text(rel):
    if not os.path.isdir(SKILL_DIR):
        raise RuntimeError(
            f"未找到 k12-lesson-planning 课标 references 目录：{SKILL_DIR}\n"
            f"请先安装该 SKILL，或设置环境变量 K12_SKILL_DIR 指向其 references 目录。"
        )
    with open(os.path.join(SKILL_DIR, rel), "r", encoding="utf-8") as f:
        return f.read()


def extract_band_standard(cur_text, band):
    """从课标原文切出 '### {band}（...）' 整段。"""
    pat = re.compile(r"###\s*" + re.escape(band) + r"（[^）]*）\s*\n(.*?)(?=\n###\s|\Z)", re.S)
    m = pat.search(cur_text)
    if m:
        return m.group(1).strip()
    idx = cur_text.find(band)
    if idx >= 0:
        return cur_text[idx : idx + 1200].strip()
    return cur_text[:1500]


# ---------------------------------------------------------------------------
# 学段教学风格（低/高/初中分化，沿用系统B既有 band 思路）
# ---------------------------------------------------------------------------
BAND_STYLE = {
    "第一学段": "小学低段(1-2年级)：多用实物/操作/情境/图示，语言口语化、短句；重直观感知与兴趣，板书用大图示。",
    "第二学段": "小学中段(3-4年级)：操作与半抽象过渡，开始建立算理/概念结构，配合线段图/图示。",
    "第三学段": "小学高段(5-6年级)：重算理与结构，概念本质与联系，分层练习（基础→变式→拓展），板书结构化（脉络/对比）。",
    "第四学段": "初中(7-9年级)：重概念本质、推导与知识网络，强调逻辑推理与抽象概括，板书结构化（树状/对比/易错标注）。",
}


# ---------------------------------------------------------------------------
# 紧凑 schema + 固定 6 section 范例
# ---------------------------------------------------------------------------
SCHEMA_HINT = """\
lesson.json 顶层结构：
{
  "shared": {"subject": "学科", "grade": "年级（含学段，如 五年级（小学第三学段））", "duration": 40,
             "standard_code": "课标2022年版·<学段>·<领域>·<主题>", "standard_text": "课标内容要求原文(≤30字)",
             "domain": "数与代数/图形与几何/统计与概率/综合与实践(选填)"},
  "theme": {"primary": "#b45309"},
  "documents": [
    {"id": "lesson_plan", "audience": "teacher", "eyebrow": "年级 学科 · 课时方案",
     "title": "课题名", "meta": "课标2022年版·<学段>·<领域> · 教材：人教版2024修订 · 时长分钟",
     "sections": [ {"heading": "学习目标", "blocks": [{"type":"paragraph","text":"..."}]},
                   {"heading": "教学重难点", "blocks": [{"type":"labeled","label":"重点","text":"..."},{"type":"labeled","label":"难点","text":"..."}]},
                   {"heading": "教学过程", "blocks": [
                      {"type":"phase_header","name":"导入","minutes":6},
                      {"type":"paragraph","text":"导入活动描述..."},
                      {"type":"phase_header","name":"新授","minutes":16},
                      {"type":"paragraph","text":"新授活动描述..."},
                      {"type":"phase_header","name":"巩固练习","minutes":10},
                      {"type":"paragraph","text":"练习描述..."},
                      {"type":"phase_header","name":"小结","minutes":4},
                      {"type":"paragraph","text":"小结描述..."},
                      {"type":"phase_header","name":"作业","minutes":4},
                      {"type":"paragraph","text":"分层作业描述..."} ]},
                   {"heading": "分层练习", "blocks": [
                      {"type":"labeled","label":"基础","text":"..."},
                      {"type":"labeled","label":"提高","text":"..."},
                      {"type":"labeled","label":"拓展","text":"..."} ]},
                   {"heading": "板书设计", "blocks": [{"type":"paragraph","text":"..."}]},
                   {"heading": "作业", "blocks": [{"type":"paragraph","text":"..."}]} ]}
  ]
}
block 类型：paragraph(纯段) / labeled(标签+文本) / list(列表) / callout(突出) / phase_header(name,minutes) / from_shared(key) / data_table 。
"""

REQUIRED_SECTIONS = ["学习目标", "教学重难点", "教学过程", "分层练习", "板书设计", "作业"]


# ---------------------------------------------------------------------------
# 课题级教材原文锚（与课件端共用同一份 vendor/kb/ 知识库）
# ---------------------------------------------------------------------------
def kb_anchor_for_plan(entry):
    """构造教案向的事实锚文本：注入本课题教材原文 + 一致性约束。

    与课件端的 kb_block 不同，这里不禁止写板书/时间分配（教案本就要写），
    只保证『定义/公式/例题/数据 与原文一致，不引入原文未涵盖的算法』。
    检索逻辑与课件端完全一致（courseware_engine.kb.retrieve_kb），实现两端共用同一 KB。
    """
    if not entry:
        return ""
    src = entry.get("source", "")
    txt = entry.get("original_text", "")
    bits = []
    if entry.get("key_points"):
        bits.append("要点提示：" + "；".join(entry["key_points"]))
    if entry.get("formulas"):
        bits.append("公式/标准解法：" + "；".join(entry["formulas"]))
    if entry.get("cautions"):
        bits.append("⚠️ 易混警示：" + entry["cautions"])
    head = (
        "\n（以下是本课题的权威教材原文（人教版），教案中的定义、公式、例题、数据必须与之一致，"
        "严禁编造或张冠李戴；并严格按照本课题原文范围设计，不得引入原文未涵盖的后续算法或概念"
        "——若原文未出现通分、约分、异分母运算等，教案所有环节（含板书、小结、练习）严禁出现这些内容。）\n"
        f"（来源：{src}）\n--- 原文开始 ---\n{txt}\n--- 原文结束 ---\n"
    )
    if bits:
        head += "\n".join(bits) + "\n"
    return head


# ---------------------------------------------------------------------------
# 构建 prompt
# ---------------------------------------------------------------------------
def build_prompt(form):
    subject = form.get("subject", "数学")
    grade = form.get("grade", "五年级")
    topic = form.get("topic", "")
    duration = int(form.get("duration") or 40)

    cf, sf = SUBJECT_FILES.get(subject, SUBJECT_FILES["数学"])
    cur = _load_text(cf)
    subj_ref = _load_text(sf)
    band = _band(grade)
    std = extract_band_standard(cur, band)
    style = BAND_STYLE.get(band, BAND_STYLE["第三学段"])

    # 课题级教材原文（与课件端共用同一份 vendor/kb/）
    kb_entry = retrieve_kb({"subject": subject, "grade": grade, "topic": topic})
    kb_anchor = kb_anchor_for_plan(kb_entry)

    user = f"""# 课题信息
- 学科：{subject}
- 年级：{grade}
- 课题：{topic}
- 课时：{duration} 分钟
- 所属学段：{band}

# 课标内容要求（本学段，必须严格据此设计，不得超纲）
{std}

# 本课题教材原文依据（与课件端共用同一知识库 vendor/kb/，必须严格据此，禁止编造）
{kb_anchor}

# 学科教学结构指引（来自 K12 学科模板，遵循其环节与产出结构）
{subj_ref}

# 输出 schema
{SCHEMA_HINT}

# 硬性约束（务必遵守）
1. documents 数组只需包含 id="lesson_plan" 一个文档（本系统仅消费教案正文，不需学生材料/听课表）。
2. lesson_plan 的 sections 标题必须是这 6 个，顺序随意：{ " / ".join(REQUIRED_SECTIONS) }。
3. 教学过程 用 phase_header 块（{{"type":"phase_header","name":"环节名","minutes":N}}）表示每个环节，各环节 minutes 之和必须精确等于 {duration} 分钟；每个 phase_header 后跟 paragraph 描述该环节活动。
4. 严格在本学段课标内容要求范围内展开，严禁引入课标未涵盖的后续内容或算法。例如：若本课只讲同分母分数，严禁出现通分、约分、异分母分数运算；若只讲“初步认识”，不涉及运算算法。所有例题与练习必须可用本课已学方法直接求解。注意：板书设计、小结、练习中的每一句话也不得出现通分、约分、异分母、化简等未涵盖内容——只写本课范围内（如同分母比较/加减）的表述。
5. 学段教学风格：{style}
6. 落实“双减”：作业分层（基础/提高/拓展或基础/拓展/弹性），小学1-2年级不布置书面家庭作业。
7. 只输出合法 JSON，不要任何解释性文字、不要 Markdown 代码块围栏。

请输出 lesson.json。"""

    system = "你是资深中国 K-12 学科教研员，严格依据义务教育课程标准（2022年版）编写课时教案，教材依据人教版2024修订版教科书。你只输出符合 schema 的 lesson.json，不输出任何解释。"
    return system, user


# ---------------------------------------------------------------------------
# 校验 + 兜底
# ---------------------------------------------------------------------------
def _scope_allows_tonfen(form, shared):
    """判定本课范围是否允许出现 通分/约分/异分母（仅当课标/课题明确涵盖时才允许）。"""
    band = _band(form.get("grade", ""))
    cf = SUBJECT_FILES.get(form.get("subject", "数学"), SUBJECT_FILES["数学"])[0]
    std = extract_band_standard(_load_text(cf), band)
    scope = " ".join([
        str(form.get("topic", "")),
        str(shared.get("standard_text", "")),
        str(shared.get("standard_code", "")),
        std,
    ])
    return ("通分" in scope) or ("约分" in scope) or ("异分母" in scope)


_OVERSCOPE_KW = ("通分", "约分", "异分母", "化简", "公分母")


def _clean_text(t):
    """按小句丢弃含超纲算法的片段，保留同句正确部分。仅当本课不允许时才调用。"""
    parts = re.split(r"([，。；;])", t)
    out = []
    for i in range(0, len(parts), 2):
        clause = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        if any(k in clause for k in _OVERSCOPE_KW):
            continue
        out.append(clause + sep)
    return "".join(out).strip()


def _walk_clean(blocks, shared):
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if "text" in b and isinstance(b["text"], str):
            b["text"] = _clean_text(b["text"])
        if "label" in b and isinstance(b["label"], str):
            b["label"] = _clean_text(b["label"])
        if "items" in b and isinstance(b["items"], list):
            b["items"] = [_clean_text(str(i)) for i in b["items"]]
        if "blocks" in b and isinstance(b["blocks"], list):
            _walk_clean(b["blocks"], shared)
        if "rows" in b and isinstance(b["rows"], list):
            b["rows"] = [[_clean_text(str(c)) for c in r] for r in b["rows"]]
        if "headers" in b and isinstance(b["headers"], list):
            b["headers"] = [_clean_text(str(h)) for h in b["headers"]]


def clean_lesson(lesson, form):
    """教案级后置清洗：若本课范围不允许 通分/约分/异分母，删除所有相关小句（保留正确部分）。"""
    shared = lesson.get("shared", {}) or {}
    if _scope_allows_tonfen(form, shared):
        return lesson  # 本课确实教通分，不清洗
    for d in lesson.get("documents", []) or []:
        for sec in d.get("sections", []) or []:
            _walk_clean(sec.get("blocks", []), shared)
    # 顺带清洗 shared 中可能注册的超纲文本
    for k, v in list(shared.items()):
        if isinstance(v, str) and any(kw in v for kw in _OVERSCOPE_KW):
            shared[k] = _clean_text(v)
    return lesson


def _validate(data, form):
    if not isinstance(data, dict):
        raise ValueError("lesson.json 顶层不是对象")
    shared = data.setdefault("shared", {})
    shared.setdefault("subject", form.get("subject", ""))
    shared.setdefault("grade", form.get("grade", ""))
    shared.setdefault("duration", int(form.get("duration") or 40))
    docs = data.setdefault("documents", [])
    lp = next((d for d in docs if d.get("id") == "lesson_plan"), None)
    if lp is None:
        lp = {"id": "lesson_plan", "audience": "teacher", "title": form.get("topic", ""),
              "sections": []}
        docs.append(lp)
    headings = [s.get("heading") for s in lp.get("sections", [])]
    for h in REQUIRED_SECTIONS:
        if not any(h in (x or "") for x in headings):
            lp.setdefault("sections", []).append({"heading": h, "blocks": []})
    return data


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------
def generate_lesson(form, client, temperature=0.5, timeout=180, max_tokens=4000, verbose=False):
    """form: {subject, grade, topic, duration}。返回 lesson.json dict。"""
    # 强模型（推理型）的教案 JSON 输出可达 4000+ 字符，推理还会额外消耗 token；
    # 弱模型的 4000 上限对强模型不够，这里按模型强弱动态放宽（避免长教案被截断导致 JSON 解析失败）。
    if hasattr(client, "is_strong") and client.is_strong():
        max_tokens = max(max_tokens, 12000)
    system, user = build_prompt(form)
    raw = client.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        timeout=timeout,
        max_tokens=max_tokens,
    )
    data = extract_json(raw)
    data = _validate(data, form)
    data = clean_lesson(data, form)  # 教案级超纲清洗（仅当本课范围不允许时生效）
    if verbose:
        txt = json.dumps(data, ensure_ascii=False)
        print(f"  教案生成完成：sections={len(data.get('documents', [{}])[0].get('sections', [])) if data.get('documents') else 0}", flush=True)
        print(f"  教案超纲残留检测 通分={txt.count('通分')} 约分={txt.count('约分')} 异分母={txt.count('异分母')}", flush=True)
    return data


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    import os as _os

    load_dotenv(_os.path.join(HERE, ".env"))
    from courseware_engine.llm import LLMClient

    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", default="数学")
    ap.add_argument("--grade", default="五年级")
    ap.add_argument("--topic", default="分数的初步认识")
    ap.add_argument("--duration", type=int, default=40)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    client = LLMClient(
        api_key=_os.environ["AI_API_KEY"],
        base_url=_os.environ.get("AI_BASE_URL", ""),
        model=_os.environ.get("AI_MODEL", ""),
    )
    form = {"subject": a.subject, "grade": a.grade, "topic": a.topic, "duration": a.duration}
    lesson = generate_lesson(form, client)
    out = a.out or f"out/lesson_{a.subject}_{a.topic}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(lesson, f, ensure_ascii=False, indent=2)
    print("wrote", out)
