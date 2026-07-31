"""课评路由：编辑器 + 单人同步生成（幂等） + 确认/请假 + 同班去重。

并发策略（v6）：前端 4 路 Promise 池，每份课评打一次
POST /reviews/<rid>/generate（同步、5-8s 返回）。后端只负责单份生成 +
status 状态机（pending/generating/draft/confirmed/leave/failed）作为断点续跑唯一真相。
"""
from datetime import datetime

from flask import (
    render_template, redirect, url_for, flash, request, current_app, jsonify,
)
from flask_login import login_required, current_user
from extensions import db
from models.class_student import Klass, Student, Enrollment
from models.lesson import Lesson, Review, Courseware, StyleSample
from models.class_type_preset import ClassTypePreset
from ai.llm_client import LLMClient
from ai.channel import Channel
from ai.prompt_builder import build_messages
from ai.redact import Redactor
from ai.review_scorer import score_review

from . import reviews_bp

GENERATING_TTL = 120  # 秒：超过则允许重入


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

    hist = _history_for(student.id, review.id)
    style = _get_style_examples(klass.id)
    cw_text = ""
    if lesson.courseware_id:
        cw = Courseware.query.get(lesson.courseware_id)
        cw_text = cw.extracted_text if cw else ""

    red = Redactor(student.name, student.preferred_name)
    s_name = red.redact(student.name) or "{{STU}}"
    s_nick = red.redact(student.preferred_name) if student.preferred_name else s_name
    hist_r = [red.redact(h) for h in hist]
    style_r = [red.redact(s) for s in style]

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
    )
    client = LLMClient()
    raw = client.complete(messages, timeout=120)
    text = red.restore(raw)

    review.content = text
    review.ai_raw = raw
    review.status = 'draft'
    review.model_used = current_app.config.get('AI_MODEL', 'glm-4-flash')
    review.score_json = score_review(text, preset=preset)
    review.generating_since = None
    review.error_msg = None
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

    return render_template(
        "reviews/editor.html",
        klass=klass, lesson=lesson, preset=preset, students=students, reviews=reviews,
        quick_tags_flat=quick_tags_flat,
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
         "edited_at": r.edited_at.isoformat() if r.edited_at else None}
        for r in rows
    ]
    return jsonify(data)


@reviews_bp.route("/<review_id>/generate", methods=["POST"])
@login_required
def generate(review_id):
    review = _review_or_404(review_id)
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
    review.content = request.form.get("content", review.content)
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
    db.session.commit()
    return jsonify({"ok": True, "status": "leave"})


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
    red = Redactor(student.name, student.preferred_name)
    s_name = red.redact(student.name) or "{{STU}}"
    s_nick = red.redact(student.preferred_name) if student.preferred_name else s_name
    messages = build_messages(
        preset=preset, student_name=s_name, preferred_name=s_nick,
        lesson_info={"title": lesson.title, "common_notes": lesson.common_notes,
                     "objectives": lesson.objectives or []},
        courseware_text=cw_text,
        history_reviews=[red.redact(h) for h in hist],
        style_examples=[red.redact(s) for s in style],
        trial=(lesson.lesson_type == 'trial'),
        reference_opening=red.redact(reference_opening),
    )
    client = LLMClient()
    raw = client.complete(messages, timeout=120)
    text = red.restore(raw)
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
