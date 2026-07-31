"""平台免费通道 + 配额控制。

智谱 GLM-4-Flash 单 Key 永久免费、30 并发。本通道在用户未配置自带 Key 时启用，
按 (user_id, date, channel='platform') 统计当日生成数用于配额拦截。
多 Key 轮询只解决「扩容」（并发老师多时分散压力），不解决单次速度。
"""
from datetime import date

from extensions import db
from models.user import DailyUsage


class Channel:
    def __init__(self, user_id, api_keys=None):
        self.user_id = user_id
        self.api_keys = api_keys or []

    def under_quota(self, quota=None):
        from flask import current_app

        quota = quota or current_app.config.get("PLATFORM_QUOTA", 100)
        rec = (
            DailyUsage.query.filter_by(
                user_id=self.user_id, date=date.today(), channel="platform"
            )
            .first()
        )
        if rec is None:
            return True
        return rec.gen_count < quota

    def pick_key(self, index=0):
        """多 Key 轮询：返回第 index 个 Key（溢出则回绕）。"""
        if not self.api_keys:
            return None
        return self.api_keys[index % len(self.api_keys)]

    def record_usage(self, tokens_prompt=0, tokens_completion=0, channel="platform"):
        rec = (
            DailyUsage.query.filter_by(
                user_id=self.user_id, date=date.today(), channel=channel
            )
            .first()
        )
        if rec is None:
            rec = DailyUsage(user_id=self.user_id, date=date.today(), channel=channel)
            db.session.add(rec)
        rec.gen_count = (rec.gen_count or 0) + 1
        rec.prompt_tokens = (rec.prompt_tokens or 0) + tokens_prompt
        rec.completion_tokens = (rec.completion_tokens or 0) + tokens_completion
        db.session.commit()
        return rec
