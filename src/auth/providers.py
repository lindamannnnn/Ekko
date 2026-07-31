"""登录 provider。

当前实现 PasswordProvider（邮箱+密码）。
微信 / 短信 provider 为灰态占位：企业资质 + 已备案域名才能启用，
代码保留接口，UI 显示「即将推出」且不可点击。
"""
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db
from models.user import User


class BaseProvider:
    name = None
    available = False

    def register(self, *args, **kwargs):
        raise NotImplementedError

    def authenticate(self, *args, **kwargs):
        raise NotImplementedError


class PasswordProvider(BaseProvider):
    name = 'password'
    available = True

    @staticmethod
    def hash_password(password: str) -> str:
        return generate_password_hash(password)

    @staticmethod
    def check_password(user: User, password: str) -> bool:
        if not user or not user.password_hash:
            return False
        return check_password_hash(user.password_hash, password)

    @staticmethod
    def register(email: str, password: str, display_name: str | None = None) -> User:
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            display_name=display_name or email.split('@')[0],
            auth_provider='password',
        )
        db.session.add(user)
        db.session.commit()
        return user


class WechatProvider(BaseProvider):
    """企业微信/公众号 OAuth。需企业资质 + ICP 备案域名，暂未启用。"""
    name = 'wechat'
    available = False

    def register(self, *args, **kwargs):
        raise NotImplementedError('微信登录暂未开放')


class SmsProvider(BaseProvider):
    """短信验证码登录。需短信服务商资质 + 备案，暂未启用。"""
    name = 'sms'
    available = False

    def register(self, *args, **kwargs):
        raise NotImplementedError('短信登录暂未开放')


# 注册页 / 登录页展示的第三方入口；available=False 的显示为灰态
PROVIDER_CARDS = [
    {'name': 'wechat', 'label': '微信登录', 'available': WechatProvider.available},
    {'name': 'sms', 'label': '短信验证码', 'available': SmsProvider.available},
]
