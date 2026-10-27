import json
from pathlib import Path

import pytest

from deploy.preflight import REQUIRED_COLUMNS, check_deployment, main


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []
        self.closed = False

    def execute(self, sql, params):
        assert sql.startswith('SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS')
        assert sql.count('%s') == 5
        self.queries.append((sql, params))

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, rows=None):
        self.cur = FakeCursor(rows if rows is not None else [(table, column) for table, columns in REQUIRED_COLUMNS.items() for column in columns])
        self.closed = False
        self.options = None

    def connect(self, **options):
        self.options = options
        return self

    def cursor(self):
        return self.cur

    def close(self):
        self.closed = True


@pytest.fixture
def legacy(tmp_path):
    target = tmp_path / 'site'
    target.mkdir()
    (target / '.env').write_text('MYSQL_HOST=localhost\nMYSQL_PORT=3306\nMYSQL_DB=existing_db\nMYSQL_USER=old_user\nMYSQL_PASSWORD="not-a-real-db-password"\nALIYUN_KEY=not-a-real-qwen-key\n', encoding='utf-8')
    return target


def check(target, db=None, environ=None, **kwargs):
    db = db or FakeConnection()
    return check_deployment(target, environ={} if environ is None else environ, connect=db.connect,
                            which=lambda _: None, find_spec=lambda _: None, **kwargs), db


def codes(result):
    return {item['code'] for item in result['checks']}


def test_legacy_schema_check_is_read_only_and_keeps_files(legacy):
    before = {p.relative_to(legacy): p.read_bytes() for p in legacy.rglob('*') if p.is_file()}
    result, db = check(legacy)
    assert result['ok']
    assert 'MYSQL_SCHEMA_READY' in codes(result)
    assert len(db.cur.queries) == 1
    assert db.cur.queries[0][1][0] == 'existing_db'
    assert db.options['password'] == 'not-a-real-db-password'
    assert db.closed and db.cur.closed
    assert {p.relative_to(legacy): p.read_bytes() for p in legacy.rglob('*') if p.is_file()} == before
    assert not (legacy / 'var').exists()
    outward = json.dumps(result)
    assert 'not-a-real-db-password' not in outward and 'not-a-real-qwen-key' not in outward
    assert 'existing_db' not in outward and 'old_user' not in outward


def test_missing_schema_blocks_deployment_and_names_exact_columns(legacy):
    db = FakeConnection([('users', 'id')])
    result, _ = check(legacy, db)
    assert not result['ok']
    message = next(item['message'] for item in result['checks'] if item['code'] == 'MYSQL_SCHEMA_MISSING')
    assert 'users.hashed_password' in message and 'account_email_limits.bucket' in message
    assert db.closed and db.cur.closed


@pytest.mark.parametrize('override,expected', [
    ('PUBLIC_SITE_URL=\n', 'PUBLIC_SITE_CONFLICT'),
    ('PUBLIC_SITE_URL=http://127.0.0.1:8000\n', 'PUBLIC_SITE_CONFLICT'),
    ('PUBLIC_SITE_URL=https://other-wiscomper.com\n', 'PUBLIC_SITE_CONFLICT'),
    ('PORT=3088\n', 'PORT_CONFLICT'),
    ('LEGACY_ACCOUNT_BACKEND=sqlite\n', 'ACCOUNT_BACKEND_CONFLICT'),
    ('MYSQL_PORT=bad\n', 'MYSQL_PORT_INVALID'),
    ('ALIYUN_KEY=\n', 'QWEN_KEY_MISSING'),
    ('VISUALIZATION_QWEN_BASE_URL=https://third-party.example/v1\n', 'QWEN_CONFIG_INVALID'),
])
def test_existing_configuration_cannot_be_silently_overridden(legacy, override, expected):
    with (legacy / '.env.local').open('w', encoding='utf-8') as stream:
        stream.write(override)
    result, _ = check(legacy)
    assert not result['ok'] and expected in codes(result)


def test_environment_and_existing_deploy_file_are_read(legacy):
    (legacy / '.env.deploy').write_text('PUBLIC_SITE_URL=https://deploy-wiscomper.com\nVISUALIZE_PORT=8000\n', encoding='utf-8')
    result, _ = check(legacy, environ={'PUBLIC_SITE_URL': 'https://www.wiscomper.com', 'PORT': '8123'}, port=8123)
    assert result['ok']


def test_ai_disabled_does_not_require_key_or_call_provider(legacy):
    result, _ = check(legacy, environ={'AI_ENABLED': '0', 'ALIYUN_KEY': ''})
    assert result['ok'] and 'AI_DISABLED' in codes(result)
    assert 'QWEN_KEY_MISSING' not in codes(result)


def test_mysql_exception_never_discloses_credentials(legacy):
    class FakeError(Exception):
        errno = 1045

    def failing_connect(**_):
        raise FakeError('password=do-not-show user=private-user')

    result = check_deployment(legacy, environ={}, connect=failing_connect, which=lambda _: None, find_spec=lambda _: None)
    assert not result['ok'] and 'MYSQL_AUTH_FAILED' in codes(result)
    assert 'do-not-show' not in json.dumps(result) and 'private-user' not in json.dumps(result)


def test_missing_target_or_env_does_not_connect(tmp_path):
    def denied_connect(**_):
        pytest.fail('must not connect')

    for target, code in ((tmp_path / 'missing', 'TARGET_INVALID'), (tmp_path, 'ENV_MISSING')):
        result = check_deployment(target, environ={}, connect=denied_connect)
        assert not result['ok'] and code in codes(result)


def test_missing_database_configuration_does_not_connect(legacy):
    db = FakeConnection()
    result, _ = check(legacy, db, environ={'MYSQL_USER': ''})
    assert not result['ok'] and 'MYSQL_CONFIG_MISSING' in codes(result)
    assert db.options is None


def test_cli_failure_is_nonzero_without_reading_real_settings(tmp_path, capsys):
    assert main(['--target', str(tmp_path / 'missing'), '--json']) == 1
    output = json.loads(capsys.readouterr().out)
    assert output['ok'] is False


def test_smtp_github_optional_configuration_only(legacy):
    result, _ = check(legacy, environ={'SMTP_HOST': 'smtp.invalid.test', 'SMTP_USERNAME': 'mailer@example.test',
                         'SMTP_PASSWORD': 'not-a-real-smtp-password', 'EMAIL_CODE_SECRET': 'x'*32,
                         'GITHUB_CLIENT_ID': 'not-real', 'GITHUB_CLIENT_SECRET': 'not-a-real-github-secret'})
    assert result['ok']
    assert {'SMTP_CONFIG_PRESENT', 'GITHUB_CONFIG_PRESENT'} <= codes(result)
    assert 'not-a-real' not in json.dumps(result)
