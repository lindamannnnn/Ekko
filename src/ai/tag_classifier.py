"""渲染期标签情感判定（生成卡片图片时使用）。

职责：判断单个课堂表现标签是否为「负向」。负向标签（含老师自定义的）在生成
卡片图片时一律不渲染。

判定策略（混合，兼顾速度 / 成本 / 稳定性）：
  1. 硬负向关键词快速判定：命中的明显负向短语直接判 negative，跳过 LLM（覆盖
     「需加强练习」「注意力分散」等常见快捷标签，也保证 LLM 不可用时不漏判）。
  2. 其余交给 AI 判定（用户要求「生成图片的时候 给 AI 判断」），支持任意自定义标签。
  3. 进程内缓存：同一标签文本只调一次 LLM；AI 失败则回退到规则判定。

注意：本模块只用于「渲染 / 生成图片」路径。课评生成期给 AI 的「教师信号」分析
仍用 prompt_builder._classify_tag（规则版、零额外成本），两者互不影响。
"""
from ai.llm_client import LLMClient

# 进程内缓存：tag 文本 -> 'negative' / 'positive' / 'neutral'
_cache: dict[str, str] = {}

# 命中即判负向的明显短语（跳过 AI）。刻意排除「困难」等可能出现在正向语境
# （如「克服困难」）的词，避免误杀；这类交给 AI 判定。
_HARD_NEG = (
    "需加强", "有待", "待提高", "待加强", "待巩固", "需巩固", "需提升",
    "薄弱", "不足", "欠缺", "生疏", "退步", "吃力", "差劲", "潦草",
    "马虎", "粗心", "分心", "走神", "溜号", "开小差", "调皮", "散漫",
    "不认真", "不专注", "不积极", "易分心", "注意力不集中", "爱讲话",
    "爱说话", "基础弱", "基础差", "需改进", "待改进", "需努力", "缺漏",
)

_SYSTEM = (
    "你是一个严格的短标签情感分类器。用户输入是一句给学生的「课堂表现标签」"
    "（通常 2-8 个字，可能由老师自定义填写）。请只判断这个标签整体表达的是"
    "正面、中性还是负面。\n"
    "判定标准：\n"
    "- negative（负面）：暗示学生表现不足、需要改进、存在缺点。例如「需加强练习」"
    "「有待提高」「注意力分散」「粗心大意」「基础薄弱」「书写潦草」「爱开小差」等。\n"
    "- positive（正面）：表扬、肯定、做得好的方面。例如「积极互动」「专注听讲」"
    "「表现优异」「逻辑清晰」「乐于助人」「创意十足」「注意力集中」等。\n"
    "- neutral（中性）：客观描述、既不明显褒也不明显贬。例如「使用铅笔」「完成练习」"
    "「坐第一排」等。\n"
    "只输出一个英文单词：negative / positive / neutral。不要任何解释或标点。"
)


def _rule_fallback(tag: str) -> str:
    """AI 不可用时的兜底：复用 prompt_builder 的规则判定。"""
    from ai.prompt_builder import _classify_tag
    return _classify_tag(tag)


def classify_tag(tag, user=None) -> str:
    """返回 'negative' / 'positive' / 'neutral'。负向标签在卡片图片中不渲染。"""
    if not tag:
        return "neutral"
    t = str(tag).strip()
    if not t:
        return "neutral"
    if t in _cache:
        return _cache[t]

    # 1) 硬负向快速判定
    if any(k in t for k in _HARD_NEG):
        _cache[t] = "negative"
        return "negative"

    # 2) 交给 AI 判定（课评侧固定平台默认模型 GLM-4-Flash，不用用户自定义 KEY）
    result = None
    try:
        client = LLMClient()
        resp = client.complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": t},
            ],
            temperature=0,
            timeout=20,
        )
        label = (resp or "").strip().lower()
        if "negative" in label:
            result = "negative"
        elif "positive" in label:
            result = "positive"
        elif "neutral" in label:
            result = "neutral"
        else:
            result = _rule_fallback(t)
    except Exception:
        result = _rule_fallback(t)

    _cache[t] = result
    return result


def render_tags(tags, user=None) -> list[str]:
    """过滤掉负向标签，返回应在卡片「本次亮点」中渲染的标签列表。"""
    out = []
    for t in (tags or []):
        if not t:
            continue
        t = str(t).strip()
        if not t:
            continue
        if classify_tag(t, user=user) != "negative":
            out.append(t)
    return out
