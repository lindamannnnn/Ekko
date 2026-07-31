"""班级蓝图：列表 / 新建 / 详情 / 学生管理 / 归档。"""
from flask import Blueprint

classes_bp = Blueprint("classes", __name__, url_prefix="/classes")

from . import routes  # noqa: F401,E402
