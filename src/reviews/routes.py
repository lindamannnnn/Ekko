"""课评路由：编辑器 + 单人同步生成（幂等） + 确认/请假 + 同班去重。

并发策略（v6）：前端 4 路 Promise 池，每份课评打一次
POST /reviews/<rid>/generate（同步、5-8s 返回）。后端只负责单份生成 +
status 状态机（pending/generating/draft/confirmed/leave/failed）作为断点续跑唯一真相。

全项目**唯一**的课评生成入口是 `_generate_for`（by-keys / editor / dedup 都汇到这里），
所有数据源都在此组装进 prompt，不再有第二套生成逻辑。
"""
import json
import re
from datetime import datetime

from flask import (
    render_template, redirect, url_for, flash, request, current_app, jsonify,
)
from flask_login import login_required, current_user
from sqlalchemy.orm.attributes import flag_modified
from extensions import db
from models.class_student import Klass, Student, Enrollment
from models.lesson import Lesson, Review, Courseware, StyleSample
from models.class_type_preset import ClassTypePreset
from ai.llm_client import LLMClient
from ai.channel import Channel
from ai.prompt_builder import build_messages, load_subject_template
from ai.review_library import get_library_example
from ai.redact import Redactor
from ai.review_scorer import score_review
from ai.review_normalize import finalize_review

from . import reviews_bp

GENERATING_TTL = 120  # 秒：超过则允许重入


def _split_ai_highlights(text: str):
    """从 AI 原稿里解析「亮点标签」区块。返回 (highlights: list[str], body: str)。

    仅当模型真的输出了显式标记「【AI亮点标签】」才认；否则视为无标签，
    整段原文作为正文返回（后续由规则兜底提取或直接展示）。
    兼容弱模型把多标签写在同一行（顿号/逗号/空格分隔）的变体。
    """
    marker = "【AI亮点标签】"
    idx = text.find(marker)
    if idx < 0:
        # 退化变体：去空格版本
        marker2 = "【AI 亮点标签】"
        idx = text.find(marker2)
        marker = marker2
    if idx < 0:
        return [], text

    body = text[:idx].rstrip()
    tail = text[idx + len(marker):]

    highlights = []
    for line in tail.splitlines():
        line = line.strip().strip("【】[]()").strip()
        line = re.sub(r"^[:：·•\-—]+\s*", "", line).strip()
        # 一行内可能用顿号/逗号/空格分隔多个标签
        for part in re.split(r"[、，,\s]+", line):
            p = part.strip()
            if not p:
                continue
            if 2 <= len(p) <= 12 and "亮点" not in p and "标签" not in p \
               and not any(ch in p for ch in "。？！；…：:"):
                highlights.append(p)
            if len(highlights) >= 4:
                break
        if len(highlights) >= 4:
            break
    return highlights, body


def _get_style_examples(class_id):
    """本班 confirmed 稿 > 用户全局样本 > 内置范文。"""
    samples = (
        StyleSample.query.filter_by(class_id=class_id, is_active=True)
        .order_by(StyleSample.source.desc())
        .all()
    )
    return [s.content for s in samples if s.content]


def _klass_or_404(class_id):
    return Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()


def _review_or_404(review_id):
    return Review.query.filter_by(id=review_id, user_id=current_user.id).first_or_404()


def _students_for(class_id):
    return (
        Student.query.join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.class_id == class_id, Enrollment.deleted_at.is_(None),
                Student.deleted_at.is_(None))
        .all()
    )


def _history_for(student_id, exclude_review_id, limit=3):
    rows = (
        Review.query.join(Lesson, Lesson.id == Review.lesson_id)
        .filter(
            Review.student_id == student_id,
            Review.user_id == current_user.id,
            Review.status == 'confirmed',
            Review.id != exclude_review_id,
            Lesson.deleted_at.is_(None),
        )
        .order_by(Lesson.lesson_date.desc().nullslast())
        .limit(limit)
        .all()
    )
    return [r.content for r in rows if r.content]


def _generate_for(review: Review) -> dict:
    """单份生成：组装四源 prompt → 调 LLM → 脱敏还原 → 存库。返回结果 dict。"""
    klass = _klass_or_404(review.class_id)
    preset = ClassTypePreset.query.filter_by(code=klass.type_code).first()
    lesson = Lesson.query.get(review.lesson_id)
    student = Student.query.get(review.student_id)
    if not (lesson and student):
        raise ValueError("课次或学生不存在")

    # 学科课评模板：作为「格式 + 写法示范」注入（严禁 AI 照抄模板示例内容，
    # 必须结合本节课课件/教案真实内容生成）。subject_code 同时驱动开头范式差异化。
    subject_code = klass.type_code
    subject_template = load_subject_template(subject_code)

    hist = _history_for(student.id, review.id)
    style = _get_style_examples(klass.id)

    # 课程内容：课件优先，回退班级共享 _course_content（无每课课件时仍可生成）
    cw_text = ""
    if lesson.courseware_id:
        cw = Courseware.query.get(lesson.courseware_id)
        cw_text = cw.extracted_text if cw else ""
    if not cw_text:
        cw_text = (klass.extra_data or {}).get("_course_content") or ""

    # 班级级优秀历史课评（次优先级风格范例）
    excellent_raw = (klass.extra_data or {}).get("_excellent_review") or ""
    # 同类别课评库兜底：仅当「该生历史课评」与「班级优秀课评」都空时
    library_example = ""
    if not hist and not excellent_raw:
        library_example = get_library_example(klass.type_code, klass.type_name_custom)

    # 教师本节课输入：快捷标签 + 一句话评语（评价/事实锚点，R3③ 禁止编造的依据）
    quick_tags = review.perf_tags or []
    one_sentence = review.perf_note or ""

    red = Redactor(student.name, student.preferred_name)
    s_name = red.redact(student.name) or "{{STU}}"
    s_nick = red.redact(student.preferred_name) if student.preferred_name else s_name
    hist_r = [red.redact(h) for h in hist]
    style_r = [red.redact(s) for s in style]
    excellent_review = red.redact(excellent_raw) if excellent_raw else ""

    lesson_info = {
        "title": lesson.title,
        "common_notes": lesson.common_notes,
        "objectives": lesson.objectives or [],
    }
    messages = build_messages(
        preset=preset,
        student_name=s_name,
        preferred_name=s_nick,
        lesson_info=lesson_info,
        courseware_text=cw_text,
        history_reviews=hist_r,
        style_examples=style_r,
        trial=(lesson.lesson_type == 'trial'),
        subject_code=subject_code,
        subject_template=subject_template,
        gender=student.gender,
        quick_tags=quick_tags,
        one_sentence=one_sentence,
        excellent_review=excellent_review,
        library_example=library_example,
    )
    # 课评固定使用平台默认模型（GLM-4-Flash），不用用户自定义 KEY——
    # 用户 KEY 只对课前备课/课件生效（见 prep/views.py）。
    client = LLMClient()
    raw = client.complete(messages, timeout=120)
    text = red.restore(raw)
    # 教师未点标签时，模型会在文末附「【AI亮点标签】」区块：先解析剥离，正文只留课评
    ai_highlights, body = _split_ai_highlights(text)
    # 后端确定性兜底：
    #  - 有「班级级优秀历史课评」作模板时，保留模型多段维度化结构（force_two=False），不硬截断；
    #  - 否则强制 2 段 + 1 空行结构，并按预置上限做字数硬截断。
    force_two = not bool(excellent_raw)
    text = finalize_review(
        body,
        (preset.length_max if preset else None) if force_two else None,
        force_two=force_two,
    )

    # 用账号昵称作为教师签名追加在正文末尾，保持统一落款
    teacher_name = current_user.display_name or '教师'
    sign = f"\n\n——{teacher_name}"
    if not text.rstrip().endswith(teacher_name):
        text = text.rstrip() + sign

    review.content = text
    review.ai_raw = raw
    review.status = 'draft'
    review.model_used = current_app.config.get('AI_MODEL', 'glm-4-flash')
    review.score_json = score_review(text, preset=preset)
    review.generating_since = None
    review.error_msg = None
    # 存 AI 自动总结的亮点标签（老师没点标签时由模型产出），供卡片渲染优先使用
    if ai_highlights:
        meta = dict(review.meta_json or {})
        meta['ai_highlights'] = ai_highlights
        review.meta_json = meta
        flag_modified(review, 'meta_json')
    db.session.commit()

    chan = Channel(current_user.id)
    chan.record_usage(channel='platform')
    return {"ok": True, "status": "draft", "score": review.score_json}


@reviews_bp.route("/<class_id>/<lesson_id>/editor")
@login_required
def editor(class_id, lesson_id):
    klass = _klass_or_404(class_id)
    lesson = Lesson.query.filter_by(id=lesson_id, user_id=current_user.id).first_or_404()
    preset = ClassTypePreset.query.filter_by(code=klass.type_code).first()
    students = _students_for(class_id)

    # 确保每个学生都有一条 review（pending），并取出全部
    reviews = []
    for s in students:
        rev = Review.query.filter_by(
            class_id=class_id, lesson_id=lesson_id, student_id=s.id,
            user_id=current_user.id,
        ).first()
        if rev is None:
            rev = Review(
                user_id=current_user.id, class_id=class_id,
                lesson_id=lesson_id, student_id=s.id, status='pending',
            )
            db.session.add(rev)
        reviews.append(rev)
    db.session.commit()

    quick_tags_flat = []
    if preset and preset.quick_tags:
        for _dim, tags in preset.quick_tags.items():
            if isinstance(tags, list):
                quick_tags_flat.extend(tags)

    # 是否有可生成的内容：班级共享 _course_content 或 本节课有课件
    course_ready = bool(
        (klass.extra_data or {}).get("_course_content")
        or Lesson.query.filter_by(class_id=class_id, deleted_at=None)
        .join(Courseware, Courseware.id == Lesson.courseware_id)
        .first()
    )

    return render_template(
        "reviews/editor.html",
        klass=klass, lesson=lesson, preset=preset, students=students, reviews=reviews,
        quick_tags_flat=quick_tags_flat, course_ready=course_ready,
    )


@reviews_bp.route("/<class_id>/<lesson_id>/status")
@login_required
def status(class_id, lesson_id):
    rows = (
        Review.query.filter_by(class_id=class_id, lesson_id=lesson_id,
                              user_id=current_user.id)
        .all()
    )
    data = [
        {"id": r.id, "student_id": r.student_id, "status": r.status,
         "content": r.content, "score": r.score_json, "error_msg": r.error_msg,
         "perf_tags": r.perf_tags or [],      # 教师点选快捷标签（前端回显用）
         "perf_note": r.perf_note,            # 教师一句话评语（前端回显用，冗余于 teacher_comment）
         "teacher_comment": r.perf_note,      # 兼容旧前端字段名
         "edited_at": r.edited_at.isoformat() if r.edited_at else None}
        for r in rows
    ]
    return jsonify(data)


@reviews_bp.route("/<review_id>")
@login_required
def view_review(review_id):
    """课评只读详情页：从账号页点击记录进入，仅展示正文，不暴露编辑器控件。"""
    review = Review.query.filter_by(
        id=review_id, user_id=current_user.id
    ).first_or_404()
    klass = Klass.query.filter_by(
        id=review.class_id, user_id=current_user.id, deleted_at=None
    ).first_or_404()
    student = db.session.get(Student, review.student_id)
    lesson = db.session.get(Lesson, review.lesson_id)
    return render_template(
        "reviews/view.html",
        review=review,
        klass=klass,
        student=student,
        lesson=lesson,
    )


@reviews_bp.route("/<review_id>/generate", methods=["POST"])
@login_required
def generate(review_id):
    review = _review_or_404(review_id)
    # 请假状态直接返回固定文案，不调用 AI
    if review.status == 'leave':
        return jsonify({"ok": True, "status": "leave", "content": review.content})
    # 幂等锁：正在生成且未超时 -> 拒绝；超时 -> 允许重入
    if review.status == 'generating' and review.generating_since:
        elapsed = (datetime.utcnow() - review.generating_since).total_seconds()
        if elapsed < GENERATING_TTL:
            return jsonify({"ok": False, "status": review.status,
                            "error": "正在生成中，请稍候"}), 409

    review.status = 'generating'
    review.generating_since = datetime.utcnow()
    review.error_msg = None
    db.session.commit()
    try:
        result = _generate_for(review)
        # 回传正文，使前端生成后无需刷新即可在编辑器内显示（修复 UX 断裂）
        result["content"] = review.content
        return jsonify(result)
    except Exception as e:  # noqa: BLE001
        review.status = 'failed'
        review.error_msg = str(e)[:500]
        review.generating_since = None
        db.session.commit()
        return jsonify({"ok": False, "status": "failed", "error": str(e)}), 500


@reviews_bp.route("/<review_id>/save", methods=["POST"])
@login_required
def save(review_id):
    review = _review_or_404(review_id)
    content = request.form.get("content")
    if content is not None:
        review.content = content
    # 接收前端发来的教师点选快捷标签 / 本节课一句话评语（editor.js 会发）
    tags = request.form.get("perf_tags")
    if tags is not None:
        try:
            review.perf_tags = json.loads(tags) if tags.strip() else []
        except Exception:
            review.perf_tags = [t.strip() for t in tags.split(",") if t.strip()]
    note = request.form.get("teacher_comment")
    if note is not None:
        review.perf_note = note
    review.edited_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@reviews_bp.route("/<review_id>/confirm", methods=["POST"])
@login_required
def confirm(review_id):
    review = _review_or_404(review_id)
    review.status = 'confirmed'
    review.edited_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "status": "confirmed"})


@reviews_bp.route("/<review_id>/leave", methods=["POST"])
@login_required
def leave(review_id):
    review = _review_or_404(review_id)
    review.status = 'leave'
    review.content = '请假'
    review.ai_raw = ''
    review.generating_since = None
    review.error_msg = None
    db.session.commit()
    return jsonify({"ok": True, "status": "leave", "content": review.content})


@reviews_bp.route("/<review_id>/revert", methods=["POST"])
@login_required
def revert(review_id):
    """还原 AI 原稿（放弃手动修改）。"""
    review = _review_or_404(review_id)
    if review.ai_raw:
        review.content = review.ai_raw
        review.edited_at = None
        db.session.commit()
        return jsonify({"ok": True, "content": review.content})
    return jsonify({"ok": False, "error": "无原稿"}), 400


@reviews_bp.route("/<review_id>/delete", methods=["POST", "DELETE"])
@login_required
def delete_review(review_id):
    """软删除历史课评（从该生历史列表移除，不破坏其他依赖）。已删除幂等返回 ok。"""
    review = _review_or_404(review_id)
    if review.deleted_at:
        return jsonify({"ok": True, "review_id": review_id, "already_deleted": True})
    review.deleted_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "review_id": review_id})


@reviews_bp.route("/<class_id>/<lesson_id>/dedup", methods=["POST"])
@login_required
def dedup(class_id, lesson_id):
    from services.dedup import pairwise_scores, opening_sentence
    threshold = float(request.form.get("threshold", 0.35))
    reviews = (
        Review.query.filter_by(class_id=class_id, lesson_id=lesson_id,
                              user_id=current_user.id)
        .filter(Review.status.in_(['draft', 'confirmed']))
        .all()
    )
    pairs = pairwise_scores([(r.id, r.content or "") for r in reviews], threshold)
    rewritten = 0
    for id_a, id_b, score in pairs:
        # 重写较晚生成的一份（按 id 字典序近似，真正取 edited/created 需查；用 id 比较稳定）
        later, earlier = sorted([id_a, id_b], key=lambda x: x)
        rev_later = next((r for r in reviews if r.id == later), None)
        rev_earlier = next((r for r in reviews if r.id == earlier), None)
        if not (rev_later and rev_earlier):
            continue
        # 注入对方开头句，触发 R6 差异化，重新生成
        ref_open = opening_sentence(rev_earlier.content or "")
        try:
            _regenerate_with_reference(rev_later, ref_open)
            rev_later.dedup_score = score
            rewritten += 1
        except Exception as e:  # noqa: BLE001
            rev_later.error_msg = f"去重重写失败：{str(e)[:200]}"
            rev_later.status = 'failed'
    db.session.commit()
    return jsonify({"ok": True, "pairs": pairs, "rewritten": rewritten})


def _regenerate_with_reference(review, reference_opening):
    """带参考开头句重写一份（去重用）。"""
    klass = _klass_or_404(review.class_id)
    preset = ClassTypePreset.query.filter_by(code=klass.type_code).first()
    lesson = Lesson.query.get(review.lesson_id)
    student = Student.query.get(review.student_id)
    hist = _history_for(student.id, review.id)
    style = _get_style_examples(klass.id)
    cw_text = ""
    if lesson.courseware_id:
        cw = Courseware.query.get(lesson.courseware_id)
        cw_text = cw.extracted_text if cw else ""
    if not cw_text:
        cw_text = (klass.extra_data or {}).get("_course_content") or ""
    excellent_raw = (klass.extra_data or {}).get("_excellent_review") or ""
    library_example = ""
    if not hist and not excellent_raw:
        library_example = get_library_example(klass.type_code, klass.type_name_custom)
    quick_tags = review.perf_tags or []
    one_sentence = review.perf_note or ""
    red = Redactor(student.name, student.preferred_name)
    s_name = red.redact(student.name) or "{{STU}}"
    s_nick = red.redact(student.preferred_name) if student.preferred_name else s_name
    subject_code = klass.type_code
    subject_template = load_subject_template(subject_code)
    messages = build_messages(
        preset=preset, student_name=s_name, preferred_name=s_nick,
        lesson_info={"title": lesson.title, "common_notes": lesson.common_notes,
                     "objectives": lesson.objectives or []},
        courseware_text=cw_text,
        history_reviews=[red.redact(h) for h in hist],
        style_examples=[red.redact(s) for s in style],
        trial=(lesson.lesson_type == 'trial'),
        reference_opening=red.redact(reference_opening),
        subject_code=subject_code,
        subject_template=subject_template,
        gender=student.gender,
        quick_tags=quick_tags,
        one_sentence=one_sentence,
        excellent_review=red.redact(excellent_raw) if excellent_raw else "",
        library_example=library_example,
    )
    # 课评固定使用平台默认模型（GLM-4-Flash），不用用户自定义 KEY。
    client = LLMClient()
    raw = client.complete(messages, timeout=120)
    text = red.restore(raw)
    force_two = not bool(excellent_raw)
    text = finalize_review(
        text,
        (preset.length_max if preset else None) if force_two else None,
        force_two=force_two,
    )
    review.content = text
    review.ai_raw = raw
    review.status = 'draft'
    review.model_used = current_app.config.get('AI_MODEL', 'glm-4-flash')
    review.score_json = score_review(text, preset=preset)
    review.generating_since = None


@reviews_bp.route("/<review_id>/edit", methods=["GET", "POST"])
@login_required
def edit(review_id):
    review = _review_or_404(review_id)
    if request.method == "POST":
        review.content = request.form.get("content", review.content)
        review.edited_at = datetime.utcnow()
        db.session.commit()
        flash("课评已保存", "success")
        return redirect(url_for("classes.detail", class_id=review.class_id))
    return render_template("reviews/edit.html", review=review)


# ===================== 关键路由：by-keys（无 lesson_id 的 AI 生成） =====================
# 旧设计：AI 生成必须先调 status 端点拿 review_id、再调 /<rid>/generate。
# 这条链路任何一环失败（缓存/竞态/字段不匹配）都会弹窗，故障面太广。
# 新设计：按自然键（class_id + student_id ± lesson_id）直接生成，
# 后端自己保证 review 行存在（找不到就当场创建），前端 AI 生成按钮
# 改为直接 POST 这个端点，根本上消灭弹窗。

def _generate_by_keys_impl(class_id, lesson_id, student_id, allow_fallback):
    """by-keys 端点的公共实现。
    class_id:    班级
    lesson_id:   课次（None 时按 allow_fallback 自动选/建）
    student_id:  学生
    allow_fallback: True 时允许自动选最近 lesson 或自建今日 lesson
    """
    klass = _klass_or_404(class_id)
    student = Student.query.filter_by(id=student_id, deleted_at=None).first()
    if not student:
        return jsonify({"ok": False, "error": "学生不存在"}), 404
    enrollment = Enrollment.query.filter_by(
        student_id=student_id, class_id=class_id, deleted_at=None,
    ).first()
    if not enrollment:
        return jsonify({"ok": False, "error": "该学生不在本班"}), 404

    # --- 解析 lesson ---
    lesson = None
    if lesson_id:
        lesson = Lesson.query.filter_by(
            id=lesson_id, user_id=current_user.id, class_id=class_id, deleted_at=None,
        ).first()
    if not lesson and allow_fallback:
        lesson = (
            Lesson.query.filter_by(class_id=class_id, deleted_at=None)
            .order_by(Lesson.lesson_date.desc().nullslast(), Lesson.created_at.desc())
            .first()
        )
    if not lesson and allow_fallback:
        from models.lesson import Lesson as _Lesson
        lesson = _Lesson(
            user_id=current_user.id, class_id=class_id,
            title="今日课堂", lesson_type="regular",
            lesson_date=datetime.utcnow().date(),
        )
        db.session.add(lesson)
        db.session.commit()
    if not lesson:
        return jsonify({"ok": False, "error": "课次不存在或已删除"}), 404

    # --- 接收前端 inline 课程内容 / 教师评语 ---
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:  # noqa: BLE001
        payload = {}
    inline_course = (payload.get("course_content") or "").strip()
    if inline_course:
        extra = dict(klass.extra_data or {})
        if (extra.get("_course_content") or "").strip() != inline_course:
            extra["_course_content"] = inline_course
            klass.extra_data = extra
            flag_modified(klass, "extra_data")
            db.session.commit()

    review = Review.query.filter_by(
        class_id=class_id, lesson_id=lesson.id, student_id=student_id,
        user_id=current_user.id,
    ).first()
    if review is None:
        review = Review(
            user_id=current_user.id, class_id=class_id,
            lesson_id=lesson.id, student_id=student_id, status='pending',
        )
        db.session.add(review)
        db.session.commit()
    inline_note = (payload.get("teacher_comment") or "").strip()
    if inline_note and (review.perf_note or "").strip() != inline_note:
        review.perf_note = inline_note
        db.session.commit()

    # 接收前端 inline 教师点选快捷标签（与 teacher_comment 同源，保证 by-keys 链路
    # 也能把教师标签作为事实锚点传给 AI，与 editor 链路一致）
    inline_tags = payload.get("perf_tags")
    if inline_tags:
        try:
            parsed = json.loads(inline_tags) if isinstance(inline_tags, str) else inline_tags
            if isinstance(parsed, list) and parsed:
                review.perf_tags = [str(t) for t in parsed]
                db.session.commit()
        except Exception:  # noqa: BLE001
            pass

    has_cw = bool(lesson.courseware_id and Courseware.query.get(lesson.courseware_id))
    has_content = bool((klass.extra_data or {}).get("_course_content"))
    if not has_cw and not has_content:
        return jsonify({"ok": False, "status": review.status,
                        "error": "本节课还没有课件，也没有填写班级共享课程内容，无法生成课评。请先上传本节课课件，或在班级详情页填写共享课程内容后再生成。"}), 400

    if review.status == 'generating' and review.generating_since:
        elapsed = (datetime.utcnow() - review.generating_since).total_seconds()
        if elapsed < 300:  # GENERATING_TTL
            return jsonify({"ok": False, "status": review.status,
                            "error": "正在生成中，请稍候"}), 409

    review.status = 'generating'
    review.generating_since = datetime.utcnow()
    review.error_msg = None
    db.session.commit()
    try:
        result = _generate_for(review)
        result['review_id'] = review.id
        # 详情页 AI 生成按钮用 setAiContent(genData.content) 把内容写回 textarea，
        # 必须把生成后的课评正文一并返回（之前漏了导致前端误判为失败弹「未知错误」）。
        result['content'] = review.content
        if allow_fallback and not lesson_id:
            result['lesson_id'] = lesson.id
        return jsonify(result)
    except Exception as e:  # noqa: BLE001
        review.status = 'failed'
        review.error_msg = str(e)[:500]
        db.session.commit()
        current_app.logger.exception('AI generate by-keys failed')
        return jsonify({"ok": False, "status": "failed", "error": str(e)[:500]}), 500


@reviews_bp.route("/by-keys/<class_id>/<lesson_id>/<student_id>/generate", methods=["POST"])
@login_required
def generate_by_keys(class_id, lesson_id, student_id):
    """有 lesson_id 的 by-keys 端点（lesson 必须存在）。"""
    return _generate_by_keys_impl(class_id, lesson_id, student_id, allow_fallback=False)


@reviews_bp.route("/by-keys/<class_id>/<student_id>/generate", methods=["POST"])
@login_required
def generate_by_keys_no_lesson(class_id, student_id):
    """无 lesson_id 的 by-keys 端点（自动选最近 lesson 或自建今日 lesson）。"""
    return _generate_by_keys_impl(class_id, None, student_id, allow_fallback=True)


@reviews_bp.route("/<class_id>/history/<student_id>", methods=["GET"])
@login_required
def history(class_id, student_id):
    """按学生查所有已生成课评（不依赖 lesson_id），供前端历史弹窗用。"""
    klass = _klass_or_404(class_id)
    # 安全检查：学生必须在该班
    enrollment = Enrollment.query.filter_by(
        student_id=student_id, class_id=class_id, deleted_at=None,
    ).first()
    if not enrollment:
        return jsonify({"ok": False, "error": "该学生不在本班"}), 404
    rows = (
        Review.query
        .filter_by(student_id=student_id, class_id=class_id, user_id=current_user.id)
        .filter(Review.deleted_at.is_(None))
        .filter(Review.content.isnot(None))
        .order_by(Review.updated_at.desc().nullslast(), Review.created_at.desc())
        .limit(50)
        .all()
    )
    reviews = []
    for r in rows:
        reviews.append({
            "id": r.id,
            "review_id": r.id,   # 别名：前端统一用 review_id，避免 id/class_id 混淆
            "lesson_id": r.lesson_id,
            "status": r.status,
            "content": r.content or "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return jsonify({"ok": True, "reviews": reviews})
