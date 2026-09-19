"""Email onboarding/recovery against a disposable MySQL database; mail is captured."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import bcrypt
import mysql.connector
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config, database, email_service as mail, access
from app.request_guard import RequestGuard
from app.routers import auth, accounts
from app.store import SESSION_STORE, CAPTCHA_STORE
from app.usage_guard import UsageLedger


@pytest.fixture(scope='module')
def schema():
    if os.getenv('WISDOM_DATABASE_TESTS') != '1':
        pytest.skip('Requires disposable MySQL schema privileges')
    name = 'qa_email_' + uuid.uuid4().hex
    options = dict(host=config.MYSQL_HOST, port=config.MYSQL_PORT, user=config.MYSQL_USER, password=config.MYSQL_PASSWORD)
    conn = mysql.connector.connect(**options)
    cur = conn.cursor()
    created = False
    try:
        cur.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
        created = True
        cur.execute(f'USE `{name}`')
        from test_baota_upgrade import run_installer
        assert run_installer(cur)['upgrade_status'] == 'OK'
        conn.commit()
        yield lambda: mysql.connector.connect(**options, database=name)
    finally:
        if created:
            conn.rollback()
            assert name.startswith('qa_email_') and len(name) == 41
            cur.execute(f'DROP DATABASE `{name}`')
        cur.close()
        conn.close()


@pytest.fixture
def env(schema, monkeypatch, tmp_path):
    monkeypatch.setattr(database, 'get_db_connection', schema)
    with database.transaction() as (_, cur):
        cur.execute('DELETE FROM account_email_codes')
        cur.execute('DELETE FROM account_email_limits')
        cur.execute('DELETE FROM users')
    monkeypatch.setattr(config, 'EMAIL_CODE_SECRET', 'test-only-email-secret-with-32-characters')
    monkeypatch.setattr(config, 'SMTP_HOST', 'mail.test')
    monkeypatch.setattr(config, 'SMTP_FROM', 'noreply@example.test')
    monkeypatch.setattr(config, 'EMAIL_DAILY_LIMIT', 10)
    monkeypatch.setattr(config, 'EMAIL_SEND_COOLDOWN_SECONDS', 60)
    monkeypatch.setenv('API_REQUESTS_PER_MINUTE', '500')
    monkeypatch.setattr('app.request_guard.ledger', UsageLedger(tmp_path/'usage.sqlite3'))
    sent = []
    monkeypatch.setattr(mail, '_send_message', lambda email, code, purpose: sent.append((email, code, purpose)))
    app = FastAPI()
    app.include_router(auth.router, prefix='/api')
    app.include_router(accounts.router, prefix='/api')
    app.add_middleware(RequestGuard)
    for endpoint in ['/api/user/profile', '/api/formulas', '/api/wrongbook', '/api/solve/stream', '/api/admin/users', '/api/agent/tasks']:
        if endpoint != '/api/admin/users':
            app.add_api_route(endpoint, lambda: {'ok': True}, methods=['GET'])
    with TestClient(app) as client:
        yield client, sent
    with database.transaction() as (_, cur):
        cur.execute('SELECT username FROM users')
        for user in cur.fetchall():
            SESSION_STORE.remove_value(user['username'])


def picture():
    key = uuid.uuid4().hex
    CAPTCHA_STORE[key] = 'ABCD'
    return {'captcha_id': key, 'captcha': 'ABCD'}


def seed(username='old_student', email=None, verified=False, role='member'):
    with database.transaction() as (_, cur):
        cur.execute('INSERT INTO users(username,hashed_password,email,email_verified) VALUES(%s,%s,%s,%s)',
                    (username, bcrypt.hashpw(b'old-password', bcrypt.gensalt(rounds=4)).decode(), email, verified))
        uid = cur.lastrowid
        cur.execute('INSERT INTO account_access(user_id,role) VALUES(%s,%s)', (uid, role))
    return uid


def sign_in(client, username='old_student', password='old-password'):
    return client.post('/api/login', json={'username': username, 'password': password, **picture()})


def test_registration_requires_email_and_preserves_proof_on_retry(env):
    client, sent = env
    body = {'username': 'new_student', 'password': 'new-password'}
    assert client.post('/api/register', json=body).json()['code'] == 'email_verification_required'
    assert client.post('/api/email/send-code', json={'email': 'new@example.test', 'purpose': 'register'}).status_code == 400
    send = client.post('/api/email/send-code', json={'email': 'NEW@example.test', 'purpose': 'register', **picture()})
    assert send.status_code == 200 and sent[-1][1] not in send.text
    body.update(email='new@example.test', email_code=sent[-1][1])
    seed('new_student')
    assert client.post('/api/register', json=body).status_code == 400
    body['username'] = 'new_student_2'
    assert client.post('/api/register', json=body).status_code == 200
    body['username'] = 'replay'
    assert client.post('/api/register', json=body).status_code == 400
    login = sign_in(client, 'new_student_2', 'new-password')
    assert login.json()['email_verified'] is True
    assert client.get('/api/user/profile').status_code == 200
    with database.transaction() as (_, cur):
        cur.execute('SELECT email,email_verified,hashed_password FROM users WHERE username=%s', ('new_student_2',))
        row = cur.fetchone()
        assert row['email'] == 'new@example.test' and row['email_verified']
        assert bcrypt.checkpw(b'new-password', row['hashed_password'].encode())


@pytest.mark.parametrize('role', ['member', 'vip', 'admin'])
def test_old_accounts_are_gated_until_their_own_email_is_verified(env, role):
    client, sent = env
    uid = seed(role=role)
    login = sign_in(client)
    assert login.status_code == 200 and login.json()['email_verified'] is False
    assert client.get('/api/user/me').status_code == 200
    state = client.get('/api/account/access').json()
    assert state['email_verified'] is False and state['can_manage'] is False
    for path in ['/api/user/profile', '/api/formulas', '/api/wrongbook', '/api/solve/stream', '/api/admin/users', '/api/agent/tasks']:
        result = client.get(path)
        assert result.status_code == 403 and result.json()['code'] == 'email_verification_required'
    with pytest.raises(access.AccessDenied, match='邮箱验证'):
        access.consume('calculate', ('test', 'old_student'))
    request = client.post('/api/email/send-code', json={'email': 'old@example.test', 'purpose': 'verify'})
    assert request.status_code == 200
    result = client.post('/api/email/verify', json={'email': 'old@example.test', 'code': sent[-1][1]})
    assert result.status_code == 200
    assert client.get('/api/user/profile').status_code == 200
    assert client.get('/api/user/me').json()['email_verified']
    with database.transaction() as (_, cur):
        cur.execute('SELECT role FROM account_access WHERE user_id=%s', (uid,))
        assert cur.fetchone()['role'] == role


def test_wrong_attempts_persist_and_challenges_expire(env):
    client, sent = env
    mail.issue_code('student@example.test', 'register', requester_ip='test')
    code = sent[-1][1]
    wrong = '000000' if code != '000000' else '111111'
    noop = lambda *args: None
    for _ in range(5):
        with pytest.raises(mail.EmailServiceError):
            mail.verify_code('student@example.test', 'register', wrong, action=noop)
    with database.transaction() as (_, cur):
        cur.execute('SELECT attempts FROM account_email_codes')
        assert cur.fetchone()['attempts'] == 5
    with pytest.raises(mail.EmailServiceError):
        mail.verify_code('student@example.test', 'register', code, action=noop)
    mail.issue_code('expired@example.test', 'register', requester_ip='test')
    with database.transaction() as (_, cur):
        cur.execute('UPDATE account_email_codes SET expires_at=DATE_SUB(UTC_TIMESTAMP(),INTERVAL 1 SECOND)')
    with pytest.raises(mail.EmailServiceError):
        mail.verify_code('expired@example.test', 'register', sent[-1][1], action=noop)


def test_challenge_cannot_cross_accounts_or_purposes(env):
    client, sent = env
    a = seed('a')
    b = seed('b')
    sign_in(client, 'a')
    client.post('/api/email/send-code', json={'email': 'shared@example.test', 'purpose': 'verify'})
    code = sent[-1][1]
    sign_in(client, 'b')
    assert client.post('/api/email/verify', json={'email': 'shared@example.test', 'code': code}).status_code == 400
    assert client.post('/api/register', json={'username': 'intruder', 'password': 'new-password', 'email': 'shared@example.test', 'email_code': code}).status_code == 400
    sign_in(client, 'a')
    assert client.post('/api/email/verify', json={'email': 'shared@example.test', 'code': code}).status_code == 200


def test_signed_in_user_can_change_email_with_new_address_proof(env):
    client, sent = env
    uid = seed(email='old@example.test', verified=True)
    assert sign_in(client).status_code == 200
    request = client.post('/api/email/send-code', json={
        'email': 'new-address@example.test', 'purpose': 'change_email', 'current_password': 'old-password'
    })
    assert request.status_code == 200 and sent[-1][0] == 'new-address@example.test'
    result = client.post('/api/email/change', json={
        'email': 'new-address@example.test', 'code': sent[-1][1], 'current_password': 'old-password'
    })
    assert result.status_code == 200
    with database.transaction() as (_, cur):
        cur.execute('SELECT email,email_verified FROM users WHERE id=%s', (uid,))
        row = cur.fetchone()
        assert row['email'] == 'new-address@example.test' and row['email_verified']
    assert client.get('/api/user/me').json()['email_verified'] is True


def test_email_change_rejects_another_accounts_address(env):
    client, sent = env
    seed(username='first', email='first@example.test', verified=True)
    seed(username='second', email='second@example.test', verified=True)
    assert sign_in(client, 'first').status_code == 200
    result = client.post('/api/email/send-code', json={
        'email': 'second@example.test', 'purpose': 'change_email', 'current_password': 'old-password'
    })
    assert result.status_code == 400


def test_email_change_requires_password_even_with_valid_session_and_code(env):
    client, sent = env
    seed(email='old@example.test', verified=True)
    sign_in(client)
    request={'email':'new@example.test','purpose':'change_email'}
    for password in (None, 'wrong-password', '数'*30):
        assert client.post('/api/email/send-code',json={**request,'current_password':password}).status_code==403
    assert sent==[]
    assert client.post('/api/email/send-code',json={**request,'current_password':'old-password'}).status_code==200
    payload={'email':'new@example.test','code':sent[-1][1]}
    assert client.post('/api/email/change',json=payload).status_code==422
    assert client.post('/api/email/change',json={**payload,'current_password':'wrong-password'}).status_code==403
    assert client.get('/api/user/me').json()['email_address']=='old@example.test'
    # A mistyped current password must not consume a valid email challenge.
    assert client.post('/api/email/change',json={**payload,'current_password':'old-password'}).status_code==200


def test_reset_changes_password_revokes_all_sessions_and_is_one_time(env):
    client, sent = env
    seed(email='bound@example.test', verified=True)
    first = sign_in(client).cookies['auth_session']
    second = sign_in(client).cookies['auth_session']
    result = client.post('/api/password/forgot/request', json={'email': 'BOUND@example.test', 'purpose': 'reset', **picture()})
    assert result.status_code == 200 and sent[-1][1] not in result.text
    body = {'email': 'bound@example.test', 'code': sent[-1][1], 'new_password': 'new-password'}
    assert client.post('/api/password/forgot/reset', json=body).status_code == 200
    assert SESSION_STORE.get(first) is None and SESSION_STORE.get(second) is None
    assert client.get('/api/user/me').status_code == 401
    assert client.post('/api/password/forgot/reset', json=body).status_code == 400
    assert sign_in(client).status_code == 401
    assert sign_in(client, password='new-password').status_code == 200


def test_reset_request_is_neutral_and_alias_has_same_policy(env):
    client, sent = env
    seed(email='exists@example.test', verified=True)
    messages = []
    for email in ['exists@example.test', 'missing@example.test', 'exists@example.test']:
        result = client.post('/api/email/send-code', json={'email': email, 'purpose': 'reset', **picture()})
        assert result.status_code == 200
        messages.append(result.json()['message'])
    assert len(set(messages)) == 1 and len(sent) == 1


def test_concurrent_send_and_consumption_are_serialized(env):
    client, sent = env
    def attempt(_):
        try:
            mail.issue_code('race@example.test', 'register', requester_ip='test')
            return True
        except mail.EmailServiceError:
            return False
    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(attempt, range(4))) == 1
    code = sent[-1][1]
    def redeem(_):
        try:
            mail.verify_code('race@example.test', 'register', code, action=lambda *args: None)
            return True
        except mail.EmailServiceError:
            return False
    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(redeem, range(4))) == 1


def test_send_ip_cap_failed_delivery_and_missing_config(env, monkeypatch):
    client, sent = env
    for n in range(30):
        mail.issue_code(f'person{n}@example.test', 'register', requester_ip='same-ip')
    with pytest.raises(mail.EmailServiceError, match='频繁'):
        mail.issue_code('another@example.test', 'register', requester_ip='same-ip')
    def failed(*args):
        raise mail.EmailDeliveryError('邮件暂时无法发送，请稍后重试。')
    monkeypatch.setattr(mail, '_send_message', failed)
    with pytest.raises(mail.EmailDeliveryError):
        mail.issue_code('failed@example.test', 'register', requester_ip='different-ip')
    with database.transaction() as (_, cur):
        cur.execute("SELECT consumed_at FROM account_email_codes WHERE email='failed@example.test'")
        assert cur.fetchone()['consumed_at'] is not None
    monkeypatch.setattr(config, 'SMTP_HOST', '')
    result = client.post('/api/email/send-code', json={'email': 'clean@example.test', 'purpose': 'register', **picture()})
    assert result.status_code == 503 and '尚未配置' in result.json()['message']
    assert 'code_hash' not in result.text and 'email_code' not in result.text


@pytest.mark.parametrize('email', ['a@b', 'x\r\nBcc: evil@example.test', '..a@example.test', 'a..b@example.test', 'a@-bad.test', 'a@bad..test'])
def test_email_validation_rejects_malformed_addresses(email):
    with pytest.raises(ValueError):
        mail.normalize_email(email)


@pytest.mark.parametrize('purpose, action', [('register', '注册账户'), ('verify', '验证邮箱'),
                                           ('reset', '重置密码'), ('change_email', '更换邮箱')])
def test_smtp_uses_tls_and_contains_only_intended_recipient(monkeypatch, purpose, action):
    from unittest.mock import MagicMock
    monkeypatch.setattr(config, 'EMAIL_CODE_SECRET', 'x'*40)
    monkeypatch.setattr(config, 'SMTP_HOST', 'mail.test')
    monkeypatch.setattr(config, 'SMTP_FROM', 'sender@example.test')
    monkeypatch.setattr(config, 'SMTP_FROM_NAME', '智算视界')
    monkeypatch.setattr(config, 'SMTP_USE_TLS', True)
    monkeypatch.setattr(config, 'SMTP_PORT', 465)
    monkeypatch.setattr(config, 'SMTP_USERNAME', '')
    smtp = MagicMock()
    monkeypatch.setattr(mail.smtplib, 'SMTP_SSL', smtp)
    mail._send_message('student@example.test', '012345', purpose)
    server = smtp.return_value.__enter__.return_value
    message = server.send_message.call_args.args[0]
    assert message['To'] == 'student@example.test'
    # Inspect serialized MIME as an email client receives it, including leading zeroes.
    from email import policy
    from email.parser import BytesParser
    message = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    assert message.get_content_type() == 'multipart/alternative'
    assert '012345' in message.get_body(preferencelist=('plain',)).get_content()
    assert '012345' in message.get_body(preferencelist=('html',)).get_content()
    assert action in message['Subject']
    assert smtp.call_args.kwargs['context'].check_hostname


def test_smtp_auth_failure_is_actionable_and_redacted(monkeypatch, caplog):
    from unittest.mock import MagicMock
    import smtplib
    monkeypatch.setattr(mail, 'ensure_configured', lambda: None)
    monkeypatch.setattr(config, 'SMTP_USERNAME', 'sender@example.test')
    monkeypatch.setattr(config, 'SMTP_PORT', 465)
    monkeypatch.setattr(config, 'SMTP_USE_TLS', True)
    smtp = MagicMock()
    server = smtp.return_value.__enter__.return_value
    server.login.side_effect = smtplib.SMTPAuthenticationError(535, b'private-provider-response')
    monkeypatch.setattr(mail.smtplib, 'SMTP_SSL', smtp)
    with pytest.raises(mail.EmailAuthenticationError) as failure:
        mail._send_message('student@example.test', '123456', 'verify')
    result = auth.service_error(failure.value)
    assert result.status_code == 503
    assert b'email_auth_failed' in result.body
    assert '535' in caplog.text
    assert 'private-provider-response' not in caplog.text + str(failure.value)
    assert b'private-provider-response' not in result.body
    server.send_message.assert_not_called()
