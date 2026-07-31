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

from . import lessons_bp

ALLOWED_EXT = {".txt", ".pptx", ".docx", ".doc", ".pdf"}
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "uploads")


def _save_courseware(class_id, file_storage):
    """保存上传文件 -> Courseware 记录，返回 (Courseware, extracted_text, objectives)。"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"不支持的文件类型：{ext}（支持 txt/pptx/docx/pdf）")
    fname = uuid.uuid4().hex + ext
    dest = os.path.join(UPLOAD_DIR, fname)
    file_storage.save(dest)
    text = extract_text(dest)
    objs = extract_objectives(text)
    cw = Courseware(
        user_id=current_user.id, class_id=class_id,
        source_filename=secure_filename(file_storage.filename or "file"),
        stored_path=dest, extracted_text=text,
    )
    db.session.add(cw)
    db.session.flush()
    return cw, objs


@lessons_bp.route("/<class_id>/new", methods=["GET", "POST"])
@login_required
def new(class_id):
    klass = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    if request.method == "GET":
        return render_template("lessons/new.html", klass=klass)
    title = request.form.get("title", "").strip()
    lesson_date = request.form.get("lesson_date", "")
    common_notes = request.form.get("common_notes", "")
    objectives_raw = request.form.get("objectives", "")
    cw_text = request.form.get("courseware_text", "")
    if not title:
        flash("课次标题不能为空", "error")
        return render_template("lessons/new.html", klass=klass)
    ld = None
    if lesson_date:
        try:
            ld = datetime.strptime(lesson_date, "%Y-%m-%d").date()
        except ValueError:
            ld = None
    lesson = Lesson(
        user_id=current_user.id,
        class_id=class_id,
        title=title,
        lesson_date=ld,
        common_notes=common_notes or None,
        objectives=[a.strip() for a in [objectives_raw] if a] or None,
    )
    db.session.add(lesson)
    db.session.flush()
    # 课件：优先文件上传，其次粘贴文本
    file = request.files.get("courseware_file")
    if file and file.filename:
        try:
            cw, objs = _save_courseware(class_id, file)
            lesson.courseware_id = cw.id
            # 自动抽取知识点（若老师没手填则采用）
            if not lesson.objectives and objs:
                lesson.objectives = objs
        except ValueError as e:
            flash(str(e), "error")
    elif cw_text.strip():
        cw = Courseware(user_id=current_user.id, class_id=class_id, extracted_text=cw_text)
        db.session.add(cw)
        db.session.flush()
        lesson.courseware_id = cw.id
    db.session.commit()
    flash(f"课次【{title}】已创建", "success")
    return redirect(url_for("classes.detail", class_id=class_id))


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
