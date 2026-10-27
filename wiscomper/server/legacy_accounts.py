"""Compatibility with the old users/account_access schema; no MySQL DDL.

MySQL remains authoritative when selected. Local SQLite is an explicit separate
backend, never an automatic fallback after remote authentication fails.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import threading

import bcrypt
from configuration import normalize_settings


class AccountError(ValueError):
    def __init__(self, message, status=400, code='invalid_request'):
        super().__init__(message)
        self.status, self.code = status, code


def normalize_email(value):
    value = str(value or '').strip().lower()
    if len(value) > 254 or value.count('@') != 1:
        raise AccountError('请输入有效的邮箱地址。')
    local, domain = value.rsplit('@', 1)
    try:
        domain = domain.encode('idna').decode('ascii')
    except UnicodeError:
        raise AccountError('请输入有效的邮箱地址。') from None
    if (not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local)
            or local.startswith('.') or local.endswith('.') or '..' in local
            or len(domain.split('.')) < 2 or len(local + '@' + domain) > 254
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in domain.split('.'))):
        raise AccountError('请输入有效的邮箱地址。')
    return local + '@' + domain


def validate_password(password):
    if not isinstance(password, str) or len(password) < 6 or len(password.encode('utf-8')) > 72:
        raise AccountError('密码至少需要 6 位，且不能超过 72 字节。')
    return password


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Cursor:
    def __init__(self, raw, sqlite=False):
        self.raw, self.sqlite = raw, sqlite

    def execute(self, sql, params=()):
        if self.sqlite:
            sql = sql.replace('%s', '?').replace(' FOR UPDATE', '').replace('BINARY ', '')
            params = tuple(value.isoformat(sep=' ') if isinstance(value, datetime) else value for value in params)
        self.raw.execute(sql, params)
        return self

    def fetchone(self):
        row = self.raw.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.raw.fetchall()]

    @property
    def lastrowid(self):
        return self.raw.lastrowid


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
 hashed_password TEXT NOT NULL, email TEXT UNIQUE,
 email_verified INTEGER NOT NULL DEFAULT 0, email_verified_at TIMESTAMP NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS account_access(
 user_id INTEGER PRIMARY KEY REFERENCES users(id), role TEXT NOT NULL DEFAULT 'member'
 CHECK(role IN ('member','vip','admin')), disabled INTEGER NOT NULL DEFAULT 0,
 daily_limit INTEGER NULL, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS account_email_codes(
 id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NULL REFERENCES users(id),email TEXT NOT NULL,
 purpose TEXT NOT NULL,code_hash TEXT NOT NULL,expires_at TIMESTAMP NOT NULL,consumed_at TIMESTAMP NULL,
 attempts INTEGER NOT NULL DEFAULT 0,requester_ip_hash TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS ix_email_code_lookup ON account_email_codes(email,purpose,created_at);
CREATE TABLE IF NOT EXISTS account_email_limits(bucket TEXT PRIMARY KEY,window_start TIMESTAMP NOT NULL,used INTEGER NOT NULL DEFAULT 0);
"""


class LegacyAccounts:
    def __init__(self, get_settings, get_store, *, sender=None):
        self.get_settings, self.get_store = get_settings, get_store
        self.sender = sender
        self.lock = threading.RLock()
        self._initialized = set()
        self._dummy_hash = bcrypt.hashpw(secrets.token_bytes(24), bcrypt.gensalt(rounds=12))

    @property
    def settings(self):
        return normalize_settings(self.get_settings())

    @property
    def backend(self):
        value = self.settings.get('LEGACY_ACCOUNT_BACKEND', 'sqlite')
        if value not in {'sqlite', 'mysql'}:
            raise AccountError('账户数据库配置无效。', 503, 'account_unavailable')
        return value

    @property
    def path(self):
        return Path(self.get_store().path).with_name('legacy-accounts.sqlite3')

    @property
    def namespace(self):
        if self.backend == 'sqlite':
            source = 'sqlite:' + str(self.path.resolve()).casefold()
        else:
            values = self._mysql_options()
            source = f"mysql:{values['host'].casefold()}:{values['port']}:{values['database']}"
        return hashlib.sha256(source.encode()).hexdigest()[:24]

    def _mysql_options(self):
        settings = self.settings
        try:
            value = {'host': settings.get('LEGACY_MYSQL_HOST', ''),
                     'user': settings.get('LEGACY_MYSQL_USER', ''),
                     'password': settings.get('LEGACY_MYSQL_PASSWORD', ''),
                     'database': settings.get('LEGACY_MYSQL_DATABASE', ''),
                     'port': int(settings.get('LEGACY_MYSQL_PORT') or 3306),
                     'connection_timeout': 5, 'autocommit': False, 'charset': 'utf8mb4'}
            if not all(value[key] for key in ('host', 'user', 'database')) or not 1 <= value['port'] <= 65535:
                raise ValueError()
            return value
        except (TypeError, ValueError):
            raise AccountError('账户数据库配置不完整。', 503, 'account_unavailable') from None

    @contextmanager
    def transaction(self, *, write=False):
        conn = raw = None
        try:
            if self.backend == 'mysql':
                import mysql.connector
                conn = mysql.connector.connect(**self._mysql_options())
                raw = conn.cursor(dictionary=True)
                raw.execute("SET time_zone = '+00:00'")
                conn.start_transaction()
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.path, timeout=10)
                conn.row_factory = sqlite3.Row
                conn.execute('PRAGMA foreign_keys=ON')
                with self.lock:
                    if self.path not in self._initialized:
                        conn.executescript(SQLITE_SCHEMA)
                        self._initialized.add(self.path)
                conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                raw = conn.cursor()
            yield Cursor(raw, self.backend == 'sqlite')
            conn.commit()
        except AccountError:
            if conn: conn.rollback()
            raise
        except Exception as error:
            if conn: conn.rollback()
            if isinstance(error, sqlite3.IntegrityError) or getattr(error, 'errno', None) == 1062:
                raise AccountError('用户名或邮箱已被使用。', 409, 'account_exists') from None
            raise AccountError('账户服务暂不可用，请稍后重试。', 503, 'account_unavailable') from None
        finally:
            if raw: raw.close()
            if conn: conn.close()

    def _row(self, cur, clause, params, *, lock=False):
        return cur.execute("""SELECT u.id,u.username,u.hashed_password,u.email,u.email_verified,u.email_verified_at,
            COALESCE(a.role,'member') AS role,COALESCE(a.disabled,0) AS disabled,a.daily_limit
            FROM users u LEFT JOIN account_access a ON a.user_id=u.id WHERE """ + clause + (' FOR UPDATE' if lock else ''), params).fetchone()

    def _profile(self, row):
        if not row:
            raise AccountError('账户不存在，请重新登录。', 401, 'login_required')
        if row['disabled']:
            raise AccountError('此账户已停用，请联系管理员。', 403, 'account_disabled')
        role = row['role'] if row['role'] in {'member', 'vip', 'admin'} else 'member'
        daily = row.get('daily_limit')
        return dict(id=row['id'], username=row['username'], login=row['username'], name=row['username'],
                    email=row.get('email') or '', email_verified=bool(row.get('email_verified')),
                    role=role, disabled=False, daily_limit=None if daily is None else max(0, int(daily)),
                    auth_provider='email', avatar_url=None, profile_url=None,
                    _credential_version=hashlib.sha256(row['hashed_password'].encode()).hexdigest())

    def get_user(self, user_id):
        with self.transaction() as cur:
            return self._profile(self._row(cur, 'u.id=%s', (user_id,)))

    def _reserve(self, cur, scopes):
        """Fixed windows serialize on durable rows; keys disclose no email/IP."""
        now = utcnow()
        for scope, window, maximum in sorted(scopes):
            key = hashlib.sha256(('wiscomper:' + scope).encode()).hexdigest()
            insert = ('INSERT OR IGNORE INTO account_email_limits(bucket,window_start,used) VALUES(%s,%s,0)' if cur.sqlite else
                      'INSERT IGNORE INTO account_email_limits(bucket,window_start,used) VALUES(%s,%s,0)')
            cur.execute(insert, (key, now))
            row = cur.execute('SELECT window_start,used FROM account_email_limits WHERE bucket=%s FOR UPDATE', (key,)).fetchone()
            started = row['window_start']
            if isinstance(started, str): started = datetime.fromisoformat(started)
            elapsed = (now - started).total_seconds()
            if elapsed >= window:
                cur.execute('UPDATE account_email_limits SET window_start=%s,used=1 WHERE bucket=%s', (now, key))
            elif row['used'] >= maximum:
                raise AccountError('操作过于频繁，请稍后再试。', 429, 'rate_limited')
            else:
                cur.execute('UPDATE account_email_limits SET used=used+1 WHERE bucket=%s', (key,))

    def authenticate(self, identifier, password, requester_ip=''):
        if not isinstance(identifier, str) or not 1 <= len(identifier.strip()) <= 255:
            raise AccountError('用户名、邮箱或密码错误。', 401, 'login_failed')
        identifier = identifier.strip()
        if '@' in identifier:
            try: identifier = normalize_email(identifier)
            except AccountError: pass
        with self.transaction(write=True) as cur:
            self._reserve(cur, [('login-ip:' + (requester_ip or 'unknown'), 900, 60),
                                ('login-id:' + identifier.casefold(), 900, 12)])
        with self.transaction() as cur:
            row = self._row(cur, '(u.username=%s OR u.email=%s)', (identifier, identifier))
        valid = False
        try:
            raw = password.encode() if isinstance(password, str) else b''
            valid = bcrypt.checkpw(raw if 0 < len(raw) <= 72 else b'invalid', row['hashed_password'].encode() if row else self._dummy_hash)
            valid = valid and bool(row) and 0 < len(raw) <= 72
        except (ValueError, TypeError, UnicodeError):
            pass
        if not valid:
            raise AccountError('用户名、邮箱或密码错误。', 401, 'login_failed')
        return self._profile(row)

    def email_status(self):
        from .email_accounts import configured
        ready = configured(self.settings)
        try:
            available = self.backend == 'sqlite' or bool(self._mysql_options())
        except AccountError:
            available = False
        return dict(login_available=available, configured=ready,
                    message='支持邮箱或用户名密码登录。' if ready else '可用邮箱或用户名密码登录；邮箱验证码服务尚未配置。')

    def send_code(self, email, purpose, requester_ip='', user_id=None):
        from .email_accounts import send_code
        return send_code(self, email, purpose, requester_ip=requester_ip, user_id=user_id)

    def register(self, username, password, email, code):
        from .email_accounts import register
        return register(self, username, password, email, code)

    def verify(self, user_id, email, code):
        from .email_accounts import verify
        return verify(self, user_id, email, code)

    def reset(self, email, code, new_password):
        from .email_accounts import reset
        return reset(self, email, code, new_password)

    def import_library(self, user_id, owner):
        from .legacy_import import import_library
        return import_library(self, user_id, owner)
