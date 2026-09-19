"""Durable, purpose-bound email challenges. Secrets and plaintext codes never leave SMTP."""
from email.message import EmailMessage
from email.utils import formataddr
import hashlib
import hmac
import re
import secrets
import smtplib
import ssl
import logging

from . import config
from .database import transaction
from .email_templates import verification_content


class EmailServiceError(RuntimeError):
    pass


class EmailDeliveryError(EmailServiceError):
    pass


class EmailConfigurationError(EmailDeliveryError):
    pass


class EmailAuthenticationError(EmailConfigurationError):
    pass


class EmailRateLimitError(EmailServiceError):
    pass


def normalize_email(value):
    email = (value or '').strip().lower()
    if len(email) > 254 or email.count('@') != 1:
        raise ValueError('请输入有效的邮箱地址。')
    local, domain = email.rsplit('@', 1)
    try:
        domain = domain.encode('idna').decode('ascii')
    except UnicodeError:
        raise ValueError('请输入有效的邮箱地址。') from None
    labels = domain.split('.')
    if (not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local)
            or local.startswith('.') or local.endswith('.') or '..' in local
            or len(labels) < 2 or len(local + '@' + domain) > 254
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)):
        raise ValueError('请输入有效的邮箱地址。')
    return local + '@' + domain


def mask_email(email):
    if not email or '@' not in email:
        return ''
    local, domain = email.split('@', 1)
    return local[:1] + '***@' + domain


def _secret():
    secret = config.EMAIL_CODE_SECRET
    if len(secret) < 32 or secret.startswith('replace_'):
        raise EmailConfigurationError('邮箱服务尚未配置，请联系作者。')
    return secret.encode()


def ensure_configured():
    _secret()
    if not config.SMTP_HOST or not config.SMTP_FROM or config.SMTP_HOST == 'smtp.example.com':
        raise EmailConfigurationError('邮箱服务尚未配置，请联系作者。')


def _digest(email, purpose, code, user_id):
    return hmac.new(_secret(), f'{purpose}:{user_id}:{email}:{code}'.encode(), hashlib.sha256).hexdigest()


def _send_message(email, code, purpose, *, preview=False):
    ensure_configured()
    subject, plain, html = verification_content(
        code, purpose, max(60, min(config.EMAIL_CODE_EXPIRE_SECONDS, 900)) // 60, preview=preview)
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = formataddr((config.SMTP_FROM_NAME, config.SMTP_FROM))
    message['To'] = email
    message.set_content(plain)
    message.add_alternative(html, subtype='html')
    context = ssl.create_default_context()
    try:
        implicit_tls = config.SMTP_USE_TLS and config.SMTP_PORT == 465
        factory = smtplib.SMTP_SSL if implicit_tls else smtplib.SMTP
        kwargs = {'timeout': 15}
        if implicit_tls:
            kwargs['context'] = context
        with factory(config.SMTP_HOST, config.SMTP_PORT, **kwargs) as server:
            if config.SMTP_USE_TLS and not implicit_tls:
                server.starttls(context=context)
            if config.SMTP_USERNAME:
                server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        # Log only the status, never credentials or the provider's raw response.
        logging.getLogger(__name__).warning('SMTP authentication rejected (status %s)', exc.smtp_code)
        raise EmailAuthenticationError('发信邮箱认证失败，请联系作者检查发信账号与邮箱授权码是否匹配。') from None
    except (OSError, smtplib.SMTPException, ValueError):
        raise EmailDeliveryError('邮件暂时无法发送，请稍后重试。') from None


def _reserve(cur, email, ip, user_id):
    # Row locks serialize shared limits across processes and simultaneous send requests.
    # The global cap bounds sending to many distinct addresses; all purposes share limits.
    limits = [
        ('cooldown:' + email, max(60, config.EMAIL_SEND_COOLDOWN_SECONDS), 1),
        ('email:' + email, 86400, max(1, min(config.EMAIL_DAILY_LIMIT, 30))),
        ('ip:' + ip, 86400, 30),
        ('global', 86400, 500),
    ]
    if user_id is not None:
        limits.append(('user:' + str(user_id), 86400, 10))
    for scope, window, maximum in sorted(limits):
        key = hashlib.sha256(scope.encode()).hexdigest()
        cur.execute('''INSERT INTO account_email_limits(bucket,window_start,used)
            VALUES(%s,UTC_TIMESTAMP(),0) ON DUPLICATE KEY UPDATE bucket=bucket''', (key,))
        cur.execute('''SELECT used,TIMESTAMPDIFF(SECOND,window_start,UTC_TIMESTAMP()) AS elapsed
            FROM account_email_limits WHERE bucket=%s FOR UPDATE''', (key,))
        row = cur.fetchone()
        if row['elapsed'] >= window:
            cur.execute('UPDATE account_email_limits SET window_start=UTC_TIMESTAMP(),used=1 WHERE bucket=%s', (key,))
        elif row['used'] >= maximum:
            raise EmailRateLimitError('验证码获取过于频繁，请稍后再试。')
        else:
            cur.execute('UPDATE account_email_limits SET used=used+1 WHERE bucket=%s', (key,))


def issue_code(email, purpose, *, user_id=None, requester_ip='', deliver=True):
    email = normalize_email(email)
    if purpose not in {'register', 'verify', 'reset', 'change_email'}:
        raise ValueError('请求无效。')
    ensure_configured()
    code = f'{secrets.randbelow(1_000_000):06d}'
    code_hash = _digest(email, purpose, code, user_id)
    with transaction() as (_, cur):
        _reserve(cur, email, requester_ip or 'unknown', user_id)
        # Binding to the user prevents a challenge issued under one account from
        # verifying another. New sends invalidate only this account/purpose.
        cur.execute('''UPDATE account_email_codes SET consumed_at=UTC_TIMESTAMP()
            WHERE email=%s AND purpose=%s AND user_id <=> %s AND consumed_at IS NULL''',
            (email, purpose, user_id))
        cur.execute('''INSERT INTO account_email_codes
            (user_id,email,purpose,code_hash,expires_at,requester_ip_hash,consumed_at)
            VALUES(%s,%s,%s,%s,DATE_ADD(UTC_TIMESTAMP(),INTERVAL %s SECOND),%s,
                IF(%s, NULL, UTC_TIMESTAMP()))''',
            (user_id, email, purpose, code_hash, max(60, min(config.EMAIL_CODE_EXPIRE_SECONDS, 900)),
             hashlib.sha256((requester_ip or 'unknown').encode()).hexdigest(), deliver))
        code_id = cur.lastrowid
    if deliver:
        try:
            _send_message(email, code, purpose)
        except EmailDeliveryError:
            with transaction() as (_, cur):
                cur.execute('UPDATE account_email_codes SET consumed_at=UTC_TIMESTAMP() WHERE id=%s', (code_id,))
            raise
    return email


def prune_expired():
    """Startup maintenance kept outside issuance transactions and their row locks."""
    with transaction() as (_, cur):
        cur.execute('DELETE FROM account_email_codes WHERE created_at < DATE_SUB(UTC_TIMESTAMP(),INTERVAL 2 DAY)')
        cur.execute('DELETE FROM account_email_limits WHERE window_start < DATE_SUB(UTC_TIMESTAMP(),INTERVAL 2 DAY)')


def verify_code(email, purpose, code, *, user_id=None, action):
    """Consume and mutate the account in ONE transaction; failed attempts commit."""
    email = normalize_email(email)
    code = (code or '').strip()
    if not re.fullmatch(r'[0-9]{6}', code):
        raise EmailServiceError('验证码不正确或已过期。')
    invalid = False
    result = None
    with transaction() as (conn, cur):
        cur.execute('''SELECT * FROM account_email_codes
            WHERE email=%s AND purpose=%s AND user_id <=> %s AND consumed_at IS NULL
              AND expires_at > UTC_TIMESTAMP()
            ORDER BY id DESC LIMIT 1 FOR UPDATE''', (email, purpose, user_id))
        row = cur.fetchone()
        if not row or row['attempts'] >= 5:
            invalid = True
        elif not hmac.compare_digest(_digest(email, purpose, code, user_id), row['code_hash']):
            cur.execute('UPDATE account_email_codes SET attempts=attempts+1 WHERE id=%s', (row['id'],))
            invalid = True
        else:
            result = action(conn, cur, row)
            cur.execute('UPDATE account_email_codes SET consumed_at=UTC_TIMESTAMP() WHERE id=%s', (row['id'],))
    # Do not raise inside transaction: that would roll back failed-attempt counters.
    if invalid:
        raise EmailServiceError('验证码不正确或已过期。')
    return result
