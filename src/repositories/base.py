"""多租户隔离仓储基类。

P3 的核心安全机制：所有业务查询都强制注入 user_id（+ org_id）过滤，
且默认过滤软删除。业务代码一律通过 Repo 访问数据，绝不直接裸写
`Model.query.filter_by(...)`，从根上杜绝跨租户越权读取。
"""
from datetime import datetime

from extensions import db
from models.base import SoftDeleteMixin


class BaseRepo:
    def __init__(self, model, user_id: str | None = None, org_id: str | None = None):
        self.model = model
        self.user_id = user_id
        self.org_id = org_id

    # ---------- 隔离核心 ----------
    def _has(self, attr: str) -> bool:
        return hasattr(self.model, attr)

    def _scope(self, query):
        if self.user_id is not None and self._has('user_id'):
            query = query.filter(self.model.user_id == self.user_id)
        if self.org_id is not None and self._has('org_id'):
            query = query.filter(self.model.org_id == self.org_id)
        if issubclass(self.model, SoftDeleteMixin):
            query = query.filter(self.model.deleted_at.is_(None))
        return query

    def raw(self):
        """返回已注入隔离条件的 query（供高级联表查询）。"""
        return self._scope(self.model.query)

    # ---------- CRUD ----------
    def get(self, id: str):
        return self.raw().filter(self.model.id == id).first()

    def list(self, **filters):
        q = self.raw()
        for k, v in filters.items():
            q = q.filter(getattr(self.model, k) == v)
        return q.all()

    def count(self, **filters):
        q = self.raw()
        for k, v in filters.items():
            q = q.filter(getattr(self.model, k) == v)
        return q.count()

    def create(self, **kwargs):
        obj = self.model(**kwargs)
        if self.user_id is not None and self._has('user_id'):
            obj.user_id = self.user_id
        if self.org_id is not None and self._has('org_id'):
            obj.org_id = self.org_id
        db.session.add(obj)
        # 写事务保持极短（见风险 T10）；这里立即提交并收尾
        db.session.commit()
        return obj

    def update(self, id: str, **kwargs):
        obj = self.get(id)  # 已按 user_id 过滤，越权 id 返回 None
        if not obj:
            return None
        for k, v in kwargs.items():
            setattr(obj, k, v)
        db.session.commit()
        return obj

    def soft_delete(self, id: str):
        obj = self.get(id)
        if obj and self._has('deleted_at'):
            obj.deleted_at = datetime.utcnow()
            db.session.commit()
        return obj

    def restore(self, id: str):
        obj = self.model.query.filter(self.model.id == id).first()
        if obj and self._has('deleted_at'):
            obj.deleted_at = None
            db.session.commit()
        return obj

    def hard_delete(self, id: str):
        obj = self.get(id)
        if obj:
            db.session.delete(obj)
            db.session.commit()
        return obj
