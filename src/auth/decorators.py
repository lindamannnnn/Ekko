"""后台守卫装饰器。"""
from functools import wraps

from flask import abort, redirect, url_for
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def _deco(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('admin_bp.admin_login'))
        if not getattr(current_user, 'is_superuser', False):
            abort(403)
        return f(*args, **kwargs)
    return _deco
