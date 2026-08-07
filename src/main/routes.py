"""主蓝图路由。"""
from flask import Blueprint, redirect, url_for
from flask_login import login_required

bp = Blueprint('main', __name__)


@bp.route('/')
@login_required
def index():
    # 登录后第一页 = 班级列表（用户要求的「大厅」实际就是展示班级的页面）
    return redirect(url_for('classes.index'))
