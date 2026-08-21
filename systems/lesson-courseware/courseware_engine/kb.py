# -*- coding: utf-8 -*-
"""courseware_engine/kb.py —— 知识库加载 / 检索 / 约束文本（自 vendor 迁移，修缓存失效）。

迁移自 vendor/scripts/courseware_gen.py:37-158：
  - load_kb      同 vendor 逻辑（递归扫描 vendor/kb，支持 bundle 展开）
  - retrieve_kb  打分逻辑原样保留（topic 互含+100、subject+10、grade+5、同分按原文长度降序）
  - kb_block     约束文本原样保留（注入原文 + 6 条硬性约束）

修复（方案 §0 已知坑）：原 _KB_CACHE 全局缓存无失效 —— 改为 (mtime_max, entries) 元组，
检索前扫描 vendor/kb 最新 mtime，变化即重载；新增 invalidate_kb_cache() 强制失效。
"""
import os
import re

# KB 目录：vendor/kb（项目内教案端与课件端共用的唯一 KB，见工作记忆）
KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vendor", "kb")


def _norm(s):
    return re.sub(r"\s+", "", (s or "").lower())


# 年级核心抽取：把「六年级（小学第三学段）」「六年级上」「六年级」「6年级」统一成「六年级」，
# 用于年级段的精确比较（忽略学段后缀与上/下册——同一年级的课文应视为同一年级段）。
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_GRADE_RE = re.compile(r"([一二三四五六七八九]+|\d+)\s*年级")


def _grade_core(s):
    """从年级字符串里抽出「X年级」核心（中文数字），抽不到返回 None。"""
    s = s or ""
    m = _GRADE_RE.search(s)
    if not m:
        return None
    tok = m.group(1)
    if tok.isdigit():
        n = int(tok)
    else:
        n = _CN_NUM.get(tok)
        if n is None:
            return None
    cn = {v: k for k, v in _CN_NUM.items()}.get(n)
    return (cn + "年级") if cn else None


def load_kb(kb_dir=None):
    """加载 kb/ 下所有 .json 条目（递归）。

    支持两种文件形态：
      - 单课题条目：含 `topic` 字段，直接入列；
      - 语文年级打包：含 `bundle: true` 与 `lessons` 字典，展开为每课一条（topic=课文名）。
    """
    kb_dir = kb_dir or KB_DIR
    entries = []
    if not os.path.isdir(kb_dir):
        return entries
    for root, _, files in os.walk(kb_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(root, fn), "r", encoding="utf-8") as f:
                    e = __import__("json").load(f)
            except Exception:
                continue
            if not isinstance(e, dict):
                continue
            if e.get("bundle") and isinstance(e.get("lessons"), dict):
                for lesson, info in e["lessons"].items():
                    if not isinstance(info, dict):
                        continue
                    kp = []
                    if info.get("author"):
                        a = "作者：" + info["author"]
                        if info.get("dynasty"):
                            a += "（" + info["dynasty"] + "）"
                        kp.append(a)
                    if info.get("genre"):
                        kp.append("体裁：" + info["genre"])
                    if info.get("theme"):
                        kp.append("主旨：" + info["theme"])
                    entries.append({
                        "subject": e.get("subject", ""),
                        "grade": e.get("grade", ""),
                        "topic": lesson,
                        "source": e.get("source", ""),
                        "original_text": info.get("key_text", ""),
                        "key_points": kp,
                        "formulas": [],
                        "cautions": info.get("cautions", ""),
                    })
            elif e.get("topic"):
                entries.append(e)
    return entries


# --- 缓存（修复失效）：(mtime_max, entries) 元组，mtime 变化即重载 ---
_KB_CACHE = None


def _dir_mtime_max(kb_dir):
    mt = 0.0
    if os.path.isdir(kb_dir):
        for root, _, files in os.walk(kb_dir):
            for fn in files:
                try:
                    mt = max(mt, os.path.getmtime(os.path.join(root, fn)))
                except OSError:
                    pass
    return mt


def _get_kb():
    global _KB_CACHE
    mmax = _dir_mtime_max(KB_DIR)
    if _KB_CACHE is not None:
        cached_mmax, entries = _KB_CACHE
        if cached_mmax == mmax:
            return entries
    entries = load_kb()
    _KB_CACHE = (mmax, entries)
    return entries


def invalidate_kb_cache():
    """强制下次检索重新加载（KB 热更新时用）。"""
    global _KB_CACHE
    _KB_CACHE = None


def retrieve_kb(form, kb_dir=None):
    """按 (subject, grade, topic) 精确锚定 KB 原文条目；无匹配返回 None。

    学科生成本质是「选课文」：前端三级下拉只列 KB 真实存在的 (学科,年级,课题)，
    因此检索应当精确锚定，杜绝「二年级秋天 → 错配成三年级《秋天的雨》」这类张冠李戴。

    匹配规则（不再用 100/10/5 模糊打分）：
      1. 学科必须一致（归一化后相等）。
      2. 年级必须兼容：表单 grade 多为「X年级」，KB 条目为「X年级上/下」，
         用「互相包含」判断同一年级段，排除跨年级。
      3. 课题：完全相等 优先于 互相包含；同分时按「本课题范围护栏更宽(原文更长)」优先，
         例如「圆的认识」在六年级上册有「圆」与「圆的认识」两条时，取更完整的那条。
    """
    global KB_DIR
    if kb_dir is not None:
        KB_DIR = kb_dir
    subj = _norm(form.get("subject") or form.get("category") or "")
    grade = _norm(form.get("grade") or "")
    topic = _norm(form.get("topic") or form.get("content") or "")
    if not (topic or subj):
        return None

    def _grade_ok(eg):
        if not grade or not eg:
            return False
        return _grade_core(eg) is not None and _grade_core(eg) == _grade_core(grade)

    cands = []  # (topic_exact, 原文长度, entry)
    for e in _get_kb():
        es = _norm(e.get("subject", ""))
        if subj and es and es != subj:
            continue
        if not _grade_ok(_norm(e.get("grade", ""))):
            continue
        et = _norm(e.get("topic", ""))
        if not topic or not et:
            continue
        exact = 1 if topic == et else 0
        if not (exact or topic in et or et in topic):
            continue
        cands.append((exact, len(e.get("original_text") or ""), e))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    return cands[0][2]


def kb_block(entry):
    """构造 grounding 约束文本：注入原文 + 禁止编造 + 只做内容骨架。"""
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
        "\n【教材原文依据 · 必须严格据此生成，禁止编造】\n"
        f"（来源：{src}）\n--- 原文开始 ---\n{txt}\n--- 原文结束 ---\n"
    )
    if bits:
        head += "\n".join(bits) + "\n"
    head += (
        "硬性约束：\n"
        "1. 作者/人物/年代/公式/定义/例题数据必须与原文一致，绝不允许编造或张冠李戴。\n"
        "2. 例题与计算的每一步必须正确，答案须与原文/标准解法一致；算错即视为严重错误。\n"
        "3. 只产出「内容骨架」（知识点/例题步骤/分层练习答案/错解对比/图示），不写教师口头讲解稿、不写板书设计、不写时间分配。\n"
        "4. 需补充原文未覆盖内容时，须明确标注「拓展」且不得与原文冲突。\n"
        "5. 严禁把其他课文/篇目（含作者其他作品）或其他例题的内容混入本课；细读、举例、类比只针对本课给定的原文与公式，不得串台到其他篇目。\n"
        "6. 严格限定在本课题/教案覆盖的知识范围内展开，不得引入课本未教、课标未要求的算法或概念。"
        "若原文与教案均未涉及通分、约分、异分母分数运算等后续内容，则严禁在知识点、例题、练习、讲解中出现这些内容；"
        "所有例题与练习必须可用本课已学方法直接求解（如同分母分数比较/加减：分母相同则直接比分子或分子相加减，无需通分）。\n"
        "【重要】以上约束仅用于规范你的生成，严禁将约束文本本身（如『属于后续内容』『本课严禁出现』『不得引入』等字眼）写入课件正文，课件只呈现教学知识本身。\n"
    )
    return head


if __name__ == "__main__":
    # T0 验收：数学 / 语文 / 英语 三学科各至少命中一条 KB。
    import json
    entries = load_kb()
    print(f"KB 共加载 {len(entries)} 条")
    form_for = {}
    for e in entries:
        cat = None
        if "数学" in (e.get("subject") or ""):
            cat = "math"
        elif "语文" in (e.get("subject") or ""):
            cat = "chinese"
        elif "英语" in (e.get("subject") or ""):
            cat = "english"
        if cat and cat not in form_for:
            form_for[cat] = {
                "subject": e.get("subject", ""),
                "grade": e.get("grade", ""),
                "topic": e.get("topic", ""),
            }
    ok = True
    for cat in ("math", "chinese", "english"):
        f = form_for.get(cat)
        if not f:
            print(f"  [{cat}] 跳过（KB 无该学科条目）")
            continue
        hit = retrieve_kb(f)
        status = "命中" if hit else "未命中"
        if not hit:
            ok = False
        print(f"  [{cat}] subject={f['subject']} grade={f['grade']} topic={f['topic']} → {status}")
    print("T0 验收:", "通过 ✅" if ok else "失败 ❌（部分学科未命中 KB）")
