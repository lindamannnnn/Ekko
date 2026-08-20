# -*- coding: utf-8 -*-
"""
kb_validator.py —— 教材 KB「编写期」校验闸门（确定性，零 LLM）。

定位：在 content_fill / render 之前运行。任何违反都**阻断**该课生成，
并回报精确问题（哪一段、哪条规则、证据是什么），使「人工/弱模型写 KB」
引入的事实、术语、一致性错误在编写期就被拦下——而不是等老师审输出。

为什么是流程组件而不是手修某一课：
  老师能挑出的错误（板书归类矛盾、答案幻觉字、缺拼音、术语误用、关键句重复）
  都是**可规则化**的。把它们写成确定性规则后，6 课 + 未来上百课都自动受益，
  且同一类错误永不再犯。老师 Agent 的职责是「帮我们发现要加哪条规则」，
  而不是「每课人工审一遍」。

规则清单：
  R0  结构完整性：每段有 kind/layout/slots；layout 已注册；tiers 有 basic 且答案非空
  R1  词语卡拼音：chinese 的 word_grid 每张卡必须有 phonetic
  R2  答案提示字接地：答案里「注意'X、Y、Z'等字」的 X/Y/Z 必须能在题面或原文中找到
  R3  术语误用：lead_in 的 qtag 不应是「设问」（设问=自问自答，导入提问不是）
  R4  关键句重复标注：同一课出现 >1 句被标「关键句/中心句/重点关键句」→ 易混淆
  R5  板书归类矛盾：板书「风景优美」分支下出现物产类名词（珊瑚/鱼/海龟…）→ 与「景美物丰不分家」讲法打架
"""
import re
from .layouts import LAYOUTS

# 物产类名词词表（用于 R5 判定「这明明是物产不是风景」）
_PRODUCT_LEXICON = (
    "珊瑚", "海参", "大龙虾", "龙虾", "鱼", "海龟", "海鸟", "贝壳", "鸟蛋",
    "鸟粪", "肥料", "生物", "海参", "虾", "蟹", "海藻", "海带",
)
# 关键句类标注前缀（用于 R4）
_KEYSENT_PATTERNS = ("关键句", "中心句", "重点关键句")
# 答案提示字模式：注意“优、群、般”等字 / 注意'X'等词
_HINT_RE = re.compile(r"注意[“\"']([^”\"']+)[”\"']等[字词]")


def _cjk_chars(text):
    """返回文本中所有 CJK 字符的集合，用于「字是否在原文/题面中」的接地判定。"""
    return set(ch for ch in (text or "") if "\u4e00" <= ch <= "\u9fff")


def _collect_text(slots):
    """递归收集 slots 中所有字符串（含 list / dict 嵌套），用于全文一致性扫描。"""
    out = []
    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for iv in v.values():
                walk(iv)
        elif isinstance(v, (list, tuple)):
            for iv in v:
                walk(iv)
    walk(slots)
    return "\n".join(out)


_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_num(s):
    """把 '四' / '4' / '十' 之类转成 int（覆盖本课用到的范围）。"""
    s = (s or "").strip()
    if s.isdigit():
        return int(s)
    if s in _CN_NUM:
        return _CN_NUM[s]
    return 0


def validate_kb(kb):
    """校验一份结构化 KB。返回 (ok: bool, report: list[dict])。

    report 每条: {sev:'high'|'med'|'low', rule, where, detail}
    ok=False 表示存在 high/med 级问题，应阻断生成。
    """
    report = []
    cat = (kb.get("subject_cat") or kb.get("subject") or "").lower()
    original = kb.get("original_text", "") or ""
    src_chars = _cjk_chars(original)
    segments = kb.get("segments", []) or []

    def add(sev, rule, where, detail):
        report.append({"sev": sev, "rule": rule, "where": where, "detail": detail})

    # ---- R0 结构完整性 ----
    for i, seg in enumerate(segments, 1):
        kind = seg.get("kind", "?")
        layout = seg.get("layout", "?")
        title = seg.get("title", "")
        where = f"第{i}段[{kind}/{layout}]{title}"
        if not isinstance(seg.get("slots"), dict):
            add("high", "R0", where, "segments 缺少有效 slots 字典")
            continue
        if layout not in LAYOUTS:
            add("high", "R0", where, f"layout '{layout}' 未注册")
            continue
        if layout == "tiers":
            sl = seg["slots"]
            basic = sl.get("basic") or []
            if not basic:
                add("med", "R0", where, "tiers 缺少 basic 层")
            for layer_name in ("basic", "standard", "advanced"):
                for j, it in enumerate(sl.get(layer_name) or [], 1):
                    ans = (it or {}).get("a") or (it or {}).get("ans") or ""
                    if not ans.strip():
                        add("high", "R0", where,
                            f"{layer_name} 第{j}题答案空")

    # ---- R1 词语卡拼音 ----
    # english 必填；chinese 识字/古诗必填；chinese 现代文可选（LOW，不阻断）
    is_chinese = ("chinese" in cat or kb.get("subject") == "语文")
    is_english = ("english" in cat or kb.get("subject") == "英语")
    lesson_type = kb.get("lesson_type", "")
    r1_strict = is_english or (is_chinese and lesson_type in ("poem", "recognition"))
    r1_soft = is_chinese and lesson_type not in ("poem", "recognition")
    if r1_strict or r1_soft:
        sev = "med" if r1_strict else "low"
        for i, seg in enumerate(segments, 1):
            if seg.get("layout") != "word_grid":
                continue
            title = seg.get("title", "")
            where = f"第{i}段[word_grid]{title}"
            missing = []
            for w in seg["slots"].get("words", []) or []:
                if not (w.get("phonetic") or "").strip():
                    missing.append(w.get("word", "?"))
            if missing:
                hint = "字词教学需拼音" if r1_strict else "现代文词卡可加拼音便于朗读"
                add(sev, "R1", where,
                    f"词语卡缺少拼音：{', '.join(missing)}（{hint}）")

    # ---- R2 答案提示字接地（幻觉字）----
    for i, seg in enumerate(segments, 1):
        sl = seg.get("slots", {}) or {}
        if seg.get("layout") != "tiers":
            continue
        title = seg.get("title", "")
        where = f"第{i}段[tiers]{title}"
        for layer_name in ("basic", "standard", "advanced"):
            for j, it in enumerate(sl.get(layer_name) or [], 1):
                q = (it or {}).get("q") or ""
                a = (it or {}).get("a") or (it or {}).get("ans") or ""
                m = _HINT_RE.search(a)
                if not m:
                    continue
                # 提取被点名的字（按 、，, 分割）
                named = re.split(r"[、，,\s]+", m.group(1))
                named = [c for c in named if c]
                pool = _cjk_chars(q) | src_chars
                bad = [c for c in named if c not in pool]
                if bad:
                    add("high", "R2", where,
                        f"{layer_name} 第{j}题答案点名「{m.group(1)}」等字，"
                        f"但其中 {bad} 不在题面/原文中（幻觉字）")

    # ---- R3 术语误用：设问 ----
    for i, seg in enumerate(segments, 1):
        if seg.get("layout") != "lead_in":
            continue
        qtag = (seg.get("slots", {}) or {}).get("qtag", "")
        title = seg.get("title", "")
        where = f"第{i}段[lead_in]{title}"
        if qtag == "设问":
            add("med", "R3", where,
                "导入提问误标「设问」（设问=自问自答修辞格，导入引子应标「想一想/问题」）")

    # ---- R4 关键句重复标注 ----
    keysents = []  # (where, sentence)
    for i, seg in enumerate(segments, 1):
        sl = seg.get("slots", {}) or {}
        blob = _collect_text(sl)
        title = seg.get("title", "")
        where = f"第{i}段[{seg.get('kind')}]{title}"
        # 1) 连续模式：关键句：S / 重点关键句：S
        for pat in _KEYSENT_PATTERNS:
            for mm in re.finditer(re.escape(pat) + r"[：:]\s*“?([^”\n]{2,30})", blob):
                keysents.append((where, mm.group(1).strip("”' ")))
        # 2) split 布局：head 含「关键句/中心句」，则对应 body 首句算一句被标句子
        if seg.get("layout") == "split":
            for hk, bk in (("head_l", "body_l"), ("head_r", "body_r")):
                h = sl.get(hk, "") or ""
                if any(k in h for k in ("关键句", "中心句")):
                    b = sl.get(bk, []) or []
                    if b and isinstance(b[0], str):
                        s = re.split(r"[。\n]", b[0])[0].strip("”' ")
                        if s:
                            keysents.append((where, s))
    # 去重（重点关键句 含 关键句 会致同一句被两条 pattern 命中）
    seen, uniq = set(), []
    for w, s in keysents:
        if (w, s) in seen:
            continue
        seen.add((w, s))
        uniq.append((w, s))
    if len(uniq) > 1:
        detail = "；".join(f"{w} → {s}" for w, s in uniq)
        add("med", "R4", "全课",
            f"同一课出现 {len(uniq)} 句被标为关键句/中心句，易混淆：{detail}")

    # ---- R6 排比「有的」数量一致性（轻微）----
    stated = [(i, _cn_num(m.group(1)), seg.get("title", ""))
              for i, seg in enumerate(segments, 1)
              if (m := re.search(r'([0-9一二三四五六七八九十]+)\s*个\s*[""“]?有的',
                                 _collect_text(seg.get("slots", {}) or {})))]
    if stated:
        max_n = max(n for _, n, _ in stated)
        for i, seg in enumerate(segments, 1):
            if any(si == i for si, _, _ in stated):
                continue  # 跳过“自称 N 个”的段
            blob = _collect_text(seg.get("slots", {}) or {})
            cnt = blob.count("有的")
            if "排比" in blob and cnt and cnt != max_n:
                add("low", "R6", f"第{i}段[{seg.get('kind')}]{seg.get('title','')}",
                    f"排比展示 {cnt} 个「有的」，但课文/他处称 {max_n} 个，数量不一致")

    # ---- R5 板书归类矛盾（物产误归风景优美）----
    for i, seg in enumerate(segments, 1):
        if seg.get("layout") != "board":
            continue
        title = seg.get("title", "")
        where = f"第{i}段[board]{title}"
        for br in seg["slots"].get("branches", []) or []:
            label = (br or {}).get("label", "")
            if not ("风景" in label or "景色" in label or "优美" in label):
                continue
            items = (br or {}).get("items", []) or []
            hit = []
            for it in items:
                for lex in _PRODUCT_LEXICON:
                    if lex in it:
                        hit.append(it)
                        break
            if hit:
                add("high", "R5", where,
                    f"「{label}」分支下出现物产类名词 {hit}，"
                    f"与「风景优美/物产丰富不分家」的讲法矛盾（应归入物产丰富）")

    high = [r for r in report if r["sev"] == "high"]
    med = [r for r in report if r["sev"] == "med"]
    ok = len(high) == 0
    return ok, report, {"high": len(high), "med": len(med), "low": len([r for r in report if r["sev"] == "low"])}


def format_report(report, counts):
    """把 report 渲染成可读文本（供 demo / 日志输出）。"""
    if not report:
        return "KB 校验：全部通过 ✅"
    lines = [f"KB 校验：发现 {counts['high']} 严重 / {counts['med']} 中等"]
    for r in report:
        lines.append(f"  [{r['sev'].upper()}] {r['rule']} @ {r['where']} — {r['detail']}")
    return "\n".join(lines)
