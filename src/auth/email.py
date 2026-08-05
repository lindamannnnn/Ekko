"""邮件发送 + 签名 token（邮箱验证 / 密码重置）。

SMTP 未配置时进入 dev 模式：不真正发信，调用方应把链接打到控制台/页面，
保证整条流程可在无真实邮箱授权码时跑通。授权码到位后只需在 .env 填 MAIL_* 即可。
"""
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from typing import Optional

from flask import current_app
from itsdangerous import URLSafeTimedSerializer


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=salt)


def generate_token(user_id: str, salt: str, max_age: int) -> str:
    """签发带过期时间的 token（max_age 单位秒）。"""
    return _serializer(salt).dumps({'uid': str(user_id)})


def verify_token(token: str, salt: str, max_age: int) -> Optional[str]:
    """校验 token，失败（过期/篡改）返回 None。"""
    try:
        data = _serializer(salt).loads(token, max_age=max_age)
        return data.get('uid')
    except Exception:
        return None


def send_email(to: str, subject: str, html: str) -> bool:
    """发送 HTML 邮件。SMTP 未配置（无 server）时进入 dev 模式不真发。"""
    cfg = current_app.config
    server = cfg.get('MAIL_SERVER')
    user = cfg.get('MAIL_USERNAME')
    pw = cfg.get('MAIL_PASSWORD')
    sender = cfg.get('MAIL_DEFAULT_SENDER') or user
    if not server:
        current_app.logger.warning(
            'SMTP 未配置（MAIL_SERVER 为空），邮件未实际发送（dev 模式）。收件人=%s 主题=%s', to, subject
        )
        return False

    msg = MIMEText(html, '.feature' if False else 'html', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = sender
    msg['To'] = to

    try:
        with smtplib.SMTP(server, int(cfg.get('MAIL_PORT', 587)), timeout=10) as s:
            if cfg.get('MAIL_USE_TLS'):
                s.starttls()
            if user and pw:
                s.login(user, pw)
            s.sendmail(sender, [to], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001
        current_app.logger.error('邮件发送失败: %s', e)
        return False
