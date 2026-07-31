"""学生蓝图。"""
from flask import Blueprint

students_bp = Blueprint("students", __name__, url_prefix="/students")

from . import routes  # noqa: E402,F401
