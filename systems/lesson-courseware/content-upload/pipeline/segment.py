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


# ---- 代码块预处理（v3 修复：保留 Python/代码类教学内容） ----
_CODE_MARKER = re.compile(r"^§§CODE_BLOCK_(\d+)§§$")

# 常见无围栏代码块语言标记（教育/教培场景常见）
_UNFENCED_LANGS = {
    "python", "py",
    "plaintext", "text",
    "scratch",
    "javascript", "js",
    "html", "css",
    "java", "c", "cpp", "c++",
    "bash", "shell", "sh",
    "sql",
    "json", "yaml", "yml",
}


class CodeBlockExtractor:
    """把代码块从正文抽出，替换成占位符，切页后再回填到 slide['code']。

    识别两种写法：
      1. 标准 markdown 围栏：```python ... ```
      2. 无围栏但带语言标记：python / plaintext / python + 运行 ...
    占位符格式：§§CODE_BLOCK_N§§（几乎不可能与用户正文冲突）
    """

    def __init__(self, text: str):
        self.blocks: list[dict] = []
        self.text = self._extract(text)

    # 用于终止无围栏代码块的"子标题"：方式、写法、参考答案、解析等
    _BLOCK_END_HEAD_RE = re.compile(
        r"^(?:方式|写法|步骤|方法|参考答案|答案|解析|说明|注意|小结|总结)"
        r"[\d一二三四五六七八九十]*[、.:：\s]",
        re.I)

    # C++ 代码特征行（启发式识别无围栏代码块）
    _CPP_CODE_RE = re.compile(
        r"^(?:#include|#define|using namespace|int main|void main|"
        r"cout\s*<<|cin\s*>>|return\s+\d|"
        r"[\w\s\*\&<>:]+\([^)]*\)\s*\{?|"   # 函数声明/定义（含 int main() { ）
        r"^\s*\{|\}|\s*//|\s*printf|\s*scanf|"
        r"\s*if\s*\(|\s*for\s*\(|\s*while\s*\(|\s*else\b)",
        re.I)

    def _looks_like_code(self, line: str) -> bool:
        """判断一行是否像代码（启发式，用于无围栏无语言标记的代码块识别）。"""
        s = (line or "").strip()
        if not s:
            return False
        # C++ 预处理指令（#include/#define/#pragma 等）——必须优先于 markdown 标题判断
        if re.match(r"^#(?:include|define|pragma|ifdef|ifndef|endif|import)\b", s, re.I):
            return True
        # 含分号/花括号/流操作符，大概率是代码
        if self._CPP_CODE_RE.match(s):
            return True
        # 单行花括号（代码块边界）
        if s in ("{", "}", "};", "{;"):
            return True
        # 以分号结尾且含英文/符号（排除中文句子）
        if s.endswith(";") and re.search(r"[a-zA-Z_#<>&|]", s) and not re.search(r"[。，；！？]", s):
            return True
        # 赋值/比较/算术运算符在行首或紧跟空格（排除「C++程序」这种文本里的 ++）
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_\s]*[=+\-*/%<>!&|]", s) and not re.search(r"[。，；！？]", s):
            return True
        return False

    def _is_heading(self, line: str) -> bool:
        """判断行是否为章节标题（用于终止无围栏代码块）。

        注意：Python 代码里 # 开头的注释非常常见，不能把 # 当 markdown 标题，
        否则无围栏代码块会被注释行强行截断。
        """
        s = (line or "").strip()
        if s.startswith("#"):
            return False
        if self._BLOCK_END_HEAD_RE.match(s):
            return True
        return bool(_HEAD_RE.match(s))

    def _looks_like_prose(self, line: str) -> bool:
        """中文字句且以中文标点结尾，视为正文说明，应终止无围栏代码块。

        排除 # 开头的 Python 注释，避免误伤代码注释。
        """
        s = (line or "").strip()
        if not s or s.startswith("#"):
            return False
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", s))
        if cn_chars / max(len(s), 1) >= 0.5 and s[-1] in "。，；！？":
            return True
        return False

    def _add_block(self, code_lines: list, lang: str = "") -> str | None:
        code = "\n".join(code_lines)
        if not code.strip():
            return None
        idx = len(self.blocks)
        self.blocks.append({"lang": lang, "code": code})
        return f"§§CODE_BLOCK_{idx}§§"

    def _extract(self, text: str) -> str:
        lines = text.split("\n")
        out: list[str] = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            s = line.strip()

            # 1) 标准 markdown 围栏
            if s.startswith("```"):
                lang = s[3:].strip()
                i += 1
                code_lines: list[str] = []
                while i < n:
                    if lines[i].strip().startswith("```"):
                        i += 1
                        break
                    code_lines.append(lines[i])
                    i += 1
                marker = self._add_block(code_lines, lang)
                if marker:
                    out.append(marker)
                continue

            # 2) 无围栏语言标记（支持 "python\n运行\n代码" 或 "plaintext\n代码" 或 "scratch\n代码"）
            if s in _UNFENCED_LANGS:
                lang = s
                i += 1
                if i < n and lines[i].strip() == "运行":
                    i += 1
                code_lines = []
                while i < n:
                    cur = lines[i]
                    cs = cur.strip()
                    # 终止条件：新的代码块、新围栏、或新标题
                    if cs.startswith("```") or cs in _UNFENCED_LANGS:
                        break
                    if self._is_heading(cur):
                        break
                    if self._looks_like_prose(cur):
                        break
                    # 单个空行保留；连续空行且后续是 heading/结尾则终止
                    if not cs:
                        # 往后看，跳过空行
                        j = i + 1
                        while j < n and not lines[j].strip():
                            j += 1
                        if j >= n:
                            break
                        if self._is_heading(lines[j]) or lines[j].strip().startswith("```") or lines[j].strip() in _UNFENCED_LANGS:
                            break
                        code_lines.append(cur)
                        i += 1
                        continue
                    code_lines.append(cur)
                    i += 1
                # 去掉末尾积累的纯空行
                while code_lines and not code_lines[-1].strip():
                    code_lines.pop()
                marker = self._add_block(code_lines, lang)
                if marker:
                    out.append(marker)
                continue

            # 3) 启发式无围栏代码块：连续多行代码特征行（无语言标记，如教案里标题后直接跟代码）
            # 向前看：如果当前行不像代码但下一行像代码，且当前行是短标题行，则当前行留给标题
            if not self._looks_like_code(line) and i + 1 < n and self._looks_like_code(lines[i + 1]):
                # 当前行可能是标题，检查是否够短（≤30字）且无代码特征
                if len(s) <= 30 and not self._looks_like_code(line):
                    out.append(line)
                    i += 1
                    continue
            if self._looks_like_code(line):
                code_lines = [line]
                i += 1
                while i < n:
                    cur = lines[i]
                    cs = cur.strip()
                    if not cs:
                        # 代码块内允许单个空行，连续空行或后续是标题则终止
                        j = i + 1
                        while j < n and not lines[j].strip():
                            j += 1
                        if j >= n or self._is_heading(lines[j]) or self._looks_like_prose(lines[j]):
                            break
                        code_lines.append(cur)
                        i += 1
                        continue
                    if cs.startswith("```") or cs in _UNFENCED_LANGS or self._is_heading(cur) or self._looks_like_prose(cur):
                        break
                    if not self._looks_like_code(cur):
                        # 遇到不像代码的行，终止（可能是代码块后的正文说明）
                        break
                    code_lines.append(cur)
                    i += 1
                while code_lines and not code_lines[-1].strip():
                    code_lines.pop()
                if len(code_lines) >= 2:  # 至少2行才算代码块（防单行误判）
                    marker = self._add_block(code_lines, "cpp")
                    if marker:
                        out.append(marker)
                    continue
                else:
                    # 单行不够成块，回退当普通行
                    out.append(line)
                    continue

            # 4) 普通行
            out.append(line)
            i += 1
        return "\n".join(out)

    def _replace_code_markers(self, text: str) -> str:
        """把文本中的代码占位符替换回真实代码块。"""
        def repl(m):
            idx = int(m.group(1))
            if 0 <= idx < len(self.blocks):
                return self.blocks[idx]["code"]
            return m.group(0)
        return _CODE_MARKER.sub(repl, text)

    def restore_slide(self, slide: dict) -> dict:
        bullets: list[str] = []
        codes: list[str] = []
        for b in slide.get("bullets", []):
            s = str(b).strip()
            if _CODE_MARKER.match(s):
                codes.append(self._replace_code_markers(s))
            else:
                bullets.append(b)
        # code 字段里也可能被 LLM 放了占位符
        raw_code = slide.get("code")
        if raw_code:
            codes.append(self._replace_code_markers(str(raw_code)))
        if codes:
            slide["code"] = "\n\n".join(c for c in codes if c.strip())
        else:
            slide.pop("code", None)
        slide["bullets"] = bullets
        # 防御：切页后处理可能把占位符 pop 成 title
        if _CODE_MARKER.match(str(slide.get("title") or "").strip()):
            slide["title"] = ""
        return slide


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
        return {"title": "", "bullets": lines, "code": ""}
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
    # code 字段保留多行代码原文，不拆行、不清洗缩进
    code = str(obj.get("code") or "").rstrip()
    return {"title": title, "bullets": flat, "code": code}


def segment_by_llm(text: str, client, max_slides: int = 24) -> list:
    prompt = (
        "你是一个「内容分段器」。下面是一段用户上传的课程内容纯文本。"
        "请把它拆成若干张幻灯片（slides），用于制作课件。\n"
        "严格要求：\n"
        "1. 只做分段，不要改写、不要润色、不要新增原文没有的知识点或例子；\n"
        "2. 尽量保留用户原文的词句，标题可用原文小标题或一句话概括本页主题；\n"
        f"3. 最多 {max_slides} 张；每张含 title（字符串）、bullets（字符串数组，每点一句原文要点），以及可选的 code（字符串，完整保留多行代码块，不要拆行、不要清洗缩进）；\n"
        "4. **每个 bullet 必须是 1 行字符串**，禁止包含 \\n 换行符；"
        "如果一段文本里有多个并列要点，必须把它们拆成多条 bullets（一条一行）；\n"
        "5. bullets 里直接放原文要点，不要保留 markdown 标记符号（###、##、-、*、>、•、：开头的序号等都剥掉）；\n"
        "6. 如果原文有代码块（如 ```python ... ``` 或 python/运行 ... 开头的代码），必须整段保留在 code 字段中，不要把代码拆进 bullets；\n"
        "7. 只输出 JSON 数组，不要任何解释。格式：\n"
        '[{"title":"...","bullets":["..."],"code":"..."}, ...]\n'
        "8. 特别注意：为了保留多行代码，原文中的代码块已被替换为形如 §§CODE_BLOCK_0§§、§§CODE_BLOCK_1§§ 的占位符。"
        "你必须把这些占位符原样放进对应 slide 的 bullets 中，不要展开、不要删除、不要放到 title 里；"
        "系统会自动把它们还原成完整代码。示例：\n"
        '[{"title":"一、什么是二维数组","bullets":["一维数组是一行数据","二维数组是列表嵌套列表","§§CODE_BLOCK_0§§"]}]'
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
# 注意：#include/#define 等 C++ 预处理指令不匹配（# 后必须跟空格才是 markdown 标题）
_HEAD_RE = re.compile(
    r"^(#{1,6}\s+|第[一二三四五六七八九十百\d]+[\.、讲课章节]|[\d]+[\.、]|"
    r"[一二三四五六七八九十]+[、.、]|模块|单元|专题|讲\s*$|"
    r"Unit\s*\d|Lesson\s*\d|Part\s*\d|Chapter\s*\d)",
    re.I)
# 行首 markdown 残标记（解析层/LLM 可能带出 + 重复/混合出现）：
#   #  -  *  +  •  ·  >  （含顺序连写，如 "- ### foo" / "### > foo"）
# 用 (?:…)+ 实现"从行首连续剥",处理 LLM 偶尔吐出的多符号串
_MARK_STRIP = re.compile(
    r"^(?:[-*+•·]\s+|>\s*|#{1,6}\s+|：\s*|\.\s+)+"
)


# 行内 markdown 格式标记：不删除，保留语法供 render 层转 HTML。
# 这里只负责占位符保护（含 §§ 的行不做行内处理，防 _ 误伤）。
def _clean_inline(s: str) -> str:
    """保留行内 markdown 格式语法（**加粗**、*斜体*、`代码`、[文字](链接)），
    供 render 层转换为 HTML 标签渲染。只处理 strip，不删符号。

    特例：代码块占位符 §§CODE_BLOCK_N§§ 内含下划线，必须原样跳过。
    """
    return (s or "").strip()


def _clean_line(l: str) -> str:
    """从行首连续剥除 markdown 标记符号（#/--*/.../>/：/. 等任意顺序）。
    增强：处理括号/中文标点 + 反复 sub 直到稳定 + 行内格式清理。"""
    s = (l or "").rstrip()
    # 反复 sub 直到稳定(罕见的多层嵌套)
    for _ in range(4):
        n = _MARK_STRIP.sub("", s).strip()
        if n == s.strip():
            break
        s = n
    return _clean_inline(s)


def _looks_heading(l: str) -> bool:
    return bool(_HEAD_RE.match(l.strip()))


def _markdown_level(line: str) -> int:
    """返回行首 # 的数量（无则为 0）。"""
    m = re.match(r"^(#{1,6})\s+", line or "")
    return len(m.group(1)) if m else 0


def _regex_segment(text: str) -> list:
    """标题正则模式（无显式 # 标记时）：命中标题标记的行开新页。

    层级识别（修复混乱编号）：
      - 主章节标记：`一、` `二、` `五、`（汉字数字+顿号） 或 严格递增的 `1.` `2.` `3.` `4.`；
      - 列表项标记：数字重置/跳号（如 `1.` 后紧跟 `8.`）→ 不当标题，作为上一页的要点；
      - 空标题合并：标题下无任何要点时，不开新页，把该"标题"降格为上一页 bullet。
    """
    lines = []
    for raw in text.split("\n"):
        line = _clean_line(raw)
        if line:
            lines.append(line)

    # 第一遍：决定每行是否为"真标题"
    is_head = [False] * len(lines)
    last_arabic = 0  # 最近见到的阿拉伯数字章节号（用于判断递增）
    for idx, line in enumerate(lines):
        s = line.strip()
        # 汉字数字章节：一、二、三、…（永远算标题，是中文文档的主章节标记）
        if re.match(r"^[一二三四五六七八九十]+、", s):
            is_head[idx] = True
            continue
        # 阿拉伯数字章节：1. 2. 3.（必须严格递增才算；1. 8. 这种跳号/重置 → 列表项）
        m = re.match(r"^(\d+)[\.、]\s*(.+)$", s)
        if m:
            num = int(m.group(1))
            rest = m.group(2).strip()
            # 空标题（如单独的 "1."）不算
            if not rest:
                continue
            # 严格递增（允许 +1 或 +2 容错跳号，如原文 1→2→4 跳过 3）
            if num > last_arabic and num <= last_arabic + 3:
                is_head[idx] = True
                last_arabic = num
            else:
                # 数字重置或跳太远 → 是列表项，不是标题
                pass
            continue
        # 其他标题标记（第X讲 / Unit / Lesson / 模块 / 单元 等）保持原逻辑
        if _looks_heading(s):
            is_head[idx] = True

    # 第二遍：按 is_head 切页 + 空标题合并
    slides, cur = [], None
    for idx, line in enumerate(lines):
        if is_head[idx]:
            # 空标题合并：上一个 slide 是空壳（只有标题无要点）→ 把这个标题降为上一页的要点
            if cur is not None and not cur["bullets"] and cur["title"]:
                # 把当前标题作为上一页的第一个要点（保留语义）
                cur["bullets"].append(line)
                continue
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
    """入口：解析文本 → slides。优先 LLM，失败回退规则。

    v3 修复：先用 CodeBlockExtractor 把代码块抽出为占位符，切页后再回填到
    slide['code']，避免 Python 等多行代码被拆碎/丢弃/污染 bullets。
    """
    text = (text or "").strip()
    if not text:
        return []

    extractor = CodeBlockExtractor(text)
    working_text = extractor.text

    # 策略：只要内容含代码块，就直接走规则切页（弱模型对占位符/多行代码不可靠）；
    # 纯文本才尝试 LLM，且 LLM 若丢失占位符也回退规则。
    has_code_blocks = bool(re.search(r"§§CODE_BLOCK_\d+§§", working_text))
    has_key = bool((env or {}).get("AI_API_KEY") or os.environ.get("AI_API_KEY"))
    if allow_llm and has_key and not has_code_blocks:
        try:
            client = make_client(env)
            slides = segment_by_llm(working_text, client, max_slides)
            # 校验 LLM 是否把代码占位符弄丢；若丢失则回退规则切页
            if slides:
                original_markers = set(re.findall(r"§§CODE_BLOCK_(\d+)§§", working_text))
                found_markers = set()
                for s in slides:
                    for b in s.get("bullets", []):
                        found_markers.update(re.findall(r"§§CODE_BLOCK_(\d+)§§", str(b)))
                    found_markers.update(re.findall(r"§§CODE_BLOCK_(\d+)§§", str(s.get("title", ""))))
                if original_markers and not original_markers.issubset(found_markers):
                    slides = None
            if slides:
                for s in slides:
                    extractor.restore_slide(s)
                return slides
        except Exception:
            pass

    slides = _rule_segment(working_text)
    for s in slides:
        extractor.restore_slide(s)
    return slides
