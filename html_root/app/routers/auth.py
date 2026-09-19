"""Account sign-in, verified registration and email-based recovery."""
import logging
import uuid
from typing import Optional

import bcrypt
from fastapi import APIRouter, Response, Cookie, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from mysql.connector.errors import IntegrityError

from ..database import transaction
from ..store import CAPTCHA_STORE, SESSION_STORE
from ..request_origin import public_scheme
from ..models import AuthModel, EmailCodeRequest, EmailVerifyModel, EmailChangeModel, PasswordResetModel
from ..email_service import (
    EmailServiceError, EmailDeliveryError, EmailConfigurationError, EmailAuthenticationError, EmailRateLimitError, normalize_email, mask_email,
    issue_code, verify_code,
)
from ..access import load_principal, AccessDenied
from logic.captcha import generate_captcha_image_bytes

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])
RESET_NOTICE = '如果该邮箱已绑定账户，验证码将发送到你的邮箱。'


def error(message, status=400, code='invalid_request'):
    return JSONResponse(status_code=status, content={'status': 'error', 'message': message, 'code': code})


def service_error(exc):
    if isinstance(exc, AccessDenied):
        return error(str(exc), exc.status, exc.code)
    if isinstance(exc, EmailAuthenticationError):
        return error(str(exc), 503, 'email_auth_failed')
    if isinstance(exc, EmailDeliveryError):
        return error(str(exc), 503, 'email_unavailable')
    if isinstance(exc, EmailRateLimitError):
        return error(str(exc), 429, 'email_rate_limited')
    if isinstance(exc, (ValueError, EmailServiceError)):
        return error(str(exc), 400, 'email_code_invalid')
    if isinstance(exc, IntegrityError):
        return error('用户名或邮箱已被使用，请登录或更换后重试。')
    # Never log input, SMTP exceptions, database parameters, passwords or codes.
    logger.warning('Account operation failed (%s)', type(exc).__name__)
    return error('账户服务暂不可用，请稍后重试。', 503, 'account_unavailable')


def _captcha_ok(captcha, captcha_id):
    stored = CAPTCHA_STORE.pop(captcha_id or '', None)
    return bool(stored and captcha and stored == captcha.upper().strip())


def account_state(principal):
    verified = bool(principal.get('email_verified'))
    return {'status': 'success', 'username': principal['username'], 'role': principal['role'],
            'email': mask_email(principal.get('email')), 'email_verified': verified,
            # 仅返回给已登录账户本人，用于邮箱验证/更换时自动填充；页面展示仍使用脱敏 email。
            'email_address': principal.get('email') or '',
            'code': None if verified else 'email_verification_required'}


def current_principal(session):
    name = SESSION_STORE.get(session or '')
    if not name:
        raise AccessDenied('请先登录。', 401, 'login_required')
    return load_principal(name)


def validate_new_password(password):
    if len(password) < 6 or len(password.encode()) > 72:
        raise ValueError('密码至少需要 6 位，且不能超过 72 字节。')


def require_current_password(password, user):
    if (not password or len(password.encode()) > 72 or not user
            or not bcrypt.checkpw(password.encode(), user['hashed_password'].encode())):
        raise AccessDenied('当前密码不正确，请重新输入。', 403, 'reauthentication_required')


@router.get('/captcha')
async def get_captcha():
    code, image = generate_captcha_image_bytes()
    captcha_id = str(uuid.uuid4())
    CAPTCHA_STORE[captcha_id] = code.upper()
    return StreamingResponse(image, media_type='image/png',
                             headers={'X-Captcha-ID': captcha_id, 'Cache-Control': 'no-store'})


@router.post('/email/send-code')
def send_email_code(data: EmailCodeRequest, request: Request, auth_session: Optional[str] = Cookie(None)):
    try:
        email = normalize_email(data.email)
        principal = current_principal(auth_session) if data.purpose in {'verify', 'change_email'} else None
        if principal and data.purpose == 'verify':
            if principal.get('email_verified'):
                return error('此账户已完成邮箱验证。')
            if principal.get('email') and principal['email'].lower() != email:
                return error('请输入当前账户绑定的邮箱。')
        elif principal and data.purpose == 'change_email':
            with transaction() as (_, cur):
                cur.execute('SELECT hashed_password FROM users WHERE id=%s', (principal['id'],))
                require_current_password(data.current_password, cur.fetchone())
            if principal.get('email') and principal['email'].lower() == email:
                return error('新邮箱不能与当前绑定邮箱相同。')
        elif not _captcha_ok(data.captcha, data.captcha_id):
            return error('图片验证码错误或已过期，请刷新后重试。', code='captcha_invalid')
        with transaction() as (_, cur):
            cur.execute('SELECT id FROM users WHERE email=%s', (email,))
            existing = cur.fetchone()
        deliver = True
        user_id = principal['id'] if principal else None
        if data.purpose == 'reset':
            deliver = bool(existing)
            user_id = existing['id'] if existing else None
        elif data.purpose == 'change_email':
            if existing and existing['id'] != principal['id']:
                return error('该邮箱已被其他账户使用，请更换邮箱。')
            user_id = principal['id']
        elif data.purpose == 'verify' and principal and existing and existing['id'] != principal['id']:
            # 旧账户首次绑定邮箱时也必须绑定到唯一地址，不能静默生成一个无法使用的验证码。
            return error('该邮箱已被其他账户使用，请更换一个邮箱。')
        elif existing and (not principal or existing['id'] != principal['id']):
            deliver = False
        from ..request_guard import client_ip
        try:
            issue_code(email, data.purpose, user_id=user_id,
                       requester_ip=client_ip(request.scope, request.headers), deliver=deliver)
        except EmailServiceError as exc:
            # Avoid disclosing existence through rate limits or delivery failures.
            # A missing SMTP configuration is checked independently of existence.
            if data.purpose != 'reset' or isinstance(exc, EmailConfigurationError):
                raise
        if data.purpose == 'reset':
            notice = RESET_NOTICE
        elif data.purpose == 'change_email':
            notice = '验证码已发送到新邮箱，请查收后完成更换。'
        else:
            notice = '若邮箱可用于此操作，验证码将发送到邮箱，请查收。'
        return {'status': 'success', 'message': notice, 'email': mask_email(email), 'retry_after': 60}
    except Exception as exc:
        return service_error(exc)


@router.post('/password/forgot/request')
def forgot_password_request(data: EmailCodeRequest, request: Request):
    if data.purpose != 'reset':
        return error('请求无效。')
    return send_email_code(data, request, None)


@router.post('/register')
def register(data: AuthModel):
    try:
        if not data.email or not data.email_code:
            return error('请填写邮箱并获取邮箱验证码。', code='email_verification_required')
        email = normalize_email(data.email)
        validate_new_password(data.password)
        username = data.username.strip()
        if not username:
            return error('请填写用户名。')
        # Email proof has already passed the picture captcha at send time.
        # Consumption and account creation commit together so failures are retryable.
        def create(conn, cur, challenge):
            cur.execute('SELECT id FROM users WHERE username=%s OR email=%s', (username, email))
            if cur.fetchone():
                raise ValueError('用户名或邮箱已被使用，请登录或更换后重试。')
            hashed = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
            cur.execute('''INSERT INTO users(username,hashed_password,email,email_verified,email_verified_at)
                VALUES(%s,%s,%s,1,UTC_TIMESTAMP())''', (username, hashed, email))
        verify_code(email, 'register', data.email_code, action=create)
        return {'status': 'success', 'message': '注册成功，请登录。'}
    except Exception as exc:
        return service_error(exc)


@router.post('/login')
def login(data: AuthModel, response: Response, request: Request):
    if not _captcha_ok(data.captcha, data.captcha_id):
        return error('图片验证码错误或已过期，请刷新后重试。', code='captcha_invalid')
    try:
        with transaction() as (_, cur):
            cur.execute('SELECT id,username,hashed_password FROM users WHERE username=%s', (data.username,))
            user = cur.fetchone()
        if not user or len(data.password.encode()) > 72 or not bcrypt.checkpw(data.password.encode(), user['hashed_password'].encode()):
            return error('用户名或密码错误。', 401, 'login_failed')
        principal = load_principal(user['username'])
        # Serialize session creation with a password reset on the same account.
        with transaction() as (_, cur):
            cur.execute('SELECT hashed_password FROM users WHERE id=%s FOR UPDATE', (user['id'],))
            latest = cur.fetchone()
            if not latest or latest['hashed_password'] != user['hashed_password']:
                return error('密码已更改，请重新登录。', 401, 'login_failed')
            session_id = str(uuid.uuid4())
            SESSION_STORE[session_id] = user['username']
        secure = public_scheme(request.scope, request.headers) == 'https'
        response.set_cookie(key='auth_session', value=session_id, max_age=86400,
                            httponly=True, samesite='lax', secure=secure)
        return account_state(principal)
    except Exception as exc:
        return service_error(exc)


@router.get('/user/me')
def get_current_user(auth_session: Optional[str] = Cookie(None)):
    try:
        return account_state(current_principal(auth_session))
    except Exception as exc:
        return service_error(exc)


@router.get('/user/check-username')
def check_username(username: str = Query(..., max_length=64)):
    raw = username.strip()
    if not raw:
        return {'available': False}
    try:
        with transaction() as (_, cur):
            cur.execute('SELECT id FROM users WHERE username=%s', (raw,))
            return {'available': cur.fetchone() is None}
    except Exception:
        return JSONResponse(status_code=503, content={'available': False, 'message': '账户服务暂不可用。'})


@router.post('/email/verify')
def verify_email(data: EmailVerifyModel, auth_session: Optional[str] = Cookie(None)):
    try:
        principal = current_principal(auth_session)
        email = normalize_email(data.email)
        def bind(conn, cur, challenge):
            cur.execute('SELECT email,email_verified FROM users WHERE id=%s FOR UPDATE', (principal['id'],))
            user = cur.fetchone()
            if not user or user['email_verified'] or user['email'] and user['email'].lower() != email:
                raise ValueError('邮箱与当前账户不匹配，或已经完成验证。')
            cur.execute('SELECT id FROM users WHERE email=%s AND id<>%s', (email, principal['id']))
            if cur.fetchone():
                raise ValueError('该邮箱已被其他账户使用，请更换邮箱。')
            cur.execute('''UPDATE users SET email=%s,email_verified=1,email_verified_at=UTC_TIMESTAMP()
                WHERE id=%s''', (email, principal['id']))
        verify_code(email, 'verify', data.code, user_id=principal['id'], action=bind)
        return {'status': 'success', 'message': '邮箱验证成功，可以继续使用了。', 'email_verified': True}
    except Exception as exc:
        return service_error(exc)


@router.post('/email/change')
def change_email(data: EmailChangeModel, auth_session: Optional[str] = Cookie(None)):
    """Replace the signed-in account email after proving control of the new address."""
    try:
        principal = current_principal(auth_session)
        email = normalize_email(data.email)
        if principal.get('email') and principal['email'].lower() == email:
            raise ValueError('新邮箱不能与当前绑定邮箱相同。')

        def bind(conn, cur, challenge):
            cur.execute('SELECT email,hashed_password FROM users WHERE id=%s FOR UPDATE', (principal['id'],))
            user = cur.fetchone()
            if not user:
                raise AccessDenied('账户不存在或已失效。', 401, 'login_required')
            require_current_password(data.current_password, user)
            cur.execute('SELECT id FROM users WHERE email=%s AND id<>%s', (email, principal['id']))
            if cur.fetchone():
                raise ValueError('该邮箱已被其他账户使用，请更换邮箱。')
            cur.execute('''UPDATE users SET email=%s,email_verified=1,email_verified_at=UTC_TIMESTAMP()
                WHERE id=%s''', (email, principal['id']))

        verify_code(email, 'change_email', data.code, user_id=principal['id'], action=bind)
        return {'status': 'success', 'message': '邮箱已更新并完成验证。', 'email': mask_email(email), 'email_verified': True}
    except Exception as exc:
        return service_error(exc)


@router.post('/password/forgot/reset')
def forgot_password_reset(data: PasswordResetModel, response: Response):
    try:
        email = normalize_email(data.email)
        validate_new_password(data.new_password)
        with transaction() as (_, cur):
            cur.execute('SELECT id FROM users WHERE email=%s', (email,))
            user = cur.fetchone()
        if not user:
            raise EmailServiceError('验证码不正确或已过期。')
        def reset(conn, cur, challenge):
            cur.execute('SELECT username,email FROM users WHERE id=%s FOR UPDATE', (user['id'],))
            latest = cur.fetchone()
            if not latest or latest['email'].lower() != email:
                raise EmailServiceError('验证码不正确或已过期。')
            hashed = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
            cur.execute('''UPDATE users SET hashed_password=%s,email_verified=1,
                email_verified_at=COALESCE(email_verified_at,UTC_TIMESTAMP()) WHERE id=%s''', (hashed, user['id']))
            SESSION_STORE.remove_value(latest['username'])
        verify_code(email, 'reset', data.code, user_id=user['id'], action=reset)
        response.delete_cookie(key='auth_session')
        return {'status': 'success', 'message': '密码已重置，请使用新密码登录。'}
    except Exception as exc:
        return service_error(exc)


@router.post('/logout')
async def logout(response: Response, auth_session: Optional[str] = Cookie(None)):
    SESSION_STORE.pop(auth_session or '', None)
    response.delete_cookie(key='auth_session')
    return {'status': 'success', 'message': '已退出登录。'}
