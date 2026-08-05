"""课次、课件、课评、阶段总结、风格样本相关模型。"""
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Boolean, JSON, ForeignKey, Text, Float, Integer,
    UniqueConstraint,
)

from extensions import db
from models.base import UUIDMixin, TenantMixin, SoftDeleteMixin


class Lesson(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """一节课。共性描述（common_notes）与知识点（objectives）挂在这里。"""
    __tablename__ = 'lessons'

    class_id = Column(String(36), ForeignKey('classes.id'), nullable=False, index=True)
    lesson_date = Column(db.Date, nullable=True)
    title = Column(String(255), nullable=False)
    lesson_type = Column(String(16), default='normal', nullable=False)   # normal / trial
    objectives = Column(JSON, nullable=True)        # 课件解析自动抽取的知识点
    common_notes = Column(Text, nullable=True)      # 全班共性表现描述
    courseware_id = Column(String(36), ForeignKey('coursewares.id'), nullable=True)


class Courseware(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """上传的课件/教案。仅存文件与抽取文本，不直接参与生成。"""
    __tablename__ = 'coursewares'

    class_id = Column(String(36), ForeignKey('classes.id'), nullable=False, index=True)
    source_filename = Column(String(255), nullable=True)
    stored_path = Column(String(512), nullable=True)        # 磁盘路径（UUID 命名）
    extracted_text = Column(Text, nullable=True)
    # 上传留痕：时间 + 上传人（解决「教师上传历史查不到」的盲区）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by = Column(String(128), nullable=True)


class Review(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """单份课评。status 是并发进度与断点续跑的唯一真相来源。"""
    __tablename__ = 'reviews'

    class_id = Column(String(36), ForeignKey('classes.id'), nullable=False, index=True)
    student_id = Column(String(36), ForeignKey('students.id'), nullable=False, index=True)
    lesson_id = Column(String(36), ForeignKey('lessons.id'), nullable=False, index=True)

    # pending → generating → draft → confirmed
    #                          ↘ failed（error_msg）   leave（请假）
    status = Column(String(16), default='pending', nullable=False, index=True)

    perf_tags = Column(JSON, nullable=True)     # 老师点选的快捷标签
    perf_note = Column(Text, nullable=True)     # 老师手写的个别补充
    content = Column(Text, nullable=True)       # 最终/草稿正文
    ai_raw = Column(Text, nullable=True)        # AI 原稿（用于「还原原稿」）
    meta_json = Column(JSON, nullable=True)     # improvement_points 等
    score_json = Column(JSON, nullable=True)    # 评分结果
    dedup_score = Column(Float, nullable=True)  # 横向去重相似度
    model_used = Column(String(128), nullable=True)
    error_msg = Column(Text, nullable=True)
    edited_at = Column(DateTime, nullable=True)     # 老师手动改过 → 非空
    sent_at = Column(DateTime, nullable=True)       # 顺序复制发送记录
    generating_since = Column(DateTime, nullable=True)  # 幂等锁：生成开始时间，超时(120s)可重入

    lesson = db.relationship("Lesson", foreign_keys=[lesson_id], lazy="joined")

    __table_args__ = (
        UniqueConstraint('student_id', 'lesson_id', name='uq_review_student_lesson'),
    )


class TermSummary(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """阶段/期末总结（把该生一段时间内的 confirmed 课评二次合成）。"""
    __tablename__ = 'term_summaries'

    student_id = Column(String(36), ForeignKey('students.id'), nullable=False, index=True)
    class_id = Column(String(36), ForeignKey('classes.id'), nullable=True, index=True)
    term_label = Column(String(64), nullable=True)
    period_start = Column(db.Date, nullable=True)
    period_end = Column(db.Date, nullable=True)
    content = Column(Text, nullable=True)
    source_review_ids = Column(JSON, nullable=True)
    status = Column(String(16), default='draft', nullable=False)


class StyleSample(UUIDMixin, TenantMixin, SoftDeleteMixin, db.Model):
    """老师写作风格样本。优先级：本班 confirmed 稿 > 用户全局样本 > 内置范文。"""
    __tablename__ = 'style_samples'

    class_id = Column(String(36), ForeignKey('classes.id'), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String(16), default='manual', nullable=False)  # manual / confirmed / builtin
    is_active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        # 加速「按用户+班级查样本」
        db.Index('ix_style_sample_user_class', 'user_id', 'class_id'),
    )
