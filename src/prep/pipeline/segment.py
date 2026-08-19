# -*- coding: utf-8 -*-
"""pipeline/segment.py —— 切页层：把纯文本切成结构化 slides。

核心约束（v3 计划 v2 重做）：只做语义分段，**不改写**用户原话。
  - 有免费 API：让弱模型按原文逻辑切分为 [{title, bullets[]}]，prompt 强制「保留原词、不新增、不润色」；
  - 无 API / 调用失败：规则降级（按标题行 / 空行 / 序号分段）。

slide 结构：
  {"title": str, "bullets": [str, ...]}
也兼容 "body"（整段文本）字段用于降级长文。
"""
import os
import re
import json
from .llm import make_client


def _extract_json_array(text: str):
    """从模型输出里稳健抽取 JSON 数组（兼容 ```json 围栏 / 前后多余文本）。"""
    if text is None:
        return None
    s = text.strip()
    # 去掉 ```json ... ``` 围栏
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s)
    # 截取第一个 [ 到最后一个 ]
    a, b = s.find("["), s.rfind("]")
    if a != -1 and b != -1 and b > a:
        s = s[a:b + 1]
    try:
        data = json.loads(s)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return None


def _norm_slide(obj) -> dict:
    """把模型给的任意 dict 规整为 {title, bullets}。
    关键：每个 bullet 必须 1 行(不可含 \\n),且行首 markdown 标记必须被剥光。
    多行块会被按行拆成多条 bullets,残留的 ###/-/> 等会被 _clean_line 清洗。
    """
    if not isinstance(obj, dict):
        s = str(obj)
        # 单元素也是块:按行拆并清
        lines = []
        for ln in s.split("\n"):
            ln = _clean_line(ln)
            if ln:
                lines.append(ln)
        return {"title": "", "bullets": lines}
    title = str(obj.get("title") or obj.get("heading") or "").strip()
    title = _clean_line(title)
    raw = obj.get("bullets") or obj.get("points") or obj.get("items") or []
    if isinstance(raw, str):
        raw = [raw]
    flat = []
    for b in raw:
        if b is None:
            continue
        s = str(b)
        for ln in s.split("\n"):
            ln = _clean_line(ln)
            if ln:
                flat.append(ln)
    body = str(obj.get("body") or "").strip()
    if not flat and body:
        for ln in body.split("\n"):
            ln = _clean_line(ln)
            if ln:
                flat.append(ln)
    return {"title": title, "bullets": flat}


def segment_by_llm(text: str, client, max_slides: int = 24) -> list:
    prompt = (
        "你是一个「内容分段器」。下面是一段用户上传的课程内容纯文本。"
        "请把它拆成若干张幻灯片（slides），用于制作课件。\n"
        "严格要求：\n"
        "1. 只做分段，不要改写、不要润色、不要新增原文没有的知识点或例子；\n"
        "2. 尽量保留用户原文的词句，标题可用原文小标题或一句话概括本页主题；\n"
        f"3. 最多 {max_slides} 张；每张含 title（字符串）与 bullets（字符串数组，每点一句原文要点）；\n"
        "4. **每个 bullet 必须是 1 行字符串**，禁止包含 \\n 换行符；"
        "如果一段文本里有多个并列要点，必须把它们拆成多条 bullets（一条一行）；\n"
        "5. bullets 里直接放原文要点，不要保留 markdown 标记符号（###、##、-、*、>、•、：开头的序号等都剥掉）；\n"
        "6. 只输出 JSON 数组，不要任何解释。格式：\n"
        '[{"title":"...","bullets":["...","..."]}, ...]'
    )
    try:
        out = client.complete(
            [{"role": "system", "content": prompt},
             {"role": "user", "content": text[:12000]}],
            temperature=0.2, max_tokens=2000, retries=2)
        arr = _extract_json_array(out)
        if arr:
            slides = [_norm_slide(x) for x in arr]
            slides = [s for s in slides if s["title"] or s["bullets"]]
            if slides:
                return slides
    except Exception:
        pass
    return []


# 标题识别：显式标记（# / 第X讲 / 数字. / 模块 / Unit / Lesson / Part / 章 / 节 …）
_HEAD_RE = re.compile(
    r"^(#{1,6}\s*|第[一二三四五六七八九十百\d]+[\.、讲课章节]|[\d]+[\.、]|"
    r"[一二三四五六七八九十]+[、.、]|模块|单元|专题|讲\s*$|"
    r"Unit\s*\d|Lesson\s*\d|Part\s*\d|Chapter\s*\d)",
    re.I)
# 行首 markdown 残标记（解析层/LLM 可能带出 + 重复/混合出现）：
#   #  -  *  +  •  ·  >  （含顺序连写，如 "- ### foo" / "### > foo"）
# 用 (?:…)+ 实现"从行首连续剥",处理 LLM 偶尔吐出的多符号串
_MARK_STRIP = re.compile(
    r"^(?:[-*+•·]\s+|>\s*|#{1,6}\s+|：\s*|\.\s+)+"
)


def _clean_line(l: str) -> str:
    """从行首连续剥除 markdown 标记符号（#/--*/.../>/：/. 等任意顺序）。
    增强：处理括号/中文标点 + 反复 sub 直到稳定。"""
    s = (l or "").rstrip()
    # 反复 sub 直到稳定(罕见的多层嵌套)
    for _ in range(4):
        n = _MARK_STRIP.sub("", s).strip()
        if n == s.strip():
            break
        s = n
    return s.strip()


def _looks_heading(l: str) -> bool:
    return bool(_HEAD_RE.match(l.strip()))


def _markdown_level(line: str) -> int:
    """返回行首 # 的数量（无则为 0）。"""
    m = re.match(r"^(#{1,6})\s+", line or "")
    return len(m.group(1)) if m else 0


def _regex_segment(text: str) -> list:
    """标题正则模式（无显式 # 标记时）：命中标题标记的行开新页。"""
    slides, cur = [], None
    for raw in text.split("\n"):
        line = _clean_line(raw)
        if not line:
            continue
        if _looks_heading(line):
            if cur is not None:
                slides.append(cur)
            cur = {"title": line, "bullets": []}
        else:
            if cur is None:
                cur = {"title": "", "bullets": []}
            cur["bullets"].append(line)
    if cur is not None:
        slides.append(cur)
    return slides


def _marker_segment(text: str) -> list:
    """Markdown 模式：按文档“章节层级”切页。
      - 文档含显式 # 标题时启用；
      - 切页层级 = 出现次数>1 的最小两个 # 层级（区分“文档总标题/章节/子节”）；
        例：# 章节 + ## 子节 + ### 步骤 → 在 # 与 ## 处开新页，### 作要点；
      - 更浅的总标题跳过；首个顶层标题作封面（不成页）；
      - 代码围栏（```）内容并入要点（保留话术/提示词等核心内容）；
      - 表格行去 | 后并入要点；跳过分隔行。
    """
    lines = text.split("\n")
    levels = [_markdown_level(l) for l in lines if _markdown_level(l) >= 1]
    if not levels:
        return _regex_segment(text)
    distinct = sorted(set(levels))
    # 切页层级 = 第二浅的不同层级（至少取最浅）；即“章节 + 子节”两级都开新页
    split_max = distinct[1] if len(distinct) > 1 else distinct[0]
    min_lvl = distinct[0]
    skip_first = (min_lvl <= split_max)  # 顶层标题在切页层级内 → 首个作封面

    slides, cur = [], None
    in_fence = False
    for raw in lines:
        s = (raw or "").strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        lvl = _markdown_level(raw)
        line = _clean_line(raw)
        if not line:
            continue
        if lvl >= 1:
            if lvl <= split_max:
                if skip_first:
                    skip_first = False
                    continue  # 文档顶层标题作封面
                if cur is not None:
                    slides.append(cur)
                cur = {"title": line, "bullets": []}
            else:  # 更深的标题 → 要点
                if cur is None:
                    cur = {"title": "", "bullets": []}
                if "|" in line:
                    line = line.strip("|").replace("|", " · ").strip()
                if line and not set(line) <= set("|-· "):
                    cur["bullets"].append(line)
        else:
            if cur is None:
                cur = {"title": "", "bullets": []}
            if "|" in line:
                line = line.strip("|").replace("|", " · ").strip()
            if line and not set(line) <= set("|-· "):
                cur["bullets"].append(line)
    if cur is not None:
        slides.append(cur)
    # 清理：无标题但有要点的，用首条要点作标题；丢弃无要点的空页
    out = []
    for s in slides:
        if not s["title"] and s["bullets"]:
            s["title"] = s["bullets"].pop(0)
        if s["bullets"]:
            out.append(s)
    return out


def _para_segment(text: str) -> list:
    """段落模式（无显式标记时）：按空行分段，首行短则作标题。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    slides = []
    for p in paras:
        lines = [_clean_line(l) for l in p.split("\n") if _clean_line(l)]
        if not lines:
            continue
        first, title, bullets = lines[0], "", lines
        if len(first) <= 24 and first[-1] not in "。，；．.、":
            title, bullets = first, lines[1:]
        if not bullets:
            bullets = [title] if title else []
        slides.append({"title": title, "bullets": bullets})
    return slides


def _rule_segment(text: str) -> list:
    """规则降级主入口：
      文本含显式 markdown # 标题 → markdown 层级切页；
      否则含标题正则标记（第X讲 / 数字. 等）→ 正则模式；
      否则段落模式。
    """
    if any(_markdown_level(l) >= 1 for l in text.split("\n")):
        return _marker_segment(text)
    has_marker = any(_looks_heading(l) for l in text.split("\n"))
    slides = _regex_segment(text) if has_marker else _para_segment(text)
    out = []
    for s in slides:
        if not s["title"] and not s["bullets"]:
            continue
        if not s["title"] and s["bullets"]:
            s["title"] = s["bullets"].pop(0)
        out.append(s)
    return out


def segment(text: str, env: dict = None, max_slides: int = 24,
            allow_llm: bool = True) -> list:
    """入口：解析文本 → slides。优先 LLM，失败回退规则。"""
    text = (text or "").strip()
    if not text:
        return []
    # 无 API key 时直接走规则，避免无谓网络请求/401 噪声
    has_key = bool((env or {}).get("AI_API_KEY") or os.environ.get("AI_API_KEY"))
    if allow_llm and has_key:
        try:
            client = make_client(env)
            slides = segment_by_llm(text, client, max_slides)
            if slides:
                return slides
        except Exception:
            pass
    return _rule_segment(text)
