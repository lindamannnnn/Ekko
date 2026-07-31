"""班级类型预置（9 类内置，全局只读，从 seeds 载入）。"""
from sqlalchemy import Column, String, Integer, JSON

from extensions import db
from models.base import UUIDMixin


class ClassTypePreset(UUIDMixin, db.Model):
    """机构类型预置：维度 / 语气 / 字数 / emoji 数 / 类型侧重 / 快捷标签 / 图片模板。

    注意：此表不带 user_id（全局只读）。主键用 code 更易读，但仍保留 UUID id 以统一约定。
    """
    __tablename__ = 'class_type_presets'

    code = Column(String(32), unique=True, nullable=False)        # art / music / dance ...
    name = Column(String(64), nullable=False)
    dimensions = Column(JSON, nullable=False)                    # 评价维度列表
    tone = Column(String(128), nullable=True)                    # 语气
    length_min = Column(Integer, default=180, nullable=False)
    length_max = Column(Integer, default=320, nullable=False)
    emoji_min = Column(Integer, default=2, nullable=False)
    emoji_max = Column(Integer, default=5, nullable=False)
    prompt_hints = Column(JSON, nullable=True)                   # focus / vocab / avoid
    quick_tags = Column(JSON, nullable=True)                     # {维度: [标签...]}
    card_template = Column(String(16), default='general', nullable=False)  # work/skill/academic/general
