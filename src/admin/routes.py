"""平台总后台：独立登录 + 只读总览（与教师端完全隔离）。"""
import os
from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app, session
from flask_login import current_user, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, SubmitField
from werkzeug.security import check_password_hash
from auth.decorators import admin_required
from sqlalchemy import func

from extensions import db
from models.user import User, DailyUsage, GenerationLog
from models.class_student import Klass, Student, Enrollment
from models.lesson import Lesson, Courseware, Review

admin_bp = Blueprint('admin_bp', __name__)

# ── 后台网关（第二道门，IP 无关）──────────────────────────────────────────
# 进入任何后台路由前必须先输入管理密钥，密钥错误直接挡在门外。
ADMIN_GATE_KEY = os.environ.get('ADMIN_GATE_KEY', '')


class _GateForm(FlaskForm):
    key = PasswordField('管理密钥')
    submit = SubmitField('进入后台')


@admin_bp.before_request
def _admin_gate():
    """除网关自身、登录页、登出外，所有后台请求都需先过管理密钥。"""
    if request.endpoint in ('admin_bp.gate', 'admin_bp.admin_login', 'admin_bp.admin_logout'):
        return
    if not session.get('admin_gate_ok'):
        return redirect(url_for('admin_bp.gate'))


@admin_bp.route('/_gate', methods=['GET', 'POST'])
def gate():
    """管理密钥输入页：密钥正确则在 session 打标，放行后续后台请求。"""
    form = _GateForm()
    if form.validate_on_submit():
        if form.key.data == ADMIN_GATE_KEY:
            session['admin_gate_ok'] = True
            return redirect(url_for('admin_bp.admin_login'))
        flash('管理密钥错误', 'danger')
    return render_template('admin/gate.html', form=form)


# ── AI 用量聚合（dashboard 与 usage 页共用）─────────────────────────────────

def _usage_stats(days=7):
    """跨租户聚合 DailyUsage：今日/区间总量、按日趋势、按教师排行、通道分布。"""
    today = date.today()
    start = today - timedelta(days=days - 1)

    rows = (
        DailyUsage.query.filter(DailyUsage.date >= start, DailyUsage.date <= today)
        .all()
    )

    # 今日
    today_gen = sum(r.gen_count or 0 for r in rows if r.date == today)
    today_tok = sum(
        (r.prompt_tokens or 0) + (r.completion_tokens or 0)
        for r in rows if r.date == today
    )
    # 区间
    range_gen = sum(r.gen_count or 0 for r in rows)
    range_tok = sum((r.prompt_tokens or 0) + (r.completion_tokens or 0) for r in rows)

    # 按日趋势（补齐无数据的日期，图表不断档）
    by_day = {}
    for r in rows:
        d = by_day.setdefault(r.date, {"gen": 0, "tok": 0})
        d["gen"] += r.gen_count or 0
        d["tok"] += (r.prompt_tokens or 0) + (r.completion_tokens or 0)
    trend = []
    for i in range(days):
        d = start + timedelta(days=i)
        item = by_day.get(d, {"gen": 0, "tok": 0})
        trend.append({
            "date": d.strftime("%m-%d"),
            "full_date": d.strftime("%Y-%m-%d"),
            "gen": item["gen"],
            "tok": item["tok"],
            "is_today": d == today,
        })
    peak_gen = max([t["gen"] for t in trend], default=0)

    # 按教师排行
    quota = current_app.config.get("PLATFORM_QUOTA", 100)
    per_user = {}
    for r in rows:
        u = per_user.setdefault(r.user_id, {"gen": 0, "tok": 0, "today_gen": 0})
        u["gen"] += r.gen_count or 0
        u["tok"] += (r.prompt_tokens or 0) + (r.completion_tokens or 0)
        if r.date == today:
            u["today_gen"] += r.gen_count or 0
    ranking = []
    if per_user:
        umap = {
            u.id: u for u in User.query.filter(User.id.in_(list(per_user.keys()))).all()
        }
        for uid, v in per_user.items():
            u = umap.get(uid)
            ranking.append({
                "user_id": uid,
                "name": (u.display_name or u.email) if u else "（已删除账号）",
                "gen": v["gen"],
                "tok": v["tok"],
                "today_gen": v["today_gen"],
                "quota_pct": min(round(v["today_gen"] / quota * 100), 100) if quota else 0,
                "over_quota": quota and v["today_gen"] >= quota,
            })
        ranking.sort(key=lambda x: -x["gen"])

    # 通道分布
    channel_dist = {}
    for r in rows:
        channel_dist[r.channel or "platform"] = (
            channel_dist.get(r.channel or "platform", 0) + (r.gen_count or 0)
        )

    return {
        "days": days,
        "quota": quota,
        "today_gen": today_gen,
        "today_tok": today_tok,
        "range_gen": range_gen,
        "range_tok": range_tok,
        "avg_gen": round(range_gen / days, 1),
        "trend": trend,
        "peak_gen": peak_gen,
        "ranking": ranking,
        "channel_dist": channel_dist,
        "active_users": len(per_user),
    }


# ── 独立后台登录（不共用 /auth/login）─────────────────────────────────────

@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    """后台独立登录页——只接受超管账号，普通教师一律拒绝。"""
    # 已登录超管直接进总览
    if current_user.is_authenticated and getattr(current_user, 'is_superuser', False):
        return redirect(url_for('admin_bp.dashboard'))

    if request.method == 'POST':
        from security.ratelimit import check_rate_limit, hit_rate_limit, reset_rate_limit
        if check_rate_limit('admin.login'):
            flash('登录尝试过于频繁，请 5 分钟后再试', 'danger')
            # 用 redirect 而非 render：避免浏览器刷新时弹出"重新提交表单"提示
            return redirect(url_for('admin_bp.admin_login'))
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        # 排除软删除账号：已注销账号不得进入后台
        user = User.query.filter_by(email=email).filter(User.deleted_at.is_(None)).first()
        # 兼容纯用户名（如 seyououat520）：不含 @ 时自动补 @local.dev 再查
        if not user and '@' not in email:
            user = User.query.filter_by(email=(email.lower() + '@local.dev')).filter(User.deleted_at.is_(None)).first()
        if user and check_password_hash(user.password_hash, password):
            if getattr(user, 'is_superuser', False):
                login_user(user)
                reset_rate_limit('admin.login')
                return redirect(url_for('admin_bp.dashboard'))
            else:
                hit_rate_limit('admin.login')
                flash('该账号无后台管理权限', 'danger')
                return redirect(url_for('admin_bp.admin_login'))
        else:
            hit_rate_limit('admin.login')
            flash('邮箱或密码错误', 'danger')
            return redirect(url_for('admin_bp.admin_login'))

    return render_template('admin/login.html')


@admin_bp.route('/logout')
def admin_logout():
    """后台登出。"""
    logout_user()
    return redirect(url_for('admin_bp.admin_login'))


@admin_bp.route('/')
@admin_required
def dashboard():
    # 跨租户聚合：所有老师的数据在此一览（不作 user_id 过滤）
    users_n = User.query.count()
    classes_n = Klass.query.count()
    students_n = Student.query.count()
    reviews_n = Review.query.count()
    coursewares_n = Courseware.query.count()

    # 课评状态分布
    status_dist = dict(
        db.session.query(Review.status, func.count())
        .group_by(Review.status).all()
    )

    # 磁盘占用（uploads/ 目录）
    up_root = current_app.root_path
    # src/admin/routes.py -> 上三级即项目根
    import os
    up_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'uploads',
    )
    disk = 0
    if os.path.isdir(up_dir):
        for _root, _dirs, _files in os.walk(up_dir):
            for _f in _files:
                _p = os.path.join(_root, _f)
                if os.path.isfile(_p):
                    disk += os.path.getsize(_p)

    return render_template(
        'admin/dashboard.html',
        users=users_n,
        classes=classes_n,
        students=students_n,
        reviews=reviews_n,
        coursewares=coursewares_n,
        status_dist=status_dist,
        disk_mb=round(disk / 1024 / 1024, 2),
        usage=_usage_stats(days=7),
    )


@admin_bp.route('/usage')
@admin_required
def usage():
    """AI 用量看板：生成量趋势、配额水位、按教师排行、失败日志。"""
    try:
        days = int(request.args.get('days', 7))
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, 90))

    stats = _usage_stats(days=days)

    # 最近生成日志（含失败）
    logs = (
        GenerationLog.query.order_by(GenerationLog.created_at.desc()).limit(50).all()
    )
    uids = {l.user_id for l in logs if l.user_id}
    umap = {
        u.id: (u.display_name or u.email)
        for u in (User.query.filter(User.id.in_(list(uids))).all() if uids else [])
    }
    log_rows = [{
        'log': l,
        'user_name': umap.get(l.user_id, '（已删除账号）'),
    } for l in logs]

    fail_n = sum(1 for l in logs if l.error)
    lat_list = [l.latency_ms for l in logs if l.latency_ms]
    avg_latency = round(sum(lat_list) / len(lat_list)) if lat_list else 0

    return render_template(
        'admin/usage.html',
        usage=stats,
        days=days,
        log_rows=log_rows,
        fail_n=fail_n,
        avg_latency=avg_latency,
        log_total=len(logs),
    )


@admin_bp.route('/users')
@admin_required
def users():
    """所有账号（跨租户全量）。"""
    from models.class_student import Student, Enrollment
    users = User.query.order_by(User.created_at.desc()).all()
    # 每个用户的班级数 / 学生数（按 user_id 过滤）
    stat = {}
    for u in users:
        cls_n = Klass.query.filter_by(user_id=u.id, deleted_at=None).count()
        stu_n = Student.query.filter_by(user_id=u.id).count()
        stat[u.id] = (cls_n, stu_n)
    return render_template('admin/users.html', users=users, stat=stat)


@admin_bp.route('/users/<uid>/delete', methods=['POST'])
@admin_required
def delete_user(uid):
    """删除账号（级联清理其名下全部租户数据）。user_id 非外键，需手动清理。"""
    from models.user import ApiCredential, DailyUsage, GenerationLog
    from models.lesson import Lesson, Courseware, Review, TermSummary, StyleSample

    u = User.query.filter_by(id=uid).first()
    if not u:
        flash('账号不存在', 'danger')
        return redirect(url_for('admin_bp.users'))

    # 禁止删除当前登录账号，避免把自己锁在后台外
    if u.id == current_user.id:
        flash('不能删除当前登录的账号', 'danger')
        return redirect(url_for('admin_bp.users'))

    # 按引用层级从子到父级联删除，避免留下孤儿数据
    Review.query.filter_by(user_id=u.id).delete()
    TermSummary.query.filter_by(user_id=u.id).delete()
    StyleSample.query.filter_by(user_id=u.id).delete()
    Lesson.query.filter_by(user_id=u.id).delete()
    Courseware.query.filter_by(user_id=u.id).delete()
    Enrollment.query.filter_by(user_id=u.id).delete()
    Student.query.filter_by(user_id=u.id).delete()
    Klass.query.filter_by(user_id=u.id).delete()
    GenerationLog.query.filter_by(user_id=u.id).delete()
    DailyUsage.query.filter_by(user_id=u.id).delete()
    ApiCredential.query.filter_by(user_id=u.id).delete()
    db.session.delete(u)
    db.session.commit()
    flash(f'已删除账号 {u.email}', 'success')
    return redirect(url_for('admin_bp.users'))


@admin_bp.route('/coursewares')
@admin_required
def coursewares():
    """所有上传的课件（带时间 + 上传人 + 关联班级/课次）。"""
    from models.class_student import Klass
    from models.lesson import Lesson
    cws = Courseware.query.order_by(Courseware.created_at.desc()).all()
    # 反查每个课件当前挂在哪节课（lesson.courseware_id = cw.id）
    rows = []
    for cw in cws:
        klass = Klass.query.filter_by(id=cw.class_id).first()
        lesson = Lesson.query.filter_by(courseware_id=cw.id).first()
        lesson_title = lesson.title if lesson else '（未关联课次）'
        # 磁盘文件大小（KB）
        _sp = cw.stored_path
        _size = round(os.path.getsize(_sp) / 1024, 1) if (_sp and os.path.exists(_sp)) else 0
        rows.append({
            'cw': cw,
            'class_name': klass.name if klass else '（未知班级）',
            'lesson_title': lesson_title,
            'size_kb': _size,
        })
    return render_template('admin/coursewares.html', rows=rows)


@admin_bp.route('/reviews')
@admin_required
def reviews():
    """所有课评（跨租户全量，按状态分布）。"""
    from models.class_student import Klass, Student
    from models.lesson import Lesson
    revs = Review.query.all()
    rows = []
    for rv in revs:
        klass = Klass.query.filter_by(id=rv.class_id).first()
        student = Student.query.filter_by(id=rv.student_id).first()
        lesson = Lesson.query.filter_by(id=rv.lesson_id).first()
        rows.append({
            'rv': rv,
            'class_name': klass.name if klass else '（未知）',
            'student_name': student.name if student else '（未知）',
            'lesson_title': lesson.title if lesson else '（未知）',
        })
    return render_template('admin/reviews.html', rows=rows)


@admin_bp.route('/review/<rid>')
@admin_required
def review_detail(rid):
    """单份课评的完整内容（可下钻）。"""
    from models.class_student import Klass, Student
    from models.lesson import Lesson, Review
    rv = Review.query.get(rid)
    if not rv:
        abort(404)
    klass = Klass.query.filter_by(id=rv.class_id).first()
    student = Student.query.filter_by(id=rv.student_id).first()
    lesson = Lesson.query.filter_by(id=rv.lesson_id).first()
    return render_template(
        'admin/review_detail.html',
        rv=rv, klass=klass, student=student, lesson=lesson,
    )


@admin_bp.route('/courseware/<cid>')
@admin_required
def courseware_detail(cid):
    """单个课件的完整信息（可下钻）。"""
    import os as _os
    from models.class_student import Klass
    from models.lesson import Lesson, Courseware
    cw = Courseware.query.get(cid)
    if not cw:
        abort(404)
    klass = Klass.query.filter_by(id=cw.class_id).first()
    lesson = Lesson.query.filter_by(courseware_id=cw.id).first()
    _sp = cw.stored_path
    _size = round(_os.path.getsize(_sp) / 1024, 1) if (_sp and _os.path.exists(_sp)) else 0
    return render_template(
        'admin/courseware_detail.html',
        cw=cw, klass=klass, lesson=lesson, size_kb=_size,
    )


@admin_bp.route('/classes')
@admin_required
def classes():
    """所有班级列表（与 class_detail 下钻区分）。"""
    from models.class_student import Student, Enrollment
    ks = Klass.query.filter_by(deleted_at=None).all()
    stu_count = {}
    for k in ks:
        n = db.session.query(Enrollment).filter_by(class_id=k.id).count()
        stu_count[k.id] = n
    return render_template('admin/classes.html', ks=ks, stu_count=stu_count)


@admin_bp.route('/class/<kid>')
@admin_required
def class_detail(kid):
    """单个班级 + 在册学生名单（可下钻）。"""
    from models.class_student import Student, Enrollment
    k = Klass.query.filter_by(id=kid, deleted_at=None).first()
    if not k:
        abort(404)
    members = (
        db.session.query(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.class_id == k.id).all()
    )
    return render_template('admin/class_detail.html', k=k, members=members)


@admin_bp.route('/user/<uid>')
@admin_required
def user_detail(uid):
    """单个账号 + 名下班级/学生（可下钻）。"""
    from models.class_student import Student
    u = User.query.filter_by(id=uid).first()
    if not u:
        abort(404)
    cls_list = Klass.query.filter_by(user_id=u.id, deleted_at=None).all()
    stu_list = Student.query.filter_by(user_id=u.id).all()
    return render_template(
        'admin/user_detail.html', u=u, cls_list=cls_list, stu_list=stu_list,
    )
