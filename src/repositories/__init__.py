"""仓储层入口：按实体提供 Repo 构造器。"""
from extensions import db
from models.class_student import Klass, Student, Enrollment
from models.lesson import Lesson, Courseware, Review, TermSummary, StyleSample
from models.user import ApiCredential, DailyUsage, GenerationLog, User
from models.class_type_preset import ClassTypePreset
from .base import BaseRepo


def repo(model, user_id=None, org_id=None):
    return BaseRepo(model, user_id, org_id)


# 便捷构造器：业务层只传 user_id 即可自动隔离
def klasses(user_id, org_id=None):
    return BaseRepo(Klass, user_id, org_id)

def students(user_id, org_id=None):
    return BaseRepo(Student, user_id, org_id)

def enrollments(user_id, org_id=None):
    return BaseRepo(Enrollment, user_id, org_id)

def lessons(user_id, org_id=None):
    return BaseRepo(Lesson, user_id, org_id)

def reviews(user_id, org_id=None):
    return BaseRepo(Review, user_id, org_id)

def coursewares(user_id, org_id=None):
    return BaseRepo(Courseware, user_id, org_id)

def style_samples(user_id, org_id=None):
    return BaseRepo(StyleSample, user_id, org_id)

def term_summaries(user_id, org_id=None):
    return BaseRepo(TermSummary, user_id, org_id)

def api_credentials(user_id, org_id=None):
    return BaseRepo(ApiCredential, user_id, org_id)

def daily_usage(user_id, org_id=None):
    return BaseRepo(DailyUsage, user_id, org_id)

def generation_logs(user_id, org_id=None):
    return BaseRepo(GenerationLog, user_id, org_id)


# 全局只读（无 user_id 维度）
def class_type_presets():
    return BaseRepo(ClassTypePreset)

def users():
    return BaseRepo(User)


__all__ = [
    'BaseRepo', 'repo',
    'klasses', 'students', 'enrollments', 'lessons', 'reviews', 'coursewares',
    'style_samples', 'term_summaries', 'api_credentials', 'daily_usage',
    'generation_logs', 'class_type_presets', 'users',
]
