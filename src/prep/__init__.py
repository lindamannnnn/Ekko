"""课前备课 Blueprint（prep）。

把原本独立运行在 content-upload/app.py 的课前备课功能挂到 class-review-system 下，
统一账号、session、后台与导航。
"""
import os
import sys

from flask import Blueprint

PREP_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENT_UPLOAD_DIR = os.path.normpath(
    os.path.join(PREP_DIR, '..', '..', '..', 'lesson-courseware', 'content-upload')
)
if CONTENT_UPLOAD_DIR not in sys.path:
    sys.path.insert(0, CONTENT_UPLOAD_DIR)

prep_bp = Blueprint(
    'prep',
    __name__,
    template_folder='templates/prep',
    static_folder='static/prep',
    url_prefix='/prep',
)

from . import views  # noqa: E402,F401
