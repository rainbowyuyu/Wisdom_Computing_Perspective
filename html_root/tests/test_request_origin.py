"""Browser origins at the TLS proxy must not be compared to its internal host."""
from unittest.mock import Mock

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.request_guard import RequestGuard
from app.request_origin import origin_allowed, public_scheme
from app.routers import auth
from app.store import CAPTCHA_STORE, SESSION_STORE
from app.usage_guard import UsageLedger


@pytest.fixture(autouse=True)
def origin_environment(monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS', '')
    monkeypatch.setenv('TRUSTED_PROXY_IPS', '127.0.0.1, ::1 ')


@pytest.mark.parametrize('scheme,peer,headers,expected', [
    ('http', '127.0.0.1', {'host':'127.0.0.1:8000', 'origin':'https://www.wiscomper.com', 'sec-fetch-site':'same-origin'}, True),
    ('http', '127.0.0.1', {'host':'127.0.0.1:8000', 'origin':'https://school.example:8443', 'x-forwarded-host':'school.example:8443', 'x-forwarded-proto':'https'}, True),
    ('http', '::1', {'host':'school.example', 'origin':'https://school.example', 'x-forwarded-proto':'https'}, True),
    ('https', '203.0.113.10', {'host':'School.Example:443', 'origin':'https://school.example'}, True),
    ('http', '203.0.113.10', {'host':'127.0.0.1:8000', 'origin':'http://127.0.0.1:8000'}, True),
    ('http', '203.0.113.10', {'host':'127.0.0.1:8000', 'origin':'http://localhost:5173'}, True),
    ('http', '203.0.113.10', {'host':'school.example', 'origin':'https://evil.invalid', 'x-forwarded-host':'evil.invalid', 'x-forwarded-proto':'https'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'https://school.example:8443', 'x-forwarded-proto':'https'}, False),
    ('https', '203.0.113.10', {'host':'school.example', 'origin':'http://school.example'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'https://evil.invalid', 'sec-fetch-site':'same-origin'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'null'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'https://[bad'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'http://school.example:bad'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'http://user@school.example'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'http://school.example/path'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'https://evil.invalid https://school.example'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'http://school.example', 'x-forwarded-host':'evil.invalid, school.example'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'https://www.wiscomper.com.evil.invalid'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'origin':'http://www.wiscomper.com'}, False),
    ('http', '127.0.0.1', {'host':'school.example', 'sec-fetch-site':'cross-site'}, False),
    ('http', '127.0.0.1', {'host':'school.example'}, True),
])
def test_origin_checks(scheme, peer, headers, expected):
    assert origin_allowed({'scheme':scheme, 'client':(peer, 12345)}, headers) is expected


def test_explicit_allowlist_replaces_production_default(monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS', ' https://other.example:8443/ ')
    scope = {'scheme':'http', 'client':('203.0.113.10', 12345)}
    assert origin_allowed(scope, {'host':'internal', 'origin':'https://other.example:8443', 'sec-fetch-site':'cross-site'})
    assert not origin_allowed(scope, {'host':'internal', 'origin':'https://www.wiscomper.com'})
    assert not origin_allowed(scope, {'host':'internal', 'origin':'https://other.example'})


def test_forwarded_scheme_is_only_trusted_from_configured_proxy():
    assert public_scheme({'scheme':'http', 'client':('203.0.113.10', 1)}, {'x-forwarded-proto':'https'}) == 'http'
    assert public_scheme({'scheme':'http', 'client':('::1', 1)}, {'x-forwarded-proto':'https'}) == 'https'


@pytest.mark.parametrize('base_url,origin,proxy_headers,secure', [
    ('http://127.0.0.1:8000', 'https://www.wiscomper.com', {'x-forwarded-proto':'https'}, True),
    ('http://127.0.0.1:8000', 'http://127.0.0.1:8000', {}, False),
    ('http://localhost:8000', 'http://localhost:8000', {}, False),
    ('http://127.0.0.1:8000', 'http://localhost:5173', {}, False),
])
def test_origin_reaches_real_login_and_sets_correct_session_cookie(monkeypatch, tmp_path, base_url, origin, proxy_headers, secure):
    monkeypatch.setattr('app.request_guard.ledger', UsageLedger(tmp_path / 'usage.sqlite3'))
    monkeypatch.setenv('API_REQUESTS_PER_MINUTE', '30')
    username = 'origin_regression_user'
    cursor = Mock()
    cursor.fetchone.return_value = {'username':username, 'hashed_password':bcrypt.hashpw(b'test-only-password', bcrypt.gensalt(rounds=4)).decode()}
    conn = Mock()
    conn.cursor.return_value = cursor
    monkeypatch.setattr(auth, 'get_db_connection', lambda:conn)
    monkeypatch.setattr('app.access.load_principal', lambda _: {'id':1, 'username':username, 'role':'member'})
    app = FastAPI()
    app.add_middleware(RequestGuard)
    app.include_router(auth.router, prefix='/api')
    captcha_id = 'origin-regression-captcha'
    CAPTCHA_STORE[captcha_id] = 'ABCD'
    session = None
    try:
        with TestClient(app, base_url=base_url, client=('127.0.0.1', 12345)) as client:
            headers = {'origin':origin, 'sec-fetch-site':'same-origin', **proxy_headers}
            data = {'username':username, 'password':'test-only-password', 'captcha':'ABCD', 'captcha_id':captcha_id}
            blocked = client.post('/api/login', headers={**headers, 'origin':'https://evil.invalid'}, json=data)
            assert blocked.status_code == 403
            assert CAPTCHA_STORE.get(captcha_id) == 'ABCD'
            cursor.execute.assert_not_called()
            response = client.post('/api/login', headers=headers, json=data)
            assert response.status_code == 200, response.text
            assert response.json()['username'] == username
            session = response.cookies['auth_session']
            assert SESSION_STORE.get(session) == username
            cookies = response.headers.get_list('set-cookie')
            for name in ('auth_session=', 'wisdom_trial='):
                cookie = next(cookie for cookie in cookies if name in cookie)
                assert 'HttpOnly' in cookie and 'samesite=lax' in cookie.lower()
                assert ('Secure' in cookie) is secure
    finally:
        CAPTCHA_STORE.pop(captcha_id, None)
        if session:
            SESSION_STORE.pop(session, None)
