"""应用工厂（替代 run.py 的 os.chdir 模式）。

P1 阶段只做：初始化扩展、注册模型、配置 SQLite（WAL + 短事务纪律）、
载入类型预置 seeds。蓝图 / 路由在 P3 接入；AI 通道在 P4 接入。
"""
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv  # 加载 .env 到 os.environ（P4 AI Key / SMTP 等配置）
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event, inspect

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

    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod'),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            'DATABASE_URL',
            f"sqlite:///{os.path.join(app.instance_path, 'app.db')}",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # 写事务保持极短；绝不在事务里调 LLM（见风险 T10）
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"timeout": 15}},
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,  # 上传上限 20MB
        # —— 邮件（SMTP）—— 未配置时进入 dev 模式（控制台打印链接，不真发信）
        MAIL_SERVER=os.environ.get('MAIL_SERVER', ''),
        MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
        MAIL_USERNAME=os.environ.get('MAIL_USERNAME', ''),
        MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD', ''),
        MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER', ''),
        MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true',
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
    from main import main_bp
    from classes import classes_bp
    from lessons import lessons_bp
    from reviews import reviews_bp
    from students import students_bp
    from cards import card_bp
    from reports import reports_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(lessons_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(card_bp)
    app.register_blueprint(reports_bp)
    # reviews 蓝图是纯 JSON API（前端 fetch 带登录态），整体豁免 CSRF；
    # 鉴权仍由 @login_required 保证。登录/注册表单在 auth 蓝图，仍受 CSRF 保护。
    csrf.exempt(reviews_bp)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, user_id)

    _configure_sqlite_pragmas(app)

    # 幂等载入 9 类机构类型预置（表尚未创建时跳过，待迁移后由 `flask seed` 执行）
    from sqlalchemy import inspect
    with app.app_context():
        tables = inspect(db.engine).get_table_names()
        if 'class_type_presets' in tables:
            load_class_type_presets()

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
        db.create_all()
    app.run(host='127.0.0.1', port=5000, debug=False)
