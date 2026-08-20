# -*- coding: utf-8 -*-
"""courseware_engine/schemas.py —— 数据契约（Agent 间接口）。

按方案 §3 定义：
  TeachingEvent / DesignDNA / TeachingScript / StyleRecipe / PageSpec
外加 coerce/validate，保证「弱模型输出 → 合法数据」的宽松解析与白名单清洗。

所有契约是纯数据（dataclass），不依赖 llm/kb/layouts，可被 agents/layouts/pipeline 自由引用。
"""
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# 白名单 / 正则（validate 与 coerce 共用）
# ---------------------------------------------------------------------------
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# DesignDNA 枚举（方案 §3）
MOODS = ["沉静典雅", "活泼童趣", "理性严谨", "温润质朴",
         "明快清朗", "古雅厚重", "清新自然", "端庄大气"]
CONTENT_FORMS = ["text_heavy", "proof_heavy", "dialogue", "verse", "mixed"]
DENSITIES = ["sparse", "balanced", "dense"]
STAGES = ["low", "mid", "high", "junior"]
PALETTE_HINTS = ["warm_ink", "bamboo_green", "cinnabar", "indigo", "paper",
                "ink_black", "sky_blue", "amber", "plum", "mint", "rose", "slate"]
EVENT_KINDS = ["lead_in", "concept", "example", "activity", "practice",
               "homework", "summary", "board", "objectives", "cover"]

# StyleRecipe 白名单
DECORATIONS = ["seal", "branch", "dot_grid", "wave", "none"]
ILLUSTRATION_STYLES = ["line_art", "flat", "none"]
FONT_WHITELIST = {
    "serif": '"Noto Serif SC","Songti SC","SimSun",serif',
    "sans": '"PingFang SC","Microsoft YaHei","Heiti SC",sans-serif',
    "kaiti": '"Kaiti SC","KaiTi","STKaiti",serif',
    "rounded": '"Yuanti SC","Hiragino Sans GB","PingFang SC",sans-serif',
}
PALETTE_KEYS = ["primary", "primary700", "accent", "bg", "surface",
                "ink", "muted", "line", "cover1", "cover2"]
# 种子化兜底 palette（非法 hex 单值替换为这组硬编码合法 hex）
SAFE_PALETTE = {
    "primary": "#9a3412", "primary700": "#7c2d12", "accent": "#0f766e",
    "bg": "#f7f3ec", "surface": "#fffdf8", "ink": "#292524",
    "muted": "#78716c", "line": "#e7ddcb", "cover1": "#44403c", "cover2": "#1c1917",
}


# ---------------------------------------------------------------------------
# 1) TeachingEvent（解析Agent 输出的最小单元）
# ---------------------------------------------------------------------------
@dataclass
class TeachingEvent:
    event_id: str                       # "e1".."eN"
    kind: str                           # EVENT_KINDS 之一
    title: str
    minutes: Optional[int] = None
    intent: str = ""                    # 教学意图（1-2 句）
    content_brief: str = ""             # 环节内容要点（≤200字）
    page_hint: list = field(default_factory=list)   # [{"focus":..., "layout_candidates":[...]}]
    kb_refs: list = field(default_factory=list)     # 引用 KB 原文片段

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            event_id=str(d.get("event_id", "")),
            kind=str(d.get("kind", "concept")),
            title=str(d.get("title", "")),
            minutes=(int(d["minutes"]) if isinstance(d.get("minutes"), (int, float)) else None),
            intent=str(d.get("intent", "")),
            content_brief=str(d.get("content_brief", "")),
            page_hint=list(d.get("page_hint", []) or []),
            kb_refs=list(d.get("kb_refs", []) or []),
        )

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# 2) DesignDNA（整课设计基因，驱动风格与版式偏好）
# ---------------------------------------------------------------------------
@dataclass
class DesignDNA:
    subject_cat: str = "general"        # math|chinese|english|science|...|general
    stage: str = "mid"                  # low|mid|high|junior
    lesson_type: str = "standard"       # 古诗/文言文/现代文/识字/grammar/reading/standard
    mood: str = "温润质朴"              # 枚举 MOODS
    content_form: str = "mixed"         # CONTENT_FORMS
    density: str = "balanced"           # DENSITIES
    palette_hint: str = "warm_ink"      # PALETTE_HINTS

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            subject_cat=str(d.get("subject_cat", "general")),
            stage=str(d.get("stage", "mid")),
            lesson_type=str(d.get("lesson_type", "standard")),
            mood=str(d.get("mood", "温润质朴")),
            content_form=str(d.get("content_form", "mixed")),
            density=str(d.get("density", "balanced")),
            palette_hint=str(d.get("palette_hint", "warm_ink")),
        )

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# 3) TeachingScript（解析Agent 完整输出）
# ---------------------------------------------------------------------------
@dataclass
class TeachingScript:
    version: int = 1
    identity: dict = field(default_factory=dict)   # {subject,grade,topic,duration,standard_code,standard_text}
    events: list = field(default_factory=list)     # list[TeachingEvent]
    dna: DesignDNA = field(default_factory=DesignDNA)

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            version=int(d.get("version", 1)),
            identity=dict(d.get("identity", {}) or {}),
            events=[TeachingEvent.from_dict(e) for e in (d.get("events", []) or [])],
            dna=DesignDNA.from_dict(d.get("dna", {})),
        )

    def to_dict(self):
        return {
            "version": self.version,
            "identity": self.identity,
            "events": [e.to_dict() for e in self.events],
            "dna": self.dna.to_dict(),
        }


# ---------------------------------------------------------------------------
# 4) StyleRecipe（风格Agent 输出 + validate 白名单清洗）
# ---------------------------------------------------------------------------
@dataclass
class StyleRecipe:
    palette: dict = field(default_factory=dict)
    fonts: dict = field(default_factory=dict)
    layout_prefs: dict = field(default_factory=dict)
    illustration: dict = field(default_factory=dict)
    decorations: list = field(default_factory=list)

    def validate(self) -> "StyleRecipe":
        """逐项过白名单/正则，非法单项替换为种子化默认（不整体丢弃）。"""
        # palette：10 色全过 hex 正则
        p = dict(self.palette or {})
        for k in PALETTE_KEYS:
            v = p.get(k)
            if not (isinstance(v, str) and HEX_RE.match(v)):
                p[k] = SAFE_PALETTE[k]
        self.palette = p
        # fonts：head/body 必须在白名单
        f = dict(self.fonts or {})
        f["head"] = f.get("head") if f.get("head") in FONT_WHITELIST.values() else FONT_WHITELIST["serif"]
        f["body"] = f.get("body") if f.get("body") in FONT_WHITELIST.values() else FONT_WHITELIST["sans"]
        self.fonts = f
        # illustration
        ill = dict(self.illustration or {})
        ill["style"] = ill.get("style") if ill.get("style") in ILLUSTRATION_STYLES else "line_art"
        ill["diagram_kinds"] = [str(x) for x in (ill.get("diagram_kinds") or []) if isinstance(x, str)]
        self.illustration = ill
        # decorations：过滤到白名单、去重、'none' 仅在没有其它装饰时保留、最多 2 个
        decos = [str(x) for x in (self.decorations or []) if str(x) in DECORATIONS]
        decos = list(dict.fromkeys(decos))  # 保序去重
        if "none" in decos and len(decos) > 1:
            decos = [d for d in decos if d != "none"]
        self.decorations = decos[:2] or ["none"]
        # layout_prefs：确保结构合法
        lp = dict(self.layout_prefs or {})
        lp["preferred"] = [str(x) for x in (lp.get("preferred") or []) if isinstance(x, str)]
        lp["avoid"] = [str(x) for x in (lp.get("avoid") or []) if isinstance(x, str)]
        pk = lp.get("per_kind")
        lp["per_kind"] = {str(k): [str(x) for x in v if isinstance(x, str)]
                          for k, v in (pk or {}).items()} if isinstance(pk, dict) else {}
        self.layout_prefs = lp
        return self

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(
            palette=dict(d.get("palette") or {}),
            fonts=dict(d.get("fonts") or {}),
            layout_prefs=dict(d.get("layout_prefs") or {}),
            illustration=dict(d.get("illustration") or {}),
            decorations=list(d.get("decorations") or []),
        )


# ---------------------------------------------------------------------------
# 6) LessonContent（分科教师 AGENT 输出的「教学语义」契约）
# ---------------------------------------------------------------------------
# 强模型路径的核心契约：教师 AGENT 只产出「这节课教什么」，完全不碰「页面长什么样」。
# 这份语义 schema 由程序确定性映射成 segments（layout/slots 技术结构），
# 视觉由 style.py 按学科/学段皮肤套用。键名固定，禁止模型漂移。
@dataclass
class LessonContent:
    title: str = ""                                     # 课题
    objectives: list = field(default_factory=list)      # ["目标1",...]
    lead_in: dict = field(default_factory=dict)         # {scenario, question}
    concepts: list = field(default_factory=list)        # [{statement, points:[...], analogy, pitfall}]
    examples: list = field(default_factory=list)        # [{problem, steps:[...], answer, method}]
    diagrams: list = field(default_factory=list)        # [{type, ...svg参数, caption}] 数学示意图
    practice: dict = field(default_factory=dict)        # {basic:[{q,a}], standard:[...], advanced:[...]}
    summary: dict = field(default_factory=dict)         # {points:[...], formula}
    board: dict = field(default_factory=dict)           # {center, branches:[{label, items:[...]}]}
    homework: dict = field(default_factory=dict)        # {basic:[{q,a}], standard:[...], advanced:[...]}

    @classmethod
    def from_dict(cls, d):
        d = d if isinstance(d, dict) else {}
        def _as_dict(v):
            return v if isinstance(v, dict) else {}
        def _as_list(v):
            return v if isinstance(v, list) else []
        def _qa_list(v):
            """档位 → [{q,a}]。容错：强模型可能把单题写成 {q,a}（非数组），自动包成 [dict]。"""
            if isinstance(v, dict) and v.get("q"):
                v = [v]
            out = []
            for it in _as_list(v):
                if isinstance(it, dict):
                    out.append({"q": str(it.get("q", "")), "a": str(it.get("a", ""))})
            return out
        def _tiers(v):
            v = _as_dict(v)
            return {
                "basic": _qa_list(v.get("basic")),
                "standard": _qa_list(v.get("standard")),
                "advanced": _qa_list(v.get("advanced")),
            }
        lead_in = _as_dict(d.get("lead_in"))
        summary = _as_dict(d.get("summary"))
        board = _as_dict(d.get("board"))
        # summary 键名漂移归一化：强模型可能写 patterns/words 而非 points/formula
        summary_points = summary.get("points")
        if not summary_points and summary.get("patterns"):
            summary_points = summary["patterns"]
        if not summary_points and summary.get("words"):
            summary_points = summary["words"]
        summary_formula = summary.get("formula", "")
        # board 键名漂移归一化：强模型可能写 words/patterns 而非 branches
        board_branches = board.get("branches")
        if not board_branches and (board.get("words") or board.get("patterns")):
            raw_branches = board.get("words") or board.get("patterns") or []
            # words/patterns 是 [str]，转成 branches [{label, items}]
            if isinstance(raw_branches, list):
                board_branches = []
                for it in raw_branches:
                    if isinstance(it, str):
                        board_branches.append({"label": it[:16], "items": [it[:40]]})
                    elif isinstance(it, dict):
                        board_branches.append(it)
        return cls(
            title=str(d.get("title", "")),
            objectives=[str(x) for x in _as_list(d.get("objectives")) if isinstance(x, str)],
            lead_in={k: str(v) for k, v in lead_in.items() if isinstance(v, str)},
            concepts=[
                {"statement": str(c.get("statement", "")),
                 "points": [str(x) for x in _as_list(c.get("points")) if isinstance(x, str)],
                 "analogy": str(c.get("analogy", "")), "pitfall": str(c.get("pitfall", ""))}
                for c in _as_list(d.get("concepts")) if isinstance(c, dict)
            ],
            examples=[
                {"problem": str(e.get("problem", "")),
                 "steps": [str(x) for x in _as_list(e.get("steps")) if isinstance(x, str)],
                 "answer": str(e.get("answer", "")), "method": str(e.get("method", ""))}
                for e in _as_list(d.get("examples")) if isinstance(e, dict)
            ],
            diagrams=[dict(x) for x in _as_list(d.get("diagrams")) if isinstance(x, dict)],
            practice=_tiers(d.get("practice")),
            summary={
                "points": [str(x) for x in _as_list(summary_points) if isinstance(x, str)],
                "formula": str(summary_formula),
            },
            board={
                "center": str(board.get("center", "")),
                "branches": [
                    {"label": str(b.get("label", "")),
                     "items": [str(x) for x in _as_list(b.get("items")) if isinstance(x, str)]}
                    for b in _as_list(board_branches) if isinstance(b, dict)
                ],
            },
            homework=_tiers(d.get("homework")),
        )

    def to_dict(self):
        return asdict(self)
@dataclass
class PageSpec:
    page_id: str                         # "p01"
    event_id: str
    kind: str                            # 冗余事件 kind，渲染用
    layout_id: str
    slots: dict = field(default_factory=dict)
    style_overrides: dict = field(default_factory=dict)  # 仅允许 {accent, align, vertical}
    source: str = "llm"                  # "llm" | "retry" | "skeleton"

    def to_dict(self):
        return asdict(self)


def coerce_pagespec(raw, event=None, layouts=None, cat=None, stage=None):
    """宽松解析单页 JSON → PageSpec；任何一步失败返回 None（走兜底骨架页）。

    校验链：
      - raw 必须 dict 且含 layout_id
      - layout_id ∈ 注册表（layouts 传入）
      - 若提供 cat/stage，则要求 layout 的 applicable 命中（当前 cat/kind/stage）
      - check_slots 通过（必填齐、list 长度 ∈ 上下限、str 超长截断）
    """
    if not isinstance(raw, dict):
        return None
    layout_id = raw.get("layout_id")
    if not layout_id or not isinstance(layouts, dict) or layout_id not in layouts:
        return None
    defn = layouts[layout_id]
    # applicable 校验（若提供 cat/stage）
    if cat is not None:
        kind = (event.kind if event else raw.get("kind")) or ""
        if not defn.is_applicable(cat, kind, stage):
            return None
    slots = defn.check_slots(raw.get("slots") or {})
    if slots is None:
        return None
    # style_overrides 仅允许三个键
    so = raw.get("style_overrides") or {}
    so = {k: so[k] for k in ("accent", "align", "vertical") if k in so}
    ev = event
    return PageSpec(
        page_id=str(raw.get("page_id", "")),
        event_id=str(raw.get("event_id", ev.event_id if ev else "")),
        kind=str(raw.get("kind", ev.kind if ev else defn.layout_id)),
        layout_id=layout_id,
        slots=slots,
        style_overrides=so,
        source=str(raw.get("source", "llm")),
    )
