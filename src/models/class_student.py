"""班级、学生、报名关系（学生独立于班级，支持一人多班 / 升班转班）。"""
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Boolean, JSON, ForeignKey, Text, UniqueConstraint,
)

from extensions import db
from models.base import UUIDMixin, TenantMixin, SoftDeleteMixin


class Klass(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """班级。一个老师可建多个班级，每个班级选一种类型。"""
    __tablename__ = 'classes'

    name = Column(String(128), nullable=False)
    type_code = Column(String(32), nullable=False)                 # 关联 class_type_presets.code
    type_name_custom = Column(String(128), nullable=True)          # 自定义类型名（覆盖 type_code 显示）
    dimensions = Column(JSON, nullable=True)                       # 自定义评价维度（覆盖预置）
    quick_tags_custom = Column(JSON, nullable=True)                # 自定义快捷标签
    review_term = Column(String(32), default='课评', nullable=False)
    archived_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_klass_user_name'),
    )


class Student(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """学生。不挂 class_id —— 一人可加入多个班级，升班转班不丢历史。"""
    __tablename__ = 'students'

    name = Column(String(128), nullable=False)
    preferred_name = Column(String(128), nullable=True)   # 去姓称呼
    gender = Column(String(8), nullable=True)             # 男/女/未知
    birth_date = Column(db.Date, nullable=True)
    profile_json = Column(JSON, nullable=True)            # 备注、家长信息等


class Enrollment(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """班级-学生关联。一人多班、升班转班全靠它。"""
    __tablename__ = 'enrollments'

    student_id = Column(String(36), ForeignKey('students.id'), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey('classes.id'), nullable=False, index=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    left_at = Column(DateTime, nullable=True)            # null = 在读

    __table_args__ = (
        UniqueConstraint('student_id', 'class_id', name='uq_enrollment_student_class'),
    )
