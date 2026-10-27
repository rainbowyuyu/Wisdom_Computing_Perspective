from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import secrets

import bcrypt
import pytest

from server.legacy_accounts import AccountError, LegacyAccounts, normalize_email, utcnow
from server.storage import Store


@pytest.fixture
def accounts(tmp_path):
    store = Store(tmp_path / 'workspace.sqlite3')
    settings = {'EMAIL_CODE_SECRET': secrets.token_hex(32), 'SMTP_HOST': 'smtp.invalid.test',
                'SMTP_FROM': 'mailer@example.test', 'SMTP_USE_TLS': '1'}
    sent = []
    service = LegacyAccounts(lambda: settings, lambda: store, sender=lambda *args: sent.append(args))
    return service, store, settings, sent


def seed(service, username='old-user', email='old@example.test', password='OldPass!2', *, role=None, verified=True, disabled=False, daily=None):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()
    with service.transaction(write=True) as cur:
        cur.execute('INSERT INTO users(username,hashed_password,email,email_verified) VALUES(%s,%s,%s,%s)', (username, hashed, email, int(verified)))
        ident = cur.lastrowid
        if role:
            cur.execute('INSERT INTO account_access(user_id,role,disabled,daily_limit) VALUES(%s,%s,%s,%s)', (ident, role, int(disabled), daily))
    return ident, hashed


def signin(service, store, ident, profile=None):
    sid, csrf = secrets.token_hex(32), secrets.token_hex(32)
    store.create_session(sid, csrf)
    return store.login_legacy(sid, ident, profile or service.get_user(ident), secrets.token_hex(32), secrets.token_hex(32), namespace=service.namespace)


def test_old_bcrypt_login_email_username_and_live_access_roles(accounts):
    service, _, _, _ = accounts
    ident, hashed = seed(service, username='rainbow_yu')
    for identifier in ['rainbow_yu', 'OLD@EXAMPLE.TEST']:
        user = service.authenticate(identifier, 'OldPass!2')
        assert user['id'] == ident and user['role'] == 'member'
        assert 'hashed_password' not in user and hashed not in json.dumps(user)
    with service.transaction(write=True) as cur:
        cur.execute('INSERT INTO account_access(user_id,role,daily_limit) VALUES(%s,%s,%s)', (ident, 'admin', 0))
    assert service.get_user(ident)['role'] == 'admin'
    assert service.get_user(ident)['daily_limit'] == 0
    with service.transaction(write=True) as cur:
        cur.execute('UPDATE account_access SET role=%s,disabled=1 WHERE user_id=%s', ('member', ident))
    with pytest.raises(AccountError) as rejected:
        service.get_user(ident)
    assert rejected.value.status == 403
    with service.transaction() as cur:
        assert cur.execute('SELECT hashed_password FROM users WHERE id=%s', (ident,)).fetchone()['hashed_password'] == hashed


def test_password_failures_are_generic_and_rate_limited(accounts):
    service, _, _, _ = accounts
    seed(service)
    for value in ['wrong', 'x'*73]:
        with pytest.raises(AccountError) as rejected:
            service.authenticate('old-user', value)
        assert rejected.value.code == 'login_failed'
    with pytest.raises(AccountError) as missing:
        service.authenticate('no-such-user', 'wrong')
    assert missing.value.code == 'login_failed'
    for _ in range(10):
        with pytest.raises(AccountError): service.authenticate('old-user', 'wrong')
    with pytest.raises(AccountError) as limited:
        service.authenticate('old-user', 'OldPass!2')
    assert limited.value.status == 429


def test_registration_consumes_purpose_bound_code_atomically(accounts):
    service, _, _, sent = accounts
    notice = service.send_code('NEW@example.test', 'register', requester_ip='test-peer')
    code = sent[-1][1]
    assert notice['retry_after'] == 60 and code not in json.dumps(notice)
    with service.transaction() as cur:
        stored = cur.execute('SELECT code_hash FROM account_email_codes').fetchone()['code_hash']
    assert code != stored and len(stored) == 64
    with pytest.raises(AccountError): service.reset('new@example.test', code, 'new-password')
    result = service.register('new-user', 'new-password', 'new@example.test', code)
    assert result['email_verified'] and result['role'] == 'member'
    assert service.authenticate('new@example.test', 'new-password')['id'] == result['id']
    with pytest.raises(AccountError): service.register('another', 'new-password', 'new@example.test', code)


def test_wrong_code_attempts_commit_and_expired_codes_fail(accounts):
    service, _, _, sent = accounts
    service.send_code('person@example.test', 'register')
    code = sent[-1][1]
    wrong = '111111' if code != '111111' else '222222'
    for _ in range(5):
        with pytest.raises(AccountError): service.register('person', 'new-password', 'person@example.test', wrong)
    with service.transaction() as cur:
        assert cur.execute('SELECT attempts FROM account_email_codes').fetchone()['attempts'] == 5
    with pytest.raises(AccountError): service.register('person', 'new-password', 'person@example.test', code)
    service.send_code('expired@example.test', 'register')
    expired = sent[-1][1]
    with service.transaction(write=True) as cur:
        cur.execute('UPDATE account_email_codes SET expires_at=%s WHERE email=%s', (utcnow()-timedelta(seconds=1), 'expired@example.test'))
    with pytest.raises(AccountError): service.register('expired', 'new-password', 'expired@example.test', expired)


def test_verification_is_bound_to_signed_in_identity_and_email(accounts):
    service, _, _, sent = accounts
    first, _ = seed(service, email=None, verified=False)
    other, _ = seed(service, username='other-user', email='other@example.test', verified=False)
    service.send_code('binding@example.test', 'verify', user_id=first)
    code = sent[-1][1]
    with pytest.raises(AccountError): service.verify(other, 'binding@example.test', code)
    user = service.verify(first, 'binding@example.test', code)
    assert user['email'] == 'binding@example.test' and user['email_verified']
    assert not service.get_user(other)['email_verified']
    with pytest.raises(AccountError): service.send_code('steal@example.test', 'verify', user_id=first)


def test_reset_changes_credential_stamp_replays_fail_and_sessions_can_be_revoked(accounts):
    service, store, _, sent = accounts
    ident, _ = seed(service)
    _, owner, logged = signin(service, store, ident)
    store.put('job', {'id': 'export-job', 'owner': owner, 'kind': 'export', 'status': 'completed'})
    render_sid = store.render_session(owner, 'export-job', [])
    old_version = logged['user']['_credential_version']
    service.send_code('old@example.test', 'reset')
    code = sent[-1][1]
    user = service.reset('old@example.test', code, 'Replacement!3')
    assert user['_credential_version'] != old_version
    with pytest.raises(AccountError): service.authenticate('old-user', 'OldPass!2')
    assert service.authenticate('old-user', 'Replacement!3')['id'] == ident
    assert store.revoke_legacy_sessions(ident, namespace=service.namespace) == 2
    assert store.session_identity(logged['id']) is None
    assert store.session_identity(render_sid) is None
    assert store.get_legacy_user_id(owner, namespace=service.namespace) == ident
    with pytest.raises(AccountError): service.reset('old@example.test', code, 'AnotherPass!4')


def test_missing_email_does_not_send_and_delivery_failure_invalidates_proof(accounts):
    service, _, _, sent = accounts
    seed(service)
    missing = service.send_code('absent@example.test', 'reset', requester_ip='first')
    assert not sent
    service.sender = lambda *args: (_ for _ in ()).throw(RuntimeError('private SMTP response must not escape'))
    failed = service.send_code('old@example.test', 'reset', requester_ip='second')
    assert missing['message'] == failed['message']
    with service.transaction() as cur:
        rows = cur.execute('SELECT consumed_at FROM account_email_codes').fetchall()
    assert all(row['consumed_at'] for row in rows)


def test_concurrent_registration_consumes_code_once(accounts):
    service, _, _, sent = accounts
    service.send_code('concurrent@example.test', 'register')
    code = sent[-1][1]

    def register(index):
        try: return service.register('user'+str(index), 'new-password', 'concurrent@example.test', code)
        except AccountError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, range(2)))
    assert sum(result is not None for result in results) == 1
    with service.transaction() as cur:
        assert len(cur.execute('SELECT id FROM users').fetchall()) == 1


def test_legacy_and_github_same_name_never_merge_and_source_is_bound(accounts):
    service, store, _, _ = accounts
    ident, _ = seed(service, username='matching')
    sid = secrets.token_hex(32)
    store.create_session(sid, secrets.token_hex(32))
    _, github_owner, _ = store.login_github(sid, 123, {'login': 'matching', 'email': 'old@example.test'}, secrets.token_hex(32), secrets.token_hex(32))
    _, legacy_owner, _ = signin(service, store, ident)
    assert github_owner != legacy_owner
    assert store.get_legacy_user_id(github_owner, namespace=service.namespace) is None
    assert store.get_legacy_user_id(legacy_owner, namespace='0'*24) is None
    assert signin(service, store, ident)[1] == legacy_owner


def test_mysql_failure_never_falls_back_to_local_database(accounts, monkeypatch):
    service, _, settings, _ = accounts
    seed(service)
    settings.update(LEGACY_ACCOUNT_BACKEND='mysql', LEGACY_MYSQL_HOST='db.invalid.test', LEGACY_MYSQL_USER='app', LEGACY_MYSQL_DATABASE='legacy')
    import mysql.connector
    monkeypatch.setattr(mysql.connector, 'connect', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('db password detail')))
    with pytest.raises(AccountError) as failure:
        service.authenticate('old-user', 'OldPass!2')
    assert failure.value.status == 503 and 'password detail' not in str(failure.value)


def test_smtp_configuration_and_tls_multipart_template_are_mocked(accounts, monkeypatch):
    service, _, settings, _ = accounts
    from server.email_accounts import smtp_send
    settings.update(SMTP_USERNAME='mailer@example.test', SMTP_PORT='587')
    assert not service.email_status()['configured']
    settings['SMTP_PASSWORD'] = 'test-placeholder-credential'
    assert service.email_status()['configured']
    events = []

    class MockSMTP:
        def __init__(self, host, port, **kwargs):
            events.append(('connect', host, port))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, context): events.append(('tls',))
        def login(self, username, password): events.append(('login',))
        def send_message(self, message):
            assert message.get_content_type() == 'multipart/alternative'
            plain, html = list(message.iter_parts())
            assert '123456' in plain.get_content() and '123456' in html.get_content()
            assert '<table' in html.get_content() and '<script' not in html.get_content()
            assert 'wiscomper.com' not in html.get_content()
            events.append(('send',))

    monkeypatch.setattr('server.email_accounts.smtplib.SMTP', MockSMTP)
    smtp_send(settings, 'target@example.test', '123456', 'verify')
    assert [event[0] for event in events] == ['connect', 'tls', 'login', 'send']


def test_unlimited_member_usage_is_recorded_and_site_limit_still_applies(accounts):
    _, store, _, _ = accounts
    store.reserve(3, 10, owner='vip-owner', owner_limit=None)
    assert store.usage('vip-owner')['account_reserved'] == 3
    with pytest.raises(ValueError): store.reserve(9, 10, owner='vip-owner', owner_limit=None)
    assert store.usage('vip-owner')['account_reserved'] == 3


def test_owned_legacy_content_import_is_read_only_idempotent_and_preserves_new_edits(accounts):
    service, store, _, _ = accounts
    ident, _ = seed(service)
    _, owner, _ = signin(service, store, ident)
    with service.transaction(write=True) as cur:
        cur.execute('CREATE TABLE formulas(id INTEGER PRIMARY KEY,user_id TEXT,latex TEXT,note TEXT)')
        cur.execute('CREATE TABLE example_video_notes(id INTEGER PRIMARY KEY,user_id TEXT,video_id TEXT,time_sec REAL,content TEXT)')
        cur.execute('INSERT INTO formulas VALUES(1,%s,%s,%s)', ('old-user', 'x^2', '旧说明'))
        cur.execute('INSERT INTO formulas VALUES(2,%s,%s,%s)', ('other-user', 'foreign-secret', 'private'))
        cur.execute('INSERT INTO example_video_notes VALUES(1,%s,%s,%s,%s)', ('old-user', 'old-video', 4.5, '<b>plain note</b>'))
    first = service.import_library(ident, owner)
    assert first['imported'] == 2 and not first['warnings']
    formula = store.list('formula', owner)[0]
    formula['note'] = 'new edited note'
    store.put('formula', formula)
    again = service.import_library(ident, owner)
    assert again['imported'] == 0 and again['skipped'] == 2
    assert store.get('formula', formula['id'], owner)['note'] == 'new edited note'
    note = store.list('learning', owner)[0]
    assert '<b>plain note</b>' in note['note'] and '4.5' in note['note']
    assert not note['project_id'] and note['time_sec'] is None
    with service.transaction() as cur:
        assert cur.execute('SELECT note FROM formulas WHERE id=1').fetchone()['note'] == '旧说明'
        assert len(cur.execute('SELECT id FROM formulas').fetchall()) == 2
    with pytest.raises(AccountError): service.import_library(ident, 'another-owner')


@pytest.mark.parametrize('value', ['x', 'x@localhost', 'a..b@example.test', 'evil\nheader@example.test'])
def test_email_normalization_rejects_unsafe_addresses(value):
    with pytest.raises(AccountError): normalize_email(value)
