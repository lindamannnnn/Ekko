"""课前备课生成任务模型。"""
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Text, Integer

from extensions import db
from models.base import UUIDMixin, TenantMixin, SoftDeleteMixin


class PrepJob(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """课前备课生成任务（学科生成 / 内容生成）。"""
    __tablename__ = 'prep_jobs'

    mode = Column(String(16), nullable=False)          # subject / content
    status = Column(String(16), default='pending', nullable=False, index=True)
    # pending -> running -> success / failed

    filename = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    original_text = Column(Text, nullable=True)

    subject = Column(String(32), nullable=True)
    grade = Column(String(32), nullable=True)
    topic = Column(String(255), nullable=True)
    duration = Column(Integer, nullable=True)
    style = Column(String(32), nullable=True)
    title = Column(String(255), nullable=True)

    lesson_path = Column(String(512), nullable=True)
    courseware_path = Column(String(512), nullable=True)
    error_msg = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
