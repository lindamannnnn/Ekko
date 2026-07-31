"""主蓝图路由。"""
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

bp = Blueprint('main', __name__)


@bp.route('/')
@login_required
def index():
    return redirect(url_for('classes.index'))
