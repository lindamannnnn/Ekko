"""课次路由实现（带蓝图装饰器）。"""
import os
import uuid
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from models.class_student import Klass
from models.lesson import Lesson, Courseware
from parsers.core import extract_text, extract_objectives
from security.upload_check import validate_upload, check_extracted_text

from . import lessons_bp


def _tour_next(req, cur):
    if req.args.get('tour'):
        nxt = req.args.get('step', default=cur, type=int) + 1
        return f'?tour=1&step={nxt}'
    return ''

ALLOWED_EXT = {".txt", ".pptx", ".docx", ".doc", ".pdf"}
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "uploads")


def _save_courseware(class_id, file_storage):
    """保存上传文件 -> Courseware 记录，返回 (Courseware, extracted_text, objectives)。"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    # 扩展名 + 文件头魔数 + 大小校验（防改名绕过 / 超大文件）；校验后指针已回到开头
    ext = validate_upload(file_storage)
    fname = uuid.uuid4().hex + ext
    dest = os.path.join(UPLOAD_DIR, fname)
    file_storage.save(dest)
    text = extract_text(dest)
    check_extracted_text(text)  # 防解析炸弹：抽取文本过长直接拒绝
    objs = extract_objectives(text)
    cw = Courseware(
        user_id=current_user.id, class_id=class_id,
        source_filename=secure_filename(file_storage.filename or "file"),
        stored_path=dest, extracted_text=text,
        created_at=datetime.utcnow(), uploaded_by=current_user.email,
    )
    db.session.add(cw)
    db.session.flush()
    return cw, objs




@lessons_bp.route("/<lesson_id>/detail")
@login_required
def detail(lesson_id):
    lesson = Lesson.query.filter_by(id=lesson_id, user_id=current_user.id).first_or_404()
    return render_template("lessons/detail.html", lesson=lesson)


@lessons_bp.route("/<lesson_id>/courseware", methods=["POST"])
@login_required
def upload_courseware(lesson_id):
    """课后补传/重传课件：解析文本 + 抽取知识点，更新到该课次。"""
    lesson = Lesson.query.filter_by(id=lesson_id, user_id=current_user.id).first_or_404()
    file = request.files.get("courseware_file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    try:
        cw, objs = _save_courseware(lesson.class_id, file)
        lesson.courseware_id = cw.id
        if objs:
            lesson.objectives = objs
        db.session.commit()
        return jsonify({"ok": True, "objectives": objs, "text_len": len(cw.extracted_text or ""),
                        "empty": (cw.extracted_text or "").strip() == ""})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
