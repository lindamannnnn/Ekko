"""鉴权路由：注册 / 登录 / 登出 / 邮箱验证 / 密码找回。"""
import datetime
from urllib.parse import urlparse

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, current_app,
)
from flask_login import login_user, logout_user, login_required, current_user

from auth.forms import (
    RegistrationForm, LoginForm, RequestResetForm, ResetPasswordForm,
)
from auth.providers import PasswordProvider, PROVIDER_CARDS
from auth.email import generate_token, verify_token, send_email
from extensions import db
from models.user import User

bp = Blueprint('auth', __name__, url_prefix='/auth')

VERIFY_SALT = 'email-verify'
VERIFY_MAX_AGE = 1800  # 30 分钟
RESET_SALT = 'password-reset'
RESET_MAX_AGE = 3600   # 60 分钟


def _is_safe_redirect_target(target: str) -> bool:
    """防止 next 参数造成的开放重定向。"""
    if not target:
        return False
    host = urlparse(target).netloc
    return not host or host == urlparse(request.host_url).netloc


def _send_verification(user: User) -> bool:
    token = generate_token(user.id, VERIFY_SALT, VERIFY_MAX_AGE)
    link = url_for('auth.verify_email', token=token, _external=True)
    sent = send_email(
        user.email,
        '验证你的课评系统邮箱',
        render_template('auth/email_verify.html', link=link, user=user),
    )
    if not sent:
        current_app.logger.warning('[dev] 邮箱验证链接: %s', link)
    return sent


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash('该邮箱已注册，请直接登录', 'warning')
            return redirect(url_for('auth.login'))
        user = PasswordProvider.register(email, form.password.data, form.display_name.data)
        _send_verification(user)
        return render_template(
            'auth/verify_notice.html', email=email,
            dev_mode=(not current_app.config.get('MAIL_PASSWORD')),
        )
    return render_template('auth/register.html', form=form, providers=PROVIDER_CARDS)


@bp.route('/verify-email/<token>')
def verify_email(token):
    uid = verify_token(token, VERIFY_SALT, VERIFY_MAX_AGE)
    if not uid:
        flash('验证链接无效或已过期，请重新获取', 'danger')
        return redirect(url_for('auth.login'))
    user = db.session.get(User, uid)
    if user and user.email_verified_at is None:
        user.email_verified_at = datetime.datetime.utcnow()
        db.session.commit()
        flash('邮箱验证成功，现在可以使用全部功能', 'success')
    else:
        flash('邮箱已验证', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and PasswordProvider.check_password(user, form.password.data):
            login_user(user, remember=bool(form.remember.data))
            user.last_login_at = datetime.datetime.utcnow()
            db.session.commit()
            flash('登录成功', 'success')
            next_ = request.args.get('next')
            if next_ and _is_safe_redirect_target(next_):
                return redirect(next_)
            return redirect(url_for('main.index'))
        flash('邮箱或密码不正确', 'danger')
    return render_template('auth/login.html', form=form, providers=PROVIDER_CARDS)


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/resend-verify', methods=['POST'])
@login_required
def resend_verify():
    if current_user.email_verified_at:
        flash('邮箱已验证', 'info')
        return redirect(url_for('main.index'))
    sent = _send_verification(current_user)
    flash(
        '验证邮件已重新发送' + ('（dev 模式未真正发送，请查看控制台链接）' if not sent else ''),
        'info',
    )
    return redirect(url_for('main.index'))


@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RequestResetForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_token(user.id, RESET_SALT, RESET_MAX_AGE)
            link = url_for('auth.reset_password', token=token, _external=True)
            sent = send_email(
                email,
                '重置你的课评系统密码',
                render_template('auth/email_reset.html', link=link, user=user),
            )
            if not sent:
                current_app.logger.warning('[dev] 密码重置链接: %s', link)
        # 无论是否存在都返回相同提示，避免邮箱枚举
        flash('如果该邮箱已注册，我们已发送重置密码邮件', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html', form=form)


@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    uid = verify_token(token, RESET_SALT, RESET_MAX_AGE)
    if not uid:
        flash('重置链接无效或已过期，请重新获取', 'danger')
        return redirect(url_for('auth.login'))
    user = db.session.get(User, uid)
    if not user:
        flash('重置链接无效', 'danger')
        return redirect(url_for('auth.login'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = PasswordProvider.hash_password(form.password.data)
        db.session.commit()
        flash('密码已重置，请使用新密码登录', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', form=form)
