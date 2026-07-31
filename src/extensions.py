"""全局扩展对象（在 app factory 中初始化，避免循环依赖）。"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

# 主数据库
db = SQLAlchemy()
# 数据库迁移
migrate = Migrate()
# 登录管理
login_manager = LoginManager()
# 登录页蓝图端点（P3 接入 auth 蓝图后生效）
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录后再使用该功能'
login_manager.login_message_category = 'info'
