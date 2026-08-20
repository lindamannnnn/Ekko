# -*- coding: utf-8 -*-
"""app.py —— 课前备课工作台（content-upload 分支）。

流程：
  ① 课前首页 /：二选一 —— 根据学科生成 / 根据内容生成
  ② /subject：语数英 3 科 → 教案 + 课件
  ③ /content：上传/粘贴内容 → 安全校验 → 选风格 → 课件
  ④ /generating/<job>：有趣的生成动画 + 轮询状态
  ⑤ /result/<job>：预览/下载
  ⑥ /admin/uploads：当前用户的生成记录后台

登录：简单邮箱 + 密码（MVP），用户可上传自己的 API KEY 用于学科生成的强模型升级。
与系统 B 的集成：通过 subprocess 调用 orchestrator.py，不 import B 的代码。
"""
import os
import sys
import re
import uuid
import json
import hashlib
import sqlite3
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from flask import Flask, request, render_template, redirect, url_for, flash, session, send_file, jsonify
from pipeline.ingest import ingest_file, ingest_text
from pipeline.segment import segment
from pipeline.moderate import moderate
from render import render, list_styles, STYLE_IDS
from kb_courses import list_kb_courses, get_entry, kb_to_slides

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "content-upload-feature-dev"

DB_PATH = os.path.join(BASE_DIR, "uploads.db")
OUT_DIR = os.path.join(BASE_DIR, "out")
os.makedirs(OUT_DIR, exist_ok=True)

ALLOWED_EXT = {".txt", ".md", ".markdown", ".csv", ".html", ".htm",
               ".docx", ".pptx", ".pdf"}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB
MAX_TEXT = 20000
RETENTION_DAYS = 7  # 生成的课件/教案文件保留天数
EKKO_DB = os.environ.get("EKKO_DB") or os.path.normpath(os.path.join(BASE_DIR, "..", "..", "class-review-system", "instance", "app.db"))

# 学科生成仅支持 3 科
SUBJECTS = ["语文", "数学", "英语"]
# 年级：1~9 上下册
GRADES = [f"{g}{s}" for g in range(1, 10) for s in ("年级上", "年级下")]

# 风格 demo 目录
DEMO_DIR = os.path.join(OUT_DIR, "_style_demos")
os.makedirs(DEMO_DIR, exist_ok=True)

# ---- 数据库 ----

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            password_hash TEXT NOT NULL,
            ai_api_key TEXT,
            ai_base_url TEXT,
            ai_model TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            filename TEXT,
            file_size INTEGER,
            original_text TEXT,
            subject TEXT,
            grade TEXT,
            topic TEXT,
            duration INTEGER,
            style TEXT,
            title TEXT,
            lesson_path TEXT,
            courseware_path TEXT,
            error_msg TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        """)


init_db()

# ---- 工具函数 ----

def load_env():
    """读取项目根 .env 到 os.environ（不覆盖已存在的环境变量）。"""
    p = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(p):
        return
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def now():
    return datetime.now().isoformat(timespec="seconds")


def _hash_pw(pw: str) -> str:
    return hashlib.sha256((pw + app.secret_key).encode("utf-8")).hexdigest()


def _current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _current_user():
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


_ekko_db_mtime = 0
_ekko_reviews_cache = {}
_ekko_name_cache = {}

def _load_ekko_display_name(email: str) -> str:
    """从 Ekko 数据库读取 display_name，用于首次登录时同步教师名字。"""
    if not os.path.exists(EKKO_DB):
        return ""
    cache_key = (email, os.path.getmtime(EKKO_DB))
    if cache_key in _ekko_name_cache:
        return _ekko_name_cache[cache_key]
    try:
        conn = sqlite3.connect(EKKO_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT display_name FROM users WHERE email=? AND deleted_at IS NULL",
            (email,)
        ).fetchone()
        name = (row["display_name"] or "") if row else ""
        _ekko_name_cache[cache_key] = name
        return name
    except Exception:
        return ""


def _load_ekko_reviews(email: str) -> list:
    """读取 Ekko 课评记录（按用户邮箱关联）。课评记录在 Ekko 中永久保存，此处只读。"""
    if not os.path.exists(EKKO_DB):
        return []
    # 简单缓存：同一邮箱 60 秒内不重复读
    global _ekko_db_mtime, _ekko_reviews_cache
    mtime = os.path.getmtime(EKKO_DB)
    cache_key = (email, mtime)
    if cache_key in _ekko_reviews_cache:
        return _ekko_reviews_cache[cache_key]
    try:
        conn = sqlite3.connect(EKKO_DB)
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id, display_name FROM users WHERE email=? AND deleted_at IS NULL",
            (email,)
        ).fetchone()
        if not user:
            _ekko_reviews_cache[cache_key] = []
            return []
        user_id = user["id"]
        rows = conn.execute("""
            SELECT r.id, r.class_id, r.student_id, r.lesson_id, r.status,
                   r.content, r.created_at, r.updated_at,
                   c.name AS class_name,
                   s.name AS student_name,
                   l.title AS lesson_title
            FROM reviews r
            LEFT JOIN classes c ON r.class_id = c.id AND c.deleted_at IS NULL
            LEFT JOIN students s ON r.student_id = s.id AND s.deleted_at IS NULL
            LEFT JOIN lessons l ON r.lesson_id = l.id AND l.deleted_at IS NULL
            WHERE r.user_id = ? AND r.deleted_at IS NULL
            ORDER BY r.created_at DESC
        """, (user_id,)).fetchall()
        result = [dict(r) for r in rows]
        _ekko_reviews_cache[cache_key] = result
        return result
    except Exception as e:
        return []


def _cleanup_expired_files():
    """删除超过 RETENTION_DAYS 的生成文件，但保留数据库记录。"""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    with _db() as conn:
        rows = conn.execute("""
            SELECT id, courseware_path, lesson_path, created_at FROM jobs
            WHERE status = 'success'
        """).fetchall()
    deleted_count = 0
    for r in rows:
        try:
            created = datetime.fromisoformat(r["created_at"])
        except Exception:
            continue
        if created < cutoff:
            for path in (r["courseware_path"], r["lesson_path"]):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        deleted_count += 1
                    except Exception:
                        pass
            # 如果 job 目录为空，也删除目录
            job_dir = os.path.join(OUT_DIR, r["id"])
            if os.path.isdir(job_dir):
                try:
                    if not os.listdir(job_dir):
                        os.rmdir(job_dir)
                except Exception:
                    pass
    return deleted_count


def _safe_filename(name: str) -> str:
    """保留中英文、数字、下划线、点、横线，其余替换下划线。"""
    import re
    name = os.path.basename(name)
    name = re.sub(r"[^\w\u4e00-\u9fa5.\-]", "_", name)
    return name or "unnamed"


def _magic_ok(data: bytes, ext: str) -> bool:
    """魔数校验。"""
    if ext in (".docx", ".pptx"):
        return data[:4] == b"PK\x03\x04"
    if ext == ".pdf":
        return data[:4] == b"%PDF"
    return True


def _build_demo_decks():
    """预生成每个风格的 demo 单文件 HTML（3 页样例）。"""
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
        # demo 预览卡片里不要出现任何滚动条
        hide_scroll = "<style>html,body,.slide{overflow:hidden!important}*::-webkit-scrollbar{display:none!important}.slide{overflow-y:hidden!important}</style>"
        html = html.replace("</head>", hide_scroll + "</head>", 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)


_build_demo_decks()


# ---- 页面路由 ----

@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        next_url = request.form.get("next") or url_for("index")
        with _db() as conn:
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row:
            if row["password_hash"] == _hash_pw(pw):
                # 每次登录都尝试从 Ekko 同步 display_name
                ekko_name = _load_ekko_display_name(email)
                if ekko_name and ekko_name != row["name"]:
                    with _db() as conn:
                        conn.execute("UPDATE users SET name=?, updated_at=? WHERE id=?",
                                     (ekko_name, now(), row["id"]))
                session["user_id"] = row["id"]
                return redirect(next_url)
            flash("邮箱或密码错误")
        else:
            # MVP：首次登录自动创建账户；若 Ekko 有同名教师，同步 display_name
            uid = uuid.uuid4().hex
            name = _load_ekko_display_name(email) or email.split("@")[0]
            with _db() as conn:
                conn.execute("""
                    INSERT INTO users (id, email, name, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (uid, email, name, _hash_pw(pw), now(), now()))
            session["user_id"] = uid
            return redirect(next_url)
    return render_template("login.html", next=request.args.get("next", url_for("index")))


@app.route("/auth/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = _current_user()
    error = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            name = (request.form.get("name") or "").strip()
            with _db() as conn:
                conn.execute("UPDATE users SET name=?, updated_at=? WHERE id=?",
                             (name or user["email"].split("@")[0], now(), user["id"]))
            flash("教师名字已更新")
            return redirect(url_for("account"))
        elif action == "password":
            old_pw = request.form.get("old_password") or ""
            new_pw = request.form.get("new_password") or ""
            confirm_pw = request.form.get("confirm_password") or ""
            if user["password_hash"] != _hash_pw(old_pw):
                error = "原密码错误"
            elif len(new_pw) < 6:
                error = "新密码至少 6 位"
            elif new_pw != confirm_pw:
                error = "两次输入的新密码不一致"
            else:
                with _db() as conn:
                    conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
                                 (_hash_pw(new_pw), now(), user["id"]))
                flash("密码已修改，请重新登录")
                session.clear()
                return redirect(url_for("login"))
        elif action == "key":
            key = (request.form.get("ai_api_key") or "").strip()
            base_url = (request.form.get("ai_base_url") or "").strip()
            model = (request.form.get("ai_model") or "").strip()
            with _db() as conn:
                if key:
                    conn.execute("""
                        UPDATE users SET ai_api_key=?, ai_base_url=?, ai_model=?, updated_at=?
                        WHERE id=?
                    """, (key, base_url or None, model or None, now(), user["id"]))
                    flash("API KEY 已保存")
                else:
                    conn.execute("""
                        UPDATE users SET ai_api_key=NULL, ai_base_url=?, ai_model=?, updated_at=?
                        WHERE id=?
                    """, (base_url or None, model or None, now(), user["id"]))
                    flash("API KEY 已清空")
            return redirect(url_for("account") + "#api-key")
    # 读取生成记录与课评记录
    with _db() as conn:
        jobs = conn.execute("""
            SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC
        """, (user["id"],)).fetchall()
        jobs = [dict(r) for r in jobs]
    _cleanup_expired_files()
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for j in jobs:
        try:
            created = datetime.fromisoformat(j["created_at"])
        except Exception:
            created = datetime.now()
        j["expired"] = created < cutoff
        j["has_files"] = bool(
            (j["courseware_path"] and os.path.exists(j["courseware_path"])) or
            (j["lesson_path"] and os.path.exists(j["lesson_path"]))
        )
    reviews = _load_ekko_reviews(user["email"])
    return render_template("account.html", user=user, jobs=jobs, reviews=reviews,
                           retention_days=RETENTION_DAYS, mask_key=_mask_key(user.get("ai_api_key") or ""),
                           error=error, now=datetime.now())


@app.route("/")
def index():
    return render_template("index.html", styles=list_styles(), user=_current_user())


@app.route("/courses")
@login_required
def courses():
    """返回知识库课程树，但仅包含语数英 3 科。"""
    tree = list_kb_courses()
    filtered = {k: v for k, v in tree.items() if k in SUBJECTS}
    return filtered


# ---- API KEY 管理 ----

@app.route("/api/user/key", methods=["POST"])
@login_required
def api_user_key():
    user = _current_user()
    key = (request.form.get("ai_api_key") or "").strip()
    base_url = (request.form.get("ai_base_url") or "").strip()
    model = (request.form.get("ai_model") or "").strip()
    action = request.form.get("action")
    with _db() as conn:
        if action == "clear" or not key:
            conn.execute("""
                UPDATE users SET ai_api_key=NULL, ai_base_url=?, ai_model=?, updated_at=?
                WHERE id=?
            """, (base_url or None, model or None, now(), user["id"]))
        else:
            conn.execute("""
                UPDATE users SET ai_api_key=?, ai_base_url=?, ai_model=?, updated_at=?
                WHERE id=?
            """, (key, base_url or None, model or None, now(), user["id"]))
    flash("API KEY 已更新" if key else "API KEY 已清空")
    return redirect(url_for("subject") + "#model-info")


# ---- 学科生成 ----

@app.route("/subject", methods=["GET", "POST"])
@login_required
def subject():
    user = _current_user()
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
            job_id = uuid.uuid4().hex
            job_dir = os.path.join(OUT_DIR, job_id)
            os.makedirs(job_dir, exist_ok=True)
            with _db() as conn:
                conn.execute("""
                    INSERT INTO jobs (id, user_id, mode, status, created_at, updated_at,
                                      subject, grade, topic, duration, style, title)
                    VALUES (?, ?, 'subject', 'running', ?, ?, ?, ?, ?, ?, ?, ?)
                """, (job_id, user["id"], now(), now(), subject_name, grade, topic,
                       int(duration), style, title or topic))
            t = threading.Thread(target=_run_subject_job, args=(job_id, user["id"]))
            t.daemon = True
            t.start()
            return redirect(url_for("generating", job=job_id))
    return render_template("subject.html", styles=list_styles(), subjects=SUBJECTS,
                           user=user, error=error,
                           mask_key=_mask_key(user.get("ai_api_key") or ""))


def _run_subject_job(job_id: str, user_id: str):
    """后台线程：调用系统 B orchestrator 生成教案 + 课件。"""
    with _db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not job or not user:
        return
    user = dict(user)
    job = dict(job)
    job_dir = os.path.join(OUT_DIR, job_id)
    lesson_path = os.path.join(job_dir, "lesson.html")
    courseware_path = os.path.join(job_dir, "index.html")

    env = dict(os.environ)
    load_env()
    # 如果用户上传了自己的 key，优先使用
    if user.get("ai_api_key"):
        env["AI_API_KEY"] = user["ai_api_key"]
    if user.get("ai_base_url"):
        env["AI_BASE_URL"] = user["ai_base_url"]
    if user.get("ai_model"):
        env["AI_MODEL"] = user["ai_model"]

    try:
        # 调用系统 B orchestrator（示例 CLI，需与真实 orchestrator 参数对齐）
        cmd = [
            sys.executable,
            os.path.join(os.path.dirname(BASE_DIR), "orchestrator.py"),
            "--subject", job["subject"],
            "--grade", job["grade"],
            "--topic", job["topic"],
            "--duration", str(job["duration"]),
            "--out", job_dir,
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:500] or "生成失败")
        # 解析 stdout 中的输出文件路径
        lesson = None
        course = None
        for line in (result.stdout or "").splitlines():
            if line.startswith("教案 HTML:"):
                lesson = line.split(":", 1)[1].strip()
            elif line.startswith("课件 HTML:"):
                course = line.split(":", 1)[1].strip()
        # 兜底：扫描常见命名
        out_files = os.listdir(job_dir)
        if not lesson:
            lesson = next((os.path.join(job_dir, f) for f in out_files if f.startswith("lesson_") or f == "lesson.html"), None)
        if not course:
            course = next((os.path.join(job_dir, f) for f in out_files if f.startswith("course_") or f == "index.html"), None)

        # 用用户选择的风格重新渲染课件（orchestrator 输出固定风格，这里覆盖为所选风格）
        style = job.get("style") or STYLE_IDS[0]
        if style not in STYLE_IDS:
            style = STYLE_IDS[0]
        try:
            lesson_text = ""
            if lesson and os.path.exists(lesson):
                with open(lesson, "r", encoding="utf-8") as f:
                    raw_html = f.read()
                # 简单去标签提取文本
                lesson_text = re.sub(r"<[^>]+>", " ", raw_html)
                lesson_text = re.sub(r"\s+", "\n", lesson_text).strip()
            if lesson_text:
                slides = segment(lesson_text, env={}, allow_llm=False)
                if slides:
                    title = job.get("title") or job.get("topic") or "课件"
                    courseware_html = render(slides, style, title=title)
                    with open(courseware_path, "w", encoding="utf-8") as f:
                        f.write(courseware_html)
                    course = courseware_path
        except Exception:
            # 风格渲染失败则回退 orchestrator 原课件
            pass

        if not course and os.path.exists(courseware_path):
            course = courseware_path

        with _db() as conn:
            conn.execute("""
                UPDATE jobs SET status='success', updated_at=?,
                                lesson_path=?, courseware_path=?
                WHERE id=?
            """, (now(), lesson, course, job_id))
    except Exception as e:
        with _db() as conn:
            conn.execute("""
                UPDATE jobs SET status='failed', updated_at=?, error_msg=?
                WHERE id=?
            """, (now(), str(e)[:500], job_id))


# ---- 内容上传 ----

@app.route("/content", methods=["GET", "POST"])
@login_required
def content():
    user = _current_user()
    if request.method == "POST":
        f = request.files.get("file")
        text = (request.form.get("text") or "").strip()
        use_api_mod = request.form.get("use_api_mod") == "on"
        if not f and not text:
            return render_template("content.html", error="请上传文件或粘贴文本", user=user)

        raw = ""
        filename = None
        file_size = 0
        try:
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext not in ALLOWED_EXT:
                    return render_template("content.html", error=f"不支持的文件类型：{ext}", user=user)
                data = f.read()
                if len(data) > MAX_FILE_SIZE:
                    return render_template("content.html", error="文件超过 15MB 限制", user=user)
                if not _magic_ok(data, ext):
                    return render_template("content.html", error="文件格式与扩展名不符", user=user)
                file_size = len(data)
                filename = _safe_filename(f.filename)
                tmp_path = os.path.join(OUT_DIR, "_tmp", uuid.uuid4().hex + ext)
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
            return render_template("content.html", error=f"解析失败：{str(e)[:200]}", user=user)

        if not raw:
            return render_template("content.html", error="未能从内容中提取到文本", user=user)

        mod = moderate(raw, env=dict(os.environ), use_api=use_api_mod)
        if not mod["ok"]:
            return render_template("content.html", error="内容未通过合规审核：" + mod["reason"], user=user)

        content_id = uuid.uuid4().hex
        with _db() as conn:
            conn.execute("""
                INSERT INTO jobs (id, user_id, mode, status, created_at, updated_at,
                                  filename, file_size, original_text)
                VALUES (?, ?, 'content', 'content_ready', ?, ?, ?, ?, ?)
            """, (content_id, user["id"], now(), now(), filename, file_size, raw))
        return redirect(url_for("content_style", cid=content_id))

    return render_template("content.html", user=user)


@app.route("/content/<cid>/style", methods=["GET", "POST"])
@login_required
def content_style(cid):
    user = _current_user()
    with _db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (cid, user["id"])).fetchone()
    if not job:
        flash("记录不存在")
        return redirect(url_for("index"))
    if request.method == "POST":
        style = request.form.get("style") or STYLE_IDS[0]
        title = (request.form.get("title") or "").strip()
        with _db() as conn:
            conn.execute("""
                UPDATE jobs SET status='running', updated_at=?, style=?, title=?
                WHERE id=?
            """, (now(), style, title or job["filename"], cid))
        t = threading.Thread(target=_run_content_job, args=(cid,))
        t.daemon = True
        t.start()
        return redirect(url_for("generating", job=cid))
    return render_template("content_style.html", job=dict(job), styles=list_styles(), user=user)


def _run_content_job(job_id: str):
    """后台线程：segment + render 生成课件。"""
    with _db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return
    try:
        slides = segment(job["original_text"], env=dict(os.environ))
        if not slides:
            raise RuntimeError("切页失败：未能将内容拆分为幻灯片")
        title = job["title"] or slides[0].get("title") or "我的课件"
        html_out = render(slides, job["style"], title=title)
        out_path = os.path.join(OUT_DIR, job_id, "index.html")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_out)
        with _db() as conn:
            conn.execute("""
                UPDATE jobs SET status='success', updated_at=?, courseware_path=?
                WHERE id=?
            """, (now(), out_path, job_id))
    except Exception as e:
        with _db() as conn:
            conn.execute("""
                UPDATE jobs SET status='failed', updated_at=?, error_msg=?
                WHERE id=?
            """, (now(), str(e)[:500], job_id))


# ---- 生成中 / 状态 / 结果 ----

@app.route("/generating/<job>")
@login_required
def generating(job):
    user = _current_user()
    with _db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job, user["id"])).fetchone()
    if not row:
        flash("记录不存在")
        return redirect(url_for("index"))
    return render_template("generating.html", job=dict(row))


@app.route("/status/<job>")
@login_required
def status(job):
    user = _current_user()
    with _db() as conn:
        row = conn.execute("SELECT status, error_msg FROM jobs WHERE id=? AND user_id=?",
                           (job, user["id"])).fetchone()
    if not row:
        return jsonify({"status": "not_found"})
    return jsonify({"status": row["status"], "error": row["error_msg"]})


@app.route("/result/<job>")
@login_required
def result(job):
    user = _current_user()
    with _db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job, user["id"])).fetchone()
    if not row:
        flash("记录不存在")
        return redirect(url_for("index"))
    job = dict(row)
    style_name = dict((s["id"], s["name"]) for s in list_styles()).get(job.get("style"), job.get("style") or "")
    return render_template("result.html", job=job, style_name=style_name)


# ---- 预览 / 下载 / 风格样例 ----

@app.route("/preview/<job>")
@login_required
def preview(job):
    user = _current_user()
    with _db() as conn:
        row = conn.execute("SELECT courseware_path FROM jobs WHERE id=? AND user_id=?",
                           (job, user["id"])).fetchone()
    if not row or not row["courseware_path"] or not os.path.exists(row["courseware_path"]):
        return "未找到课件", 404
    return send_file(row["courseware_path"], mimetype="text/html")


@app.route("/preview-lesson/<job>")
@login_required
def preview_lesson(job):
    user = _current_user()
    with _db() as conn:
        row = conn.execute("SELECT lesson_path FROM jobs WHERE id=? AND user_id=?",
                           (job, user["id"])).fetchone()
    if not row or not row["lesson_path"] or not os.path.exists(row["lesson_path"]):
        return "未找到教案", 404
    return send_file(row["lesson_path"], mimetype="text/html")


@app.route("/download/<job>")
@login_required
def download(job):
    user = _current_user()
    with _db() as conn:
        row = conn.execute("SELECT courseware_path, title FROM jobs WHERE id=? AND user_id=?",
                           (job, user["id"])).fetchone()
    if not row or not row["courseware_path"] or not os.path.exists(row["courseware_path"]):
        return "未找到课件", 404
    name = (row["title"] or "课件").replace(" ", "_") + ".html"
    return send_file(row["courseware_path"], mimetype="text/html",
                     as_attachment=True, download_name=name)


@app.route("/download-lesson/<job>")
@login_required
def download_lesson(job):
    user = _current_user()
    with _db() as conn:
        row = conn.execute("SELECT lesson_path, title FROM jobs WHERE id=? AND user_id=?",
                           (job, user["id"])).fetchone()
    if not row or not row["lesson_path"] or not os.path.exists(row["lesson_path"]):
        return "未找到教案", 404
    name = (row["title"] or "教案").replace(" ", "_") + ".html"
    return send_file(row["lesson_path"], mimetype="text/html",
                     as_attachment=True, download_name=name)


@app.route("/style-demo/<style_id>")
@login_required
def style_demo(style_id):
    path = os.path.join(DEMO_DIR, f"{style_id}.html")
    if not os.path.exists(path):
        return "风格样例不存在", 404
    return send_file(path, mimetype="text/html")


# ---- 后台 ----

@app.route("/admin/uploads")
@login_required
def admin_uploads():
    user = _current_user()
    _cleanup_expired_files()
    with _db() as conn:
        rows = conn.execute("""
            SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC
        """, (user["id"],)).fetchall()
    jobs = [dict(r) for r in rows]
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for j in jobs:
        try:
            created = datetime.fromisoformat(j["created_at"])
        except Exception:
            created = datetime.now()
        j["expired"] = created < cutoff
        j["has_files"] = bool(
            (j["courseware_path"] and os.path.exists(j["courseware_path"])) or
            (j["lesson_path"] and os.path.exists(j["lesson_path"]))
        )
    style_names = {s["id"]: s["name"] for s in list_styles()}
    return render_template("admin.html", jobs=jobs, style_names=style_names,
                           user=user, retention_days=RETENTION_DAYS)


# ---- 兼容旧入口（保留） ----

@app.route("/generate", methods=["POST"])
@login_required
def generate():
    """旧的统一生成入口：知识库选课 or 上传内容。"""
    mode = request.form.get("mode") or "upload"
    style = request.form.get("style") or STYLE_IDS[0]
    title = (request.form.get("title") or "").strip()
    if style not in STYLE_IDS:
        style = STYLE_IDS[0]

    slides = []
    if mode == "kb":
        subject = (request.form.get("subject") or "").strip()
        grade = (request.form.get("grade") or "").strip()
        topic = (request.form.get("topic") or "").strip()
        if not (subject and topic):
            flash("请先选择 科目 / 年级 / 课程")
            return redirect(url_for("index"))
        if subject not in SUBJECTS:
            flash("仅支持语文、数学、英语三科")
            return redirect(url_for("index"))
        entry = get_entry(subject, grade, topic)
        if not entry:
            flash("知识库中未找到该课程")
            return redirect(url_for("index"))
        slides = kb_to_slides(entry)
        if not slides:
            flash("该课程知识库内容为空，无法生成")
            return redirect(url_for("index"))
        if not title:
            title = (grade + " " if grade else "") + topic
    else:
        f = request.files.get("file")
        text = (request.form.get("text") or "").strip()
        use_api_mod = request.form.get("use_api_mod") == "on"
        raw = ""
        try:
            if f and f.filename:
                ext = os.path.splitext(f.filename)[1].lower()
                if ext not in ALLOWED_EXT:
                    flash("不支持的文件类型：" + ext)
                    return redirect(url_for("index"))
                data = f.read()
                if len(data) > MAX_FILE_SIZE:
                    flash("文件超过 15MB")
                    return redirect(url_for("index"))
                tmp_path = os.path.join(OUT_DIR, "_tmp", uuid.uuid4().hex + ext)
                os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
                with open(tmp_path, "wb") as fh:
                    fh.write(data)
                raw = ingest_file(tmp_path)
                os.remove(tmp_path)
            elif text:
                raw = ingest_text(text[:MAX_TEXT])
            else:
                flash("请上传文件或粘贴文本")
                return redirect(url_for("index"))
        except Exception as e:
            flash("解析失败：" + str(e)[:200])
            return redirect(url_for("index"))

        if not raw:
            flash("未能从内容中提取到文本")
            return redirect(url_for("index"))
        mod = moderate(raw, env=dict(os.environ), use_api=use_api_mod)
        if not mod["ok"]:
            flash("内容未通过合规审核：" + mod["reason"])
            return redirect(url_for("index"))
        slides = segment(raw, env=dict(os.environ))
        if not slides:
            flash("切页失败")
            return redirect(url_for("index"))
        if not title:
            title = slides[0].get("title") or "我的课件"

    html_out = render(slides, style, title=title)
    job = uuid.uuid4().hex
    user = _current_user()
    job_dir = os.path.join(OUT_DIR, job)
    os.makedirs(job_dir, exist_ok=True)
    out_path = os.path.join(job_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_out)
    with _db() as conn:
        conn.execute("""
            INSERT INTO jobs (id, user_id, mode, status, created_at, updated_at,
                              style, title, courseware_path)
            VALUES (?, ?, 'upload', 'success', ?, ?, ?, ?, ?)
        """, (job, user["id"], now(), now(), style, title, out_path))
    return redirect(url_for("result", job=job))


if __name__ == "__main__":
    load_env()
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
