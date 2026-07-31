"""图片模板（4 套：work / skill / academic / general）。

按机构类型分组渲染，共用 CSS 变量；html2canvas（UMD）前端导出 750px 长图 PNG。
"""
from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.lesson import Review, Lesson
from models.class_student import Klass
from models.class_type_preset import ClassTypePreset

from flask import Blueprint
card_bp = Blueprint("cards", __name__)


@card_bp.route("/preview/<review_id>", methods=["GET", "POST"])
@login_required
def preview(review_id):
    review = Review.query.filter_by(id=review_id, user_id=current_user.id).first_or_404()
    lesson = Lesson.query.get(review.lesson_id)
    klass = Klass.query.get(review.class_id)
    preset = ClassTypePreset.query.filter_by(code=klass.type_code).first() if klass else None
    if request.method == "POST":
        return jsonify({"ok": True})
    return render_template("cards/preview.html", review=review, lesson=lesson, klass=klass, preset=preset)
