"""鉴权相关表单（含 CSRF）。"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Regexp, ValidationError
from models.user import User


class UniqueEmail(object):
    """邮箱唯一性校验：已注册则不能重复注册。"""
    def __init__(self, message='该邮箱已注册，请直接登录或更换邮箱'):
        self.message = message

    def __call__(self, form, field):
        if field.data:
            email = field.data.strip().lower()
            if User.query.filter_by(email=email).first():
                raise ValidationError(self.message)


class RegistrationForm(FlaskForm):
    display_name = StringField('昵称', validators=[DataRequired(message='请输入昵称'), Length(max=128, message='昵称过长')])
    email = StringField('邮箱', validators=[DataRequired(), Email(message='邮箱格式不正确'), UniqueEmail()])
    password = PasswordField(
        '密码',
        validators=[
            DataRequired(message='请输入密码'),
            Length(min=8, message='密码至少 8 位'),
            Regexp(
                r'^(?=.*[A-Za-z])(?=.*\d).*$',
                message='密码需同时包含字母与数字',
            ),
        ],
    )
    confirm = PasswordField(
        '确认密码', validators=[DataRequired(), EqualTo('password', message='两次密码不一致')]
    )
    submit = SubmitField('注册')


class LoginForm(FlaskForm):
    email = StringField('邮箱', validators=[DataRequired(), Email(message='邮箱格式不正确')])
    password = PasswordField('密码', validators=[DataRequired()])
    remember = BooleanField('记住我')
    submit = SubmitField('登录')


class RequestResetForm(FlaskForm):
    email = StringField('邮箱', validators=[DataRequired(), Email(message='邮箱格式不正确')])
    submit = SubmitField('发送重置邮件')


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        '新密码', validators=[DataRequired(), Length(min=8, message='密码至少 8 位')]
    )
    confirm = PasswordField(
        '确认新密码', validators=[DataRequired(), EqualTo('password', message='两次密码不一致')]
    )
    submit = SubmitField('重置密码')
