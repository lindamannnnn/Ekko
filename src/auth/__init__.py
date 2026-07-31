"""鉴权蓝图：邮箱+密码开放注册（可插拔 provider 预留微信/短信）。"""
from auth.routes import bp as auth_bp

__all__ = ['auth_bp']
