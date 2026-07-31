"""班级路由实现（带蓝图装饰器）。"""
from datetime import datetime

from flask import (
    render_template, redirect, url_for, flash, request,
)
from flask_login import login_required, current_user
from extensions import db
from models.class_student import Klass, Student, Enrollment
from models.class_type_preset import ClassTypePreset

from . import classes_bp


@classes_bp.route("/")
@login_required
def index():
    klasses = (
        Klass.query.filter_by(user_id=current_user.id, deleted_at=None)
        .order_by(Klass.created_at.desc())
        .all()
    )
    return render_template("classes/index.html", klasses=klasses)


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
    k = Klass(user_id=current_user.id, name=name, type_code=type_code)
    db.session.add(k)
    db.session.commit()
    flash(f"班级【{name}】已创建", "success")
    return redirect(url_for("classes.detail", class_id=k.id))


@classes_bp.route("/<class_id>/detail")
@login_required
def detail(class_id):
    k = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    students = (
        Student.query.join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.class_id == class_id, Student.deleted_at.is_(None))
        .all()
    )
    return render_template("classes/detail.html", klass=k, students=students)


@classes_bp.route("/<class_id>/students/add", methods=["GET", "POST"])
@login_required
def add_students(class_id):
    k = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    if request.method == "GET":
        return render_template("classes/add_students.html", klass=k)
    raw = request.form.get("names", "")
    names = [n.strip() for n in raw.replace(",", "\n").split("\n") if n.strip()]
    added = 0
    for nm in names:
        s = Student(user_id=current_user.id, name=nm)
        db.session.add(s)
        db.session.flush()
        enr = Enrollment(student_id=s.id, class_id=class_id)
        db.session.add(enr)
        added += 1
    db.session.commit()
    flash(f"已添加 {added} 名学生", "success")
    return redirect(url_for("classes.detail", class_id=class_id))


@classes_bp.route("/<class_id>/archive", methods=["POST"])
@login_required
def archive(class_id):
    k = Klass.query.filter_by(id=class_id, user_id=current_user.id, deleted_at=None).first_or_404()
    k.archived_at = datetime.utcnow()
    db.session.commit()
    flash("班级已归档", "success")
    return redirect(url_for("classes.index"))
