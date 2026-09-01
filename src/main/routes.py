"""主蓝图路由。"""
import os
from flask import Blueprint, redirect, url_for, render_template, request, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from extensions import db
from models.prep_job import PrepJob
from models.lesson import Review
from models.class_student import Klass, Student

bp = Blueprint('main', __name__)


@bp.route('/account/test-key', methods=['POST'])
@login_required
def account_test_key():
    """账号页 AI KEY 连通性测试：用表单填入的 key/base_url/model 发最小请求验证。

    用户没填某字段时回退到其已保存的配置，都没填回退平台默认（GLM-4-Flash）。
    """
    from ai.llm_client import LLMClient
    key = (request.form.get('ai_api_key') or '').strip() or (current_user.ai_api_key or '')
    base_url = (request.form.get('ai_base_url') or '').strip() or (current_user.ai_base_url or '')
    model = (request.form.get('ai_model') or '').strip() or (current_user.ai_model or '')
    client = LLMClient(
        api_key=key or None,
        base_url=base_url or None,
        model=model or None,
    )
    ok, msg = client.test_connection()
    return jsonify({'ok': ok, 'message': msg})


@bp.route('/')
def index():
    """网站大厅：课前备课与课后课评的统一入口，未登录也可访问。"""
    return render_template('index.html')


_PREP_RETENTION_DAYS = 7


@bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """系统 A 账号页：基本信息 + 修改昵称/密码 + 课前备课 AI 通道 + 生成记录 + 课评记录。"""
    from auth.providers import PasswordProvider

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
            flash('API KEY 已保存' if key else 'API KEY 已清空', 'success')
        elif action == 'profile':
            display_name = (request.form.get('display_name') or '').strip()
            if display_name:
                current_user.display_name = display_name
                db.session.commit()
                flash('昵称已更新', 'success')
        elif action == 'password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            if not PasswordProvider.check_password(current_user, current_password):
                flash('当前密码不正确', 'danger')
            elif new_password != confirm_password:
                flash('两次输入的新密码不一致', 'danger')
            elif len(new_password) < 6:
                flash('新密码至少 6 位', 'danger')
            else:
                current_user.password_hash = PasswordProvider.hash_password(new_password)
                db.session.commit()
                flash('密码已修改', 'success')
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

    # —— 课后课评记录（永久保存，按班级分组，每班最近 3 条）——
    review_rows = (
        Review.query.join(Klass, Review.class_id == Klass.id)
        .filter(Klass.user_id == current_user.id, Klass.deleted_at.is_(None))
        .limit(200)
        .all()
    )
    from collections import defaultdict
    grouped = defaultdict(list)
    for r in review_rows:
        klass = Klass.query.get(r.class_id)
        student = Student.query.get(r.student_id)
        if not klass or not student:
            continue
        ts = r.edited_at or r.sent_at or datetime.min
        grouped[r.class_id].append({
            'review_id': r.id,
            'class_id': r.class_id,
            'lesson_id': r.lesson_id,
            'class_name': klass.name,
            'student_name': student.name,
            'content': (r.content or '')[:160],
            'status': r.status,
            'created_at': ts,
        })
    reviews = []
    for items in grouped.values():
        items.sort(key=lambda x: x['created_at'], reverse=True)
        reviews.extend(items[:3])
    reviews.sort(key=lambda x: x['created_at'], reverse=True)

    return render_template(
        'account.html',
        user=current_user,
        prep_jobs=prep_jobs,
        prep_retention=_PREP_RETENTION_DAYS,
        reviews=reviews,
    )
