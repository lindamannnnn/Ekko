"""存档导出（Excel / PDF）+ 首页未写提醒。"""
from io import BytesIO

from flask import Blueprint, render_template, send_file, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.class_student import Klass, Student, Enrollment
from models.lesson import Lesson, Review

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/export-xlsx/<class_id>", methods=["GET"])
@login_required
def export_xlsx(class_id):
    klass = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    students = (
        Student.query.join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.class_id == class_id, Enrollment.deleted_at.is_(None),
                Student.deleted_at.is_(None))
        .all()
    )
    reviews = (
        Review.query.filter_by(class_id=class_id, user_id=current_user.id)
        .order_by(Review.student_id)
        .all()
    )
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = klass.name
    ws.append(["学生", "课次", "课评状态", "课评内容"])
    rev_map = {r.student_id: r for r in reviews}
    for s in students:
        r = rev_map.get(s.id)
        ws.append([s.name, "", r.status if r else "pending",
                   (r.content or "") if r else ""])
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, download_name=f"{klass.name}-课评.xlsx", as_attachment=True)


@reports_bp.route("/export-pdf/<class_id>", methods=["GET"])
@login_required
def export_pdf(class_id):
    klass = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    students = (
        Student.query.join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.class_id == class_id, Enrollment.deleted_at.is_(None),
                Student.deleted_at.is_(None))
        .all()
    )
    reviews = (
        Review.query.filter_by(class_id=class_id, user_id=current_user.id).all()
    )
    rev_map = {r.student_id: r for r in reviews}
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    flow = [Paragraph(f"<b>{klass.name}</b> 课评存档", styles['Title'])]
    for s in students:
        r = rev_map.get(s.id)
        flow.append(Paragraph(f"{s.name}：{(r.content or '（待生成）')[:200]}", styles['Normal']))
        flow.append(Spacer(1, 6))
    doc.build(flow)
    buf.seek(0)
    return send_file(buf, download_name=f"{klass.name}-课评.pdf", as_attachment=True)


@reports_bp.route("/reminder")
@login_required
def reminder():
    """首页片段：本周还有几个班完全没写课评。"""
    total = Klass.query.filter_by(user_id=current_user.id, deleted_at=None).count()
    written = (
        Klass.query.join(Enrollment, Enrollment.class_id == Klass.id)
        .filter(Klass.user_id == current_user.id, Klass.deleted_at.is_(None))
        .intersect(
            Klass.query.filter_by(user_id=current_user.id)
            .join(Review, Review.class_id == Klass.id)
            .filter(Review.user_id == current_user.id)
        )
        if False else None
    )
    # 简化：统计「有至少一份 confirmed/draft 课评」的班级数
    from sqlalchemy import func
    written_ids = [
        k.id for k in Klass.query.filter_by(user_id=current_user.id, deleted_at=None).all()
        if Review.query.filter_by(class_id=k.id, user_id=current_user.id)
        .filter(Review.status.in_(['confirmed', 'draft'])).first() is not None
    ]
    remaining = total - len(written_ids)
    return jsonify({"total": total, "written": len(written_ids), "remaining": remaining})
