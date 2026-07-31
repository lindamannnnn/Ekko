"""学生档案：跨班课评时间线 + 阶段总结生成/编辑。"""
from datetime import datetime

from flask import render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from extensions import db
from models.class_student import Student, Enrollment, Klass
from models.lesson import Lesson, Review, TermSummary
from models.class_type_preset import ClassTypePreset
from ai.llm_client import LLMClient
from ai.redact import Redactor
from services.summary_builder import build_summary_messages

from . import students_bp


@students_bp.route("/<student_id>")
@login_required
def archive(student_id):
    student = Student.query.filter_by(id=student_id, user_id=current_user.id, deleted_at=None).first_or_404()
    classes = (
        Klass.query.join(Enrollment, Enrollment.class_id == Klass.id)
        .filter(Enrollment.student_id == student_id, Enrollment.deleted_at.is_(None),
                Klass.deleted_at.is_(None), Klass.user_id == current_user.id)
        .all()
    )
    reviews = (
        Review.query.join(Lesson, Lesson.id == Review.lesson_id)
        .filter(Review.student_id == student_id, Review.user_id == current_user.id,
                Lesson.deleted_at.is_(None))
        .order_by(Lesson.lesson_date.desc().nullslast())
        .all()
    )
    summaries = (
        TermSummary.query.filter_by(student_id=student_id, user_id=current_user.id)
        .order_by(TermSummary.created_at.desc() if hasattr(TermSummary, 'created_at') else TermSummary.period_end.desc())
        .all()
    )
    return render_template(
        "students/archive.html",
        student=student, classes=classes, reviews=reviews, summaries=summaries,
    )


@students_bp.route("/<student_id>/summary", methods=["POST"])
@login_required
def generate_summary(student_id):
    student = Student.query.filter_by(id=student_id, user_id=current_user.id, deleted_at=None).first_or_404()
    # 取该生已确认课评作为素材
    reviews = (
        Review.query.join(Lesson, Lesson.id == Review.lesson_id)
        .filter(Review.student_id == student_id, Review.user_id == current_user.id,
                Review.status == 'confirmed', Lesson.deleted_at.is_(None))
        .order_by(Lesson.lesson_date.asc())
        .all()
    )
    # 预置：取该生第一个班级的类型
    first_class = (
        Klass.query.join(Enrollment, Enrollment.class_id == Klass.id)
        .filter(Enrollment.student_id == student_id, Klass.user_id == current_user.id,
                Klass.deleted_at.is_(None))
        .first()
    )
    preset = ClassTypePreset.query.filter_by(code=first_class.type_code).first() if first_class else None

    red = Redactor(student.name, student.preferred_name)
    snippets = []
    for r in reviews:
        lesson = Lesson.query.get(r.lesson_id)
        snippets.append({
            "date": lesson.lesson_date.isoformat() if lesson and lesson.lesson_date else "某课次",
            "class_name": (Klass.query.get(r.class_id).name if r.class_id else ""),
            "content": red.redact(r.content or ""),
        })
    period = request.form.get("period_label", "本学期")
    messages = build_summary_messages(preset, red.redact(student.name), snippets, period)
    try:
        text = LLMClient().complete(messages, timeout=120)
        text = red.restore(text)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500

    summ = TermSummary(
        user_id=current_user.id, student_id=student_id,
        class_id=first_class.id if first_class else None,
        term_label=period, content=text,
        source_review_ids=[r.id for r in reviews],
        status='draft',
    )
    db.session.add(summ)
    db.session.commit()
    return jsonify({"ok": True, "content": text, "id": summ.id})


@students_bp.route("/<student_id>/summary/<summary_id>/save", methods=["POST"])
@login_required
def save_summary(student_id, summary_id):
    summ = TermSummary.query.filter_by(id=summary_id, user_id=current_user.id).first_or_404()
    summ.content = request.form.get("content", summ.content)
    db.session.commit()
    return jsonify({"ok": True})
