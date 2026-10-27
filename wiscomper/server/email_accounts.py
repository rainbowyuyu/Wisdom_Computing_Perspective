"""Durable, purpose/account-bound email proofs using the legacy table shapes."""
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formataddr
import hashlib
import hmac
import re
import secrets
import smtplib
import ssl

import bcrypt

from .legacy_accounts import AccountError, normalize_email, utcnow, validate_password
from .email_templates import verification_content


def configured(settings):
    secret = settings.get('EMAIL_CODE_SECRET') or ''
    return bool(isinstance(secret, str) and len(secret) >= 32 and not secret.startswith('replace_')
                and settings.get('SMTP_HOST') and settings.get('SMTP_HOST') != 'smtp.example.com'
                and (settings.get('SMTP_FROM') or settings.get('SMTP_USERNAME'))
                and (not settings.get('SMTP_USERNAME') or settings.get('SMTP_PASSWORD'))
                and str(settings.get('SMTP_USE_TLS', '1')).lower() not in {'0', 'false', 'no'})


def _ensure(service):
    if not configured(service.settings):
        raise AccountError('邮箱验证码服务尚未配置，请联系管理员。', 503, 'email_unavailable')


def _digest(service, email, purpose, code, user_id):
    # Compatible with the old challenge digest; purpose and identity prevent
    # registration/reset/verification codes from authorizing one another.
    return hmac.new(service.settings['EMAIL_CODE_SECRET'].encode(),
                    f'{purpose}:{user_id}:{email}:{code}'.encode(), hashlib.sha256).hexdigest()


def smtp_send(settings, email, code, purpose):
    subject, plain, html = verification_content(code, purpose, 10, site_url=settings.get('PUBLIC_SITE_URL') or '')
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = formataddr((settings.get('SMTP_FROM_NAME') or '智算视界', settings.get('SMTP_FROM') or settings.get('SMTP_USERNAME')))
    message['To'] = email
    message.set_content(plain)
    message.add_alternative(html, subtype='html')
    try:
        port = int(settings.get('SMTP_PORT') or 465)
        context = ssl.create_default_context()
        implicit = port == 465
        factory = smtplib.SMTP_SSL if implicit else smtplib.SMTP
        options = {'timeout': 15}
        if implicit: options['context'] = context
        with factory(settings['SMTP_HOST'], port, **options) as server:
            if not implicit: server.starttls(context=context)
            if settings.get('SMTP_USERNAME'):
                server.login(settings['SMTP_USERNAME'], settings.get('SMTP_PASSWORD') or '')
            server.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError, TypeError):
        raise AccountError('邮件暂时无法发送，请稍后重试。', 503, 'email_unavailable') from None


def send_code(service, email, purpose, *, requester_ip='', user_id=None):
    email = normalize_email(email)
    if purpose not in {'register', 'verify', 'reset'}:
        raise AccountError('验证码用途无效。')
    _ensure(service)
    if purpose == 'verify' and user_id is None:
        raise AccountError('请先登录。', 401, 'login_required')
    # Caller-supplied user IDs never select registration or reset recipients.
    if purpose != 'verify': user_id = None
    with service.transaction() as cur:
        existing = cur.execute('SELECT id FROM users WHERE email=%s', (email,)).fetchone()
        current = service._row(cur, 'u.id=%s', (user_id,)) if purpose == 'verify' else None
    if purpose == 'verify':
        service._profile(current)
        if current['email_verified'] or (current['email'] and current['email'].lower() != email):
            raise AccountError('邮箱与当前账户不匹配，或已经完成验证。')
        if existing and existing['id'] != user_id:
            raise AccountError('该邮箱已被其他账户使用。', 409, 'account_exists')
    deliver = not existing if purpose == 'register' else bool(existing) if purpose == 'reset' else True
    if purpose == 'reset': user_id = existing['id'] if existing else None
    code = f'{secrets.randbelow(1_000_000):06d}'
    now = utcnow()
    with service.transaction(write=True) as cur:
        service._reserve(cur, [('email-cooldown:' + email, 60, 1), ('email-day:' + email, 86400, 10),
                               ('email-ip:' + (requester_ip or 'unknown'), 86400, 30), ('email-global', 86400, 500)])
        null_clause = 'user_id IS NULL' if user_id is None else 'user_id=%s'
        params = (email, purpose) if user_id is None else (email, purpose, user_id)
        cur.execute(f'UPDATE account_email_codes SET consumed_at=%s WHERE email=%s AND purpose=%s AND {null_clause} AND consumed_at IS NULL', (now, *params))
        cur.execute('''INSERT INTO account_email_codes(user_id,email,purpose,code_hash,expires_at,requester_ip_hash,consumed_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s)''', (user_id, email, purpose, _digest(service, email, purpose, code, user_id),
            now + timedelta(minutes=10), hashlib.sha256((requester_ip or 'unknown').encode()).hexdigest(), None if deliver else now))
        challenge_id = cur.lastrowid
    if deliver:
        try:
            if service.sender: service.sender(email, code, purpose)
            else: smtp_send(service.settings, email, code, purpose)
        except Exception:
            with service.transaction(write=True) as cur:
                cur.execute('UPDATE account_email_codes SET consumed_at=%s WHERE id=%s', (utcnow(), challenge_id))
            # Keep the outward response independent of address existence.
            if purpose == 'verify':
                raise AccountError('邮件暂时无法发送，请稍后重试。', 503, 'email_unavailable') from None
    return dict(message='如果邮箱可用于此操作，验证码将发送到你的邮箱。',
                email=email[:1] + '***@' + email.rsplit('@', 1)[1], retry_after=60)


def _consume(service, email, purpose, code, user_id, action):
    _ensure(service)
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
        raise AccountError('验证码不正确或已过期。', 400, 'email_code_invalid')
    invalid, result = False, None
    with service.transaction(write=True) as cur:
        null_clause = 'user_id IS NULL' if user_id is None else 'user_id=%s'
        params = (email, purpose) if user_id is None else (email, purpose, user_id)
        row = cur.execute(f'''SELECT id,code_hash,attempts FROM account_email_codes WHERE email=%s AND purpose=%s
            AND {null_clause} AND consumed_at IS NULL AND expires_at>%s ORDER BY id DESC LIMIT 1 FOR UPDATE''', (*params, utcnow())).fetchone()
        if not row or row['attempts'] >= 5:
            invalid = True
        elif not hmac.compare_digest(_digest(service, email, purpose, code, user_id), row['code_hash']):
            cur.execute('UPDATE account_email_codes SET attempts=attempts+1 WHERE id=%s', (row['id'],))
            invalid = True
        else:
            result = action(cur)
            cur.execute('UPDATE account_email_codes SET consumed_at=%s WHERE id=%s', (utcnow(), row['id']))
    if invalid:
        raise AccountError('验证码不正确或已过期。', 400, 'email_code_invalid')
    return result


def register(service, username, password, email, code):
    email = normalize_email(email)
    validate_password(password)
    if not isinstance(username, str) or not 1 <= len(username.strip()) <= 64 or any(ord(c) < 32 for c in username):
        raise AccountError('用户名应为 1 至 64 个字符，不能包含控制字符。')
    username = username.strip()
    def create(cur):
        if cur.execute('SELECT id FROM users WHERE username=%s OR email=%s', (username, email)).fetchone():
            raise AccountError('用户名或邮箱已被使用。', 409, 'account_exists')
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        cur.execute('''INSERT INTO users(username,hashed_password,email,email_verified,email_verified_at)
            VALUES(%s,%s,%s,1,%s)''', (username, hashed, email, utcnow()))
        return service._profile(service._row(cur, 'u.id=%s', (cur.lastrowid,)))
    return _consume(service, email, 'register', code, None, create)


def verify(service, user_id, email, code):
    email = normalize_email(email)

    def bind(cur):
        user = service._row(cur, 'u.id=%s', (user_id,), lock=True)
        service._profile(user)
        if user['email_verified'] or (user['email'] and user['email'].lower() != email):
            raise AccountError('邮箱与当前账户不匹配，或已经完成验证。')
        if cur.execute('SELECT id FROM users WHERE email=%s AND id<>%s', (email, user_id)).fetchone():
            raise AccountError('该邮箱已被其他账户使用。', 409, 'account_exists')
        cur.execute('UPDATE users SET email=%s,email_verified=1,email_verified_at=%s WHERE id=%s', (email, utcnow(), user_id))
        return service._profile(service._row(cur, 'u.id=%s', (user_id,)))
    return _consume(service, email, 'verify', code, user_id, bind)


def reset(service, email, code, new_password):
    email = normalize_email(email)
    validate_password(new_password)
    with service.transaction() as cur:
        user = cur.execute('SELECT id FROM users WHERE email=%s', (email,)).fetchone()
    if not user:
        raise AccountError('验证码不正确或已过期。', 400, 'email_code_invalid')
    def change(cur):
        latest = service._row(cur, 'u.id=%s', (user['id'],), lock=True)
        service._profile(latest)
        if not latest['email'] or latest['email'].lower() != email:
            raise AccountError('验证码不正确或已过期。', 400, 'email_code_invalid')
        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(rounds=12)).decode()
        cur.execute('UPDATE users SET hashed_password=%s,email_verified=1,email_verified_at=COALESCE(email_verified_at,%s) WHERE id=%s',
                    (hashed, utcnow(), user['id']))
        return service._profile(service._row(cur, 'u.id=%s', (user['id'],)))
    return _consume(service, email, 'reset', code, user['id'], change)
