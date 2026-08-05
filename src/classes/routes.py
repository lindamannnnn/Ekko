"""班级路由实现（带蓝图装饰器）。"""
import os
import uuid
import copy
from datetime import datetime

from flask import (
    render_template, redirect, url_for, flash, request, jsonify,
    make_response,
)
from flask_login import login_required, current_user
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.utils import secure_filename
from extensions import db
from models.class_student import Klass, Student, Enrollment
from models.class_type_preset import ClassTypePreset
from models.lesson import Review
from security.upload_check import validate_upload, check_extracted_text

from . import classes_bp

# 课程上传相关
ALLOWED_COURSE_EXT = {".txt", ".pptx", ".docx", ".doc", ".pdf"}
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "uploads")


def _tour_next(req, cur):
    """引导流程：请求带 tour 参数时返回带下一步 step 的查询串，否则空串。"""
    if req.args.get('tour'):
        nxt = req.args.get('step', default=cur, type=int) + 1
        return f'?tour=1&step={nxt}'
    return ''


@classes_bp.route("/")
@login_required
def index():
    from sqlalchemy import text
    klasses = (
        Klass.query.filter_by(user_id=current_user.id, deleted_at=None)
        .order_by(Klass.created_at.desc())
        .all()
    )
    # 用原生 SQL 查每个班级的在读学生数（避免 ORM lazy loading 失效）
    stu_map = {}
    if klasses:
        cids = [str(k.id) for k in klasses]
        placeholders = ",".join([f"'{cid}'" for cid in cids])
        rows = db.session.execute(
            text(f"SELECT class_id, COUNT(*) AS cnt FROM enrollments "
                 f"WHERE class_id IN ({placeholders}) AND left_at IS NULL AND deleted_at IS NULL "
                 f"GROUP BY class_id")
        ).fetchall()
        stu_map = {r[0]: r[1] for r in rows}
    return render_template("classes/index.html", klasses=klasses, stu_map=stu_map)


@classes_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    presets = ClassTypePreset.query.all()
    if request.method == "GET":
        return render_template("classes/new.html", presets=presets)
    name = request.form.get("name", "").strip()
    type_code = request.form.get("type_code", "").strip()
    if not name or not type_code:
        flash("班级名称与类型均不能为空", "error")
        return render_template("classes/new.html", presets=presets)
    if ClassTypePreset.query.filter_by(code=type_code).first() is None:
        flash("班级类型无效，请从列表中选择", "error")
        return render_template("classes/new.html", presets=presets)
    k = Klass(user_id=current_user.id, name=name, type_code=type_code)
    db.session.add(k)
    db.session.commit()
    flash(f"班级【{name}】已创建", "success")
    return redirect(url_for("classes.detail", class_id=k.id) + _tour_next(request, 1))


@classes_bp.route("/<class_id>/detail")
@login_required
def detail(class_id):
    k = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    students = (
        Student.query.join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.class_id == class_id, Student.deleted_at.is_(None))
        .all()
    )
    # 本班全部课次（用于顶部课程选择器）
    from models.lesson import Lesson
    lessons = (
        Lesson.query.filter_by(class_id=class_id, deleted_at=None)
        .order_by(Lesson.lesson_date.desc().nullslast(), Lesson.created_at.desc())
        .all()
    )
    # 默认选中最新一节课次
    selected_lesson_id = request.args.get('lesson_id', type=str)
    if selected_lesson_id:
        from uuid import UUID
        try:
            selected_lesson_id = str(UUID(selected_lesson_id))
        except ValueError:
            selected_lesson_id = None
    if not selected_lesson_id and lessons:
        selected_lesson_id = lessons[0].id

    resp = make_response(render_template("classes/detail.html", klass=k, students=students,
                           lessons=lessons, selected_lesson_id=selected_lesson_id))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@classes_bp.route("/<class_id>/students/add", methods=["GET", "POST"])
@login_required
def add_students(class_id):
    k = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    if request.method == "GET":
        return render_template("classes/add_students.html", klass=k)

    # 收集所有 name_N / gender_N / nick_N 对
    rows = []
    for key in request.form:
        if key.startswith("name_") and request.form[key].strip():
            idx = key.split("_", 1)[1]
            nm = request.form[key].strip()
            gender = request.form.get("gender_" + idx, "") or None
            nick = request.form.get("nick_" + idx, "").strip()
            rows.append((nm, gender, nick))

    if not rows:
        flash("请至少填写一个学生姓名", "warning")
        return redirect(url_for("classes.add_students", class_id=class_id))

    added, skipped = 0, []
    for nm, gender, nick in rows:
        s = Student.query.filter_by(
            user_id=current_user.id, name=nm, deleted_at=None).first()
        if s is None:
            s = Student(user_id=current_user.id, name=nm, gender=gender, preferred_name=nick or None)
            db.session.add(s)
            db.session.flush()
        else:
            if gender and s.gender is None:
                s.gender = gender
            if nick:
                s.preferred_name = nick
        enr = Enrollment.query.filter_by(
            student_id=s.id, class_id=class_id, deleted_at=None).first()
        if enr is None:
            enr = Enrollment(student_id=s.id, class_id=class_id, user_id=current_user.id)
            db.session.add(enr)
            added += 1
        else:
            skipped.append(nm)

    db.session.commit()
    msg_parts = [f"已添加 {added} 名学生"]
    if skipped:
        msg_parts.append(f"（{len(skipped)} 人已存在：{', '.join(skipped)}）")
    flash("".join(msg_parts), "success" if not skipped else "warning")
    return redirect(url_for("classes.detail", class_id=class_id))


@classes_bp.route("/<class_id>/archive", methods=["POST"])
@login_required
def archive(class_id):
    k = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    k.archived_at = datetime.utcnow()
    db.session.commit()
    flash("班级已归档", "success")
    return redirect(url_for("classes.index"))


@classes_bp.route("/<class_id>/delete", methods=["POST"])
@login_required
def delete(class_id):
    k = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    from models.lesson import Lesson, Courseware, Review, TermSummary, StyleSample
    # 级联清理该班级下的全部关联数据。学生为跨班共享资源，仅解除报名、不删学生本身。
    Review.query.filter_by(class_id=class_id, user_id=current_user.id).delete()
    TermSummary.query.filter_by(class_id=class_id, user_id=current_user.id).delete()
    StyleSample.query.filter_by(class_id=class_id, user_id=current_user.id).delete()
    Lesson.query.filter_by(class_id=class_id, user_id=current_user.id).delete()
    Courseware.query.filter_by(class_id=class_id, user_id=current_user.id).delete()
    Enrollment.query.filter_by(class_id=class_id, user_id=current_user.id).delete()
    db.session.delete(k)
    db.session.commit()
    flash(f"班级【{k.name}】已删除", "success")
    return redirect(url_for("classes.index"))


def _text_to_markdown(raw_text: str, filename: str = "") -> str:
    """将抽取的纯文本转为基本 Markdown 格式。"""
    if not raw_text or not raw_text.strip():
        return ""
    lines = raw_text.split("\n")
    md_parts = []
    # 文件名作为标题（如果有）
    if filename:
        md_parts.append(f"# {filename}\n")
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            md_parts.append("")
            continue
        # 短行且看起来像标题（< 50 字符，不以列表符号开头）
        if len(stripped) < 50 and not stripped.startswith(("-", "*", " ", "·", "•", "\t", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
            md_parts.append(f"## {stripped}")
        else:
            md_parts.append(stripped)
    return "\n".join(md_parts)


@classes_bp.route("/<class_id>/upload_course", methods=["POST", "GET"])
@login_required
def upload_course(class_id):
    """课程内容上传/粘贴/读取接口（班级维度，全班共享）。

    POST：接收文件或纯文本，返回 Markdown 并保存到 Klass.extra_data._course_content
    GET ：返回该班级已保存的课程内容
    """
    klass = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    extra = klass.extra_data or {}

    # GET：返回已保存的课程内容
    if request.method == "GET":
        saved = extra.get("_course_content")
        return jsonify({"ok": True, "content": saved})

    # 模式 A：文本粘贴
    content_type = request.content_type or ""
    if "application/json" in content_type:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "内容不能为空"}), 400
        md = _text_to_markdown(text)
        # 保存到班级级别（修复 dict 引用 bug：必须复制出新 dict 再赋值 + flag_modified）
        new_extra = dict(klass.extra_data or {})
        new_extra["_course_content"] = md
        klass.extra_data = new_extra
        flag_modified(klass, "extra_data")
        db.session.commit()
        return jsonify({"ok": True, "markdown": md, "filename": "", "source": "paste"})

    # 模式 B：文件上传
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400

    try:
        ext = validate_upload(file)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    # 保存临时文件并解析
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fname = uuid.uuid4().hex + ext
    dest = os.path.join(UPLOAD_DIR, fname)
    file.save(dest)

    try:
        from parsers.core import extract_text
        raw = extract_text(dest)
        check_extracted_text(raw)
        if not raw or not raw.strip():
            return jsonify({"ok": False, "error": "无法从文件中提取文字内容（可能是扫描件图片 PDF）"}), 400

        display_name = secure_filename(file.filename)
        md = _text_to_markdown(raw, display_name)

        # 保存到班级级别（修复 dict 引用 bug）
        new_extra = dict(klass.extra_data or {})
        new_extra["_course_content"] = md
        klass.extra_data = new_extra
        flag_modified(klass, "extra_data")
        db.session.commit()

        # 清理临时文件
        try:
            os.remove(dest)
        except OSError:
            pass

        return jsonify({
            "ok": True,
            "markdown": md,
            "filename": display_name,
            "source": f"file:{ext}",
            "raw_length": len(raw),
        })
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"解析失败：{e}"}), 500


@classes_bp.route("/<class_id>/create_lesson_from_course", methods=["POST"])
@login_required
def create_lesson_from_course(class_id):
    """根据上传/粘贴的课程内容直接创建课次（跳过原 new 页面）。"""
    klass = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    course_md = (data.get("course_md") or "").strip()

    if not title:
        return jsonify({"ok": False, "error": "课次标题不能为空"}), 400

    from models.lesson import Lesson, Courseware
    from parsers.core import extract_objectives

    lesson = Lesson(
        user_id=current_user.id,
        class_id=class_id,
        title=title,
        common_notes=course_md,  # 把 MD 内容存到 common_notes
    )
    db.session.add(lesson)
    db.session.flush()

    # 如果有课程文本，也创建 Courseware 记录
    if course_md:
        cw = Courseware(
            user_id=current_user.id,
            class_id=class_id,
            source_filename=f"{title}.md",
            extracted_text=course_md,
        )
        db.session.add(cw)
        db.session.flush()
        lesson.courseware_id = cw.id
        # 自动抽取知识点
        objs = extract_objectives(course_md)
        if objs:
            lesson.objectives = objs

    db.session.commit()
    return jsonify({
        "ok": True,
        "lesson_id": lesson.id,
        "redirect": url_for("classes.detail", class_id=class_id) + f"?lesson_id={lesson.id}",
    })


@classes_bp.route("/<class_id>/excellent_review", methods=["GET", "POST", "DELETE"])
@login_required
def excellent_review(class_id):
    """优秀历史课评的存取/删除（班级维度，存入 Klass.extra_data，全班共享）。"""
    klass = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    extra = klass.extra_data or {}

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"ok": False, "error": "内容不能为空"}), 400
        # 可选：传入 lesson_id 用于统计当前课次的草稿数（前端"一键重生成"用）
        lesson_id = data.get("lesson_id")
        # 关键修复：SQLAlchemy 的 JSON 字段在 dict in-place 变更时不会自动检测为 dirty。
        # 直接拿原 dict 引用改 + 重新赋同一引用 = commit 不会写库（用户看到 200 但 DB 不动）。
        # 修复：用 copy() 强制产生新对象，再赋值给 ORM 字段，SQLAlchemy 才会写。
        # 同时显式 flag_modified 双保险。
        new_extra = dict(klass.extra_data or {})
        new_extra["_excellent_review"] = content
        klass.extra_data = new_extra
        flag_modified(klass, "extra_data")
        db.session.commit()
        # 统计当前 lesson 的草稿 review 数（仅属于本班+当前用户）
        draft_count = 0
        if lesson_id:
            draft_count = Review.query.filter_by(
                class_id=class_id, lesson_id=lesson_id, user_id=current_user.id,
                status='draft',
            ).filter(Review.deleted_at.is_(None)).count()
        return jsonify({"ok": True, "draft_count": draft_count})

    elif request.method == "DELETE":
        # 同样修：dict 引用问题
        new_extra = dict(klass.extra_data or {})
        new_extra.pop("_excellent_review", None)
        klass.extra_data = new_extra if new_extra else None
        flag_modified(klass, "extra_data")
        db.session.commit()
        return jsonify({"ok": True})

    else:  # GET
        content = (klass.extra_data or {}).get("_excellent_review")
        return jsonify({"ok": True, "content": content})
