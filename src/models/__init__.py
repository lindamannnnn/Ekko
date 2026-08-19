"""模型包入口：导入即注册全部表到 db.metadata。"""
from models.user import User, ApiCredential, DailyUsage, GenerationLog
from models.class_student import Klass, Student, Enrollment
from models.lesson import Lesson, Courseware, Review, TermSummary, StyleSample
from models.class_type_preset import ClassTypePreset
from models.prep_job import PrepJob

__all__ = [
    'User', 'ApiCredential', 'DailyUsage', 'GenerationLog',
    'Klass', 'Student', 'Enrollment',
    'Lesson', 'Courseware', 'Review', 'TermSummary', 'StyleSample',
    'ClassTypePreset', 'PrepJob',
]
