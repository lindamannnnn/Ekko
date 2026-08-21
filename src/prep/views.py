# -*- coding: utf-8 -*-
"""prep/views.py —— 课前备课 Blueprint 视图。

原 content-upload/app.py 的课前备课功能，挂载到 class-review-system 后：
- 复用系统 A 的 User / PrepJob 模型与 Flask-Login 登录态
- 删除独立账号体系
- 生成文件存到 class-review-system/uploads/prep/
"""
import os
import re
import sys
import uuid
import json
import hashlib
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    request, render_template, redirect, url_for, flash,
    send_file, jsonify, current_app,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import User, PrepJob
from . import prep_bp

from .pipeline.ingest import ingest_file, ingest_text
from .pipeline.segment import segment
from .pipeline.moderate import moderate
from .render import render, list_styles, STYLE_IDS
from .kb_courses import list_kb_courses, get_entry, kb_to_slides


# ---------- 配置 ----------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# prep 位于 class-review-system/src/prep/
PREP_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..', 'uploads', 'prep'))
os.makedirs(PREP_ROOT, exist_ok=True)

ALLOWED_EXT = {".txt", ".md", ".markdown", ".csv", ".html", ".htm",
               ".docx", ".pptx", ".pdf"}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB
MAX_TEXT = 20000
RETENTION_DAYS = 7

# 系统 B orchestrator 路径（B 归档到 systems/lesson-courseware/ 后优先使用归档路径）
_ORCHESTRATOR_CANDIDATES = [
    os.path.normpath(os.path.join(BASE_DIR, '..', '..', 'systems', 'lesson-courseware', 'orchestrator.py')),
    os.path.normpath(os.path.join(BASE_DIR, '..', '..', '..', 'lesson-courseware', 'orchestrator.py')),
    os.path.normpath(os.path.join(BASE_DIR, '..', '..', 'lesson-courseware', 'orchestrator.py')),
]
ORCHESTRATOR_PATH = None
for _c in _ORCHESTRATOR_CANDIDATES:
    if os.path.isfile(_c):
        ORCHESTRATOR_PATH = _c
        break
if ORCHESTRATOR_PATH is None:
    ORCHESTRATOR_PATH = _ORCHESTRATOR_CANDIDATES[0]

SUBJECTS = ["语文", "数学", "英语"]
GRADES = [f"{g}{s}" for g in range(1, 10) for s in ("年级上", "年级下")]

DEMO_DIR = os.path.join(PREP_ROOT, "_style_demos")
os.makedirs(DEMO_DIR, exist_ok=True)


# ---------- 工具函数 ----------

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def _safe_filename(name: str) -> str:
    name = os.path.basename(name)
    name = re.sub(r"[^\w\u4e00-\u9fa5.\-]", "_", name)
    return name or "unnamed"


def _magic_ok(data: bytes, ext: str) -> bool:
    if ext in (".docx", ".pptx"):
        return data[:4] == b"PK\x03\x04"
    if ext == ".pdf":
        return data[:4] == b"%PDF"
    return True


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _cleanup_expired_files():
    """删除超过 RETENTION_DAYS 的成功任务生成文件，保留数据库记录。"""
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    rows = PrepJob.query.filter(
        PrepJob.status == "success",
        PrepJob.created_at < cutoff,
    ).all()
    for job in rows:
        for path in (job.courseware_path, job.lesson_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        job_dir = os.path.join(PREP_ROOT, job.id)
        if os.path.isdir(job_dir):
            try:
                if not os.listdir(job_dir):
                    os.rmdir(job_dir)
            except Exception:
                pass
    db.session.commit()


def _build_demo_decks():
    """预生成每个风格的 demo 单文件 HTML。"""
    demo_slides = [
        {"title": "风格预览", "bullets": ["这是该风格的封面页", "可以看到配色与字体气质"]},
        {"title": "内容页示例", "bullets": ["要点一：清晰的信息层级", "要点二：统一的视觉语言", "要点三：适配课堂投影"]},
        {"title": "结束页", "bullets": ["谢谢观看", "点击卡片可放大预览"]},
    ]
    for sid in STYLE_IDS:
        path = os.path.join(DEMO_DIR, f"{sid}.html")
        if os.path.exists(path):
            continue
        html = render(demo_slides, sid, title=f"{sid} 风格预览")
        hide_scroll = "<style>html,body,.slide{overflow:hidden!important}*::-webkit-scrollbar{display:none!important}.slide{overflow-y:hidden!important}</style>"
        html = html.replace("</head>", hide_scroll + "</head>", 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)


_build_demo_decks()


# ---------- 学科生成后台线程 ----------

def _run_subject_job(job_id: str, user_id: str, app):
    """后台线程：调用系统 B orchestrator 生成教案 + 课件。"""
    with app.app_context():
        job = PrepJob.query.get(job_id)
        user = User.query.get(user_id)
        if not job or not user:
            return

        job_dir = os.path.join(PREP_ROOT, job_id)
        lesson_path = os.path.join(job_dir, "lesson.html")
        courseware_path = os.path.join(job_dir, "index.html")
        os.makedirs(job_dir, exist_ok=True)

        env = dict(os.environ)
        # 优先使用用户自定义 key
        if user.ai_api_key:
            env["AI_API_KEY"] = user.ai_api_key
        if user.ai_base_url:
            env["AI_BASE_URL"] = user.ai_base_url
        if user.ai_model:
            env["AI_MODEL"] = user.ai_model

        try:
            cmd = [
                sys.executable,
                ORCHESTRATOR_PATH,
                "--subject", job.subject or "",
                "--grade", job.grade or "",
                "--topic", job.topic or "",
                "--duration", str(job.duration or 40),
                "--out", job_dir,
            ]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:500] or "生成失败")

            lesson = None
            course = None
            for line in (result.stdout or "").splitlines():
                if line.startswith("教案 HTML:"):
                    lesson = line.split(":", 1)[1].strip()
                elif line.startswith("课件 HTML:"):
                    course = line.split(":", 1)[1].strip()

            out_files = os.listdir(job_dir)
            if not lesson:
                lesson = next((os.path.join(job_dir, f) for f in out_files if f.startswith("lesson_") or f == "lesson.html"), None)
            if not course:
                course = next((os.path.join(job_dir, f) for f in out_files if f.startswith("course_") or f == "index.html"), None)

            # 用所选风格重新渲染
            style = job.style or STYLE_IDS[0]
            if style not in STYLE_IDS:
                style = STYLE_IDS[0]
            try:
                lesson_text = ""
                if lesson and os.path.exists(lesson):
                    with open(lesson, "r", encoding="utf-8") as f:
                        raw_html = f.read()
                    lesson_text = re.sub(r"<[^>]+>", " ", raw_html)
                    lesson_text = re.sub(r"\s+", "\n", lesson_text).strip()
                if lesson_text:
                    slides = segment(lesson_text, env={}, allow_llm=False)
                    if slides:
                        title = job.title or job.topic or "课件"
                        courseware_html = render(slides, style, title=title)
                        with open(courseware_path, "w", encoding="utf-8") as f:
                            f.write(courseware_html)
                        course = courseware_path
            except Exception:
                pass

            if not course and os.path.exists(courseware_path):
                course = courseware_path

            job.status = "success"
            job.lesson_path = lesson
            job.courseware_path = course
        except Exception as e:
            job.status = "failed"
            job.error_msg = str(e)[:500]
        finally:
            job.updated_at = datetime.utcnow()
            db.session.commit()


# ---------- 内容生成后台线程 ----------

def _run_content_job(job_id: str, user_id: str, app):
    """后台线程：把上传/粘贴内容切页渲染成课件。"""
    with app.app_context():
        job = PrepJob.query.get(job_id)
        user = User.query.get(user_id)
        if not job:
            return
        try:
            env = dict(os.environ)
            # 优先使用用户自定义 key
            if user and user.ai_api_key:
                env["AI_API_KEY"] = user.ai_api_key
            if user and user.ai_base_url:
                env["AI_BASE_URL"] = user.ai_base_url
            if user and user.ai_model:
                env["AI_MODEL"] = user.ai_model
            slides = segment(job.original_text or "", env=env)
            if not slides:
                raise RuntimeError("切页失败：未能将内容拆分为幻灯片")
            title = job.title or slides[0].get("title") or "我的课件"
            html_out = render(slides, job.style or STYLE_IDS[0], title=title)
            out_path = os.path.join(PREP_ROOT, job_id, "index.html")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_out)
            job.status = "success"
            job.courseware_path = out_path
        except Exception as e:
            job.status = "failed"
            job.error_msg = str(e)[:500]
        finally:
            job.updated_at = datetime.utcnow()
            db.session.commit()


# ---------- 路由 ----------


@prep_bp.route("/")
def index():
    # 访问首页时惰性清理超过保留期的生成文件（保留数据库记录）
    try:
        _cleanup_expired_files()
    except Exception:
        pass
    return render_template("prep/index.html", styles=list_styles(), user=current_user)


@prep_bp.route("/courses")
@login_required
def courses():
    tree = list_kb_courses()
    filtered = {k: v for k, v in tree.items() if k in SUBJECTS}
    return filtered


@prep_bp.route("/api/user/key", methods=["POST"])
@login_required
def api_user_key():
    user = current_user
    key = (request.form.get("ai_api_key") or "").strip()
    base_url = (request.form.get("ai_base_url") or "").strip()
    model = (request.form.get("ai_model") or "").strip()
    action = request.form.get("action")

    if action == "clear" or not key:
        user.ai_api_key = None
        user.ai_base_url = base_url or None
        user.ai_model = model or None
        flash("API KEY 已清空")
    else:
        user.ai_api_key = key
        user.ai_base_url = base_url or None
        user.ai_model = model or None
        flash("API KEY 已保存")

    db.session.commit()
    return redirect(url_for("prep.subject") + "#model-info")


@prep_bp.route("/subject", methods=["GET", "POST"])
@login_required
def subject():
    user = current_user
    error = None
    if request.method == "POST":
        subject_name = (request.form.get("subject") or "").strip()
        grade = (request.form.get("grade") or "").strip()
        topic = (request.form.get("topic") or "").strip()
        duration = request.form.get("duration") or "40"
        style = request.form.get("style") or STYLE_IDS[0]
        title = (request.form.get("title") or "").strip()
        if not (subject_name and grade and topic):
            error = "请选择学科、年级和课题"
        else:
            job = PrepJob(
                user_id=user.id,
                mode="subject",
                status="running",
                subject=subject_name,
                grade=grade,
                topic=topic,
                duration=int(duration),
                style=style,
                title=title or topic,
            )
            db.session.add(job)
            db.session.commit()
            app = current_app._get_current_object()
            t = threading.Thread(target=_run_subject_job, args=(job.id, user.id, app))
            t.daemon = True
            t.start()
            return redirect(url_for("prep.generating", job=job.id))
    return render_template(
        "prep/subject.html",
        styles=list_styles(),
        subjects=SUBJECTS,
        user=user,
        error=error,
        mask_key=_mask_key(user.ai_api_key or ""),
    )


@prep_bp.route("/content", methods=["GET", "POST"])
@login_required
def content():
    user = current_user
    mask_key = _mask_key(user.ai_api_key or "")
    if request.method == "POST":
        f = request.files.get("file")
        text = (request.form.get("text") or "").strip()
        use_api_mod = request.form.get("use_api_mod") == "on"
        if not f and not text:
            return render_template("prep/content.html", mask_key=mask_key, error="请上传文件或粘贴文本", user=user, styles=list_styles())

        raw = ""
        filename = None
        file_size = 0
        try:
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext not in ALLOWED_EXT:
                    return render_template("prep/content.html", mask_key=mask_key, error=f"不支持的文件类型：{ext}", user=user, styles=list_styles())
                data = f.read()
                if len(data) > MAX_FILE_SIZE:
                    return render_template("prep/content.html", mask_key=mask_key, error="文件超过 15MB 限制", user=user, styles=list_styles())
                if not _magic_ok(data, ext):
                    return render_template("prep/content.html", mask_key=mask_key, error="文件格式与扩展名不符", user=user, styles=list_styles())
                file_size = len(data)
                filename = _safe_filename(f.filename)
                tmp_path = os.path.join(PREP_ROOT, "_tmp", uuid.uuid4().hex + ext)
                os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
                with open(tmp_path, "wb") as fh:
                    fh.write(data)
                raw = ingest_file(tmp_path)
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            elif text:
                if len(text) > MAX_TEXT:
                    text = text[:MAX_TEXT]
                raw = ingest_text(text)
                filename = "粘贴文本"
        except Exception as e:
            return render_template("prep/content.html", mask_key=mask_key, error=f"解析失败：{str(e)[:200]}", user=user, styles=list_styles())

        if not raw:
            return render_template("prep/content.html", mask_key=mask_key, error="未能从内容中提取到文本", user=user, styles=list_styles())

        mod = moderate(raw, env=dict(os.environ), use_api=use_api_mod)
        if not mod["ok"]:
            return render_template("prep/content.html", mask_key=mask_key, error="内容未通过合规审核：" + mod["reason"], user=user, styles=list_styles())

        job = PrepJob(
            user_id=user.id,
            mode="content",
            status="content_ready",
            filename=filename,
            file_size=file_size,
            original_text=raw,
        )
        db.session.add(job)
        db.session.commit()
        return redirect(url_for("prep.content_style", cid=job.id))

    return render_template("prep/content.html", mask_key=mask_key, user=user, styles=list_styles())


@prep_bp.route("/content/<cid>/style", methods=["GET", "POST"])
@login_required
def content_style(cid):
    user = current_user
    job = PrepJob.query.filter_by(id=cid, user_id=user.id).first()
    if not job:
        flash("记录不存在")
        return redirect(url_for("prep.index"))
    if request.method == "POST":
        style = request.form.get("style") or STYLE_IDS[0]
        title = (request.form.get("title") or "").strip()
        job.status = "running"
        job.updated_at = datetime.utcnow()
        job.style = style
        job.title = title or job.filename
        db.session.commit()
        app = current_app._get_current_object()
        t = threading.Thread(target=_run_content_job, args=(cid, user.id, app))
        t.daemon = True
        t.start()
        return redirect(url_for("prep.generating", job=cid))
    return render_template("prep/content_style.html", job=job, styles=list_styles(), user=user)


@prep_bp.route("/generating/<job>")
@login_required
def generating(job):
    user = current_user
    row = PrepJob.query.filter_by(id=job, user_id=user.id).first()
    if not row:
        flash("记录不存在")
        return redirect(url_for("prep.index"))
    return render_template("prep/generating.html", job=row)


@prep_bp.route("/status/<job>")
@login_required
def status(job):
    user = current_user
    row = PrepJob.query.filter_by(id=job, user_id=user.id).first()
    if not row:
        return jsonify({"status": "not_found"})
    return jsonify({"status": row.status, "error": row.error_msg})


@prep_bp.route("/result/<job>")
@login_required
def result(job):
    user = current_user
    row = PrepJob.query.filter_by(id=job, user_id=user.id).first()
    if not row:
        flash("记录不存在")
        return redirect(url_for("prep.index"))
    style_name = dict((s["id"], s["name"]) for s in list_styles()).get(row.style, row.style or "")
    return render_template("prep/result.html", job=row, style_name=style_name)


@prep_bp.route("/preview/<job>")
@login_required
def preview(job):
    user = current_user
    row = PrepJob.query.filter_by(id=job, user_id=user.id).first()
    if not row or not row.courseware_path or not os.path.exists(row.courseware_path):
        return "未找到课件", 404
    return send_file(row.courseware_path, mimetype="text/html")


@prep_bp.route("/preview-lesson/<job>")
@login_required
def preview_lesson(job):
    user = current_user
    row = PrepJob.query.filter_by(id=job, user_id=user.id).first()
    if not row or not row.lesson_path or not os.path.exists(row.lesson_path):
        return "未找到教案", 404
    return send_file(row.lesson_path, mimetype="text/html")


@prep_bp.route("/download/<job>")
@login_required
def download(job):
    user = current_user
    row = PrepJob.query.filter_by(id=job, user_id=user.id).first()
    if not row or not row.courseware_path or not os.path.exists(row.courseware_path):
        return "未找到课件", 404
    name = (row.title or "课件").replace(" ", "_") + ".html"
    return send_file(row.courseware_path, mimetype="text/html",
                     as_attachment=True, download_name=name)


@prep_bp.route("/download-lesson/<job>")
@login_required
def download_lesson(job):
    user = current_user
    row = PrepJob.query.filter_by(id=job, user_id=user.id).first()
    if not row or not row.lesson_path or not os.path.exists(row.lesson_path):
        return "未找到教案", 404
    name = (row.title or "教案").replace(" ", "_") + ".html"
    return send_file(row.lesson_path, mimetype="text/html",
                     as_attachment=True, download_name=name)


@prep_bp.route("/style-demo/<style_id>")
def style_demo(style_id):
    path = os.path.join(DEMO_DIR, f"{style_id}.html")
    if not os.path.exists(path):
        return "风格样例不存在", 404
    return send_file(path, mimetype="text/html")


@prep_bp.route("/admin/uploads")
@login_required
def admin_uploads():
    """课前备课独立后台已合并到平台总后台 /admin/prep_jobs（地址随 ADMIN_PATH）。"""
    return redirect(url_for("admin_bp.prep_jobs") + "?from=prep")
