"""主蓝图路由。"""
import os
from flask import Blueprint, redirect, url_for, render_template, request, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from extensions import db
from models.prep_job import PrepJob
from models.lesson import Review
from models.class_student import Klass, Student

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """网站大厅：课前备课与课后课评的统一入口，未登录也可访问。"""
    return render_template('index.html')


_PREP_RETENTION_DAYS = 7


@bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """系统 A 账号页：基本信息 + 课前备课 AI 通道 + 生成记录(7天) + 课评记录(永久)。"""
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'prep_key':
            key = (request.form.get('ai_api_key') or '').strip()
            base_url = (request.form.get('ai_base_url') or '').strip()
            model = (request.form.get('ai_model') or '').strip()
            if key:
                current_user.ai_api_key = key
            else:
                current_user.ai_api_key = None
            current_user.ai_base_url = base_url or None
            current_user.ai_model = model or None
            db.session.commit()
            flash('课前备课 API KEY 已保存' if key else '课前备课 API KEY 已清空', 'success')
        return redirect(url_for('main.account'))

    # —— 课前备课生成记录（文件保留 7 天，数据库记录永久）——
    prep_jobs = PrepJob.query.filter_by(user_id=current_user.id) \
        .order_by(PrepJob.created_at.desc()).limit(50).all()
    cutoff = datetime.utcnow() - timedelta(days=_PREP_RETENTION_DAYS)
    for j in prep_jobs:
        j.expired = j.created_at < cutoff
        j.has_files = bool(
            (j.courseware_path and os.path.isfile(j.courseware_path)) or
            (j.lesson_path and os.path.isfile(j.lesson_path))
        )

    # —— 课后课评记录（永久保存，按教师名下的班级关联）——
    review_rows = (
        Review.query.join(Klass, Review.class_id == Klass.id)
        .filter(Klass.user_id == current_user.id, Klass.deleted_at.is_(None))
        .order_by(Review.id.desc()).limit(50).all()
    )
    reviews = []
    for r in review_rows:
        klass = Klass.query.get(r.class_id)
        student = Student.query.get(r.student_id)
        reviews.append({
            'class_name': klass.name if klass else '—',
            'student_name': student.name if student else '—',
            'content': (r.content or '')[:120],
            'status': r.status,
            'created_at': r.edited_at or r.sent_at,
        })

    return render_template(
        'account.html',
        user=current_user,
        prep_jobs=prep_jobs,
        prep_retention=_PREP_RETENTION_DAYS,
        reviews=reviews,
    )
