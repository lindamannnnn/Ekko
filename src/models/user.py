"""用户、凭证、用量、生成日志相关模型。"""
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Boolean, Integer, Float, JSON, ForeignKey, Text,
    UniqueConstraint,
)

from extensions import db
from models.base import UUIDMixin, TenantMixin, SoftDeleteMixin


class User(UUIDMixin, db.Model):
    """平台用户（邮箱 + 密码开放注册；可插拔 provider 预留微信/短信）。"""
    __tablename__ = 'users'

    email = Column(String(255), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    auth_provider = Column(String(32), default='password', nullable=False)
    external_id = Column(String(255), nullable=True)
    display_name = Column(String(128), nullable=True)
    org_name = Column(String(255), nullable=True)          # 印在图片模板上的机构名
    review_term = Column(String(32), default='课评', nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)  # 平台总后台守卫
    last_login_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    # 课前备课自定义 AI 通道（为空时使用平台默认通道）
    ai_api_key = Column(String(255), nullable=True)
    ai_base_url = Column(String(512), nullable=True)
    ai_model = Column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint('auth_provider', 'external_id', name='uq_user_provider_external'),
    )

    # —— Flask-Login 接口 ——
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.deleted_at is None

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f"<User {self.email or self.external_id}>"


class ApiCredential(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """用户自带 AI Key（Fernet 加密存库，只显示后 4 位）。为空即走平台通道。"""
    __tablename__ = 'api_credentials'

    provider = Column(String(32), default='openai_compatible', nullable=False)
    base_url = Column(String(512), nullable=True)
    model = Column(String(128), nullable=True)
    key_ciphertext = Column(Text, nullable=False)
    key_last4 = Column(String(8), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<ApiCredential {self.provider} {self.key_last4}>"


class DailyUsage(UUIDMixin, TenantMixin, db.Model):
    """按账号/日期/通道统计用量，用于配额控制。"""
    __tablename__ = 'daily_usage'

    date = Column(db.Date, nullable=False, index=True)
    gen_count = Column(Integer, default=0, nullable=False)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    channel = Column(String(32), default='platform', nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'date', 'channel', name='uq_daily_usage_uc'),
    )


class GenerationLog(UUIDMixin, TenantMixin, db.Model):
    """生成调用日志（不记 Token 明文）。"""
    __tablename__ = 'generation_logs'

    review_id = Column(String(36), nullable=True, index=True)
    channel = Column(String(32), nullable=True)
    tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
