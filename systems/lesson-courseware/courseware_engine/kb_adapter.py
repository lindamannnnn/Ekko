# -*- coding: utf-8 -*-
"""courseware_engine/kb_adapter.py —— KB→segments 自动适配器。

【目标】让"任意一课 KB"都能上桌，不靠手写结构化 segments。
- 简单 KB（只有 subject/grade/topic/original_text/key_points）→ 自动派生
  subject_cat / stage / lesson_type / objectives / segments
- 输出结构与西沙手工结构化 KB 同 schema，能直接交给 content_fill。
- 全程确定性、零 LLM。

【适配策略】按 subject_cat 分派：
- chinese + 现代文（prose）   → 导入/段落理解/分层练习/小结/板书
- chinese + 古诗/儿歌（poem）  → 竖排呈现原文 + 字词卡 + 朗读练习
- chinese + 识字（recognition）→ 情境 + 竖排原文 + 字词 + 朗读
- math                      → 概念 + 例题步骤 + 分层练习 + 小结
- english                    → 词卡 + 句型 + 分层练习 + 小结

【诚实边界】自动适配是"够用"的最小骨架，质量不如西沙的手写 KB；
        但它走同一道闸门，老师 Agent 复验后可定位剩余差距继续迭代。
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# 字段派生
# ---------------------------------------------------------------------------
def _derive_subject_cat(subject):
    s = (subject or "").strip()
    if s in ("语文", "chinese", "Chinese"): return "chinese"
    if s in ("数学", "math", "Math"): return "math"
    if s in ("英语", "english", "English"): return "english"
    return "chinese"


def _derive_stage(grade):
    g = (grade or "")
    head = g[:1]
    cn2stage = {"一": "low", "二": "low", "三": "mid", "四": "mid", "五": "high", "六": "high"}
    if head in cn2stage:
        return cn2stage[head]
    if head.isdigit():
        n = int(head)
        if n <= 2: return "low"
        if n <= 4: return "mid"
        return "high"
    return "mid"


def _derive_lesson_type(kb, cat):
    if cat != "chinese":
        if cat == "english":
            return "standard"
        if cat == "math":
            return "concept"
        return "standard"
    text = (kb.get("original_text") or "").strip()
    topic = (kb.get("topic") or "").strip()
    grade = (kb.get("grade") or "")
    # ① 显式体裁字段优先（KB 即真相源；已为古诗/词逐条标注 genre）
    g = (kb.get("genre") or "").strip()
    if g in ("poem", "ci", "词", "古诗", "诗词"):
        return "poem"
    paras = [p for p in text.split("\n") if p.strip()]
    avg_len = (len(text) / max(1, len(paras))) if paras else len(text)
    is_short_text = len(text) <= 200
    is_poem_topic = any(k in topic for k in ("古诗", "绝句", "律诗", "词", "曲", "诗二", "诗三"))
    is_single_word_poem = is_poem_topic and avg_len <= 15
    # 古诗/词/曲：topic 含诗类关键词 + 段短 + 总长小
    if is_poem_topic and is_short_text and len(paras) <= 8:
        return "poem"
    # 短段儿歌/谚语
    if is_short_text and avg_len <= 50 and len(paras) <= 2:
        if avg_len <= 15:  # 单段极短，几乎是口诀
            return "poem"
        if grade.startswith(("一", "二")):
            return "recognition"
    # 识字：一年级 + 多行短句 + 重复结构（3 段即可，覆盖「对韵歌」等 3 段短韵文，
    # 避免卡在 儿歌<=2 与 识字>=4 之间的判定空洞被误判成 prose）
    if grade.startswith("一") and len(paras) >= 3 and avg_len <= 25:
        return "recognition"
    return "prose"


def _derive_objectives(kb, cat, stage, lesson_type):
    topic = (kb.get("topic") or "").strip()
    kps = kb.get("key_points") or []
    if cat == "chinese" and lesson_type in ("poem", "recognition"):
        return [
            f"正确、流利地朗读课文《{topic}》。",
            "认识本课生字，会写要求掌握的汉字。",
            "理解课文内容，体会作者表达的情感。",
            "背诵指定段落，积累好词佳句。",
        ][:4]
    if cat == "math":
        # 绑定课题要点（key_points），不再用「理解XX概念/掌握计算」四行套话
        _pts = []
        if kps:
            _pts.append(f"理解「{topic}」：{_clip(_kp_body(kps[0]), 40)}。")
            if len(kps) > 1 and _kp_body(kps[1]):
                _pts.append(f"掌握：{_clip(_kp_body(kps[1]), 40)}。")
        if len(_pts) < 2:
            _pts = [f"理解「{topic}」的含义。", "掌握其计算方法与表达。"]
        _pts.append("能用所学解决简单的实际问题。")
        _pts.append("结合实例感受数学与生活的联系。")
        return _pts[:4]
    if cat == "english":
        # 绑定本课 key_points（结构/否定/疑问/词汇/句型…），每课目标不同，
        # 不再四课都是"听懂会说核心词句"套话（A6 修复）。
        _pts = []
        if kps:
            _pts.append(f"掌握「{topic}」的基本结构与用法：{_clip(_kp_body(kps[0]), 36)}。")
            if len(kps) > 1 and _kp_body(kps[1]):
                _pts.append(f"理解并运用：{_clip(_kp_body(kps[1]), 36)}。")
            if len(kps) > 2 and _kp_body(kps[2]):
                _pts.append(f"能就「{topic}」进行相关表达：{_clip(_kp_body(kps[2]), 36)}。")
        if len(_pts) < 2:
            _pts = [f"听懂、会说、会读本课核心词汇与句型（{topic}）。",
                    "能在情境中运用核心句型进行交流。"]
        _pts.append("能朗读对话与短文，乐于用英语表达。")
        return _pts[:4]
    base = [
        f"朗读课文《{topic}》，读准字音、读通句子。",
        "把握课文主要内容，了解课文写了什么。",
    ]
    # 用 key_points 提炼目标（主旨/写法/重点词句），不再用「体会作者情感」套话
    for kp in kps[:2]:
        b = _kp_body(kp)
        if b:
            base.append(_clip(b, 40))
            if len(base) >= 4:
                break
    return base[:4]


# ---------------------------------------------------------------------------
# 分段工具
# ---------------------------------------------------------------------------
def _paragraphs(text):
    """按换行分段，但引号感知：引号内的换行不当作段边界。

    根治：源 KB 里跨换行的对白（如「他说："……\n……"」）按普通 \\n 切会把一句对白
    从句中劈成「开引号段」+「闭引号段」，任一段单独成页都会留下失衡引号；
    合并/丢弃任一段时整课件引号失衡。引号内换行改为空格，保持引号成对。
    """
    _O = {"“", "‘", "＂", "\u201c", "\u2018"}
    _C = {"”", "’", "＂", "\u201d", "\u2019"}
    out, buf, qd = [], [], 0
    for ch in (text or ""):
        if ch in _O:
            qd += 1
            buf.append(ch)
        elif ch in _C:
            if qd > 0:
                qd -= 1
            buf.append(ch)
        elif ch == "\n" and qd == 0:
            if buf:
                out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf).strip())
    return [p for p in out if p]


# 引号集合（弯引号，归一化后只剩 “” ）——用于"引号感知"的切句/截断，
# 避免把带引号的对话从中间劈开、留下孤立引号。
_OPEN = {"“", "‘", "＂", "\u201c", "\u2018"}
_CLOSE = {"”", "’", "＂", "\u201d", "\u2019"}


def _quote_depth(s):
    """返回 s 中未闭合的左引号数（引号深度）。"""
    d = 0
    for ch in s:
        if ch in _OPEN:
            d += 1
        elif ch in _CLOSE:
            if d > 0:
                d -= 1
    return d


def _balance_cut(s, cut):
    """找 <= cut 的最大切位，使 s[:idx] 引号平衡；若 cut 前整段都在一个开引号内，
    则前移到闭引号之后；兜底返回 cut。"""
    for idx in range(cut, max(-1, cut - 80), -1):
        if _quote_depth(s[:idx]) == 0:
            return idx
    for idx in range(cut, min(len(s), cut + 80)):
        if _quote_depth(s[:idx + 1]) == 0:
            return idx + 1
    return cut


def _norm_quotes(s):
    """引号归一化：把弯单引号统一为弯双引号（成对），去掉可能破坏排版的孤立引号/控制符。"""
    if not s:
        return s
    s = (s.replace("\u2018", "\u201c").replace("\u2019", "\u201d")
            .replace("\u201c", "\u201c").replace("\u201d", "\u201d"))
    s = re.sub(r"[\u200b\u00ad]", "", s)  # 去零宽/软连字符
    # 仅去掉"真正孤立"（使引号失衡）的行尾引号；合法的闭合引号（前文引号尚未闭合）保留。
    if s and s[-1] in _OPEN:
        s = s[:-1]
    elif s and s[-1] in _CLOSE and _quote_depth(s[:-1]) == 0:
        s = s[:-1]
    return s


def _close_quotes(s):
    """若字符串结尾仍开着引号（如段落末句是一段未闭合对白），在末尾补上对应的闭引号，
    保持引号平衡，避免"这一段写：…"提示或板书条目留下孤立开引号、整页引号失衡。"""
    s = s or ""
    depth = 0
    stack = []
    for ch in s:
        if ch in _OPEN:
            depth += 1
            stack.append(ch)
        elif ch in _CLOSE:
            if depth > 0:
                depth -= 1
                if stack:
                    stack.pop()
    if depth > 0:
        # 依开引号类型补闭引号（"→"，'→'）
        for op in stack:
            s = s + ("”" if op in "“\u201c" else "’")
    return s


def _clip(s, n, ellipsis=True):
    s = _norm_quotes(s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    # 优先在句末标点处断句（取 cut 内最后一个句末标点），避免把一句话劈成残句、留下"…"
    for punc in "。！？；":
        idx = cut.rfind(punc)
        if idx > 0:
            # 关键：即便在句末标点处断，也要补上被截断处之后才闭合的孤立开引号，
            # 否则"在牛肚子里旅行"这类含引号的目标会留下失衡开引号（输出 L≠R）。
            return _close_quotes(s[:idx + 1])
    # 次优先：在逗号/顿号/空格处断（保留完整短语，避免"赞海底…"式半词截断，
    # 长要点若只在第 40 字处有个逗号、正文远超一句，旧逻辑会落到下方平衡截断而劈出半句）。
    for punc in "，、 ,":
        idx = cut.rfind(punc)
        if idx > 0:
            return _close_quotes(s[:idx] + ("…" if ellipsis else ""))
    # 否则在 n-1 处截断，但退避到引号平衡的边界，避免留下孤立开引号
    j = _balance_cut(s, n - 1)
    if ellipsis:
        return _close_quotes(s[:j] + "…")
    # 板书等"标签型"条目：截断后不追加省略号（避免孤立"…"），仅保证引号平衡
    return _close_quotes(s[:j])


def _first_sentence(text):
    sents = _split_sentences(text or "")
    return sents[0] if sents else ""


def _strip_dev_note(text):
    """剔除开发者专用范围备注（如【本课题范围】…【本课范围】…），绝不进入学生页。

    KB 的 original_text 末尾常附"【本课题范围】仅学习…不涉及…"作为超纲护栏，
    这是给生成流程看的，不是给学生看的。任一 marker 出现即从该处截断取其前段。
    """
    if not text:
        return text
    for marker in ("【本课题范围】", "【本课范围】", "（本课题范围）", "(本课题范围)"):
        idx = text.find(marker)
        if idx != -1:
            head = text[:idx].rstrip()
            head = head.rstrip("。；;，,、 ")
            return _strip_dev_note(head)  # 递归以防多个
    return text


_STOP_WORDS = {"什么", "怎么", "为什么", "我们", "你们", "他们", "自己", "一样",
               "地方", "时候", "知道", "觉得", "因为", "所以", "没有", "是不是",
               "怎么办", "这样", "那么", "起来", "下来", "出来", "哪里", "哪儿"}


def _pick_word(text):
    """从原文抽取一个 2~4 字实词，作为本课专属的造句示例（避免对白/停用词）。"""
    cands = re.findall(r"[一-鿿]{2,4}", text or "")
    seen, out = set(), []
    for w in cands:
        if w[0] in _STOP_WORDS or w in _STOP_WORDS:
            continue
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[0] if out else ""


def _take_lines(text, max_lines=2, max_chars=160):
    paras = _paragraphs(text)
    out, total = [], 0
    for p in paras[:max_lines]:
        if total + len(p) > max_chars:
            break
        out.append(p)
        total += len(p)
    return " ".join(out) if out else (paras[0] if paras else "")


def _strip_quotes(s):
    """去掉所有弯引号，用于板书标签等"硬截断"场景，避免截断出孤立引号。"""
    return (s or "").replace("\u201c", "").replace("\u201d", "") \
                      .replace("\u2018", "").replace("\u2019", "") \
                      .replace("\u201c", "").replace("\u201d", "")


def _kp_label(kp):
    label, body = _split_label(kp)
    if label:
        return _clip(label, 8), _first_clause(body, 30)
    # 无标签：用首短句作标签（去除引号，避免板书标签被硬截断出孤立引号），整段作内容
    safe = _strip_quotes(kp)
    c = _first_clause(safe, 8)
    return (c or _clip(safe, 8)), _first_clause(safe, 30)


_BOARD_GENERIC = ["主要内容", "结构脉络", "重点词句", "写作方法", "拓展延伸"]

def _board_items(body, n=40):
    """把 kp 语义体切成板书条目（≤4 条，每条≤40）。
    在强边界（句末/分号/冒号/破折号）处断开，保留顿号列表不劈碎；
    但引号内的边界（如‘催促—不慌’里的破折号）不断开，避免劈散引号对。
    每条再软截断到 ≤40（只在自然边界处断），避免 40 字硬截断出残句。"""
    body = (body or "").strip()
    if not body:
        return []
    _stripchars = " ，、\t"
    # 引号深度感知拆分：仅在引号外（depth==0）的强边界断开
    _open = {"“", "‘"}
    _close = {"”", "’"}
    _seps = set("。！？；：—，")
    chunks, buf, qd = [], [], 0
    for ch in body:
        if ch in _open:
            qd += 1
            buf.append(ch)
        elif ch in _close:
            if qd > 0:
                qd -= 1
            buf.append(ch)
        elif ch in _seps and qd == 0:
            chunks.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    chunks.append("".join(buf))
    items = []
    for c in chunks:
        c = c.strip(_stripchars)
        if not c or len(c) <= 1:
            continue
        if len(c) > n:
            c = _clip(c, n, ellipsis=False)   # 板书条目截断不留孤立省略号
        if c:
            items.append(c)
        if len(items) >= 4:
            break
    if not items:
        items = [_clip(body, n)] if body else []
    return items


def _board_branch(kp, idx=0):
    """为板书页生成一个分支 (label, items)，保证：
    - label 始终是干净的短标签（≤8），不会把整句长内容当成标签被 16 字硬截断出残句；
    - items 在强边界处拆成 ≤4 条、每条 ≤40，保留顿号列表，避免被 40 字硬截断。
    """
    label, body = _split_label(kp)
    if label:
        label = _clip(label, 16)
    else:
        label = _BOARD_GENERIC[idx] if idx < len(_BOARD_GENERIC) else "要点"
    items = _board_items(body if body else kp, 40)
    return label, items


def _board_point(text, n=16):
    """板书短要点：去掉开头≤4字的体裁/诗体标签（如“咏物诗，”“七言绝句，”），
    取其后首短句；保证板书是“骨架浓缩”而非照抄赏析页的主旨/修辞全文。"""
    if not text:
        return ""
    parts = [p.strip() for p in (text or "").replace("，", ",").split(",") if p.strip()]
    if len(parts) >= 2 and len(parts[0]) <= 4:
        parts = parts[1:]
    body = parts[0] if parts else ""
    return _first_clause(body, n) or _clip(body, n, ellipsis=False)


# ---------------------------------------------------------------------------
# segments 生成器（按 cat + lesson_type 分派）
# ---------------------------------------------------------------------------
# 已知文体/体裁标签（不是作者名）。_extract_author 命中即跳过，
# 避免把 source 里的「（寓言，向新阳/改编）」错把「寓言」当成作者，显示成「作者：寓言」。
_GENRE_TOKENS = frozenset({
    "寓言", "童话", "神话", "传说", "民间故事", "历史故事", "神话故事", "童话故事", "寓言故事",
    "儿歌", "童谣", "散文", "小说", "诗歌", "古诗", "词", "现代诗", "说明文", "记叙文", "议论文",
})


def _extract_author(kb):
    """从 source / cautions 抽取作者（KB 多把作者埋在 source 末尾括号，缺独立字段）。

    优先显式 author 字段 → cautions 的'作者为X/作者是X' → source 末尾括号对。
    修复：旧正则里「日」为必需字符，导致普通中文作者（老舍/苏轼/李白）永远匹配不到；
    现改为：从 source 的所有括号对里，取最后一个「像作者」的内容（2-6 个汉字/字母/间隔号，
    剔除年级/册次/版本/修订/学期/教材等非作者括号），兼容 '（老舍）'、'（[清]纳兰性德）'、'（[日]清少纳言 著）'。
    另：文体标签（寓言/童话/神话…）不是作者——整段若是标签则跳过；形如「寓言，向新阳/改编」
    则取逗号后的人名/改编者，根治「作者：寓言」式错显。
    """
    if kb.get("author"):
        a = str(kb["author"]).strip()
        if a:
            return a
    cautions = kb.get("cautions", "") or ""
    source = kb.get("source", "") or ""
    m = re.search(r"作者[为是：: ]\s*([一-龥A-Za-z·]{1,8})", cautions)
    if m:
        return m.group(1).strip(" 。，、")
    # 从 source 的括号对里，倒序取第一个「像作者」的内容（source 末尾括号通常是作者）
    for cand in reversed(re.findall(r"[（(]([^（）()]{1,30})[）)]", source)):
        cand = cand.strip()
        cand = re.sub(r"^\[[A-Za-z]+\]\s*", "", cand)            # 去 [清]/[日]/[唐] 等朝代·国别标记
        # 「体裁，作者」格式（如「寓言，向新阳/改编」）→ 体裁是文体标签不是作者，
        # 取逗号后的人名/改编者，避免「作者：寓言」式错显。
        if ("，" in cand or "," in cand) and any(t in cand for t in _GENRE_TOKENS):
            cand = re.split(r"[，,]", cand)[-1].strip()
        # 「作者《篇目》之一」→ 取《》前的作者名
        _m = re.match(r"([一-龥·A-Za-z]{2,6})(《[^》]*》)?", cand)
        if _m:
            cand = _m.group(1)
        cand = re.sub(r"\s*(著|作|编|撰|译|注)\s*$", "", cand)    # 去 '著/译/编' 等
        cand = cand.strip()
        if not cand:
            continue
        if cand in _GENRE_TOKENS:          # 整段就是文体标签（如「寓言」），跳过
            continue
        if any(x in cand for x in ("年级", "册", "版", "修订", "学期", "教材", "课标", "单元", "修订版")):
            continue
        if re.fullmatch(r"[一-龥·A-Za-z]{2,6}", cand):
            return cand
    return ""


def _pick_detail(text):
    """从原文取一个本课专属的 2~4 字实词（用于差异化练习题，避免三课雷同）。

    护栏：绝不在词语/引号中间截断——只接受“左右都是非汉字边界”的完整词，
    避免出现“小公鸡和”“胡萝卜先”“在北京的”这种被劈断的题干。
    找不到完整边界词时返回空串，由调用方回退到“画出喜欢的句子”类安全题。
    """
    if not text:
        return ""
    cands = re.findall(r"[一-鿿]{2,4}", text or "")
    is_cjk = lambda ch: '一' <= ch <= '鿿'
    clean, rightbound = [], []
    for w in cands:
        if w[0] in _STOP_WORDS or w in _STOP_WORDS:
            continue
        bounded = right_only = False
        for m in re.finditer(re.escape(w), text):
            i, j = m.start(), m.end()
            left_ok = (i == 0) or (not is_cjk(text[i - 1]))
            right_ok = (j >= len(text)) or (not is_cjk(text[j]))
            if left_ok and right_ok:
                bounded = True
                break
            elif right_ok:
                right_only = True
        if bounded:
            clean.append(w)
        elif right_only:
            rightbound.append(w)
    pool = clean or rightbound
    if not pool:
        return ""
    pool.sort(key=lambda w: -len(w))   # 偏好较长词（信息更足、更可能是完整词）
    seen = set()
    for w in pool:
        if w not in seen:
            return w
    return ""


def _build_guide(kps, topic):
    """生成'阅读提示'页要点：用 key_points 的完整语义体（句末边界截断，不劈半句），
    不前缀'抓住'，根治'抓住按春''抓住写狗熊在狐狸…'这类意义不明句。"""
    guide = []
    for kp in (kps or [])[:3]:
        b = _kp_body(kp)
        if b:
            guide.append(_clip(b, 42))   # 句末边界截断，最长 42 字、不劈半句
        if len(guide) >= 4:
            break
    if not guide:
        guide = ["① 课文写了什么内容？", "② 作者用了什么写法？", "③ 表达了怎样的情感？"]
    return guide[:5]


def _first_emotional_sentence(text):
    """取原文中带感叹/疑问或情感词的句子，作情感题引用的具体锚点（拒绝空壳答）。"""
    for s in _split_sentences(text or ""):
        if any(ch in s for ch in "！？!?") or any(w in s for w in
           ("喜爱", "赞美", "热爱", "高兴", "伤心", "可爱", "特点", "感受", "心情", "感叹", "有趣")):
            return s
    return ""


def _emotion_fallback(text, main_kp, topic):
    """情感题无独立情感要点时的兜底答案：不回退「结合课文说说你的体会」式空壳，
    而是引用原文一句具体语句 + 本课主旨，给出老师可展开的真实指引（A4 修复）。"""
    quote = _first_emotional_sentence(text) or _first_sentence(text)
    anchor = _clip(main_kp, 50) if main_kp else f"《{topic}》的内容"
    if quote:
        return f"可结合“{_clip(quote, 40)}”等语句，联系{anchor}，说说自己的体会。"
    return f"联系{anchor}，结合文中具体语句，说说自己的体会。"


def _chinese_practice(kb, title, mode="practice"):
    """语文分层练习/作业：mode=homework 走课后巩固（与课堂练习不雷同）；
    mode=practice 时 KB 有 exercises 用真实题，否则按本课内容生成（答案取自
    key_points / 原文细节），保证三课不逐字雷同、且每题都有可讲的答案。"""
    if mode == "homework":
        return _chinese_homework(kb, title)
    topic = kb.get("topic", "")
    kps = kb.get("key_points") or []
    text = kb.get("original_text", "")
    ex = kb.get("exercises") or {}
    if ex:
        return _tiers_from_ex(ex, title)
    first_kp = _kp_body(kps[0]) if kps else ""
    # 题→答 语义对齐：主旨题用"中心思想/主旨"类要点，情感题用"情感/思想感情"类要点，
    # 写法题用"写法/修辞"类要点——避免"情感题答成结构"这类答非所问。
    main_kp = _kp_match(kps, ("中心思想", "主旨", "主要内容", "写了什么")) or first_kp
    # 情感题不 fallback 到 main_kp——否则「情感题答成内容梗概」（答非所问的系统性错误）
    emotion_kp = _kp_match(kps, ("情感", "感情", "思想", "喜爱", "赞美", "热爱", "感叹", "情怀", "体会", "歌颂"))
    main_ans = _clip(main_kp, 200) if main_kp else _clip(_first_sentence(text) or topic, 200)
    write_kp = _kp_match(kps, ("写法", "修辞", "表达", "结构", "描写", "顺序")) or \
        next((_kp_body(k) for k in kps if any(t in k for t in ("写法", "修辞", "表达", "结构"))), "")
    write_hint = _first_clause(write_kp, 18) if write_kp else ""
    detail = _pick_detail(text)
    return {
        "title": title,
        "basic": [
            {"q": f"朗读课文《{topic}》，读准字音、读通句子，注意停顿与语气。",
             "a": "借助拼音把生字读准，长句按意思停顿，多读几遍。"},
            {"q": "课文主要写了什么？用一两句话概括。",
             "a": main_ans},
        ],
        "standard": [
            {"q": (f"从文中找出描写“{detail}”的语句，抄写下来并读一读。" if detail
                   else "画出课文中你喜欢的句子，说说它好在哪里。"),
             "a": (_sentences_with(text, detail) or
                   (_clip(first_kp, 200) if first_kp
                    else "从用词准确、描写生动、表达情感等方面说，并结合具体语句。"))},
            {"q": "课文表达了作者怎样的情感？结合具体语句说一说。",
             "a": _clip(emotion_kp, 200) if emotion_kp else _emotion_fallback(text, main_kp, topic)},
        ],
        "advanced": [
            {"q": (f"仿照课文的写法（如{write_hint}），写一段你熟悉的生活场景。" if write_hint
                   else "仿照课文写法，写一段你熟悉的生活场景。"),
             "a": (f"用上本课学到的写法——{write_hint}，写自己真实的内容。" if write_hint
                   else f"联系《{topic}》的内容，用上本课学到的写法，写自己真实观察到的人、事、景。")},
        ],
    }


def _chinese_homework(kb, title):
    """语文课后作业：与课堂练习差异化——以抄写/朗读巩固、讲给家人听、生活小练笔为主。"""
    topic = kb.get("topic", "")
    kps = kb.get("key_points") or []
    write_kp = next((_kp_body(k) for k in kps if any(t in k for t in ("写法", "修辞", "表达", "结构"))), "")
    write_hint = _first_clause(write_kp, 18) if write_kp else ""
    return {
        "title": title,
        "basic": [
            {"q": "抄写本课生字新词，每个两遍，注意笔顺与间架结构。",
             "a": "工整书写，难字可多写几遍；建议用田字格本。"},
            {"q": f"朗读《{topic}》两遍，做到正确、流利、有感情。",
             "a": "读准字音、读通句子；长句按意思停顿，边读边想象画面。"},
        ],
        "standard": [
            {"q": f"把《{topic}》讲给家人听，说说你最喜欢的地方和理由。",
             "a": "说清课文主要内容，结合具体语句谈自己的感受。"},
            {"q": "积累本课好词佳句，摘抄三个你喜欢的词语或句子。",
             "a": "可摘抄生动词语、优美句式或精彩描写，并简单批注。"},
        ],
        "advanced": [
            {"q": (f"用本课学到的写法（如{write_hint}），观察生活写一篇小日记或一段话。"
                   if write_hint else "用本课学到的写法，观察生活写一篇小日记或一段话。"),
             "a": "写自己真实观察到的人、事、景，用上本课学到的写法。"},
        ],
    }


def _chinese_lead_question(kb):
    """语文导入问：按本课 key_points 倾向派生，避免三课都"你感受到了什么"。"""
    topic = kb.get("topic", "")
    kps = kb.get("key_points") or []
    blob = topic + " " + " ".join(kps)
    if any(t in blob for t in ("写法", "修辞", "表达", "结构")):
        return f"读一读《{topic}》，作者用了什么写法把内容写生动的？"
    if any(t in blob for t in ("情感", "喜爱", "热爱", "赞美", "喜爱之情")):
        return f"读一读《{topic}》，你从哪些语句感受到作者的情感？"
    if any(t in blob for t in ("景", "美", "春天", "秋天", "四季", "画面")):
        return f"读一读《{topic}》，你仿佛看到了怎样的画面？"
    return f"读一读《{topic}》，你读懂了什么、又感受到了什么？"


def _gen_chinese_prose(kb):
    """语文现代文：导入 → 精读指导 → 段落理解(逐段全文+学习提示) → 分层练习 → 小结 → 板书 → 作业。

    改进（根治语文问题）：
      - 每段 concept 页附带"学习提示"（从 key_points 取本课要点作镜头），老师知道这一页要看什么；
      - 导入后新增"精读指导"页，用 key_points 给老师明确的思考方向；
      - 练习/作业从原文抽取本课文专属词语造句、用真实 key_points 概括，淘汰逐字相同的套话。
    若 KB 含 exercises，则消费真实题目与答案。347 个语文 KB 通用受益。
    """
    topic = kb.get("topic", "")
    text = kb.get("original_text", "")
    kps = kb.get("key_points") or []
    paras = _paragraphs(text)
    ex = kb.get("exercises") or {}

    author = _extract_author(kb)
    source = kb.get("source", "")
    analysis_kps = [k for k in kps if any(t in k for t in ("写法", "修辞", "表达", "重点句", "赏析", "结构", "情感"))]

    segs = [
        {"kind": "cover", "layout": "cover",
         "slots": {"title": topic, "subtitle": f"{kb.get('grade','')} · 语文", "meta": ""}},
        {"kind": "objectives", "layout": "objectives",
         "slots": {"items": _derive_objectives(kb, "chinese", kb.get("stage", "mid"), "prose")}},
        {"kind": "lead_in", "layout": "lead_in",
         "slots": {"scenario": _clip(paras[0] if paras else text, 160),
                   "question": _chinese_lead_question(kb)}},
    ]

    # 作者/背景（KB 多把作者埋在 cautions/source，缺独立字段；能取到才加页，避免空壳）
    if author or source:
        info = []
        if author:
            info.append(f"作者：{author}")
        if source:
            info.append(f"出处：{_clip(source, 40)}")
        if analysis_kps:
            info.append("学习重点：" + _clip(_kp_body(analysis_kps[0]), 36))
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": f"资料链接 · 《{topic}》", "points": info[:4]}})

    # 阅读提示（精读指导）：用完整 key_points 语义体，不劈半句、不前缀"抓住"
    segs.append({"kind": "concept", "layout": "concept",
                 "slots": {"statement": "阅读提示", "points": _build_guide(kps, topic)}})

    # 段落理解：每段「首句原文 + 学习提示（字词/写法）」，砍掉「这一段写：原文」零教学机制。
    # 现代文课件不逐段搬运全文（学生有课本），每段只呈现一个教学落点。
    if paras:
        merged = []
        for p in paras:
            if merged and len("".join(p.split())) < 16:
                merged[-1] = merged[-1] + p
            else:
                merged.append(p)
        if len(merged) >= 2 and len("".join(merged[0].split())) < 16:
            merged[1] = merged[0] + merged[1]
            merged = merged[1:]
        _vocab_kp = _kp_match(kps, ("重点词句", "词语", "字词", "生字"))
        _write_kp2 = _kp_match(kps, ("写法", "修辞", "表达", "结构", "描写", "顺序"))
        for i, p in enumerate(merged[:6]):
            _pts = []
            if _vocab_kp and i == 0:
                _pts.append("重点词句：" + _clip(_vocab_kp, 80))
            if _write_kp2 and i == 1:
                _pts.append("写法点拨：" + _clip(_write_kp2, 80))
            if not _pts:
                _pts.append("读一读，边读边想：这一段写了什么？")
            _sents = _split_sentences(p)
            _stmt = _clip(_sents[0], 160) if _sents else _clip(p, 160)
            segs.append({"kind": "concept", "layout": "concept",
                         "slots": {"statement": _stmt, "points": _pts}})
    else:
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": _clip(topic, 120),
                               "points": ["读一读，想想这段话写了什么、表达了什么感情。"]}})

    # 重点句·写法点拨（把分析型 key_points 真正用起来，而非只当板书/提示）
    if analysis_kps:
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "重点句 · 写法点拨",
                               "points": [_clip(_kp_body(k), 80) for k in analysis_kps[:5]]}})

    # 朗读指导（标准教学支架，不编造；语气从 key_points 推断）
    tone = "轻快活泼" if any(any(w in k for w in ("活泼", "欢快", "有趣", "可爱")) for k in kps) else \
           "舒缓优美" if any(any(w in k for w in ("美", "喜爱", "热爱", "赞美", "优美")) for k in kps) else "自然大方"
    segs.append({"kind": "concept", "layout": "concept",
                 "slots": {"statement": "朗读指导",
                           "points": [f"读准字音、读通句子，做到正确、流利、有感情。",
                                      f"注意停顿与语气，把课文读得{tone}。",
                                      "边读边想象画面，体会作者的情感。"]}})

    # 分层练习（本课文专属，答案取自 key_points / 原文细节）
    segs.append({"kind": "practice", "layout": "tiers", "slots": _chinese_practice(kb, "分层练习")})

    # 小结
    sum_pts = [_first_clause(_kp_body(k), 60) for k in kps[:5] if _kp_body(k)] or \
              [_first_clause(p, 60) for p in paras[:3]]
    segs.append({"kind": "summary", "layout": "summary",
                 "slots": {"points": sum_pts}})

    # 板书：取 3 个分支（topic/主旨/写法）
    branches = []
    if kps:
        for i, kp in enumerate(kps[:3]):
            label, items = _board_branch(kp, i)
            branches.append({"label": label, "items": items})
    if not branches:
        branches = [{"label": "主要内容", "items": [_clip(topic, 30)]},
                    {"label": "思想情感", "items": ["体会作者情感"]},
                    {"label": "写作方法", "items": ["读写迁移"]}]
    segs.append({"kind": "board", "layout": "board",
                 "slots": {"center": topic, "branches": branches}})

    # 作业（课后巩固，与课堂练习不雷同）
    segs.append({"kind": "homework", "layout": "tiers", "slots": _chinese_practice(kb, "分层作业", "homework")})
    return segs


def _poem_lines(text, max_lines=24):
    """把原文按自然句读拆成短列（保留 阕 边界）—— 行业标准竖排古文版式。

    原则：
    · 每列 = 一个自然短语（，,、； 之间的内容），不截断、不丢字；
    · 阕与阕之间插入 '§' 标记，layout 渲染为竖虚线分隔；
    · 输出 list[str]，'§' 仅作 阕 分隔。
    """
    import re
    if not text or not text.strip():
        return [""]
    out = []
    # 多阕文本按行（或句末标点）分阕
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        stanzas = re.split(r"(?<=[。.！!？?；;])\s*", line)
        for st in stanzas:
            st = st.strip().rstrip("。.！!？?；;，,、")
            if not st:
                continue
            # 阕内按 ，,、；分
            phrases = re.split(r"[，,、；;]\s*", st)
            phrases = [p.strip() for p in phrases if p.strip()]
            if phrases:
                out.extend(phrases)
                out.append("§")
    # 去掉末尾 阕 分隔符
    while out and out[-1] == "§":
        out.pop()
    return out[:max_lines] if out else [text.strip()]


def _poem_rhythm(text):
    """古诗朗读节奏（规则生成）：七言 2/2/3，五言 2/3，按标点切句。

    确定性、零 LLM——节奏划分是客观的（按字数），无需模型。
    """
    lines = []
    for sent in re.split(r"[。！？!?；;]", text or ""):
        sent = sent.strip()
        if not sent:
            continue
        for clause in re.split(r"[，,、]", sent):
            clause = clause.strip()
            if not clause:
                continue
            n = len(clause)
            if n == 7:
                lines.append(f"{clause[:2]} / {clause[2:4]} / {clause[4:]}")
            elif n == 5:
                lines.append(f"{clause[:2]} / {clause[2:]}")
            else:
                lines.append(clause)
    return "\n".join(lines)


def _poem_word_cards(kps):
    """古诗词卡：解析「重点词句」的两种真实格式，产出独立词卡（词+拼音+释义）。

    旧逻辑按「词：释义」冒号格式解析，但真实 KB 是括号/引号格式，故解析失败、产出垃圾
    （诗词词卡因此被禁用）。现支持：
      ① 括号释义式：西林（西林寺）、岭、峰、真面目、缘（因为）
      ② 引号列表式：‘山一程，水一程’‘榆关’‘那畔’‘千帐灯’‘聒碎’‘故园’
    词 = 1-8 字实词（过滤含逗号的诗句引用）；释义取括号内；拼音用 pypinyin（可用时）。
    """
    out = []
    key_kp = ""
    for kp in (kps or []):
        if "重点词句" in kp or "重点词" in kp or "词句" in kp:
            key_kp = kp.split("：", 1)[1] if "：" in kp else (kp.split(":", 1)[1] if ":" in kp else kp)
            break
    if not key_kp:
        return out
    key_kp = key_kp.strip().rstrip("。.！!")

    # 引号包裹（‘词’‘词’）优先；否则按顿号/逗号/分号切
    # 注意：捕获上限取到 40（原 12 过短，会导致「明、男、尖、尘、从、众、林、森」这类
    # 长会意字列表整体解析失败，进而掉进 kp[0][:8] 兜底抽错字，引发 A2 生字越界）
    if any(q in key_kp for q in ("‘", "'", "“", '"')):
        terms = re.findall(r"[‘'“\"]([^’'”\"]{1,40})[’'”\"]", key_kp)
    else:
        terms = re.split(r"[、，,；;]", key_kp)

    for term in terms:
        term = (term or "").strip().strip("‘’“”'\"")
        if not term:
            continue
        # 顿号/逗号/分号分隔的「词列表」（如会意字「明、男、尖、尘、从、众、林、森」）
        # 需先拆成单字/单词再逐一判定；整串当一词会因 len>8 被误弃，进而掉进兜底抽错字（A2）
        sub_terms = re.split(r"[、，,；;]", term)
        for st in sub_terms:
            st = st.strip()
            if not st or "，" in st or "," in st:
                continue  # 含逗号的是诗句引用（如山一程，水一程），不是词
            m = re.match(r"^([一-龥]{1,6})[（(]([^（）()]{1,24})[）)]$", st)
            w, gloss = (m.group(1), m.group(2)) if m else (st, "")
            if not (1 <= len(w) <= 8):
                continue
            ph = ""
            try:
                from pypinyin import pinyin as _py, Style
                ph = " ".join("".join(x) for x in _py(w, style=Style.TONE))
            except Exception:
                pass
            out.append({"word": w, "phonetic": ph, "meaning": gloss, "example": ""})
            if len(out) >= 8:
                break
        if len(out) >= 8:
            break
    if not out:
        for kp in (kps or [])[:1]:
            w = _strip_quotes(kp).split("，")[0].split("、")[0][:8]
            if w:
                out.append({"word": w, "phonetic": "", "meaning": "", "example": ""})
    return out[:8]


def _gen_vocab(kb):
    """生成时抽生字词：从「重点词句」抽词 → 拆单字，配拼音(pypinyin)+笔画(strokes)+释义。

    确定性、零 LLM——拼音/笔画是客观数据。释义单字词沿用重点词句里的括号释义。
    """
    words = _poem_word_cards(kb.get("key_points") or [])
    # A2 修复：词卡只展示课文原文真实出现的字，杜绝越界抽错字
    # （如 识字课从「中心思想/主旨」key_point 误抽 中/心/思/想/主 等非课生字）
    text_chars = set((kb.get("original_text") or ""))
    vocab = []
    seen = set()
    for w in words:
        term = (w.get("word") or "").strip()
        meaning = w.get("meaning", "")
        for ch in term:
            if not ('\u4e00' <= ch <= '\u9fff') or ch in seen:
                continue
            if ch not in text_chars:   # 越界字符直接跳过（不在课文原文中）
                continue
            seen.add(ch)
            ph = ""
            try:
                from pypinyin import pinyin as _py, Style
                ph = "".join(_py(ch, style=Style.TONE)[0])
            except Exception:
                pass
            st = ""
            try:
                from strokes import strokes as _st
                st = f"{_st(ch)}画"
            except Exception:
                pass
            vocab.append({"char": ch, "pinyin": ph, "stroke": st,
                          "meaning": meaning if len(term) == 1 else "", "words": []})
            if len(vocab) >= 6:
                return vocab
    return vocab


def _poem_thinking_slots(kb, paras):
    """为 poem_thinking 提取结构化数据：阕（原文段落）/主旨/重点词句/修辞。

    适配 KB key_points 里的多种前缀写法（含/无前缀），鲁棒归类。
    """
    import re
    text = (kb.get("original_text") or "").strip()

    # 1) 把原文按段落切，每段作为一阕
    raw_paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if len(raw_paragraphs) <= 1:
        # 没有显式换行：按句末标点拆成 2 阕（常见 2-阕 词 / 古诗2首）
        parts = re.split(r"(?<=[。.！!？?；;])\s*", text)
        raw_paragraphs = [p.strip().rstrip("。.！!？?；;，,、") for p in parts if p.strip()]
    if not raw_paragraphs:
        raw_paragraphs = [text]

    # 2) 清理 key_points，按前缀归类
    def strip_prefix(s, prefixes):
        s = s.strip()
        for p in prefixes:
            if s.startswith(p):
                return s[len(p):].lstrip("：:、 ")
        return s

    theme = rhetoric = key_phrases = ""
    unprefixed_idx = 0  # 无前缀 kp 的位置计数
    for kp in (kb.get("key_points") or []):
        kp_strip = kp.strip()
        if not kp_strip:
            continue
        # 优先按前缀归类
        if any(kp_strip.startswith(p) for p in ("中心思想/主旨", "主旨/主题", "中心思想", "主旨", "主题", "中心")) and not theme:
            theme = strip_prefix(kp_strip,
                ["中心思想/主旨", "主旨/主题", "中心思想", "主旨", "主题", "中心"])
            continue
        if any(kp_strip.startswith(p) for p in ("重点词句",)) and not key_phrases:
            key_phrases = strip_prefix(kp_strip, ["重点词句"])
            continue
        # 篇章结构类：在这里不展示（阕已隐含），跳过但要更新位置计数
        if any(kp_strip.startswith(p) for p in ("篇章结构/描写顺序", "篇章结构", "描写顺序", "结构")):
            unprefixed_idx += 1
            continue
        if any(kp_strip.startswith(p) for p in ("修辞/写法", "修辞", "写法", "写作")) and not rhetoric:
            rhetoric = strip_prefix(kp_strip, ["修辞/写法", "修辞", "写法", "写作"])
            continue
        # 无前缀 kp 按位置归类（约定：1=theme, 2=structure 跳过, ≥3=rhetoric）
        unprefixed_idx += 1
        if unprefixed_idx == 1 and not theme:
            theme = kp_strip
        elif unprefixed_idx == 2:
            continue  # 篇章结构
        elif unprefixed_idx >= 3 and not rhetoric:
            rhetoric = kp_strip

    # 3) 主旨兜底
    if not theme:
        theme = (kb.get("key_points") or [""])[0] or _clip(text, 100)

    # 词（genre=ci）用「上阕/下阕」，古诗用「第一句/第二句…」（layout 默认）
    _stanza_labels = None
    if kb.get("genre") == "ci":
        _stanza_labels = ["上阕", "下阕"]

    return {
        "title": "笺注 · 赏析",
        "stanzas": raw_paragraphs[:4],
        "theme": theme.strip(),
        "key_phrases": key_phrases.strip(),
        "rhetoric": rhetoric.strip(),
        "stanza_labels": _stanza_labels,
    }


def _poem_lead_question(kb, poem_text):
    """诗词/古文情境导入的提问：按体裁生成更贴切的问句。

    词 → 你喜欢这首词吗？ / 古诗 → 你喜欢这首诗吗？ / 识字/古文 → 你喜欢这段话吗？
    """
    genre = kb.get("genre", "")
    topic = (kb.get("topic") or "").strip()
    if genre == "ci":
        return f"你喜欢{topic}这首词吗？为什么？"
    elif genre == "poem":
        return f"你喜欢{topic}这首诗吗？为什么？"
    else:
        return "你喜欢这段话吗？为什么？"


def _gen_chinese_poem_or_recog(kb, lesson_type):
    """语文古诗/识字/儿歌：情境导入 → 竖排呈现 → 笺注赏析 → 练习 → 小结。"""
    topic = kb.get("topic", "")
    text = kb.get("original_text", "")
    kps = kb.get("key_points") or []
    paras = _paragraphs(text)
    poem_text = "\n".join(paras) if paras else text  # 用完整原文（含全阕），不丢句
    lines = _poem_lines(poem_text)

    segs = [
        {"kind": "cover", "layout": "cover",
         "slots": {"title": topic, "subtitle": f"{kb.get('grade','')} · 语文", "meta": ""}},
        {"kind": "objectives", "layout": "objectives",
         "slots": {"items": _derive_objectives(kb, "chinese", kb.get("stage", "mid"), lesson_type)}},
        {"kind": "lead_in", "layout": "lead_in",
         "slots": {"scenario": _clip(poem_text, 160),
                   "question": _poem_lead_question(kb, poem_text)}},
    ]

    # ── 教学层：作者背景（富化 KB 提供 author_bg / author / dynasty）──
    _author = kb.get("author") or _extract_author(kb)
    _author_bg = (kb.get("author_bg") or "").strip()
    if _author or _author_bg:
        _apts = []
        if _author_bg:
            _apts.append(_author_bg)
        else:
            _dyn = (kb.get("dynasty") or "").strip()
            _apts.append((f"{_dyn} · " if _dyn else "") + f"{_author}。" if _author else f"作者：{_author}")
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": f"作者背景 · {_author or topic}", "points": _apts}})

    if lesson_type == "recognition":
        # 识字/儿歌：原文以朗读页呈现（概念 + 朗读要点），不用竖排诗版
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": _clip(poem_text, 120),
                               "points": ["正确、流利、有感情地朗读",
                                          "认识本课生字词",
                                          "理解课文内容，体会情感"]}})
    else:
        # 古诗：竖排诗版（行业标准版式：自然短语分列 + 阕虚线分隔 + 楷体）
        # 提取 作者·朝代 给 byline；优先用 KB source，否则省略
        src = (kb.get("source") or "").strip()
        # source 形如 "人教版部编版...（[清]纳兰性德）" → 取最后一个括号内容
        byline = ""
        if src:
            import re as _re
            m = _re.search(r"（([^（）]+)）\s*$", src)
            if m:
                byline = m.group(1).strip()
            else:
                # 兜底：去掉版本号后缀
                byline = _re.sub(r"^人教版.*?（|\(人教版.*?\)|人教版.*?\s", "", src).strip("（）()")
        segs.append({"kind": "concept", "layout": "vertical_poem",
                     "slots": {"title": topic, "lines": lines,
                               "byline": byline,
                               "rhythm": (kb.get("reading") or {}).get("tone") or "正确、流利、有感情地朗读"}})

    # ── 教学层：生字词（生成时抽单字 + 拼音 + 笔画 + 释义；KB 有 vocab 则用）──
    _vocab = kb.get("vocab") or _gen_vocab(kb)
    if _vocab:
        _vpts = []
        for _v in _vocab[:6]:
            _line = f"{_v.get('char','')}　{_v.get('pinyin','')}（{_v.get('stroke','')}）{_v.get('meaning','')}"
            if _v.get("words"):
                _line += "　组词：" + "、".join(_v["words"])
            _vpts.append(_line)
        # 标题用「重点词语」而非「生字词」：KB 无会写字表，抽取的是「重点词句」里的理解重点词，
        # 用「生字词」会误导（把理解词当会写字）
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "重点词语", "points": _vpts}})

    # ── 教学层：朗读指导（节奏规则生成 + 语气）──
    _reading = kb.get("reading") or {}
    _rpts = []
    if _reading.get("rhythm"):
        _rpts.extend(_reading["rhythm"].split("\n"))
    elif lesson_type != "recognition":
        _rhythm = _poem_rhythm(poem_text)
        if _rhythm:
            _rpts.extend(_rhythm.split("\n"))
    if _reading.get("tone"):
        _rpts.append(_reading["tone"])
    else:
        _rpts.append("读准字音，注意停顿与节奏，读出古诗的韵味。")
    segs.append({"kind": "concept", "layout": "concept",
                 "slots": {"statement": "朗读指导", "points": [_p for _p in _rpts if _p]}})

    # ── 教学层：诗意译文（一句一译）──
    _translation = kb.get("translation") or []
    if _translation:
        _tpts = [f"{_src}　→　{_dst}" for _src, _dst in _translation]
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "诗意译文", "points": _tpts}})

    # ── 教学层：意境赏析（意象/画面/手法/诗眼）──
    _imagery = kb.get("imagery") or {}
    if _imagery:
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "意境赏析",
                               "points": [f"{_k}：{_v}" for _k, _v in _imagery.items()]}})

    # ── 教学层：拓展延伸 ──
    _extension = kb.get("extension") or []
    if _extension:
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "拓展延伸",
                               "points": [f"{_e.get('title','')}：{_e.get('content','')}" for _e in _extension]}})

    # 字词卡（识字课抽单个生字 + 拼音；古诗用 key_points 的「词：释义」）
    if lesson_type == "recognition":
        # 识字：抽单个生字（去重、过滤常见虚词），配拼音（pypinyin 可用时），
        # 不再抽 2-4 字短语——那些是短语不是生字，且无拼音，是词卡「丑/质量差」的根源。
        _STOP_CHARS = set("的了着是在有和与就都而之乎者也啊呀呢吗吧说问这那我他她")
        chars = []
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff' and ch not in _STOP_CHARS and ch not in chars:
                chars.append(ch)
        pys = []
        try:
            from pypinyin import pinyin as _py, Style
            pys = ["".join(x) for x in _py("".join(chars), style=Style.TONE)]
        except Exception:
            pys = [""] * len(chars)
        words = [{"word": c, "phonetic": p, "meaning": "", "example": ""}
                 for c, p in zip(chars[:8], pys[:8])]
    else:
        # 古诗：把 key_points 里的「词：释义；词：释义」解析成独立词卡，
        # 避免把整条 key_point 当释义截断出 `…`、也避免每个词卡都重复整段释义。
        words = _poem_word_cards(kps)

    if words:
        if kb.get("genre") in ("poem", "ci"):
            # 富化 KB 已有「意境赏析」页（意象/画面/手法/诗眼）时，不再生成旧的
            # poem_thinking 页——它把绝句标成「上阕/下阕/其三/其四」有体裁错误，且与赏析页重复。
            if not (kb.get("imagery")):
                segs.append({"kind": "concept", "layout": "poem_thinking",
                             "slots": _poem_thinking_slots(kb, paras)})
            segs.append({"kind": "concept", "layout": "word_grid",
                         "slots": {"words": words}})
        else:
            segs.append({"kind": "concept", "layout": "word_grid",
                         "slots": {"words": words}})

    # 分层练习 —— 与 poem_thinking（赏析页）换 framing：练习偏“应用/抄写/情感”，
    # 不照抄赏析页的主旨/修辞全文，避免同一段文字在多处重复出现。
    kps0 = _kp_body(kps[0]) if kps else ""
    # 重点词句（单独取，不再 fallback 到主旨 kps0，避免「重点词题答成主旨」）
    _keyphrase = _kp_match(kps, ("重点词句", "词语", "字词"))
    # 情感/哲理（不 fallback 到 kps0，避免「情感题答成梗概」）
    _emotion = _kp_match(kps, ("情感", "感情", "喜爱", "赞美", "热爱", "感叹", "情怀", "体会"))
    segs.append({
        "kind": "practice", "layout": "tiers",
        "slots": {"title": "分层练习",
                  "basic": [
                      {"q": "正确、流利、有感情地朗读课文。",
                       "a": _clip(poem_text, 200)},
                      {"q": "背诵全诗（文）。",
                       "a": _clip(poem_text, 200)},
                  ],
                  "standard": [
                      {"q": "抄写你最喜欢的两句诗，说说为什么喜欢。",
                       "a": _clip("可从画面、情感、哲理任选一点，结合诗句说理由，如：" + (_emotion or kps0), 200)},
                      {"q": "结合词语卡，说说诗中的重点词是什么意思。",
                       "a": _clip(_keyphrase, 160) if _keyphrase else "结合词语卡的拼音与释义回答。"},
                  ],
                  "advanced": [
                      {"q": "这首诗告诉了我们什么道理？联系生活谈谈。",
                       "a": _clip(_emotion or kps0, 160)},
                  ]},
    })

    # 小结 —— 固定教学收获清单（不与赏析页/板书重复原文要点）
    segs.append({"kind": "summary", "layout": "summary",
                 "slots": {"points": [
                     "有感情地朗读并背诵课文",
                     "理解诗意，把握文章主旨",
                     "积累并运用重点词句",
                     "体会写法与表达的情感",
                 ]}})

    # 板书 —— 富化 KB 有 blackboard 时直接用；否则回退结构骨架
    _bb = kb.get("blackboard") or {}
    if _bb and _bb.get("branches"):
        segs.append({"kind": "board", "layout": "board",
                     "slots": {"center": _bb.get("center", topic),
                               "branches": _bb.get("branches", [])}})
    else:
        _write_kp = _kp_match(kps, ("比喻", "拟人", "夸张", "排比", "对偶", "托物",
                                    "借景", "白描", "反复", "对比", "叠词", "用典",
                                    "象征", "修辞", "写法"))
        board_branches = [
            {"label": "朗读·背诵", "items": ["正确、流利、有感情", "背诵全诗（文）"]},
            {"label": "内容·主旨", "items": [_board_point(kps0, 16) or "理解课文内容"]},
            {"label": "写法·特色", "items": [
                _board_point(_write_kp, 16)
                or (_board_point(_kp_body(kps[1]), 16) if len(kps) > 1 else "体会写法")
            ]},
        ]
        segs.append({"kind": "board", "layout": "board",
                     "slots": {"center": topic, "branches": board_branches}})

    # 本课写法提示：绑定真实写法（借景说理/白描/托物等），避免作业写死"比喻或拟人"与课不匹配
    _write_hint = ""
    for _k in kps:
        _wb = _kp_body(_k)
        if any(_t in _wb for _t in ("借景", "白描", "托物", "对比", "比喻", "拟人", "夸张", "反复", "写法", "修辞", "象征")):
            _write_hint = _first_clause(_wb, 16)
            break

    segs.append({
        "kind": "homework", "layout": "tiers",
        "slots": {"title": "分层作业",
                  "basic": [
                      {"q": "朗读并背诵课文。",
                       "a": _clip(poem_text, 200)},
                  ],
                  "standard": [
                      {"q": "抄写本课生字词各两遍。",
                       "a": "工整书写，注意笔顺与间架结构。"},
                  ],
                  "advanced": [
                      {"q": "仿照课文，写一段你想表达的内容。",
                       "a": ("仿照本课写法（如" + _write_hint + "），写一处景物或一个场景，表达自己的感受。"
                             if _write_hint else "仿照本课写法，写一处景物或一个场景，表达自己的感受。")},
                  ]},
    })
    return segs


def _split_sentences(p):
    """按中文句末标点切句（保留标点），返回非空句列表。
    引号感知：在引号“...”内部不切，避免把对话从中间劈开留下孤立引号。"""
    if not p:
        return []
    out, buf, depth = [], [], 0
    for ch in p:
        buf.append(ch)
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            if depth > 0:
                depth -= 1
        if ch in "。！？" and depth == 0:
            out.append("".join(buf).strip())
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _sentences_with(text, detail, maxn=120):
    """返回原文中含 detail 的句子（用于“找句子”题的答案），找不到则回退空串。

    根治 答非所问：题干要求“找出描写 X 的语句”，答案必须给真实句子，
    而不是把 first key_point（主旨）当答案。
    """
    if not detail:
        return ""
    sents = _split_sentences(text or "")
    hits = [s for s in sents if detail in s]
    if not hits:
        return ""
    out, total = [], 0
    for s in hits:
        if out and total + len(s) > maxn:
            break
        out.append(s)
        total += len(s)
    return "；".join(out) if len(out) > 1 else out[0]


def _concept_page_from_para(p, hint=None):
    """把一段 original_text 变成一个 concept 页：首句作论点，余句作支撑。
    hint（学习提示）置顶，给老师一个"看这段要看什么"的镜头，根治"只标一句不知想表达什么"。"""
    sents = _split_sentences(p)
    if not sents:
        return None
    statement = _clip(sents[0], 200)
    _stripchars = "\u201c\u201d\u2018\u2019\"'" + " ，、。！？；："
    pts = [_clip(s, 80) for s in sents[1:] if s.strip()][:4]
    # 去掉空点 / 只剩引号或标点的残点（根治裁缝 p12 的 <li>'</li>）
    pts = [p for p in pts if p and p.strip(_stripchars)]
    if hint:
        pts = [hint] + pts
    if not pts:
        return None
    return {"kind": "concept", "layout": "concept",
            "slots": {"statement": statement, "points": pts}}


_CONNECTIVES = {"就这样", "于是", "但是", "可是", "然后", "接着", "这时", "此时",
                "不过", "而且", "因为", "所以", "首先", "最后", "有一天", "原来",
                "其实", "不料", "第二天", "第三天", "第四天", "故事发生在"}

def _strip_leading_quote(s):
    """若 s 以弯引号开篇，去掉整段被引号包裹的引导语（含其闭引号），避免留下孤立引号。
    若整段都被同一对引号包裹（如‘X’），返回引号内文而非空串，避免回退到带引导语的原文。"""
    s = s.strip()
    if s and s[0] in "‘“":
        q = s[0]
        close = "’" if q == "‘" else "”"
        i = s.find(close)
        if i >= 0:
            rest = s[i + 1:].strip()
            if rest:
                return rest
            return s[1:i].strip()   # 整段被引号包裹，返回内文
    return s


def _para_hint(p):
    """从段落抽取"这一段写什么"的镜头，保证与页面对应（根治轮替套话、'不知想表达什么'）。

    对白开场时首 clause 往往只是说话人（"顾客说""裁缝说""就这样"），若直接取首 clause
    会变成"这一段写：顾客说"这种不知所云的提示。做法：
      ① 去掉开头"X说/问/道/催促…："引导词；
      ② 去掉整段被引号包裹的引导语与首尾孤立引号、开头连接词；
      ③ 取首个有意义的 clause（>3字且不含说/问/道）；若没有，退回取首 clause 或整句。
    """
    sents = _split_sentences(p)
    first_full = sents[0] if sents else p
    # 去"X说/问/道/催促/喊/叫/解释/补充："对白引导词
    m = re.match(r'^\s*[^，。：:“”‘’]{1,10}?\s*(?:说|问|道|回答|喊|叫|催促|解释|补充)\s*[：:]\s*(.*)$', first_full)
    body = m.group(1) if m else first_full
    body = _strip_leading_quote(body).strip()
    if not body:
        body = first_full
    # 去掉开头连接词（"就这样""于是"…）
    body = re.sub(r'^(就这样|于是|但是|可是|然后|接着|这时|此时|不过|而且|因为|所以|首先|最后|有一天|原来|其实|不料)[，。、]?\s*', '', body)
    # 取完整首句（在句末标点处断），而非首个 clause，避免"作为艺术家""明年冬天"这种半句不知所云
    sent = _first_sentence(body) or body
    if len(sent) > 44:
        # 超长时优先在句末/分号/逗号处软断，保留一个完整可懂的镜头
        cut = sent[:44]
        clip_at = -1
        for punc in "。！？；，":
            idx = cut.rfind(punc)
            if idx > 4:
                clip_at = idx
                break
        sent = sent[: clip_at + 1] if clip_at >= 0 else _clip(sent, 44)
    # 关键：若首句本身以开引号收尾（段落末句即一段对白、引号未闭合），
    # 必须补上闭引号，否则"这一段写：…"提示会留下孤立开引号、整页引号失衡。
    sent = _close_quotes(sent)
    return "这一段写：" + sent


def _first_clause(s, maxn=0):
    """取首个逗号/句号前的完整短句（用于板书/导读/小结等辅助页，避免截断出'…'残句）。
    仅在短句内部还有逗号时才按 maxn 进一步切短，避免把专有名词从中间劈开。"""
    s = _norm_quotes(s or "").strip()
    primary = "。！？；：，"
    depth = 0      # 括号深度
    qdepth = 0     # 引号深度（弯引号 " " 成对）
    cut = -1
    for i, ch in enumerate(s):
        if ch in "（）()":
            depth += 1 if ch in "（(" else -1
            depth = max(depth, 0)
            continue
        if ch in "“”‘’":
            qdepth += 1 if ch in "“‘" else -1
            qdepth = max(qdepth, 0)
            continue
        if ch in primary and depth == 0 and qdepth == 0:
            cut = i
            break
    c = s[:cut] if cut >= 0 else s
    if maxn and len(c) > maxn:
        depth2 = 0
        qdepth2 = 0
        cut2 = -1
        for i, ch in enumerate(c):
            if ch in "（）()":
                depth2 += 1 if ch in "（(" else -1
                depth2 = max(depth2, 0)
                continue
            if ch in "“”‘’":
                qdepth2 += 1 if ch in "“‘" else -1
                qdepth2 = max(qdepth2, 0)
                continue
            if ch in "、—" and depth2 == 0 and qdepth2 == 0:
                cut2 = i
                break
        if cut2 >= 0:
            c = c[:cut2]
    # 兜底：若截断仍留下孤立引号，去掉多余的（避免渲染出悬空 / 失衡引号）
    no = c.count("“") + c.count("‘")
    nc = c.count("”") + c.count("’")
    if no > nc:
        c = c.replace("“", "", no - nc)
    elif nc > no:
        c = c[::-1].replace("”", "", nc - no)[::-1]
    return c


# 剥离 key_point 头部 "中心思想："/"含义：" 等写成标签的前缀，
# 既避免板书/提示把内部标签当内容泄漏（如"中心思想：写急性子顾客…"），也便于取语义体判断关键词。
def _split_label(s):
    s = (s or "").strip()
    m = re.match(r'^([^：:]{1,12})[：:]\s*(.*)$', s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", s


def _kp_body(kp):
    """key_point 的语义体（已剥标签），用于答案/提示，避免把'中心思想：'当作内容输出。"""
    return _split_label(kp)[1] or (kp or "")


def _kp_match(kps, keywords):
    """从 key_points 里挑第一个语义体含任一关键词的要点（题→答 语义对齐用）。"""
    for kp in (kps or []):
        b = _kp_body(kp)
        if any(k in b for k in keywords):
            return b
    return ""


def _tiers_from_ex(ex, title="分层练习"):
    """把 KB 的 exercises 转成 tiers slots（真实答案）。"""
    out = {"title": title, "basic": [], "standard": [], "advanced": []}
    for qa in (ex.get("basic") or []):
        out["basic"].append({"q": _clip(qa.get("q", ""), 120), "a": _clip(qa.get("a", ""), 400)})
    for qa in (ex.get("standard") or []):
        out["standard"].append({"q": _clip(qa.get("q", ""), 120), "a": _clip(qa.get("a", ""), 400)})
    for qa in (ex.get("advanced") or []):
        out["advanced"].append({"q": _clip(qa.get("q", ""), 120), "a": _clip(qa.get("a", ""), 400)})
    if not out["basic"]:
        out["basic"] = [{"q": "完成本课基础练习。", "a": "独立完成，注意书写工整与单位。"}]
    return out


def _auto_diagrams(kb):
    """按课题/要点关键词自动产出 ≥1 个图示 figure（根治数学"完全没图示"）。
    薄 KB 无 diagrams 字段时也能有图；KB 自带 diagrams 时由调用方优先使用。"""
    topic = (kb.get("topic") or "")
    kps = kb.get("key_points") or []
    text = kb.get("original_text") or ""
    blob = topic + " " + " ".join(kps) + " " + text
    # 富化 KB 的 formulas / worked_examples 里常含本课真实算式（如 7×8=56），
    # 纳入检索范围才能让图示贴合本课（而非退化为通用 3×4 条）。
    blob += " " + " ".join(kb.get("formulas") or [])
    blob += " " + " ".join((w.get("problem", "") for w in (kb.get("worked_examples") or [])))

    # 比/比例课题：必须按 topic 精确判定，且排在"分数/小数"分支之前。
    # 否则"比和比例"等因 KB 同时提到"分数"（比与分数关系）会误命中分数分支，
    # 产出分数图示而非比图示；也避免"用字母表示数"等正文含"比"的课题误判。
    if re.search(r"比例|比值|前项|后项|比\s*[:：]|比$", topic):
        return [{"type": "bar_model", "note": "比表示两个数相除的关系：前项:后项=比值。",
                 "total": 12, "parts": [{"value": 3, "label": "前项 3"}, {"value": 9, "label": "后项 9"}]}]
    if re.search(r"百分数|百分比", topic):
        return [{"type": "bar_model", "note": "百分数表示一个数是另一个数的百分之多少（整体看作100）。",
                 "total": 100, "parts": [{"value": 25, "label": "25%"}, {"value": 75, "label": "75%"}]}]
    # 小数课题优先：topic 含"小数"即本课以小数为主体；其原文常写"分母是…的分数"，
    # 但那是解释小数意义，绝不能据此塞分数条（分数与小数是不同单元）。故按 topic 判定。
    if "小数" in topic or re.search(r"小数是|小数意义|小数性质|小数点移动", blob):
        return [{"type": "number_line",
                 "note": "小数在 0 与 1 之间，对应十分之几、百分之几；数轴上越往右越大。",
                 "min": 0, "max": 1, "min_label": "0", "max_label": "1",
                 "marks": [{"value": 0.1, "label": "0.1"}, {"value": 0.25, "label": "0.25"},
                           {"value": 0.5, "label": "0.5"}, {"value": 0.75, "label": "0.75"}]}]
    if re.search(r"分数", topic) and "小数" not in topic:
        return [
            {"type": "fraction_bars", "note": "分母表示平均分成几份，分子表示取了几份。",
             "bars": [{"num": 1, "den": 4, "label": "1/4"},
                      {"num": 2, "den": 4, "label": "2/4"},
                      {"num": 3, "den": 4, "label": "3/4"}],
             "common": {"den": 4, "parts": [{"num": 2, "den": 4, "label": "2/4"},
                                            {"num": 1, "den": 2, "label": "1/2"}],
                        "result": "2/4 = 1/2"}},
            {"type": "number_line", "note": "在数轴上，右边的数更大，用来比较分数大小。",
             "min": 0, "max": 1, "min_label": "0", "max_label": "1",
             "marks": [{"value": 0.25, "label": "1/4"},
                       {"value": 0.5, "label": "1/2"},
                       {"value": 0.75, "label": "3/4"}]},
        ]
    # 注：旧的 "if re.search(r'比|比例', blob)" 分支已移除——
    # 比/比例改由上方按 topic 精确判定，避免"用字母表示数"等正文含"比"的课题误判为比图示。
    if re.search(r"面积|周长|长方形|正方形", topic):
        return [{"type": "area_grid", "note": "长方形面积 = 长 × 宽；一行几个 × 几行 = 总个数。",
                 "rows": 4, "cols": 6, "shade": {"r": 0, "c": 0, "w": 4, "h": 2},
                 "title": "长 6 格 × 宽 4 格", "total_label": "总数：6 × 4 = 24",
                 "shade_label": "涂色部分：4 × 2 = 8", "caption": "长方形面积 = 长 × 宽"}]
    # 注意：长度/时间分支必须排除"单位/时/分/秒"等单字裸匹配——否则"以万/亿作单位"
    # 或任意含"分"的课文（如乘法口诀、分数）会被误判为长度/时间课题，注入无关图示。
    if re.search(r"长度|千米|毫米|分米|测量|厘米|米", topic) and not re.search(r"面积|周长", topic):
        return [{"type": "number_line", "note": "用单位长度帮助认识米、厘米等计量单位。",
                 "min": 0, "max": 10, "min_label": "0", "max_label": "10 米",
                 "marks": [{"value": 1, "label": "1"}, {"value": 5, "label": "5"}, {"value": 10, "label": "10"}]}]
    if re.search(r"钟表|认识时间|时分秒|几时|时间", topic):
        return [{"type": "number_line", "note": "1 时 = 60 分，1 分 = 60 秒，用数轴认识时间。",
                 "min": 0, "max": 60, "min_label": "0 分", "max_label": "60 分",
                 "marks": [{"value": 15, "label": "15"}, {"value": 30, "label": "30"},
                           {"value": 45, "label": "45"}, {"value": 60, "label": "60"}]}]
    if re.search(r"乘法|除法|乘除|口诀|表内", topic):
        mm = re.search(r'(\d+)\s*[×xX*]\s*(\d+)\s*=?\s*(\d+)?', blob)
        if mm and mm.group(3):
            a, b, c = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
            if 1 <= a <= 12 and 1 <= b <= 12 and c == a * b and a + b <= 24:
                return [{"type": "bar_model",
                         "note": f"{a} × {b} = {c}：表示 {a} 个 {b} 相加，或 {b} 个 {a} 相加。",
                         "total": c,
                         "parts": [{"value": b, "label": f"{b}"} for _ in range(a)]}]
        return [{"type": "bar_model", "note": "乘法是几个相同加数的和；除法是平均分。",
                 "total": 12, "parts": [{"value": 4, "label": "4"}, {"value": 4, "label": "4"}, {"value": 4, "label": "4"}]}]
    if re.search(r"余数", topic):
        return [{"type": "bar_model", "note": "有余数的除法：分完整数份后，剩下的就是余数。",
                 "total": 14, "parts": [{"value": 4, "label": "4×3"}, {"value": 2, "label": "余 2"}]}]
    if re.search(r"因数|倍数", topic):
        return [{"type": "number_line", "note": "倍数可从小到大排列，因数成对出现。",
                 "min": 0, "max": 12, "min_label": "0", "max_label": "12",
                 "marks": [{"value": 2, "label": "2"}, {"value": 4, "label": "4"},
                           {"value": 6, "label": "6"}, {"value": 8, "label": "8"}]}]
    # 大数/计数单位/数位顺序：配「数位顺序表」（认识大数的核心图示），不再落到 0-10 通用数轴。
    # 注意排除「万以内的加法和减法」等运算课（不含「认识」，重点是加减而非数位）。
    if (re.search(r"数的认识", topic) and not re.search(r"分数|小数", topic)) or re.search(r"万以上|大数|数位|计数单位", topic):
        return [{"type": "place_value",
                 "note": "数位顺序表：从个位起，每四个数位为一级（个级、万级、亿级）。",
                 "places": ["亿", "千万", "百万", "十万", "万", "千", "百", "十", "个"],
                 "digits": {"亿": "1", "千万": "2", "百万": "3", "十万": "4", "万": "5",
                            "千": "6", "百": "7", "十": "8", "个": "9"},
                 "caption": "例：123456789 读作一亿二千三百四十五万六千七百八十九"}]
    # 兜底：以下课题与数轴无关（图形认识/运动、统计、概率、代数、概念类），绝不强行塞图，
    # 避免「用数轴讲图形运动/字母表示数」这类知识性错配。仅纯数值/运算类课题才给通用数轴。
    if re.search(r"三角形|圆柱|圆锥|圆形|角|图形|立体|周长|面积|运动|平移|旋转|轴对称|"
                 r"统计|数据|可能性|位置|集合|字母|方程|因数|倍数|质数|合数|运算律|运算定律|"
                 r"平均|比|比例|百分数|折线|条形|扇形|时分秒|测量|长度|重量|容积|容积单位", topic):
        return []
    return [{"type": "number_line", "note": f"用数轴帮助认识「{topic}」。",
             "min": 0, "max": 10, "min_label": "0", "max_label": "10",
             "marks": [{"value": 2, "label": "2"}, {"value": 4, "label": "4"},
                       {"value": 6, "label": "6"}, {"value": 8, "label": "8"}]}]


def _math_lead_question(kb):
    """按课题派生导入问（删除硬编码的"一半"，根治"每课想一想都一样"）。"""
    topic = kb.get("topic", "")
    blob = topic + " " + " ".join(kb.get("key_points") or [])
    if re.search(r"百分数|百分比", topic):
        return "“出勤率 95%”是什么意思？怎样用一个数表示“占了百分之多少”？"
    if re.search(r"分数|小数", topic):
        return "一块月饼平均分给 2 人，每人得到多少？怎样表示“一半”？"
    if re.search(r"面积|周长", topic):
        return "怎样比较两个平面图形谁大谁小？用什么单位来量面积？"
    if re.search(r"比|比例", topic) and not re.search(r"比较|比大小", topic):
        return "“糖:水 = 1:5”表示什么？怎样用比表示两个量之间的关系？"
    if re.search(r"约分|通分", blob):
        return "把一个分数“变小变简单”（分子分母同除以公因数）叫什么？怎样让几个分母不同的分数变成分母相同？"
    if re.search(r"乘法|除法|乘除|口诀|表内", topic):
        return "“每盘放 3 个，4 盘一共多少个？”怎样用乘法算得又对又快？"
    if re.search(r"余数", topic):
        return "“10 个苹果每 3 个放一盘，能放几盘、剩几个？”剩下的怎么办？"
    if re.search(r"时间|钟表|几时|时分秒", topic):
        return "为什么 1 时 = 60 分？怎样在时间轴上找到“过了 25 分”？"
    if re.search(r"长度|米|厘米|千米|毫米|分米", topic):
        return "1 米和 1 厘米差多少？怎样选合适的单位来描述长度？"
    return f"生活中哪里会用到「{topic}」？你是怎样理解它的？"


def _math_practice(kb, title="分层练习"):
    """概念/图形/统计类课的练习：从 key_points 生成「问答配对 + 填空」题。

    旧判断题题干用 key_points 原句（如"轴对称、平移、旋转"），产生"判断对错：轴对称、平移、旋转"
    这种无题干假题。现改为：有「标签：内容」的 key_point → 问标签答内容；无标签 → 概念复述。
    """
    topic = kb.get("topic", "")
    kps = kb.get("key_points") or []
    text = kb.get("original_text") or ""
    out = {"title": title, "basic": [], "standard": [], "advanced": []}

    # 基础：问答配对（标签 → 内容）
    for kp in kps[:3]:
        label, body = _split_label(kp)
        b = body or kp
        if label and body:
            out["basic"].append({"q": f"{label}指的是什么？", "a": _clip(body, 120)})
        else:
            out["basic"].append({"q": f"说一说「{_clip(b, 40)}」的含义。", "a": _clip(b, 120)})

    # 提高：填空题（挖掉 key_points 里的关键数字）
    for kp in kps[:4]:
        b = _kp_body(kp)
        m = re.search(r"\d+(?:\.\d+)?", b)
        if m:
            filled = b.replace(m.group(0), "（　）", 1)
            out["standard"].append({"q": f"填空：{_clip(filled, 80)}", "a": f"填 {m.group(0)}。"})

    # 拓展：生活应用
    _kpb0 = _kp_body(kps[0]) if kps else (text or topic)
    out["advanced"].append({"q": f"结合生活，说说「{topic}」的一个应用。",
                            "a": _clip("例如：" + _kpb0 + "，用它解释生活中的一个现象。", 140)})

    # 兜底：某层空则补概念题
    if not out["basic"]:
        out["basic"] = [{"q": f"什么是「{topic}」？用自己的话说一说。", "a": _clip(text, 120) or "结合本课知识说明。"}]
    if not out["standard"]:
        out["standard"] = out["basic"][:2] or []
    if not out["advanced"]:
        out["advanced"] = out["basic"][:1] or []
    return out


def _math_homework(kb, title):
    """数学课后作业：与课堂练习差异化——熟记要点/完成课本习题/生活应用/讲给家长听。"""
    topic = kb.get("topic", "")
    kps = kb.get("key_points") or []
    text = kb.get("original_text", "")
    first = _first_sentence(text) or topic
    out = {"title": title, "basic": [], "standard": [], "advanced": []}
    if kps:
        out["basic"].append({"q": f"熟记「{_kp_label(kps[0])[1]}」的要点，并工整抄写一遍。",
                             "a": _clip(_kp_body(kps[0]), 200)})
    else:
        out["basic"].append({"q": f"熟记「{topic}」的含义，并工整抄写一遍。",
                             "a": _clip(first, 200)})
    # 从 formulas 出真实题（无 formulas 时退化为要点问答），不用"完成课本习题"元指令
    _fm = (kb.get("formulas") or [""])[0]
    _fm_body = _strip_formula_label(_fm) if _fm else ""
    if _fm_body and re.search(r"\d", _fm_body):
        out["basic"].append({"q": f"练一练：{_clip(_fm_body, 80)}，写出你的答案。",
                             "a": f"参考答案：{_clip(_fm_body, 120)}；注意书写步骤与单位。"})
    else:
        out["basic"].append({"q": f"说一说「{topic}」的要点，并默写一遍。",
                             "a": _clip(_kp_body(kps[0]), 200) if kps else _clip(first, 200)})
    out["standard"].append({"q": f"用「{topic}」解决一个生活中的实际问题，写清已知信息与解答步骤。",
                            "a": "先找已知信息与问题，再选本课方法列式，最后检查。"})
    out["advanced"].append({"q": f"把今天学的「{topic}」讲给家长听，并举一个生活中的例子；整理一道你做错的题。",
                            "a": "讲清定义与用法；错题写清错因与正确解法。"})
    return out


def _math_kp_points(kp):
    """把一条数学 key_point 变成 2~3 条可上讲台讲解的真实要点（真实内容，非元提示）。

    薄 KB 无更细的讲解材料时，按关键词给出"概念/公式/用法"的具体一句，
    保证每页都有可教的内容，而不是"教学提示：把 XXX 讲清楚"这种空话。

    关键修正：
      - 关键词判断基于"剥掉头部标签后的语义体"（如"比较：…"不再误触发"比"分支）；
      - 不再把整条 key_point 当首条要点插入，避免与页面标题重复。
    """
    k = kp or ""
    _, kk = _split_label(k)        # 用语义体判断，避免"比较"标签误触发"比"
    kk = kk or k
    out = []
    if "面积" in kk:
        out.append("面积表示平面图形或物体表面的大小。")
    if ("长方形" in kk or "长×宽" in kk) and "面积" in kk:
        out.append("长方形面积 = 长 × 宽；已知长、宽直接相乘。")
    if ("正方形" in kk or "边长" in kk) and "面积" in kk:
        out.append("正方形面积 = 边长 × 边长。")
    if "面积" in kk and "单位" in kk:
        out.append("常用面积单位：cm²、dm²、m²，相邻进率 100。")
    if "进率" in kk:
        out.append("面积单位进率：1 m² = 100 dm²，1 dm² = 100 cm²。")
    if "周长" in kk:
        out.append("周长是封闭图形一周的长度。")
        if "长方形" in kk or "长" in kk:
            out.append("长方形周长 = (长 + 宽) × 2。")
    if "比较" in kk or "比大小" in kk:
        # 「比较」不能无差别注入分数比较——那是分数课的专属内容。
        # 必须按语义体区分：分数比较 / 小数比较 / 大数（整数）比较，避免「大数的读、写与比较」张冠李戴成分数。
        if "分数" in kk:
            out.append("同分母分数比较：分母相同看分子，分子大的分数大。")
        elif "小数" in kk:
            out.append("小数比较：先比整数部分，整数部分相同再逐位比较小数部分。")
        else:
            out.append("比较两个数的大小：先比位数，位数多的数大；位数相同，从最高位比起。")
    if "分数" in kk and "百分数" not in kk:
        out.append("分数表示整体的一部分：分母 = 平均分的份数，分子 = 取走的份数。")
    if "百分数" in kk or "百分比" in kk:
        out.append("百分数表示一个数占另一个数的百分之几，整体看作 100。")
    if "小数" in kk:
        out.append("小数表示十分之几、百分之几（如0.1、0.25），是分数的另一种写法。")
    # 仅当课题确为"乘/除/口诀"主题时，才注入乘除通用讲解，
    # 避免"约分：除以最大公因数""比：a÷b"等因含"除/乘"字而误注入"除法是平均分/用乘法口诀"。
    _is_arith = bool(re.search(r"乘法|除法|乘除|乘以|口诀|表内|口算", kk))
    if "互逆" in kk:
        out.append("乘法与除法互为逆运算：积÷一个因数=另一个因数；一句口诀可写两个乘法、两个除法算式。")
    elif "求商" in kk or "求积" in kk:
        out.append("用乘法口诀求积与求商：想两个因数对应哪句口诀，积是口诀后半句；求商想“几×除数=被除数”。")
    elif "口诀" in kk:
        out.append("熟记7、8、9的乘法口诀，能顺着背、倒着背，并说出每句口诀对应的乘、除算式。")
    elif "乘" in kk and _is_arith:
        out.append("用乘法口诀可快速求积；乘除互为逆运算，可用口诀求商。")
    if "除" in kk and _is_arith and "互逆" not in kk:
        out.append("除法是平均分或包含除；整除时余数为 0。")
    if "余数" in kk:
        out.append("余数必须比除数小；剩下的不够再分一份。")
    # 仅当确为"比/比例/比值"且非"比较/比大小/对比"等时才给比的定义，根治分数课泄漏"比表示两个数相除"
    if ("比例" in kk or "比值" in kk) or \
       ("比" in kk and not any(x in kk for x in ("比较", "比大小", "比一比", "对比", "百分比", "分数", "百分数"))):
        out.append("比表示两个数相除：前项 : 后项 = 比值。")
    if "单位" in kk and "面积" not in kk and ("长度" in kk or "米" in kk or "厘米" in kk):
        out.append("长度单位：km、m、dm、cm、mm，相邻进率 10。")
    if any(t in kk for t in ("折扣", "成数", "税率", "利率", "增减", "应用")):
        out.append("常见应用：折扣（几折=百分之几十）、税率、利率、求增减百分之几。")
    if not out:
        out.append(kk)
    return out[:3]


def _strip_formula_label(fm):
    """去掉公式头部"应用：/示例：/折扣："等标签，返回语义体。"""
    if not fm:
        return ""
    return re.sub(r'^(应用|示例|例题|折扣|税率|增减|互化|意义)[：:]\s*', '', fm).strip()


# ---------------------------------------------------------------------------
# 确定性数学引擎：从 formulas（原料）生成例题/练习（零 LLM，答案程序算，100% 正确）。
# 覆盖四则 / 改写(万·亿) / 读法 / 近似。这是「生成式」路径的核心——KB 只存原料，
# 例题/练习在生成时由规则产出（变式可无限扩展，非写死成品）。
# ---------------------------------------------------------------------------
# 注意：'/' 是分数线（分数 a/b），不是除号——除法只用 '÷'。
_M_ARITH = re.compile(r"(\d+(?:\.\d+)?)\s*([+\-*×÷])\s*(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)")
_M_OP_CN = {"+": "加", "-": "减", "*": "乘", "÷": "除", "×": "乘"}
_M_OP_SYM = {"+": "+", "-": "-", "*": "×", "÷": "÷", "×": "×"}


def _m_calc(a, op, b):
    a, b = float(a), float(b)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op in ("*", "×"):
        return a * b
    if op == "÷":
        return a / b if b != 0 else None
    return None


def _m_fmt(x):
    if x is None or x == "":
        return ""
    x = float(x)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.4f}".rstrip("0").rstrip(".")


def _m_arith_example(a, op, b):
    c = _m_calc(a, op, b)
    if c is None:
        return None
    cs = _m_fmt(c)
    sym = _M_OP_SYM.get(op, op)
    cn = _M_OP_CN.get(op, op)
    return {
        "problem": f"计算：{a} {sym} {b} = ？",
        "steps": [f"想：{a} {cn} {b}，就是求 {a} 与 {b} 的{cn}法结果",
                  f"计算：{a} {sym} {b} = {cs}"],
        "answer": f"{a} {sym} {b} = {cs}。",
        "method": f"直接用 {a} {cn} {b}，得 {cs}。",
    }


def _m_arith_practice(a, op, b):
    c = _m_calc(a, op, b)
    if c is None:
        return None
    cs = _m_fmt(c)
    sym = _M_OP_SYM.get(op, op)
    return (f"计算：{a} {sym} {b} = ？", f"{a} {sym} {b} = {cs}")


def _m_inverse_practice(a, op, b, c):
    if op == "+":
        return (f"（　）+ {b} = {_m_fmt(c)}，括号里填几？", f"括号里填 {_m_fmt(a)}，因为 {a} + {b} = {_m_fmt(c)}。")
    if op == "-":
        return (f"{_m_fmt(c)} - {b} = ？", f"{_m_fmt(c)} - {b} = {_m_fmt(a)}。")
    if op in ("*", "×"):
        return (f"（　）× {b} = {_m_fmt(c)}，括号里填几？", f"括号里填 {_m_fmt(a)}，因为 {a} × {b} = {_m_fmt(c)}。")
    if op == "÷":
        return (f"{_m_fmt(c)} ÷ {b} = ？", f"{_m_fmt(c)} ÷ {b} = {_m_fmt(a)}。")
    return None


def _m_rewrite_example(raw):
    m = re.search(r"(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)\s*(亿|万)", raw)
    if not m:
        return None
    src, dst, unit = m.group(1), m.group(2), m.group(3)
    base = 100000000 if unit == "亿" else 10000
    return {
        "problem": f"把 {src} 改写成用“{unit}”作单位的数。",
        "steps": [f"看 {unit} 位，在 {unit} 位的右下角点上小数点",
                  f"{src} ÷ {base} = {dst}",
                  "去掉小数末尾的 0，在数后写上“" + unit + "”"],
        "answer": f"{src} = {dst}{unit}。",
        "method": f"改写用“{unit}”作单位：除以 {base}，点上小数点，去掉末尾 0，带上“{unit}”字。",
    }


def _m_reading_example(raw):
    m = re.search(r"(\d{4,})\s*读作\s*([一-龥零两二三四五六七八九十百千万亿]+)", raw)
    if not m:
        return None
    num_s, reading = m.group(1), m.group(2)
    return {
        "problem": f"读出这个数：{num_s}。",
        "steps": ["从高位到低位，先分级（个级、万级、亿级）", "逐级读出每一级上的数", f"合起来读作：{reading}"],
        "answer": f"{num_s} 读作 {reading}。",
        "method": "读大数先分级，从高位读起，每级末尾的 0 不读。",
    }


def _m_approx_example(raw):
    m = re.search(r"(\d+)\s*≈\s*(\d+(?:\.\d+)?)\s*(万|亿)?", raw)
    if not m:
        return None
    src, dst, unit = m.group(1), m.group(2), m.group(3) or ""
    return {
        "problem": f"用“四舍五入”法求 {src} 的近似数" + (f"（到{unit}位）" if unit else "") + "。",
        "steps": ["找到要保留的数位，看它的下一位", "下一位小于 5 就舍去，大于等于 5 就向前进一", f"{src} ≈ {dst}{unit}"],
        "answer": f"{src} ≈ {dst}{unit}。",
        "method": "四舍五入：看保留位数的下一位，小于 5 舍、大于等于 5 进。",
    }


def _deterministic_math(kb):
    """从 formulas（原料）确定性生成 worked_examples + exercises。
    返回 None 表示 formulas 不足以构造（需走免费模型/概念题兜底）。"""
    formulas = kb.get("formulas") or []
    examples, practice = [], []
    for fm in formulas:
        fm = (fm or "").strip()
        if not fm:
            continue
        label = fm.split("：", 1)[0] if "：" in fm else fm.split(":", 1)[0]
        body = fm.split("：", 1)[1] if "：" in fm else (fm.split(":", 1)[1] if ":" in fm else fm)
        raw = body if ("：" in fm or ":" in fm) else fm

        if "改写" in label or ("=" in raw and re.search(r"(亿|万)\s*$", raw)):
            ex = _m_rewrite_example(raw)
            if ex:
                if len(examples) < 3:
                    examples.append(ex)
                m = re.search(r"(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)\s*(亿|万)", raw)
                if m:
                    practice.append((f"把 {m.group(1)} 改写成用“{m.group(3)}”作单位的数。",
                                     f"{m.group(1)} = {m.group(2)}{m.group(3)}。"))
            continue
        if "读作" in raw:
            ex = _m_reading_example(raw)
            if ex:
                if len(examples) < 3:
                    examples.append(ex)
                m = re.search(r"(\d{4,})\s*读作\s*([一-龥零两二三四五六七八九十百千万亿]+)", raw)
                if m:
                    practice.append((f"读出这个数：{m.group(1)}。", f"{m.group(1)} 读作 {m.group(2)}。"))
            continue
        if "近似" in label or "≈" in raw:
            ex = _m_approx_example(raw)
            if ex:
                if len(examples) < 3:
                    examples.append(ex)
                m = re.search(r"(\d+)\s*≈\s*(\d+(?:\.\d+)?)\s*(万|亿)?", raw)
                if m:
                    unit = m.group(3) or ""
                    practice.append((f"用“四舍五入”法求 {m.group(1)} 的近似数" + (f"（到{unit}位）" if unit else "") + "。",
                                     f"{m.group(1)} ≈ {m.group(2)}{unit}。"))
            continue
        # 周长/面积/体积：从「长X宽Y + 周长/面积」「a=X,b=Y,h=Z + V」「边长X + 周长」解析
        _geo = None
        if "周长" in raw or "面积" in raw or ("体积" in raw) or ("V" in raw and "h" in raw):
            _m_lw = re.search(r"长\s*(\d+)\s*宽\s*(\d+)", raw)
            _m_bc = re.search(r"边长\s*(\d+)", raw)
            _m_v = re.search(r"[abh]\s*=\s*(\d+)\s*[,，]\s*[abh]\s*=\s*(\d+)\s*[,，]\s*[abh]\s*=\s*(\d+)", raw)
            if _m_lw:
                _x, _y = int(_m_lw.group(1)), int(_m_lw.group(2))
                if "周长" in raw:
                    _geo = {"problem": f"一个长方形，长 {_x} 厘米，宽 {_y} 厘米，它的周长是多少厘米？",
                            "steps": ["长方形周长 = (长 + 宽) × 2", f"代入：( {_x} + {_y} ) × 2 = {2 * (_x + _y)}"],
                            "answer": f"周长 = {2 * (_x + _y)} 厘米。", "method": "长方形周长 = (长 + 宽) × 2"}
                    practice.append((f"一个长方形长 {_x} 厘米、宽 {_y} 厘米，求周长。", f"({_x}+{_y})×2 = {2 * (_x + _y)} 厘米。"))
                if "面积" in raw:
                    _geo = {"problem": f"一个长方形，长 {_x} 厘米，宽 {_y} 厘米，它的面积是多少平方厘米？",
                            "steps": ["长方形面积 = 长 × 宽", f"代入：{_x} × {_y} = {_x * _y}"],
                            "answer": f"面积 = {_x * _y} 平方厘米。", "method": "长方形面积 = 长 × 宽"}
                    practice.append((f"一个长方形长 {_x} 厘米、宽 {_y} 厘米，求面积。", f"{_x}×{_y} = {_x * _y} 平方厘米。"))
            elif _m_bc and "周长" in raw:
                _z = int(_m_bc.group(1))
                _geo = {"problem": f"一个正方形，边长 {_z} 厘米，它的周长是多少厘米？",
                        "steps": ["正方形周长 = 边长 × 4", f"代入：{_z} × 4 = {4 * _z}"],
                        "answer": f"周长 = {4 * _z} 厘米。", "method": "正方形周长 = 边长 × 4"}
                practice.append((f"一个正方形边长 {_z} 厘米，求周长。", f"{_z}×4 = {4 * _z} 厘米。"))
            elif _m_v:
                _a, _b, _h = int(_m_v.group(1)), int(_m_v.group(2)), int(_m_v.group(3))
                _geo = {"problem": f"一个长方体，长 {_a} 厘米、宽 {_b} 厘米、高 {_h} 厘米，它的体积是多少立方厘米？",
                        "steps": ["长方体体积 = 长 × 宽 × 高", f"代入：{_a} × {_b} × {_h} = {_a * _b * _h}"],
                        "answer": f"体积 = {_a * _b * _h} 立方厘米。", "method": "长方体体积 = 长 × 宽 × 高"}
                practice.append((f"一个长方体长 {_a}、宽 {_b}、高 {_h}，求体积。", f"{_a}×{_b}×{_h} = {_a * _b * _h} 立方厘米。"))
            if _geo:
                if len(examples) < 3:
                    examples.append(_geo)
                continue

        # ── 同分母分数加减：a/b ± c/d = e/f（分母相同）──
        _mf = re.search(r"(\d+)/(\d+)\s*([+\-])\s*(\d+)/(\d+)\s*=\s*(\d+)/(\d+)", raw)
        if _mf and int(_mf.group(2)) == int(_mf.group(5)):
            _n1, _d1 = int(_mf.group(1)), int(_mf.group(2))
            _op = _mf.group(3)
            _n2, _d2 = int(_mf.group(4)), int(_mf.group(5))
            _nr, _dr = int(_mf.group(6)), int(_mf.group(7))
            if _d1 == _d2 == _dr:
                _exp_n = (_n1 + _n2) if _op == "+" else (_n1 - _n2)
                if _exp_n == _nr:
                    _opcn = "加" if _op == "+" else "减"
                    _ex = {"problem": f"计算：{_n1}/{_d1} {_op} {_n2}/{_d2} = ？",
                           "steps": [f"分母相同（都是 {_d1}），分母不变",
                                     f"分子相{_opcn}：{_n1} {_op} {_n2} = {_nr}",
                                     f"结果是 {_nr}/{_dr}"],
                           "answer": f"{_n1}/{_d1} {_op} {_n2}/{_d2} = {_nr}/{_dr}。",
                           "method": f"同分母分数相{_opcn}：分母不变，分子相{_opcn}。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"计算：{_n1}/{_d1} {_op} {_n2}/{_d2} = ？", f"{_nr}/{_dr}"))
            continue

        # ── 三角形/梯形/平行四边形面积（用完整 formula 判断题型，避免 label 剥离丢标签）──
        if "面积" in raw or "底" in raw or "三角" in fm or "梯形" in fm or "平行四边" in fm:
            _m_lwh = re.search(r"底\s*(\d+)\s*高\s*(\d+)", fm)
            _m_tra = re.search(r"上底\s*(\d+)\s*下底\s*(\d+)\s*高\s*(\d+)", fm)
            _area_ex = None
            if "三角" in fm and _m_lwh:
                _b, _h = int(_m_lwh.group(1)), int(_m_lwh.group(2))
                _area_ex = {"problem": f"一个三角形，底 {_b} 厘米，高 {_h} 厘米，它的面积是多少平方厘米？",
                            "steps": ["三角形面积 = 底 × 高 ÷ 2", f"代入：{_b} × {_h} ÷ 2 = {_b * _h / 2:g}"],
                            "answer": f"面积 = {_b * _h / 2:g} 平方厘米。", "method": "三角形面积 = 底 × 高 ÷ 2"}
                practice.append((f"一个三角形底 {_b} 厘米、高 {_h} 厘米，求面积。", f"{_b}×{_h}÷2 = {_b * _h / 2:g} 平方厘米。"))
            elif _m_tra:
                _a, _b, _h = int(_m_tra.group(1)), int(_m_tra.group(2)), int(_m_tra.group(3))
                _area_ex = {"problem": f"一个梯形，上底 {_a} 厘米，下底 {_b} 厘米，高 {_h} 厘米，它的面积是多少平方厘米？",
                            "steps": ["梯形面积 = (上底 + 下底) × 高 ÷ 2", f"代入：({_a} + {_b}) × {_h} ÷ 2 = {(_a + _b) * _h / 2:g}"],
                            "answer": f"面积 = {(_a + _b) * _h / 2:g} 平方厘米。", "method": "梯形面积 = (上底 + 下底) × 高 ÷ 2"}
                practice.append((f"一个梯形上底 {_a}、下底 {_b}、高 {_h}，求面积。", f"({_a}+{_b})×{_h}÷2 = {(_a + _b) * _h / 2:g} 平方厘米。"))
            elif _m_lwh:
                _b, _h = int(_m_lwh.group(1)), int(_m_lwh.group(2))
                _area_ex = {"problem": f"一个平行四边形，底 {_b} 厘米，高 {_h} 厘米，它的面积是多少平方厘米？",
                            "steps": ["平行四边形面积 = 底 × 高", f"代入：{_b} × {_h} = {_b * _h}"],
                            "answer": f"面积 = {_b * _h} 平方厘米。", "method": "平行四边形面积 = 底 × 高"}
                practice.append((f"一个平行四边形底 {_b} 厘米、高 {_h} 厘米，求面积。", f"{_b}×{_h} = {_b * _h} 平方厘米。"))
            if _area_ex:
                if len(examples) < 3:
                    examples.append(_area_ex)
                continue

        # ── 有余数除法：a÷b=c……d ──
        _mr = re.search(r"(\d+)\s*÷\s*(\d+)\s*=\s*(\d+)\s*……\s*(\d+)", raw)
        if _mr:
            _a, _b, _q, _rem = (int(_mr.group(i)) for i in range(1, 5))
            if _a == _b * _q + _rem and _rem < _b:
                _ex = {"problem": f"计算：{_a} ÷ {_b} = ？",
                       "steps": [f"想：{_b} × {_q} = {_b * _q}，最接近 {_a} 且不超过它",
                                 f"{_a} - {_b * _q} = {_rem}，剩下 {_rem}",
                                 f"所以 {_a} ÷ {_b} = {_q}……{_rem}"],
                       "answer": f"{_a} ÷ {_b} = {_q}……{_rem}。",
                       "method": "有余数除法：商 × 除数 + 余数 = 被除数，余数必须比除数小。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"计算：{_a} ÷ {_b} = ？", f"{_q}……{_rem}"))
            continue

        # ── 数的组成：35 = 3个十+5个一 ──
        _mc = re.search(r"(\d+)\s*=\s*(\d+)\s*个十\s*\+\s*(\d+)\s*个一", raw)
        if _mc:
            _n, _t, _o = int(_mc.group(1)), int(_mc.group(2)), int(_mc.group(3))
            if _n == _t * 10 + _o:
                _ex = {"problem": f"{_n} 里面有（　）个十和（　）个一？",
                       "steps": [f"{_n} 的十位是 {_t}，表示 {_t} 个十",
                                 f"{_n} 的个位是 {_o}，表示 {_o} 个一"],
                       "answer": f"{_n} = {_t} 个十 + {_o} 个一。",
                       "method": "一个两位数：十位上是几就是几个十，个位上是几就是几个一。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"{_n} 里面有（　）个十和（　）个一？", f"{_t} 个十、{_o} 个一。"))
            continue

        # ── 比较大小：48＜52 / 48＞52 ──
        _mcmp = re.search(r"(\d+)\s*([＜<>＞])\s*(\d+)", raw)
        if _mcmp:
            _a, _sym, _b = int(_mcmp.group(1)), _mcmp.group(2), int(_mcmp.group(3))
            _correct = ("＜" if _a < _b else "＞" if _a > _b else "＝")
            _sym = "＜" if _sym in ("<", "＜") else "＞" if _sym in (">", "＞") else _sym
            _ex = {"problem": f"比较大小：{_a} 和 {_b}，哪个大？",
                   "steps": [f"先比位数，位数相同再从最高位比起", f"{_a} 与 {_b} 比较，{_a} {'小' if _a < _b else '大'}"],
                   "answer": f"{_a} {_correct} {_b}。",
                   "method": "比较大小：位数相同，从最高位比起。"}
            if len(examples) < 3:
                examples.append(_ex)
            practice.append((f"比较大小：{_a} ○ {_b}。", f"{_a} {_correct} {_b}"))
            continue

        # ── 异分母分数加减：a/b ± c/d = … = e/f（末尾为最简结果）──
        _mf2 = re.search(r"(\d+)/(\d+)\s*([+\-])\s*(\d+)/(\d+)\s*=[^=]*?(\d+)/(\d+)\s*$", raw)
        if _mf2 and (_mf2.group(2) != _mf2.group(5)):
            _n1, _d1, _op = int(_mf2.group(1)), int(_mf2.group(2)), _mf2.group(3)
            _n2, _d2, _nr, _dr = int(_mf2.group(4)), int(_mf2.group(5)), int(_mf2.group(6)), int(_mf2.group(7))
            # 通分后计算，验证结果正确
            _lcm = _d1 * _d2
            _rn1 = _n1 * _d2
            _rn2 = _n2 * _d1
            _rn = (_rn1 + _rn2) if _op == "+" else (_rn1 - _rn2)
            if _rn * _dr == _nr * _lcm:
                _opcn = "加" if _op == "+" else "减"
                _ex = {"problem": f"计算：{_n1}/{_d1} {_op} {_n2}/{_d2} = ？",
                       "steps": [f"分母不同，先通分：{_d1} 和 {_d2} 的最小公倍数是 {_lcm}",
                                 f"{_n1}/{_d1} = {_rn1}/{_lcm}，{_n2}/{_d2} = {_rn2}/{_lcm}",
                                 f"分子相{_opcn}：{_rn1} {_op} {_rn2} = {_rn}，结果是 {_nr}/{_dr}"],
                       "answer": f"{_n1}/{_d1} {_op} {_n2}/{_d2} = {_nr}/{_dr}。",
                       "method": f"异分母分数相{_opcn}：先通分，再按同分母相{_opcn}。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"计算：{_n1}/{_d1} {_op} {_n2}/{_d2} = ？", f"{_nr}/{_dr}"))
            continue

        # ── 分数乘法：3×1/3=1、1/2×1/3=1/6、求100的1/4=25（排除含 ÷ 的分数除法）──
        if "×" in raw and "/" in raw and "÷" not in raw:
            _m_fm1 = re.search(r"(\d+)\s*×\s*(\d+)/(\d+)\s*=\s*(\d+)", raw)          # 整数×分数
            _m_fm2 = re.search(r"(\d+)/(\d+)\s*×\s*(\d+)/(\d+)\s*=\s*(\d+)/(\d+)", raw)  # 分数×分数
            _m_fm3 = re.search(r"求\s*(\d+)\s*的\s*(\d+)/(\d+)\s*=.*?=\s*(\d+)", raw)   # 求a的b/c
            if _m_fm1:
                _a, _bn, _bd, _r = int(_m_fm1.group(1)), int(_m_fm1.group(2)), int(_m_fm1.group(3)), int(_m_fm1.group(4))
                if _a * _bn == _r * _bd:
                    _ex = {"problem": f"计算：{_a} × {_bn}/{_bd} = ？",
                           "steps": [f"整数乘分数：{_a} × {_bn}/{_bd}", f"= {_a * _bn}/{_bd} = {_r}"],
                           "answer": f"{_a} × {_bn}/{_bd} = {_r}。",
                           "method": "整数乘分数：整数乘分子作分子，分母不变，能约分要约分。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"计算：{_a} × {_bn}/{_bd} = ？", f"{_r}"))
            elif _m_fm2:
                _a, _b, _c, _d, _r1, _r2 = (int(_m_fm2.group(i)) for i in range(1, 7))
                # 校验 a/b × c/d = r1/r2（约分后相等）
                if _a * _c * _r2 == _r1 * _b * _d:
                    _ex = {"problem": f"计算：{_a}/{_b} × {_c}/{_d} = ？",
                           "steps": [f"分数乘分数：分子乘分子，分母乘分母", f"= {_a * _c}/{_b * _d} = {_r1}/{_r2}"],
                           "answer": f"{_a}/{_b} × {_c}/{_d} = {_r1}/{_r2}。",
                           "method": "分数乘分数：分子乘分子作分子，分母乘分母作分母。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"计算：{_a}/{_b} × {_c}/{_d} = ？", f"{_r1}/{_r2}"))
            elif _m_fm3:
                _a, _bn, _bd, _r = int(_m_fm3.group(1)), int(_m_fm3.group(2)), int(_m_fm3.group(3)), int(_m_fm3.group(4))
                if _a * _bn == _r * _bd:
                    _ex = {"problem": f"求 {_a} 的 {_bn}/{_bd} 是多少？",
                           "steps": [f"求一个数的几分之几，用乘法：{_a} × {_bn}/{_bd}", f"= {_a * _bn}/{_bd} = {_r}"],
                           "answer": f"{_a} 的 {_bn}/{_bd} 是 {_r}。",
                           "method": "求一个数的几分之几：用这个数乘几分之几。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"求 {_a} 的 {_bn}/{_bd} 是多少？", f"{_r}"))
            continue

        # ── 分数除法：2/3÷4/5=…=5/6 ──
        _mfd = re.search(r"(\d+)/(\d+)\s*÷\s*(\d+)/(\d+)\s*=.*?(\d+)/(\d+)\s*$", raw)
        if _mfd:
            _a, _b, _c, _d, _r1, _r2 = (int(_mfd.group(i)) for i in range(1, 7))
            # 校验：a/b ÷ c/d = a/b × d/c = a*d / b*c
            if _a * _d * _r2 == _r1 * _b * _c:
                _ex = {"problem": f"计算：{_a}/{_b} ÷ {_c}/{_d} = ？",
                       "steps": [f"分数除法：除以一个数等于乘它的倒数", f"{_a}/{_b} ÷ {_c}/{_d} = {_a}/{_b} × {_d}/{_c}", f"= {_a * _d}/{_b * _c} = {_r1}/{_r2}"],
                       "answer": f"{_a}/{_b} ÷ {_c}/{_d} = {_r1}/{_r2}。",
                       "method": "分数除法：除以一个数等于乘这个数的倒数。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"计算：{_a}/{_b} ÷ {_c}/{_d} = ？", f"{_r1}/{_r2}"))
            continue

        # ── 约分：6/8=3/4 ──
        if "约分" in fm or "约分" in raw:
            _myf = re.search(r"(\d+)/(\d+)\s*=\s*(\d+)/(\d+)", raw)
            if _myf:
                _a, _b, _c, _d = (int(_myf.group(i)) for i in range(1, 5))
                if _a * _d == _c * _b:
                    _ex = {"problem": f"把 {_a}/{_b} 约分成最简分数。",
                           "steps": [f"分子分母同时除以它们的公因数", f"{_a}/{_b} = {_c}/{_d}"],
                           "answer": f"{_a}/{_b} = {_c}/{_d}。",
                           "method": "约分：分子分母同时除以公因数，化成最简分数。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"把 {_a}/{_b} 约分。", f"{_c}/{_d}"))
            continue

        # ── 用字母表示数：a×b=ab（字母相乘省略乘号）、S=ah（字母表示公式）──
        if "用字母" in kb.get("topic", "") or "字母" in kb.get("topic", ""):
            _ml = re.search(r"([A-Za-z])\s*[×xX*]\s*([A-Za-z])\s*=\s*([A-Za-z]{2})", raw)
            if _ml and _ml.group(3).lower() == (_ml.group(1) + _ml.group(2)).lower():
                _a, _b = _ml.group(1), _ml.group(2)
                _ex = {"problem": f"用字母表示：{_a} × {_b} 可以怎样简写？",
                       "steps": [f"字母与字母相乘，乘号可以省略", f"{_a} × {_b} = {_a}{_b}"],
                       "answer": f"{_a} × {_b} = {_a}{_b}。",
                       "method": "字母相乘，省略乘号，按字母顺序书写。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"把 {_a} × {_b} 简写成字母式。", f"{_a}{_b}"))
                continue

        # ── 解方程：x+3=9 → x=6；3x=18 → x=6 ──
        if "解方程" in fm or ("x" in raw and "=" in raw and ("解" in fm or "x =" in raw or "x=" in raw)):
            _mx1 = re.search(r"x\s*([+\-])\s*(\d+)\s*=\s*(\d+).*?x\s*=\s*(\d+)", raw)
            _mx2 = re.search(r"(\d+)\s*x\s*=\s*(\d+).*?x\s*=\s*(\d+)", raw)
            if _mx1:
                _op, _b, _c, _ans = _mx1.group(1), int(_mx1.group(2)), int(_mx1.group(3)), int(_mx1.group(4))
                _expect = (_c - _b) if _op == "+" else (_c + _b)
                if _expect == _ans:
                    _ex = {"problem": f"解方程：x {_op} {_b} = {_c}。",
                           "steps": [f"方程两边同时{'减' if _op == '+' else '加'} {_b}",
                                     f"x = {_c} {'-' if _op == '+' else '+'} {_b} = {_ans}"],
                           "answer": f"x = {_ans}。",
                           "method": "解方程：等式两边同时加减同一个数，等式仍成立。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"解方程：x {_op} {_b} = {_c}。", f"x = {_ans}"))
            elif _mx2:
                _a, _c, _ans = int(_mx2.group(1)), int(_mx2.group(2)), int(_mx2.group(3))
                if _a != 0 and _c == _a * _ans:
                    _ex = {"problem": f"解方程：{_a}x = {_c}。",
                           "steps": [f"方程两边同时除以 {_a}", f"x = {_c} ÷ {_a} = {_ans}"],
                           "answer": f"x = {_ans}。",
                           "method": "解方程：等式两边同时除以同一个不为 0 的数，等式仍成立。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"解方程：{_a}x = {_c}。", f"x = {_ans}"))
            continue

        # ── 混合运算（含括号/运算律）：12+8×3=36、25×(40+4)=1100 ──
        # 护栏：只在「真正的混合运算」上贴「混合运算顺序」方法框——即算式同时含
        # 乘/除 与 加/减（或括号改变次序）。纯单一运算（如 7×8=56、12+8=20）
        # 不算混合，绝不贴「先括号、再乘除、后加减」模板（A5 修复）。
        _mh = re.search(r"([0-9+\-×÷()（）]+)\s*=\s*(\d+(?:\.\d+)?)", raw)
        if _mh:
            _mh_src = _mh.group(1)
            _has_mul = ("×" in _mh_src or "÷" in _mh_src)
            _has_add = ("+" in _mh_src or "-" in _mh_src)
            if _has_mul and _has_add:
                _expr = _mh.group(1).replace("×", "*").replace("÷", "/").replace("（", "(").replace("）", ")")
                _res = _mh.group(2)
                if re.fullmatch(r"[0-9+\-*/()]+", _expr):
                    try:
                        _got = eval(_expr, {"__builtins__": {}}, {})  # noqa: S307 白名单字符已校验
                        if abs(_got - float(_res)) < 1e-9:
                            _disp = _mh.group(1)
                            _ex = {"problem": f"计算：{_disp} = ？",
                                   "steps": [f"先算括号里的，再算乘除，最后算加减", f"{_disp} = {_res}"],
                                   "answer": f"{_disp} = {_res}。",
                                   "method": "混合运算顺序：先括号、再乘除、后加减。"}
                            if len(examples) < 3:
                                examples.append(_ex)
                            practice.append((f"计算：{_disp} = ？", f"{_res}"))
                    except Exception:
                        pass
                continue

        # ── 平均数：90、80、70 平均=80 ──
        _mavg = re.search(r"([0-9、，,]+)\s*平均.*?=\s*(\d+(?:\.\d+)?)", raw)
        if _mavg:
            _nums = [int(x) for x in re.findall(r"\d+", _mavg.group(1))]
            _res = float(_mavg.group(2))
            if _nums and abs(sum(_nums) / len(_nums) - _res) < 1e-9:
                _ex = {"problem": f"求 {('、'.join(map(str, _nums)))} 这 {len(_nums)} 个数的平均数。",
                       "steps": [f"先求总和：{' + '.join(map(str, _nums))} = {sum(_nums)}",
                                 f"再除以个数：{sum(_nums)} ÷ {len(_nums)} = {_res:g}"],
                       "answer": f"平均数是 {_res:g}。",
                       "method": "平均数 = 总数 ÷ 份数。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"求 {('、'.join(map(str, _nums)))} 的平均数。", f"{_res:g}"))
            continue

        # ── 百分数互化：0.25=25%、25%=1/4 ──
        if "%" in raw and "=" in raw:
            _mp1 = re.search(r"(\d+(?:\.\d+)?)\s*=\s*(\d+(?:\.\d+)?)\s*%", raw)
            _mp2 = re.search(r"(\d+(?:\.\d+)?)\s*%\s*=\s*(\d+)/(\d+)", raw)
            if _mp1:
                _a, _b = float(_mp1.group(1)), float(_mp1.group(2))
                if abs(_a * 100 - _b) < 1e-9:
                    _ex = {"problem": f"把 {_a:g} 化成百分数。",
                           "steps": [f"小数化成百分数：小数点向右移动两位，加 %", f"{_a:g} × 100% = {_b:g}%"],
                           "answer": f"{_a:g} = {_b:g}%。",
                           "method": "小数→百分数：乘 100%，加百分号。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"把 {_a:g} 化成百分数。", f"{_b:g}%"))
            elif _mp2:
                _a, _b, _c = int(_mp2.group(1)), int(_mp2.group(2)), int(_mp2.group(3))
                if _a * _c == _b * 100:
                    _ex = {"problem": f"把 {_a}% 化成分数。",
                           "steps": [f"百分数化成分数：{_a}% = {_a}/100", f"约分：{_a}/100 = {_b}/{_c}"],
                           "answer": f"{_a}% = {_b}/{_c}。",
                           "method": "百分数→分数：写成 a/100 再约分。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"把 {_a}% 化成分数。", f"{_b}/{_c}"))
            continue

        # ── 比化简：2:4=1:2 ──
        if "化简" in fm:
            _mb = re.search(r"(\d+)\s*:\s*(\d+)\s*=\s*(\d+)\s*:\s*(\d+)", raw)
            if _mb:
                _a, _b, _c, _d = (int(_mb.group(i)) for i in range(1, 5))
                if _a * _d == _b * _c and _c < _a:
                    _ex = {"problem": f"化简比：{_a}:{_b}。",
                           "steps": [f"比的前项和后项同时除以它们的最大公因数", f"{_a}:{_b} = {_c}:{_d}"],
                           "answer": f"{_a}:{_b} = {_c}:{_d}。",
                           "method": "化简比：前后项同除以最大公因数。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"化简比：{_a}:{_b}。", f"{_c}:{_d}"))
            continue

        # ── 单位换算：1km=1000m、1m=100cm ──
        _munit = re.search(r"(\d+)\s*(km|m|dm|cm|mm|t|kg|g|L|mL)\s*=\s*(\d+)\s*(km|m|dm|cm|mm|t|kg|g|L|mL)", raw)
        if _munit:
            _a, _u1, _b, _u2 = int(_munit.group(1)), _munit.group(2), int(_munit.group(3)), _munit.group(4)
            if _u1 != _u2:
                _ex = {"problem": f"{_a} {_u1} = （　）{_u2}？",
                       "steps": [f"记住相邻单位的进率", f"{_a} {_u1} = {_b} {_u2}"],
                       "answer": f"{_a} {_u1} = {_b} {_u2}。",
                       "method": f"单位换算：{_u1} 与 {_u2} 之间的进率。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"{_a} {_u1} = （　）{_u2}？", f"{_b} {_u2}"))
            continue

        # ── 经过时间：8:30→9:10 是40分 ──
        _mtime = re.search(r"(\d+):(\d+)\s*[→]\s*(\d+):(\d+).*?(\d+)\s*分", raw)
        if _mtime:
            _h1, _m1, _h2, _m2, _ans = (int(_mtime.group(i)) for i in range(1, 6))
            _expect = (_h2 * 60 + _m2) - (_h1 * 60 + _m1)
            if _expect == _ans:
                _ex = {"problem": f"从 {_h1}:{_m1:02d} 到 {_h2}:{_m2:02d}，经过了多少分钟？",
                       "steps": [f"{_h1} 时 {_m1} 分到 {_h2} 时 {_m2} 分", f"经过 {_expect} 分钟"],
                       "answer": f"经过了 {_ans} 分钟。",
                       "method": "经过时间 = 结束时刻 - 开始时刻。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"从 {_h1}:{_m1:02d} 到 {_h2}:{_m2:02d} 经过多少分钟？", f"{_ans} 分钟"))
            continue

        # ── 等值分数：1/2=2/4=3/6 ──
        if "/" in raw and "=" in raw and "÷" not in raw and "×" not in raw and "+" not in raw and "-" not in raw:
            _meq = re.search(r"(\d+)/(\d+)\s*=\s*(\d+)/(\d+)", raw)
            if _meq:
                _a, _b, _c, _d = (int(_meq.group(i)) for i in range(1, 5))
                if _a * _d == _c * _b and (_a != _c or _b != _d):
                    _ex = {"problem": f"{_a}/{_b} 还等于哪些分数？写出一个与它相等的分数。",
                           "steps": [f"分数的分子和分母同时乘同一个数，分数大小不变",
                                     f"{_a}/{_b} = {_c}/{_d}"],
                           "answer": f"{_a}/{_b} = {_c}/{_d}。",
                           "method": "分数的基本性质：分子分母同乘（除）一个不为 0 的数，分数大小不变。"}
                    if len(examples) < 3:
                        examples.append(_ex)
                    practice.append((f"写出一个与 {_a}/{_b} 相等的分数。", f"{_c}/{_d}"))
            continue

        # ── 集合（容斥）：会A的8人+会B的6人−都会的3人=11人 ──
        _mset = re.search(r"(\d+)\s*人.*?(\d+)\s*人.*?(\d+)\s*人.*?=\s*(\d+)\s*人", raw)
        if _mset:
            _a, _b, _c, _r = (int(_mset.group(i)) for i in range(1, 5))
            if _a + _b - _c == _r:
                _ex = {"problem": f"会 A 的有 {_a} 人，会 B 的有 {_b} 人，两种都会的有 {_c} 人。会 A 或 B 的一共有多少人？",
                       "steps": [f"两种都会的 {_c} 人被算了两次，要减去一次",
                                 f"{_a} + {_b} - {_c} = {_r}"],
                       "answer": f"一共有 {_r} 人。",
                       "method": "集合（容斥）：总数 = 各部分之和 - 重复部分。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"会 A 的 {_a} 人，会 B 的 {_b} 人，都会的 {_c} 人，一共多少人？", f"{_r} 人"))
            continue

        # ── 位置（数对）：第3列第2行记作(3,2) ──
        _mpos = re.search(r"第\s*(\d+)\s*列第\s*(\d+)\s*行记作\s*\((\d+)\s*,\s*(\d+)\)", raw)
        if _mpos:
            _c, _r, _c2, _r2 = (int(_mpos.group(i)) for i in range(1, 5))
            if _c == _c2 and _r == _r2:
                _ex = {"problem": f"第 {_c} 列第 {_r} 行，用数对怎么表示？",
                       "steps": [f"数对先写列、后写行", f"第 {_c} 列第 {_r} 行记作 ({_c},{_r})"],
                       "answer": f"记作 ({_c},{_r})。",
                       "method": "用数对表示位置：先列后行。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"第 {_c} 列第 {_r} 行记作？", f"({_c},{_r})"))
            continue

        # ── 解比例：x:2=3:4 → x=1.5 ──
        _mprop = re.search(r"x\s*:\s*(\d+)\s*=\s*(\d+)\s*:\s*(\d+).*?x\s*=\s*(\d+(?:\.\d+)?)", raw)
        if _mprop:
            _b, _c, _d, _ans = int(_mprop.group(1)), int(_mprop.group(2)), int(_mprop.group(3)), float(_mprop.group(4))
            _expect = _b * _c / _d if _d else None
            if _expect is not None and abs(_expect - _ans) < 1e-9:
                _ex = {"problem": f"解比例：x : {_b} = {_c} : {_d}。",
                       "steps": [f"内项积 = 外项积：{_d}x = {_b} × {_c} = {_b * _c}",
                                 f"x = {_b * _c} ÷ {_d} = {_ans:g}"],
                       "answer": f"x = {_ans:g}。",
                       "method": "解比例：内项积等于外项积。"}
                if len(examples) < 3:
                    examples.append(_ex)
                practice.append((f"解比例：x : {_b} = {_c} : {_d}。", f"x = {_ans:g}"))
            continue
        for m in _M_ARITH.finditer(raw):
            a, op, b, c = m.group(1), m.group(2), m.group(3), m.group(4)
            got = _m_fmt(_m_calc(a, op, b))
            if got != _m_fmt(float(c)):
                continue  # formula 本身算错/连加被截断，跳过
            if len(examples) < 2:
                ex = _m_arith_example(a, op, b)
                if ex:
                    examples.append(ex)
            practice.append(_m_arith_practice(a, op, b))
            inv = _m_inverse_practice(a, op, b, c)
            if inv:
                practice.append(inv)
            # 变式：换数字生成新题（用于 advanced 层，避免基础=提高=拓展同题复制）
            if "." not in a and "." not in b:
                _va, _vb = int(a), int(b)
                _vc = _m_calc(str(_va + 10), op, str(_vb + 5))
                if _vc is not None and _vc > 0 and _vc < 10000:
                    practice.append(_m_arith_practice(str(_va + 10), op, str(_vb + 5)))

    if not examples:
        return None

    topic = kb.get("topic", "")

    def _tier(lo, hi):
        return [{"q": q, "a": a} for q, a in practice[lo:hi]]

    basic = _tier(0, 3)
    standard = _tier(3, 6)
    advanced = _tier(6, 8)
    if not basic:
        basic = [{"q": "完成本课基础练习。", "a": "独立完成，注意书写工整。"}]
    # 兜底：三档绝不同题——standard/advanced 不足时给「说理/应用」题，不复用 basic
    # 答案拒绝空壳话术（"能结合实例说明即可"），改用本课已挖出的真实例题作具体示例（A3 修复）。
    if not standard:
        _s_ex = examples[0] if examples else None
        standard = [{"q": f"结合「{topic}」说一个生活中的例子，并写出算法。",
                     "a": (f"例如：{_s_ex['problem']} 算法：{_s_ex.get('method','')}"
                           f"结果 {_s_ex.get('answer','')}。") if _s_ex
                          else f"可从「{topic}」的实际问题出发，列出算式并分步计算。"}]
    if not advanced:
        _a_ex = examples[-1] if examples else None
        advanced = [{"q": f"和同桌互相出题考一考「{topic}」，并说出解题依据。",
                     "a": (f"可参考：{_a_ex['problem']} 依据是{_a_ex.get('method','')}。"
                           if _a_ex else f"围绕「{topic}」出题，说清所用方法与算理依据。")}]
    return {
        "worked_examples": examples[:3],
        "exercises": {
            "basic": basic or [{"q": "完成本课基础练习。", "a": "独立完成，注意书写工整。"}],
            "standard": standard,
            "advanced": advanced,
        },
    }


def _formula_example(kb):
    """薄 KB 无 worked_examples 时，用 formulas/key_points 构造真实、连贯的例题。

    护栏：problem 绝不内嵌答案（否则变成问=答的空壳）；答案须为可核对的结果或定义。
    无法从公式解析出具体算式的，退回"概念理解"题（问≠答），绝不复用"典型问题：<定义>"占位。
    """
    topic = kb.get("topic", "")
    for fm in (kb.get("formulas") or []):
        body = _strip_formula_label(fm)
        if not body:
            continue
        ex = _build_formula_example(body, topic)
        if ex:
            return ex
    # 所有公式都无法解析成具体例题 → 用课题+要点构造概念理解题（问≠答）
    kps = [_strip_dev_note(k) for k in (kb.get("key_points") or [])]
    if kps:
        lab = _kp_label(kps[0])[0] or _first_clause(_kp_body(kps[0]), 20)
        return {
            "problem": f"「{topic}」里，“{lab}”指的是什么？",
            "steps": ["回忆课本中的例子与定义。", "用自己的话说说它的含义与用法。"],
            "answer": _clip(_kp_body(kps[0]), 200),
            "method": "结合定义理解"
        }
    return {
        "problem": f"说一说：你对「{topic}」是怎么理解的？能举一个例子吗？",
        "steps": ["回顾课本中的内容。", "用自己的话总结并能举例说明。"],
        "answer": f"「{topic}」是本课要学习的内容，要理解它的含义，并能用它解决简单的实际问题。",
        "method": "概念理解"
    }


_OPMAP = {'+': ('加', '+'), '−': ('减', '−'), '-': ('减', '-'),
           '×': ('乘', '×'), 'x': ('乘', '×'), 'X': ('乘', '×'),
           '*': ('乘', '×'), '÷': ('除以', '÷')}


def _build_formula_example(body, topic):
    """从单条公式体构造一道例题（problem 不含答案）。返回 dict 或 None。"""
    # 取首个含运算语义的片段，避免把整串公式塞进一道题
    frag = ""
    for p in re.split(r'[；;，,]', body):
        p = p.strip()
        if re.search(r'[=＝><＞＜]|倍|折|%|共|增|减', p):
            frag = p
            break
    if not frag:
        frag = body.strip()

    # 1) 算术等式 a op b = c —— 注意：'/' 是分数线（分数 a/b），不是除号；
    # 除法只用 '÷'，否则「1/5+2/5=3/5」会被误解析成「2÷5=3」生成错误例题。
    m = re.search(r'(\d+)\s*([+\-−×xX*÷])\s*(\d+)\s*[=＝]\s*(\d+)', frag)
    if m:
        a, op, b, c = m.group(1), m.group(2), m.group(3), m.group(4)
        name, sym = _OPMAP.get(op, (op, op))
        return {
            "problem": f"算一算：{a} {sym} {b} = ？",
            "steps": [f"先看运算符号，这是 {a} 和 {b} 的{name}法。",
                      f"计算：{a} {sym} {b} = {c}。",
                      f"所以结果是 {c}。"],
            "answer": f"{a} {sym} {b} = {c}",
            "method": f"{name}法计算"
        }
    # 2) 比较大小 a ＞/＜ b
    if re.search(r'[＞<＞＜]', frag) or '比较' in body:
        m = re.search(r'(\d+)\s*[＞>＜<]\s*(\d+)', frag)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            rel = '＞' if a > b else '＜' if a < b else '＝'
            return {
                "problem": f"比较大小：{a} 和 {b}，哪个大？",
                "steps": [f"在数序中，{a} 在 {b} 的{'右边' if a > b else '左边'}（越往右越大）。",
                          f"所以 {a} {rel} {b}。"],
                "answer": f"{a} {rel} {b}",
                "method": "用数的顺序比较大小"
            }
    # 3) 倍
    if '倍' in frag:
        return {
            "problem": f"关于「{topic}」，请举例说说“谁是谁的几倍”是什么意思？",
            "steps": ["先确定“1份”是多少。", "再看另一个量里包含几个这样的“1份”。",
                      "包含几个 1 份，就是它的几倍。"],
            "answer": "倍表示两个数之间的倍数关系：一个数里包含几个另一个数，就是它的几倍。",
            "method": "用“1份”理解倍数"
        }
    # 4) 折
    if '折' in frag:
        z = re.sub(r'[^0-9]', '', frag.split('折')[0])
        if z:
            pct = int(z) * 10
            return {
                "problem": f"一件商品打{z}折，是原价的百分之几？",
                "steps": [f"几折表示十分之几。", f"{z}折 = {pct}%。"],
                "answer": f"{z}折表示按原价的{pct}%出售。",
                "method": "折扣 = 百分之几十"
            }
    # 5) 百分数互化
    if '%' in frag and ('=' in frag or '＝' in frag):
        return {
            "problem": f"把下面的数进行互化：{frag}。",
            "steps": ["看清要互化的两种形式。", "按互化规则换算并写出结果。"],
            "answer": frag,
            "method": "百分数与小数/分数互化"
        }
    # 6) 含“共/增/减”的应用
    if re.search(r'共|增|减', frag):
        m = re.search(r'(\d+)\s*[盒个台件条只本组]\s*[，,、]?\s*(\d+)', frag)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return {
                "problem": f"每{m.group(1)}个装一盒，{m.group(2)}盒一共多少个？",
                "steps": [f"求几个相同加数的和，用乘法更简便。", f"{a} × {b} = {a*b}。"],
                "answer": f"{a} × {b} = {a*b}（个）",
                "method": "乘法求总数"
            }
    return None


def _dedupe_concepts(segs):
    """删除 points 集合与前面某 concept 页完全相同的重复页（根治分数课概念页重复两遍）。"""
    seen = []
    out = []
    for s in segs:
        if s.get("kind") == "concept" and s.get("layout") == "concept":
            pts = frozenset(p for p in s.get("slots", {}).get("points", []) if p)
            if pts and pts in seen:
                continue
            seen.append(pts)
        out.append(s)
    return out


def _gen_math(kb):
    """数学概念：导入 → 概念(逐段详述) → 要点梳理 → 图示 → 例题步骤 → 易错对比 → 分层练习 → 小结 → 板书 → 作业。

    富化 KB（含 worked_examples/diagrams/exercises/compare）→ 详细内容 + 真实例题步骤 + 图示 + 真实练习答案。
    薄 KB（仅 original_text/key_points）→ 自动图示(_auto_diagrams) + 课题专属练习(_math_practice) + 要点梳理页，
    97 个数学 KB 不崩、且每课都有图、练习不套话。
    """
    topic = kb.get("topic", "")
    text = kb.get("original_text", "")
    kps = kb.get("key_points") or []
    formulas = kb.get("formulas") or []
    paras = _paragraphs(text)
    we = kb.get("worked_examples") or []
    ex = kb.get("exercises") or {}
    cautions = kb.get("cautions", "")
    cmp = kb.get("compare") or {}

    # 生成时确定性引擎：KB 无预置例题/练习时，从 formulas（原料）规则生成（零 LLM、答案程序算）。
    # 这是「生成式」路径——原料不变，例题/练习变式每次都能重新生成，而非读写死的成品。
    det = _deterministic_math(kb) if (not we or not ex) else None

    segs = [
        {"kind": "cover", "layout": "cover",
         "slots": {"title": topic, "subtitle": f"{kb.get('grade','')} · 数学", "meta": ""}},
        {"kind": "objectives", "layout": "objectives",
         "slots": {"items": _derive_objectives(kb, "math", kb.get("stage", "mid"), "concept")}},
        {"kind": "lead_in", "layout": "lead_in",
         "slots": {"scenario": _clip(paras[0] if paras else text, 160),
                   "question": _math_lead_question(kb)}},
    ]

    # 概念：把 original_text 逐段展开为知识点页（仅当原文确为多段，才是真·段落教学）
    # 单段"运行式"原文（多为要点罗列/范围说明）不再整段搬运，改由下方"要点梳理"页聚焦呈现，避免重复与空泛。
    concept_paras = [p for p in paras if "【本课范围】" not in p]
    if len(concept_paras) >= 2:
        for p in concept_paras:
            pg = _concept_page_from_para(p)
            if pg:
                segs.append(pg)

    # 要点梳理：把 key_points 变成"教什么"的页面——呈现真实可讲的知识点，而非元提示。
    # 多段原文（>=3 段）已由逐段概念页完整覆盖，此处跳过避免概念页重复两遍（根治分数课重复）。
    if len(concept_paras) < 3:
        for kp in kps[:4]:
            label, body = _split_label(kp)
            stmt = label if label else body
            pts = _math_kp_points(kp)
            pts = [p for p in pts if p != stmt]   # 去掉与标题重复的要点
            if pts:
                segs.append({"kind": "concept", "layout": "concept",
                             "slots": {"statement": _clip(stmt, 200), "points": pts}})

    # 图示：KB 自带 diagrams 优先；否则按内容类型自动生成（根治"完全没图示"）
    diags = kb.get("diagrams") or _auto_diagrams(kb)
    for d in diags:
        segs.append({"kind": "concept", "layout": "diagram",
                     "slots": {"figure": [d], "caption": d.get("note", ""), "side_text": ""}})

    # 例题步骤：KB 预置 worked_examples 优先 → 生成时确定性引擎 → 公式构造/概念题兜底
    _we_src = we or (det.get("worked_examples") if det else [])
    if _we_src:
        for e in _we_src:
            steps = [_clip(s, 60) for s in (e.get("steps") or [])][:8]
            segs.append({"kind": "example", "layout": "steps",
                         "slots": {
                             "problem": _clip(e.get("problem", ""), 160),
                             "steps": steps,
                             "answer": _clip(e.get("answer", ""), 120),
                             "method": _clip(e.get("method", ""), 120),
                         }})
    elif formulas:
        # 薄 KB 无 worked_examples：优先用一条"应用/示例"类公式构造真实、连贯的例题；
        # 否则用课题要点/公式构造（已剥标签，避免"典型问题：意义：…"泄漏）。
        fe = _formula_example(kb)
        if fe:
            segs.append({"kind": "example", "layout": "steps", "slots": fe})
        else:
            kp0 = _kp_body(kps[0]) if kps else f"「{topic}」"
            fm = formulas[0] if formulas else ""
            fmbody = _strip_formula_label(fm) if fm else ""
            segs.append({"kind": "example", "layout": "steps",
                         "slots": {"problem": _clip(f"典型问题：{kp0}", 160),
                                   "steps": ([f"算法：{_clip(fmbody, 80)}"] if fmbody else [f"要点：{_clip(kp0, 80)}"]),
                                   "answer": _clip(fmbody or kp0, 160),
                                   "method": _clip(fmbody or kp0, 160)}})
    elif kps:
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "典型例题", "points": [_clip(k, 60) for k in kps[:5]]}})

    # 易错对比：仅当 KB 自带 compare 时（接地，不臆造其它课题的误区）
    if cmp:
        segs.append({"kind": "concept", "layout": "compare",
                     "slots": {
                         "right": _clip(cmp.get("right", ""), 120),
                         "wrong": _clip(cmp.get("wrong", ""), 120),
                         "why": _clip(cmp.get("why", cautions), 120),
                     }})

    # 分层练习：KB 预置 exercises 优先 → 生成时确定性引擎 → 课题专属 _math_practice 兜底
    _ex_src = ex or (det.get("exercises") if det else None)
    if _ex_src:
        segs.append({"kind": "practice", "layout": "tiers", "slots": _tiers_from_ex(_ex_src)})
    else:
        segs.append({"kind": "practice", "layout": "tiers", "slots": _math_practice(kb, "分层练习")})

    # 小结
    sum_points = [_first_clause(_kp_body(k), 60) for k in kps[:5]] or \
                 [_first_clause(p, 60) for p in concept_paras[:3]]
    segs.append({"kind": "summary", "layout": "summary",
                 "slots": {"points": sum_points, "formula": _clip(formulas[0], 80) if formulas else ""}})

    # 板书
    branches = []
    if kps:
        for i, kp in enumerate(kps[:3]):
            label, items = _board_branch(kp, i)
            branches.append({"label": label, "items": items})
    if not branches:
        branches = [{"label": "概念", "items": [topic]},
                    {"label": "方法", "items": ["读题分析"]},
                    {"label": "应用", "items": ["解决实际问题"]}]
    segs.append({"kind": "board", "layout": "board",
                 "slots": {"center": topic, "branches": branches}})

    # 作业：富化 KB 用真实 exercises；薄 KB 用课题专属 _math_practice
    if ex:
        hw = {"title": "分层作业", "basic": [], "standard": [], "advanced": []}
        for qa in (ex.get("standard") or [])[:2]:
            hw["basic"].append({"q": _clip("复习巩固：" + qa.get("q", ""), 120),
                                "a": _clip(qa.get("a", ""), 400)})
        for qa in (ex.get("advanced") or [])[:2]:
            hw["standard"].append({"q": _clip("拓展提升：" + qa.get("q", ""), 120),
                                   "a": _clip(qa.get("a", ""), 400)})
        hw["advanced"].append({"q": f"在生活中找一找「{topic}」的例子，说给家人听。",
                               "a": (f"例如用到本课知识：{_clip(formulas[0], 60)}，"
                                     f"试着用它解释一个生活现象。" if formulas
                                    else f"用「{topic}」的知识解释生活中的相关现象，说清道理。")})
        if not hw["basic"]:
            hw["basic"] = [{"q": f"完成「{topic}」基础练习若干道。", "a": "独立完成，注意书写工整与单位。"}]
        segs.append({"kind": "homework", "layout": "tiers", "slots": hw})
    else:
        segs.append({"kind": "homework", "layout": "tiers", "slots": _math_homework(kb, "分层作业")})
    segs = _dedupe_concepts(segs)
    return segs


def _split_sections(text):
    """按【标题】切分 original_text 成 {标题: 正文}。英语 KB 常含
    【核心词汇】【重点句型】【A Let's talk】【Read and write】等章节。"""
    chunks = re.split(r'【([^】]{1,30})】', text or "")
    secs = {}
    for i in range(1, len(chunks) - 1, 2):
        h, b = chunks[i].strip(), chunks[i + 1].strip()
        if h and b:
            secs[h] = b
    return secs


# eng_to_ipa 的系统性错误修正表（schwa 把 /ʌ/、长元音 /ɔː/ /ɑː/ 生成成 /ə/ 或短音）。
# 覆盖教材高频词的已知错误；查表命中则用教材英式音标，否则回退 eng_to_ipa。
_IPA_FIX = {
    "under": "ˈʌndə(r)", "ball": "bɔːl", "young": "jʌŋ", "funny": "ˈfʌni",
    "bus": "bʌs", "cup": "kʌp", "sun": "sʌn", "but": "bʌt", "up": "ʌp",
    "run": "rʌn", "much": "mʌtʃ", "just": "dʒʌst", "must": "mʌst",
    "tall": "tɔːl", "small": "smɔːl", "call": "kɔːl", "wall": "wɔːl",
    "fall": "fɔːl", "all": "ɔːl", "talk": "tɔːk", "walk": "wɔːk",
    "car": "kɑː(r)", "far": "fɑː(r)", "arm": "ɑːm", "card": "kɑːd",
    "park": "pɑːk", "dark": "dɑːk",
    "polite": "pəˈlaɪt", "shy": "ʃaɪ", "clever": "ˈklevə(r)", "strict": "strɪkt",
    "helpful": "ˈhelpfl", "hard-working": "ˌhɑːdˈwɜːkɪŋ", "quiet": "ˈkwaɪət",
    "where": "weə(r)", "there": "ðeə(r)", "here": "hɪə(r)", "near": "nɪə(r)",
}


def _english_ipa(word):
    """英文单词 → IPA 音标。优先查修正表（教材英式音标），否则用 eng_to_ipa。"""
    w = (word or "").strip().rstrip("/")
    if not w or " " in w or not re.match(r"^[A-Za-z'\-]+$", w):
        return ""
    lw = w.lower()
    if lw in _IPA_FIX:
        return _IPA_FIX[lw]
    try:
        from eng_to_ipa import convert
        return convert(w)
    except Exception:
        return ""


def _extract_english_vocab(body):
    """从【核心词汇】正文抽词卡：'father 父亲; mother 母亲; ...' → 词+义+IPA音标。"""
    words, seen = [], set()
    for entry in re.split(r'[;\n；]', body or ""):
        entry = entry.strip(" ·\t")
        if not entry:
            continue
        m = re.search(r'([A-Za-z][A-Za-z /,\.\'\-]*?)\s*([\u4e00-\u9fff].*)', entry)
        wd = m.group(1).strip() if m else entry.strip()
        mg = m.group(2).strip() if m else ""
        if not wd or wd in seen:
            continue
        seen.add(wd)
        words.append({"word": wd, "phonetic": _english_ipa(wd), "pos": "", "meaning": _clip(mg, 30), "example": ""})
    return words[:10]


def _example_for(word, corpus, limit=40):
    """在对话/短文中找含该词的例句：优先取最短句（词卡例句要短，避免整段对话挤进卡片）。"""
    if not word:
        return ""
    lw = word.lower().rstrip("/")
    best = ""
    for sent in re.split(r'(?<=[.?!])\s+', corpus or ""):
        if lw in sent.lower():
            s = sent.strip()
            if not best or len(s) < len(best):
                best = s
            if len(best) <= limit:
                break
    return _clip(best, limit)


def _english_lead_question(kb):
    topic = kb.get("topic", "")
    kps = kb.get("key_points") or []
    blob = (topic + " " + " ".join(kps)).lower()
    if "family" in blob or "家庭" in blob:
        return "Can you introduce your family in English?"
    if "shop" in blob or "购物" in blob or "买" in blob:
        return "Can you ask and answer about shopping in English?"
    if "past" in blob or "过去" in blob or "时态" in blob:
        return "Can you talk about what you did in English?"
    return f"Can you talk about {topic} in English?"


def _english_practice(kb, title, words, patterns, corpus):
    """英语课堂分层练习：以听说/同伴互动为主（听读、看图说、结对对话、填空、小调查），
    与课后作业（抄写/写作/项目）明确分源，避免「课堂练习写成作业」（A8 修复）。"""
    topic = kb.get("topic", "")
    p1 = patterns[0] if patterns else ""
    # 词汇到位时优先用真实词汇；无词汇卡（语法/综合话题）时回退到核心句型，避免编造占位词。
    w1 = words[0]["word"] if words else (p1.split("?")[0].split(".")[0].strip() if p1 else "本课词汇")
    w_example = _example_for(w1, corpus) if words else ""
    p_example = (_example_for(p1.split("?")[0].split(".")[0].strip(), corpus) if p1 else "")
    return {
        "title": title,
        "basic": [
            {"q": (f"Listen and repeat: 听录音，跟读词汇“{w1}”与核心句型，注意语音语调。"
                   if words else f"Listen and repeat: 听录音跟读「{topic}」的核心句型。"),
             "a": "模仿录音的语音、语调、连读与重音，跟读三遍。"},
            {"q": (f"Look and say: 看图片，用“{w1}”说一个完整句子。"
                   if words else f"Say a sentence with the key pattern of “{topic}”."),
             "a": (w_example or f"用“{w1}”造一个「{topic}」相关句子，注意语序。") if words
                   else f"用「{topic}」核心句型说一个句子，注意结构正确。"},
        ],
        "standard": [
            {"q": (f"Pair work: 和同桌用“{w1}”及核心句型，围绕「{topic}」编一段 2-3 轮对话。"
                   if words else f"Pair work: 和同桌用「{topic}」核心句型编一段对话。"),
             "a": "对话含提问与回答，用上本课词汇与句型，注意礼貌用语。"},
            {"q": (f"Fill in the blanks: 用本课词汇完成句子，巩固“{w1}”。"
                   if words else f"Fill in the blanks with the key pattern of “{topic}”."),
             "a": p_example or "根据句意选择正确词汇/句型，注意单复数与时态。"},
        ],
        "advanced": [
            {"q": (f"Make a survey: 用“{w1}”采访 2-3 位同学并汇报结果。"
                   if words else f"Make a survey with the key pattern of “{topic}”."),
             "a": "记录同学回答，用本课句型汇总汇报（如 I can… / He can…）。"},
        ],
    }


def _english_homework(kb, title, words, patterns, corpus):
    """英语课后作业：与课堂练习差异化——以独立书写/巩固/项目为主（抄写、写话、给家人介绍、自制词卡），
    不含课堂的听说/结对互动任务（A8 修复）。"""
    topic = kb.get("topic", "")
    p1 = patterns[0] if patterns else ""
    w1 = words[0]["word"] if words else (p1.split("?")[0].split(".")[0].strip() if p1 else "本课词汇")
    return {
        "title": title,
        "basic": [
            {"q": (f"Copy the new words and key sentences (each twice), pay attention to handwriting."
                   if words else f"Copy the key words and sentences of “{topic}” (each twice)."),
             "a": "注意书写工整与占格；单词抄写两遍并默写一遍。"},
            {"q": "Listen and read aloud at home (在家听录音朗读两遍).",
             "a": "模仿语音语调，注意连读与重音，读给家长听。"},
        ],
        "standard": [
            {"q": (f"Write 2-3 sentences about “{topic}” using “{w1}” and the key pattern."
                   if words else f"Write 2-3 sentences about “{topic}” using the key pattern."),
             "a": "用本课词汇、句型写一段小短文，注意时态与语序。"},
            {"q": f"向家人用英语介绍「{topic}」（今天学的词句或对话）。",
             "a": "大方表达，用上本课核心词汇与句型，不怕犯错。"},
        ],
        "advanced": [
            {"q": (f"Make a word/pattern card for “{topic}”, or read an extra story and share it tomorrow."
                   if words else f"Make a pattern card for “{topic}”, or read an extra story."),
             "a": "卡片列出重点词与句型；或读一则小故事，明天和同学分享。"},
        ],
    }

def _split_en_lines(text):
    """英语对话/短文按句末标点(.?!)与换行切成短行，避免单行长对话被版式裁成残句。"""
    out = []
    for ln in (text or "").split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        for part in re.split(r'(?<=[.?!])\s+', ln):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _gen_english(kb):
    """英语：导入 → 词卡 → 核心句型 → 对话/短文 → 分层练习 → 小结 → 板书 → 作业。
    解析 original_text 的【核心词汇/重点句型/Let's talk/Read and write】等章节，
    把词汇、句型、对话、短文分别成页（根治"漏掉 KB 里的对话与短文"）。"""
    topic = kb.get("topic", "")
    text = kb.get("original_text", "")
    kps = kb.get("key_points") or []
    formulas = kb.get("formulas") or []
    secs = _split_sections(text)

    # 词汇：优先【核心词汇】章节，退化取 key_points 英文头
    vocab_body = secs.get("核心词汇") or secs.get("词汇") or ""
    words = _extract_english_vocab(vocab_body)
    if not words:
        for kp in (kps or [])[:6]:
            head = kp.split("：")[0].split(":")[0].strip()
            # 仅当头部是纯英文词（含空格/连字符，不含汉字）才当作词汇卡，
            # 避免把"be过去""规则动词"等语法点误渲染成单词卡（出现"Make a sentence with be过去"）。
            if re.match(r'^[A-Za-z][A-Za-z\'\-]*$', head):
                meaning = kp.split("：", 1)[1].strip() if "：" in kp else \
                          (kp.split(":", 1)[1].strip() if ":" in kp else "")
                words.append({"word": head, "phonetic": _english_ipa(head), "pos": "", "meaning": _clip(meaning, 30), "example": ""})
    # 句型：优先【重点句型】章节（含单元标题句，如 What's he like?），退化用 key_points。
    # 之前直接用 key_points，会漏掉单元标题句（核心句型抽取不全）。
    pattern_body = secs.get("重点句型") or secs.get("句型") or ""
    if pattern_body:
        patterns = _split_en_lines(pattern_body)[:6]
    else:
        patterns = (kps or [])[:6]
    # 对话 + 短文语料（用于例句 + 成页）
    dialogue = secs.get("A Let's talk") or secs.get("Let's talk") or secs.get("对话") or ""
    short_text = secs.get("Read and write") or secs.get("短文") or secs.get("Story time") or ""
    corpus = (dialogue + " " + short_text)
    for w in words:
        if not w.get("example"):
            ex = _example_for(w["word"], corpus)
            if ex:
                w["example"] = ex

    segs = [
        {"kind": "cover", "layout": "cover",
         "slots": {"title": topic, "subtitle": f"{kb.get('grade','')} · 英语", "meta": ""}},
        {"kind": "objectives", "layout": "objectives",
         "slots": {"items": _derive_objectives(kb, "english", kb.get("stage", "mid"), "standard")}},
        {"kind": "lead_in", "layout": "lead_in",
         "slots": {"scenario": _clip((dialogue.split("\n")[0] if dialogue
                                     else (words[0]["meaning"] if words else topic)), 160),
                   "question": _english_lead_question(kb)}},
    ]

    if words:
        segs.append({"kind": "concept", "layout": "word_grid",
                     "slots": {"words": words}})
    if patterns:
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "核心句型 · Key patterns",
                               "points": [_clip(p, 60) for p in patterns[:5]]}})
    # 语法/功能课题（无核心词汇→无词卡）时，用 formulas 的"示例"句补一个例句页，避免内容过薄
    if not words:
        ex_sents = []
        for fm in formulas:
            body = _strip_formula_label(fm)
            if not body:
                continue
            for part in re.split(r'[/／]|(?<=[.?!])\s+', body):
                part = part.strip().strip('.,/')
                if part and re.search(r'[A-Za-z]', part):
                    ex_sents.append(part)
        ex_sents = ex_sents[:5]
        if ex_sents:
            segs.append({"kind": "concept", "layout": "concept",
                         "slots": {"statement": "例句 · Examples", "points": ex_sents}})
    if dialogue:
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "对话 · Let's talk",
                               "points": _split_en_lines(dialogue)[:6]}})
    if short_text:
        segs.append({"kind": "concept", "layout": "concept",
                     "slots": {"statement": "短文 · Read and write",
                               "points": _split_en_lines(short_text)[:6]}})

    segs.append({"kind": "practice", "layout": "tiers",
                 "slots": _english_practice(kb, "分层练习", words, patterns, corpus)})

    segs.append({"kind": "summary", "layout": "summary",
                 "slots": {"points": ([_first_clause(_kp_body(k), 50) for k in kps[:5] if _kp_body(k)]
                                      or ["掌握本课核心词汇与句型", "能在情境中运用句型交流",
                                          "朗读对话与短文，培养语感"])}})

    branches = []
    if words:
        branches.append({"label": "Words", "items": [w["word"] for w in words[:4]]})
    if patterns:
        branches.append({"label": "Patterns", "items": [_clip(p, 24) for p in patterns[:3]]})
    if not branches:
        branches = [{"label": "Words", "items": [topic]},
                    {"label": "Sentences", "items": ["Use the words"]},
                    {"label": "Talk", "items": ["Talk with partners"]}]
    segs.append({"kind": "board", "layout": "board",
                 "slots": {"center": topic, "branches": branches}})

    segs.append({"kind": "homework", "layout": "tiers",
                 "slots": _english_homework(kb, "Homework", words, patterns, corpus)})
    return segs


# ---------------------------------------------------------------------------
# 顶层：auto_kb(kb) -> kb'
# ---------------------------------------------------------------------------
def auto_kb(kb):
    """对简单 KB（无 segments）自动派生完整结构化 KB。

    已是结构化 KB（含 segments）时，原样返回（避免破坏手写成果）。
    """
    if kb.get("segments"):
        return kb

    # 工作副本：剔除开发者范围备注（【本课题范围】…），避免其泄漏到学生页。
    wkb = dict(kb)
    wkb["original_text"] = _strip_dev_note(wkb.get("original_text", ""))
    wkb["key_points"] = [_strip_dev_note(k) for k in (wkb.get("key_points") or [])]

    cat = _derive_subject_cat(wkb.get("subject", ""))
    stage = _derive_stage(wkb.get("grade", ""))
    lesson_type = _derive_lesson_type(wkb, cat)

    if cat == "chinese":
        if lesson_type in ("poem", "recognition"):
            segments = _gen_chinese_poem_or_recog(wkb, lesson_type)
        else:
            segments = _gen_chinese_prose(wkb)
    elif cat == "math":
        segments = _gen_math(wkb)
    elif cat == "english":
        segments = _gen_english(wkb)
    else:
        segments = _gen_chinese_prose(wkb)

    out = dict(wkb)
    out["subject_cat"] = cat
    out["stage"] = stage
    out["lesson_type"] = lesson_type
    out["duration"] = wkb.get("duration", 40)
    out["objectives"] = _derive_objectives(wkb, cat, stage, lesson_type)
    out["segments"] = segments
    return out