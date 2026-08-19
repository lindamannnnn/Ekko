"""主蓝图路由。"""
from flask import Blueprint, redirect, url_for, render_template, request, flash
from flask_login import login_required, current_user

from extensions import db

bp = Blueprint('main', __name__)


@bp.route('/')
@login_required
def index():
    # 登录后第一页 = 班级列表（用户要求的「大厅」实际就是展示班级的页面）
    return redirect(url_for('classes.index'))


@bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """系统 A 账号页：展示用户信息，并允许设置课前备课 AI 通道。"""
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
    return render_template('account.html', user=current_user)
