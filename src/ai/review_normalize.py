"""课评输出结构兜底（确定性，不依赖模型依从度）。

对应 review-generator SKILL v2 的 P2/P4 与第 7 节：
- P2/P4：课评必须只切 2 段（段1 = 课堂内容总结，段2 = 课后评价），两段之间恰好 1 个空行；
  弱模型对软指令依从度低，必须在后端用确定性规则强制归一，不能把分段完全交给模型或前端。
- 第 7 节：弱模型常突破字数上限，必要时后端做硬截断（优先从段2尾部删，保留段1内容）。

设计原则：能确定性修的（段落结构、超长截断）直接修；绝不编造内容、绝不改动姓名与事实。
"""
import re

# 编号项：1. / 1、 / 1) 开头的行（段1 课堂内容总结的标志）
_NUMBERED_RE = re.compile(r"^\s*\d+[\.\、\)]")

# 评价起点标记：出现这些词的段落，视为第 2 段（课后评价）的开始
_EVAL_MARK_RE = re.compile(
    r"^(?:亮点|可提升|不过|然而|但是|但|建议|表现方面|在后续|另外|同时|此外|"
    r"接下来|总体|小结|评价|结语|家庭建议|巩固)"
)

# 句子边界（用于字数截断时尽量切在完整句子后）
_SENT_END_RE = re.compile(r"[。！？；\n]")

# 残留占位符剥离：弱模型偶尔会把 prompt 中的方括号占位符（如
# [从本节课课件/教案中抽取的具体项目/动作名称]）当字面文本抄入输出。
# 课评正文中正常不会使用英文方括号，故直接删除形如 [...] 的整块。
_PLACEHOLDER_RE = re.compile(r"\[[^\]]{0,40}\]")
# 括号里最常见的占位引导词（命中即视为占位符泄漏，即使超长也删）
_PLACEHOLDER_HINT_RE = re.compile(
    r"\[[^\[\]]{0,60}?(?:课件|教案|具体|抽取|完成|项目|动作|任务|作品|主题|名称|练习|题目|笔画|字帖|组合|单词|句型|对话)[^\[\]]{0,40}?\]"
)


def strip_placeholder_leak(text: str) -> str:
    """剥离弱模型误抄入的方括号占位符（含提示词版，长度放宽）。"""
    if not text:
        return text
    out = _PLACEHOLDER_HINT_RE.sub("", text)
    out = _PLACEHOLDER_RE.sub("", out)
    # 清理删除后产生的多余标点/空格
    out = re.sub(r"[，,]\s*[，,]", "，", out)
    out = re.sub(r"[。．.]\s*[。．.]", "。", out)
    # ⚠ 关键修复：只折叠多余「空格」，绝不能折叠换行/空行。
    # 原写法 re.sub(r"\s{2,}"," ",out) 会把段间分隔符 \n\n（空行）也压成单空格，
    # 导致 normalize 好不容易切出的「课程内容 / 课后评价」两段被重新糊成一坨字，
    # 直接破坏「课程内容是单独一个段落」的要求。
    out = re.sub(r" {2,}", " ", out)
    # 占位符若跨行被删，可能留下 >1 个连续空行，统一收敛为恰好 1 个空行
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"^\s*[,，。、]\s*", "", out)
    return out.strip()


def _split_paragraphs(text: str):
    """按空行拆成非空段落列表。"""
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def _join_single(paras):
    """用单个换行把若干段落拼成一段（消除段内多余空行）。"""
    return "\n".join(paras)


def _eval_cut(paras):
    """找不到编号块时，用评价起点标记找切分点；返回段1 取头的个数。"""
    for i, p in enumerate(paras):
        if _EVAL_MARK_RE.search(p):
            return i
    return len(paras)  # 没找到评价起点：整段都算段1（极端兜底）


# 「以下是本节课的具体内容总结：」这类引导语。
# 新结构下段1 直接以「1.」开头，这类引导语一律删除（用户明确不要）。
_LEADIN_RE = re.compile(
    r"[^。！？\n]{0,40}(?:总结|内容|要点|知识点|如下)[^。！？\n]{0,10}[：:]\s*$"
)


def _strip_leadin(lead: str) -> str:
    """剥掉结尾的「……内容总结：」式引导语，保留真正的叙事句。"""
    out = (lead or "").strip()
    prev = None
    while out and out != prev:
        prev = out
        out = _LEADIN_RE.sub("", out).strip()
    return out


def _extract_lead_narrative(para: str, min_items: int = 1):
    """把「段1」里编号列表之前的铺垫叙事剥出来。

    新结构要求段1 只有知识点编号列表；任何出现在第一个「1.」之前的
    称呼/叙事都属于课后评价，应移到段2 开头（2026-08-04）。
    返回 (lead, list_part)；无可剥离内容时 lead 为 ""。
    """
    if not para:
        return "", para
    m = _NUM_LINE_RE.search(para)
    if not m or m.start() == 0:
        return "", para
    lead = para[: m.start()].strip()
    rest = para[m.start():].strip()
    if not lead or not rest:
        return "", para
    if len(_NUM_LINE_RE.findall(rest)) < min_items:
        return "", para
    return lead, rest


def normalize_paragraphs(text: str, force_two: bool = True) -> str:
    """归一课评段落结构。

    force_two=True（默认）：强制「2 段 + 恰好 1 空行」——段1=课堂内容总结，
        段2=课后评价。用于「无优秀课评模板」时统一系统本身模板的 2 段格式。
    force_two=False：不强制 2 段，仅做最小清理（段间恰好 1 空行、段内多余空行折叠），
        保留模型按【班级级优秀历史课评】写出的多段维度化结构。
    """
    if not text or not text.strip():
        return text or ""

    paras = _split_paragraphs(text)

    # 不强制 2 段：保留模型输出的段落层次（用于对齐优秀课评模板）
    if not force_two:
        return "\n\n".join(paras)

    # 单段：模型把「编号列表 + 评价叙述」全挤在一段里（没有空行），
    # 按空行根本切不到 → 先在最后一个编号项结束处强制切一刀
    if len(paras) == 1:
        split_txt = _split_single_para_into_two(paras[0])
        if split_txt:
            paras = _split_paragraphs(split_txt)

    # 定位「编号列表」所在的连续段落区间（段落内**含**编号行即可，
    # 因为模型常写成「一句铺垫\n1. …\n2. …」这种同段形态）
    num_idx = [i for i, p in enumerate(paras) if _NUM_LINE_RE.search(p)]

    if num_idx:
        first_num = num_idx[0]
        last_num = first_num
        for i in num_idx[1:]:
            if i == last_num + 1:      # 只吃「紧邻连续」的编号段，
                last_num = i           # 避免把段2 里偶然出现的编号行也算进段1
            else:
                break

        lead_paras = paras[:first_num]                    # 列表之前的叙事 → 归段2
        seg1 = _join_single(paras[first_num:last_num + 1])
        tail_paras = paras[last_num + 1:]                 # 列表之后的评价 → 段2

        # 列表段尾部可能直接粘着评价叙述（中间没空行）→ 再切一刀
        glued_tail = ""
        glued = _split_single_para_into_two(seg1)
        if glued:
            seg1, glued_tail = glued.split("\n\n", 1)

        # 段1 内第一个「1.」之前若还有铺垫叙事，剥出来送去段2
        inner_lead, seg1 = _extract_lead_narrative(seg1)

        # 「以下是本节课的内容总结：」这类引导语直接丢弃，真正的叙事句保留
        lead_text = _strip_leadin(
            "\n".join([p for p in (lead_paras + [inner_lead]) if p and p.strip()])
        )

        # 段2 = 列表前叙事 + 粘连尾巴 + 列表后各段（顺序即原文顺序）
        seg2 = _join_single(
            [x.strip() for x in ([lead_text, glued_tail] + tail_paras) if x and x.strip()]
        )

        if not seg1.strip():
            return seg2.strip()
        if not seg2.strip():
            return seg1.strip()
        return seg1.strip() + "\n\n" + seg2.strip()

    # 无编号列表：退回「评价起点标记」切分
    if len(paras) <= 2:
        return "\n\n".join(paras)

    cut = _eval_cut(paras)
    seg1, seg2 = paras[:cut], paras[cut:]
    if not seg2:
        return "\n\n".join(paras)
    if not seg1:
        seg1, seg2 = seg2[:1], seg2[1:]
    return _join_single(seg1) + "\n\n" + _join_single(seg2)


# 段 1 编号项：1./1、/1) 开头的行（多行模式，用于在单段内按行扫描）
_NUM_LINE_RE = re.compile(r"^\s*\d+[\.\、\)]\s*", re.MULTILINE)


def _split_single_para_into_two(text: str) -> str:
    """单段（无空行）兜底：在文本内找「段1 编号列表 → 段2 评价叙述」的边界，强制插入 \\n\\n。

    触发条件：文本里出现 ≥2 个编号项（如 1. 2. 3.），且最后一个编号项结束（句末标点）后
    紧跟叙述性内容（称呼/评价词）且没有空行。常见于弱模型把"段1 列表+段2 评价"
    全挤在一段里 —— 此时按空行根本切不到，必须主动在**最后一个编号项**结束位置切一刀。
    """
    if not text:
        return ""
    # 找所有"行首 数字编号"项的位置
    matches = list(_NUM_LINE_RE.finditer(text))
    if len(matches) < 2:
        return ""  # 没有编号列表（单段是别的内容），不强行切

    # 段 1 末尾 = 最后一个编号项所在行内的第一个句末标点位置
    # （最后一个编号项可能跨行到段 2 评价没换行；要按"行"切，再在该行内找第一个句末）
    seg1_start = matches[-1].start()
    # 找"最后一个编号项所在行"的结束位置（下一个换行 或 文本末尾）
    nl_idx = text.find("\n", seg1_start)
    seg1_end_limit = nl_idx if nl_idx != -1 else len(text)
    seg1_region = text[seg1_start:seg1_end_limit]
    end_match = re.search(r"[。！？；]", seg1_region)
    if end_match:
        # 最后一个编号项以句末标点收尾 → 在标点后切
        seg1_end = seg1_start + end_match.end()
    else:
        # 最后一个编号项没有句末标点（如 "3. 理解事件积木：当绿旗被点击"）：
        # ① 若课后评价另起一行紧跟 → 在该行末尾（下一个换行前）切一刀；
        # ② 若连换行都没有（叙述与编号项粘在同一行）→ 按"课后评价起点标记"切。
        # 这两种兜底都修掉"编号列表与课后评价被一个换行/无标点粘成单段"的融合问题。
        if nl_idx != -1:
            seg1_end = seg1_end_limit
        else:
            narr = re.search(
                r"(?:你|同学|本次|这节|今天|整体|不过|但是|但|同时|此外|另外|"
                r"接下来|总体|小结|建议|在后续|回家|在家)",
                text[seg1_start:],
            )
            if narr and narr.start() > 0:
                seg1_end = seg1_start + narr.start()
            else:
                return ""  # 最后一个编号项后既无标点也无叙述起点，结构异常，不强行切

    # 段 2 起点：seg1_end 之后，第一个非空白字符位置
    rest = text[seg1_end:]
    m = re.match(r"\s*", rest)
    seg2_start = seg1_end + (m.end() if m else 0)
    if seg2_start >= len(text):
        return ""  # 段 1 后面没有叙述内容，只有尾随空白

    seg1 = text[:seg1_end].rstrip()
    seg2 = text[seg2_start:].lstrip()
    if not seg2.strip():
        return ""
    return seg1 + "\n\n" + seg2


def _trim_to_boundary(s: str, n: int) -> str:
    """在不超过 n 字的前提下，尽量切在句子边界后；找不到则硬切到 n。"""
    if len(s) <= n:
        return s
    cut = -1
    for m in _SENT_END_RE.finditer(s):
        if m.end() <= n:
            cut = m.end()
        else:
            break
    if cut <= 0:
        cut = n
    return s[:cut].rstrip()


def _split_sentences_keep(s: str):
    """按句末标点切句并保留标点。"""
    parts = re.findall(r"[^。！？；\n]*[。！？；\n]|[^。！？；\n]+$", s or "")
    return [p for p in parts if p.strip()]


def _trim_middle_keep_tail(s: str, n: int) -> str:
    """在 n 字内保留「开头 + 结尾」，不够时从**中间**删整句。

    段2 的结尾是「可提升点 + 家庭巩固建议 + emoji」，是家长最需要看的部分。
    旧写法从尾部硬切，会让课评停在半句话上、建议整段消失
    （2026-08-04：段1 改为纯知识点列表后变长，段2 预算被压缩，此问题必现）。
    """
    if len(s) <= n:
        return s
    sents = _split_sentences_keep(s)
    if len(sents) <= 2:
        return _trim_to_boundary(s, n)

    head = sents[0]
    if len(head) >= n:
        return _trim_to_boundary(s, n)
    budget = n - len(head)

    # 从结尾往前尽量保留（最多 3 句：可提升点 + 建议 + 收尾）
    tail = []
    for x in reversed(sents[1:]):
        if len(tail) >= 3 or len(x) > budget:
            break
        tail.insert(0, x)
        budget -= len(x)

    # 预算有剩余时，按原顺序补回中间句
    middle = []
    for x in sents[1: len(sents) - len(tail)]:
        if len(x) > budget:
            break
        middle.append(x)
        budget -= len(x)

    out = (head + "".join(middle) + "".join(tail)).strip()
    return out if out else _trim_to_boundary(s, n)


def cap_length(text: str, max_len: int) -> str:
    """字数硬截断兜底：优先压缩段2（课后评价），保住段1（课堂内容总结）。

    段2 采用「保头保尾、中间删句」策略，确保结尾的家庭建议不被切掉。
    """
    if not max_len or len(text) <= max_len:
        return text

    if "\n\n" in text:
        p1, p2 = text.split("\n\n", 1)
        if len(p1) < max_len:
            allow = max_len - len(p1) - 2
            if allow > 0:
                p2 = _trim_middle_keep_tail(p2, allow)
                return p1 + "\n\n" + p2
        # 段1 本身就超长：截断段1
        return _trim_to_boundary(p1, max_len)
    return _trim_middle_keep_tail(text, max_len)


def finalize_review(text: str, max_len: int = None, force_two: bool = True) -> str:
    """生成后统一兜底。

    force_two=True：归一 2 段结构 + 剥离占位符 + 字数截断（系统本身模板场景）。
    force_two=False：保留模型多段结构（对齐优秀课评模板），仅剥离占位符、不做硬截断。
    """
    out = normalize_paragraphs(text, force_two=force_two)
    out = strip_placeholder_leak(out)
    if max_len:
        out = cap_length(out, max_len)
    return out
