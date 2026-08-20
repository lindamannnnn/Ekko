"""图片模板（4 套：work / skill / academic / general）。

按机构类型分组渲染，共用 CSS 变量；html2canvas（UMD）前端导出 750px 长图 PNG。
"""
import re
from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.lesson import Review, Lesson
from models.class_student import Klass, Student
from models.class_type_preset import ClassTypePreset
from ai.prompt_builder import _POS_KW, _FOCUS_MAP
from ai.tag_classifier import render_tags

from flask import Blueprint
card_bp = Blueprint("cards", __name__, url_prefix="/cards")


# 老师没点正面标签、AI 总结也没出结果时，按学科类型兜底 3-4 条温和短语，
# 保证卡片永远不出现「本次课尚未记录亮点」这种空态。
_HIGHLIGHT_FALLBACK_BY_TEMPLATE = {
    'skill':    ['全程专注投入', '认真跟随示范', '积极完成练习', '主动参与互动'],
    'academic': ['主动思考问题', '专注听讲并理解', '认真完成练习', '积极回答互动'],
    'work':     ['专注投入创作', '积极动手实践', '认真完成作品', '仔细打磨细节'],
    'general':  ['全程积极参与', '认真投入课堂', '专注完成学习', '主动探索尝试'],
}
# 转折句开头（不希望当亮点）
_TURN_PREFIXES = ('虽然', '尽管', '即使', '即便', '虽说',
                  '但', '不过', '然而', '可是', '虽然说')
# 连接词 / 介词开头（拆出来的子句若以这些开头，就丢；不像"亮点"）
_CONNECTIVE_PREFIXES = ('并且', '同时', '接着', '然后', '此外', '另外',
                        '继续', '还是', '也是', '也是就', '一直', '已经',
                        '在', '对于', '关于', '通过', '经过', '根据',
                        '为此', '因此', '所以', '于是', '从而', '进而',
                        '下课后', '下课时')
# 纯"xxx 中/过程里"型介词短语（信息密度太低，不像亮点）
_PLACEHOLDER_OPENERS = ('在', '于')
# 建议/待提升句开头（语义是改进，不是亮点）
_SUGGEST_PREFIXES = ('下次', '下节课', '建议家长', '建议家里', '需要加强',
                     '需要巩固', '需要提升', '有待', '待加强', '待巩固',
                     '可提升', '仍需', '还需', '希望下次', '可以尝试', '可以挑战')
# 不足语义收尾或含蓄否定（避免"流畅度还有提升空间"被算亮点）
_INSUFFICIENT_HINTS = ('还有提升空间', '有待改善', '有待提高', '尚需',
                       '稍显不足', '略显不足', '尚有不足', '仍需努力',
                       '粗心导致', '不够熟练', '不够到位', '不够稳定',
                       '不够准确', '稍有欠缺')
# 弱褒义短语（让中性短句也能当亮点，弥补短 content 的覆盖）
_WEAK_POS_PHRASES = ['得不错', '得到位', '得均匀', '得流畅', '得稳定',
                     '很认真', '很仔细', '很积极', '很专注', '很稳定',
                     '得很认真', '得很仔细', '得很专注', '得很稳定']
# 多字负向词（直接子串匹配）
_MULTI_NEG_KW = {'不够', '不足', '缓慢', '欠缺', '困难', '差劲', '潦草',
                 '马虎', '调皮', '内向', '生疏', '退步', '吃力', '混淆', '问题',
                 '粗心', '走神', '分心', '溜号', '开小差', '注意力不'}
# 单字负向词（必须独立成词：前后不能是中文，避免「不错」被「不」误判）
_SINGLE_NEG_KW = {'差', '弱', '欠', '缺', '难', '散', '急', '乱', '慌', '粗', '慢'}
# 疑问词（含在句中任何位置都算疑问）
_QUESTION_TOKENS = ('怎么样', '如何呢', '怎么呢', '能否', '是不是',
                    '怎么', '如何', '怎样', '是否')


def _is_word_boundary(s: str, i: int, klen: int) -> bool:
    """s[i:i+klen] 处前后不能是中文字符（防止「不错」被「不」误判）。"""
    if i > 0 and '\u4e00' <= s[i - 1] <= '\u9fff':
        return False
    if i + klen < len(s) and '\u4e00' <= s[i + klen] <= '\u9fff':
        return False
    return True


def _has_true_negative(s: str) -> bool:
    """判断句子是否真的包含负向词，避免「不错/不犹豫/不动手」被「不」误判。"""
    if any(kw in s for kw in _MULTI_NEG_KW):
        return True
    for kw in _SINGLE_NEG_KW:
        for m in re.finditer(re.escape(kw), s):
            if _is_word_boundary(s, m.start(), len(kw)):
                return True
    # 「不」字单独规则：必须配合负向语义才算；含正向词或弱褒义则豁免
    if '不' in s:
        has_pos = (any(kw in s for kw in _POS_KW)
                   or any(k in s for k in _WEAK_POS_PHRASES))
        if not has_pos:
            return True
    return False


def _extract_highlights(content: str, preset_template: str = 'general', n: int = 4) -> list[str]:
    """老师没选正面标签时，从 AI 课评正文里自动总结 2-4 条亮点标签。

    策略：先去"1、xxx 2、xxx"式的编号噪音 → 按句号切句 → 再按逗号/顿号拆子句
    → 只挑 3-14 字的短小短语；最后硬截到 ≤10 字，保证 chip 看着像 label 不像句子。
    纯规则，不调 LLM（速度 + 成本 + 对弱模型稳定可控）。
    输入：AI 课评全文（200-800 字），可空。
    输出：长度 ≤ 8 字的短语列表（chip 形态），已去相似开头、按评分排序。
    不足 2 条 → 按学科类型补兜底短语；永远不为空。
    """
    fb = _HIGHLIGHT_FALLBACK_BY_TEMPLATE.get(
        preset_template, _HIGHLIGHT_FALLBACK_BY_TEMPLATE['general']
    )
    n = max(2, min(4, n))

    if not content or not content.strip():
        return fb[:n]

    # 0) 清噪音：去掉"1. xxx"、"一、xxx"、"——xxx"这类列点/小标题
    text = content
    text = re.sub(r'(?m)^\s*[一二三四五六七八九十0-9]+[、.)\.]+\s*', '', text)
    text = re.sub(r'(?m)^\s*[—\-–]+\s*', '', text)
    text = re.sub(r'[•·]', '', text)

    # 1) 拆子句：句号 → 再逗号/顿号。两层都做，给"短语"更多被挑到的机会。
    candidates = []
    for sent in re.split(r'[。！？；…\n]+', text):
        sent = sent.strip().strip('"\'「」『』')
        if not sent:
            continue
        if any(t in sent for t in _QUESTION_TOKENS):
            continue
        if sent.endswith(('?', '？', '吗')):
            continue
        # 这句里有逗号/顿号 → 拆子句，短的优先
        if re.search(r'[,，、]', sent):
            for piece in re.split(r'[,，、]', sent):
                piece = piece.strip().strip('"\'「」『』')
                if 3 <= len(piece) <= 14:
                    candidates.append(piece)
        else:
            # 没逗号：整句当候选（要求短，太长就是大句）
            if 6 <= len(sent) <= 14:
                candidates.append(sent)

    if not candidates:
        return fb[:n]

    # 2) 过滤：负向 / 转折 / 待提升 / 连接词开头的短语
    def is_skip(s: str) -> bool:
        if _has_true_negative(s):
            return True
        if s.startswith(_TURN_PREFIXES):
            return True
        if s.startswith(_SUGGEST_PREFIXES):
            return True
        if s.startswith(_CONNECTIVE_PREFIXES):
            return True
        if any(h in s for h in _INSUFFICIENT_HINTS):
            return True
        return False

    good = [s for s in candidates if not is_skip(s)]
    if not good:
        return fb[:n]

    # 3) 打分：正向词 > 焦点词 > 弱褒义；"短"再加分（chip 就该精简）
    def score(s: str) -> int:
        sc = 0
        sc += sum(2 for kw in _POS_KW if kw in s)        # 显式正向词 2 分/个
        if any(k in s for k in _FOCUS_MAP.keys()):        # 焦点词 +1
            sc += 1
        if any(k in s for k in _WEAK_POS_PHRASES):        # 弱褒义 +1
            sc += 1
        if len(s) <= 6:                                    # 更短更像 chip +1
            sc += 1
        return sc

    good.sort(key=lambda s: (-score(s), len(s)))

    # 4) 去相似前缀（按前 3 字）+ 硬截 ≤ 8 字（chip 形态）
    out = []
    seen = set()
    for s in good:
        if len(out) >= n:
            break
        short = s if len(s) <= 8 else s[:8]
        # 截断后尾部落在虚词 / 介词 / 时态助词上 → 再收 1-2 字到"实词"
        for _ in range(3):
            if len(short) <= 4:
                break
            if short[-1] in '的了并和且在于把被从就也都很还又后中时前上下':
                short = short[:-1]
            else:
                break
        # 截完后太短（信息量不够）→ 丢
        if len(short) < 3:
            continue
        prefix = short[:3]
        if prefix in seen:
            continue
        seen.add(prefix)
        out.append(short)

    # 5) 真实短语不足 2 条 → 按学科补兜底
    if len(out) < 2:
        for f in fb:
            if f[:3] in seen:
                continue
            out.append(f)
            seen.add(f[:3])
            if len(out) >= n:
                break

    return out[:n] if out else fb[:n] + out


@card_bp.route("/preview/<review_id>", methods=["GET", "POST"])
@login_required
def preview(review_id):
    review = Review.query.filter_by(id=review_id, user_id=current_user.id).first_or_404()
    lesson = Lesson.query.get(review.lesson_id)
    klass = Klass.query.get(review.class_id)
    student = Student.query.get(review.student_id)
    preset = ClassTypePreset.query.filter_by(code=klass.type_code).first() if klass else None

    # 渲染期用 AI 判定标签情感：负向标签（含老师自定义）一律不渲染。
    raw_tags = [t for t in (review.perf_tags or []) if t]
    pos_tags = render_tags(raw_tags, user=current_user)   # 已过滤负向，仅保留正面 / 中性标签

    # 老师没点正面标签时：优先用「生成时 AI 自己总结的亮点标签」(meta_json.ai_highlights)，
    # 没有再回退到规则提取（兼容历史课评 / 弱模型偶尔没输出标签的情况）。
    if not pos_tags:
        ai_hl = (review.meta_json or {}).get('ai_highlights') or []
        pos_tags = ai_hl if ai_hl else _extract_highlights(
            review.content or '',
            preset_template=(preset.card_template if preset else 'general'),
            n=4,
        )

    if request.method == "POST":
        return jsonify({"ok": True})
    return render_template(
        "cards/preview.html",
        review=review, lesson=lesson, klass=klass, preset=preset, student=student,
        pos_tags=pos_tags,
    )
