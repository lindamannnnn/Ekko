"""模型公共基类：UUID 主键、租户隔离字段、软删除、时间戳。

约定（见方案 v6 第二节）：
- 主键统一 String(36) UUID
- 除 users / class_type_presets 外，每表必带 user_id（租户隔离）
- 每张业务表带 org_id（nullable，本期不启用，预留机构版）
- 所有业务表带 deleted_at（软删除）
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime

from extensions import db


def gen_id() -> str:
    return str(uuid.uuid4())


class UUIDMixin:
    id = Column(String(36), primary_key=True, default=gen_id)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class TenantMixin:
    """租户隔离字段。注意：users 与 class_type_presets 不继承此 mixin。"""
    user_id = Column(String(36), index=True, nullable=False)
    org_id = Column(String(36), index=True, nullable=True)


class SoftDeleteMixin:
    deleted_at = Column(DateTime, nullable=True)
