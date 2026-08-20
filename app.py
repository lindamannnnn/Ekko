"""应用工厂（替代 run.py 的 os.chdir 模式）。

P1 阶段只做：初始化扩展、注册模型、配置 SQLite（WAL + 短事务纪律）、
载入类型预置 seeds。蓝图 / 路由在 P3 接入；AI 通道在 P4 接入。
"""
import os
import sys
import secrets
import logging
from pathlib import Path

import click
from dotenv import load_dotenv  # 加载 .env 到 os.environ（P4 AI Key / SMTP 等配置）
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event, inspect
from sqlalchemy.exc import OperationalError

# 把 src 加入 sys.path，使 extensions / models 可作为顶层包导入
_SRC = str(Path(__file__).resolve().parent / 'src')
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from extensions import db, migrate, login_manager
import models  # noqa: F401  注册全部模型
from models.user import User
from seeds import load_class_type_presets

csrf = CSRFProtect()


def _configure_sqlite_pragmas(app: Flask) -> None:
    """SQLite 并发纪律：WAL + 忙等待超时 + 外键。详见方案 v6 风险 T10/T12。"""
    with app.app_context():
        engine = db.engine

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA busy_timeout=15000;")
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.close()


def create_app(config: dict | None = None) -> Flask:
    # 加载项目根目录 .env（AI_API_KEY / AI_BASE_URL / AI_MODEL / MAIL_* 等）
    load_dotenv(Path(__file__).resolve().parent / '.env')

    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    # SECRET_KEY：生产必须从环境变量注入固定随机串；未设置时本地生成临时密钥并告警
    # （临时密钥每次启动都变，会导致已登录用户被强制登出，仅适合本地开发）
    _secret_key = os.environ.get('SECRET_KEY')
    if not _secret_key:
        _secret_key = secrets.token_hex(32)
        logging.getLogger('app.sec').warning(
            'SECRET_KEY 未通过环境变量设置，已使用临时随机密钥（重启后失效，仅适合本地开发）。'
            '生产部署请设置环境变量 SECRET_KEY 为一个固定的随机字符串。'
        )

    app.config.from_mapping(
        SECRET_KEY=_secret_key,
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            'DATABASE_URL',
            f"sqlite:///{os.path.join(app.instance_path, 'app.db')}",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # CSRF 跨站请求伪造防护：生产必须开启。表单（登录/注册/重置）已带 csrf_token，
        # 前端 fetch 非安全请求由 base 模板的全局钩子自动附带 X-CSRFToken 头。
        # 纯 JSON API（reviews 蓝图）已整体豁免（仍由 @login_required 保护）。
        WTF_CSRF_ENABLED=True,
        # 开发期模板自动重载，避免改模板后必须重启服务
        TEMPLATES_AUTO_RELOAD=True,
        # 写事务保持极短；绝不在事务里调 LLM（见风险 T10）
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"timeout": 15}},
        MAX_CONTENT_LENGTH=15 * 1024 * 1024,  # 上传上限 15MB（课件大小限制）
        # —— 邮件（SMTP）—— 未配置时进入 dev 模式（控制台打印链接，不真发信）
        MAIL_SERVER=os.environ.get('MAIL_SERVER', ''),
        MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
        MAIL_USERNAME=os.environ.get('MAIL_USERNAME', ''),
        MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD', ''),
        MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER', ''),
        MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true',
        # 465 端口用 SMTP_SSL 套接字层（阿里云屏蔽 25 出站，163 邮箱必须走 465）
        MAIL_USE_SSL=os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true',
        # —— AI 模型通道（P4）——
        AI_API_KEY=os.environ.get('AI_API_KEY', ''),
        AI_BASE_URL=os.environ.get('AI_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4'),
        AI_MODEL=os.environ.get('AI_MODEL', 'glm-4-flash'),
    )
    if config:
        app.config.from_mapping(config)

    db.init_app(app)
    # render_as_batch=True：SQLite 不支持改列类型/加约束/删列，
    # 必须走 batch_alter_table 重建表，否则第二次迁移即卡死（见风险 T8）
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)

    # 注册蓝图（P3 接入业务蓝图）
    from auth import auth_bp
    from auth.decorators import admin_required  # noqa: F401
    from main import main_bp
    from classes import classes_bp
    from lessons import lessons_bp
    from reviews import reviews_bp
    from students import students_bp
    from cards import card_bp
    from reports import reports_bp
    from admin import admin_bp
    from prep import prep_bp
    # 后台入口随机化：用 ADMIN_PATH 作为 url_prefix（IP 无关，防止后台被扫到）
    _admin_path = os.environ.get('ADMIN_PATH', 'admin').strip('/')
    admin_bp.url_prefix = '/' + _admin_path
    app.jinja_env.globals['ADMIN_PREFIX'] = '/' + _admin_path
    app.jinja_env.globals['HALL_URL'] = os.environ.get('HALL_URL', 'http://localhost:8080/')
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(lessons_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(card_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(prep_bp)
    # reviews 蓝图是纯 JSON API（前端 fetch 带登录态），整体豁免 CSRF；
    # 鉴权仍由 @login_required 保证。登录/注册表单在 auth 蓝图，仍受 CSRF 保护。
    csrf.exempt(reviews_bp)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, user_id)

    # 关键修复：所有 HTML 响应加 no-cache，击败浏览器磁盘缓存导致的“旧模板”错觉
    @app.after_request
    def _no_cache(resp):
        ct = resp.content_type or ''
        if ct.startswith('text/html'):
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
        return resp

    _configure_sqlite_pragmas(app)

    # 幂等载入 9 类机构类型预置（表尚未创建时跳过，待迁移后由 `flask seed` 执行）
    from sqlalchemy import inspect
    with app.app_context():
        # 先建表，确保后续查询 users 表时表已存在（解决 no such table: users）
        # Gunicorn 多 worker 并发启动时，create_all(checkfirst=True) 仍可能竞态报
        # "table already exists"，捕获并忽略该错误即可，不影响幂等性。
        try:
            db.create_all()
        except OperationalError as e:
            if "already exists" not in str(e).lower():
                raise
        tables = inspect(db.engine).get_table_names()
        if 'class_type_presets' in tables:
            load_class_type_presets()

        # —— 平台总后台：补 is_superuser 列 + 按环境变量种管理员 ——
        from models.user import User
        from auth.providers import PasswordProvider
        from sqlalchemy import text as _text

        _tbls = inspect(db.engine).get_table_names()
        if 'users' in _tbls:
            _cols = [c['name'] for c in inspect(db.engine).get_columns('users')]
            if 'is_superuser' not in _cols:
                with db.engine.connect() as _conn:
                    _conn.execute(_text("ALTER TABLE users ADD COLUMN is_superuser BOOLEAN DEFAULT 0"))
            # —— 课前备课 AI 通道字段（兼容旧库）——
            if 'ai_api_key' not in _cols:
                with db.engine.connect() as _conn:
                    _conn.execute(_text("ALTER TABLE users ADD COLUMN ai_api_key VARCHAR(255)"))
            if 'ai_base_url' not in _cols:
                with db.engine.connect() as _conn:
                    _conn.execute(_text("ALTER TABLE users ADD COLUMN ai_base_url VARCHAR(512)"))
            if 'ai_model' not in _cols:
                with db.engine.connect() as _conn:
                    _conn.execute(_text("ALTER TABLE users ADD COLUMN ai_model VARCHAR(128)"))

        # —— 课件表补 created_at / uploaded_by 列（解决旧库缺列）——
        if 'coursewares' in _tbls:
            _ccols = [c['name'] for c in inspect(db.engine).get_columns('coursewares')]
            if 'created_at' not in _ccols:
                with db.engine.connect() as _conn:
                    _conn.execute(_text("ALTER TABLE coursewares ADD COLUMN created_at DATETIME"))
            if 'uploaded_by' not in _ccols:
                with db.engine.connect() as _conn:
                    _conn.execute(_text("ALTER TABLE coursewares ADD COLUMN uploaded_by VARCHAR(128)"))

        _admin_email = os.environ.get('ADMIN_EMAIL', 'admin@local.dev')
        if _admin_email:
            _u = User.query.filter_by(email=_admin_email).first()
            if not _u:
                # 管理员密码：生产必须从环境变量 ADMIN_PASSWORD 注入；未设置时生成本地随机密码并打日志
                _admin_pw = os.environ.get('ADMIN_PASSWORD')
                if not _admin_pw:
                    _admin_pw = secrets.token_hex(8)
                    logging.getLogger('app.sec').warning(
                        'ADMIN_PASSWORD 未设置，已为管理员 %s 生成随机密码：%s '
                        '（请妥善记录；生产请设置环境变量 ADMIN_PASSWORD 固定）',
                        _admin_email, _admin_pw,
                    )
                PasswordProvider.register(
                    _admin_email,
                    _admin_pw,
                    display_name='平台管理员',
                    is_superuser=True,
                )
            else:
                _u.is_superuser = True
                db.session.commit()

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    @app.cli.command('seed')
    def seed_command():
        """载入/刷新机构类型预置（需先 flask db upgrade 建表）。"""
        with app.app_context():
            load_class_type_presets()
            click.echo('class_type_presets 已载入/刷新')

    return app


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        try:
            db.create_all()
        except OperationalError as e:
            if "already exists" not in str(e).lower():
                raise
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 5000)), debug=False)
