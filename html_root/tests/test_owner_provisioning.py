"""Explicit owner provisioning preserves passwords, quotas, and other accounts."""
import os
import re
import uuid
from pathlib import Path

import mysql.connector
import pytest

from app import config
from tests.test_baota_upgrade import run_installer

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS') != '1', reason='Requires disposable MySQL database')


@pytest.mark.parametrize('owner_exists', [True, False])
def test_explicit_owner_grant(owner_exists):
    name = 'qa_owner_' + uuid.uuid4().hex
    conn = mysql.connector.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                                   user=config.MYSQL_USER, password=config.MYSQL_PASSWORD)
    cur = conn.cursor()
    created = False
    try:
        cur.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
        created = True
        cur.execute(f'USE `{name}`')
        assert run_installer(cur)['upgrade_status'] == 'OK'
        # Similar spelling must not grant the protected identity on CI collations.
        username = 'rainbow_yu' if owner_exists else 'Rainbow_yu'
        cur.execute('INSERT INTO users(username,hashed_password) VALUES(%s,%s)', (username, 'existing-hash-unchanged'))
        uid = cur.lastrowid
        cur.execute("INSERT INTO account_access(user_id,role,disabled,daily_limit) VALUES(%s,'member',1,17)", (uid,))
        cur.execute("INSERT INTO users(username,hashed_password) VALUES('other_student','other-hash')")
        other_id = cur.lastrowid
        cur.execute("INSERT INTO account_access(user_id,role) VALUES(%s,'vip')", (other_id,))
        cur.execute("INSERT INTO access_usage(principal,period,feature,used) VALUES(%s,'2026-09-19','all',12)", ('u:'+str(uid),))
        conn.commit()
        sql = (ROOT / 'deploy/grant_owner.sql').read_text(encoding='utf-8')
        statements = re.sub(r'^\s*--[^\n]*', '', sql, flags=re.M).split(';')
        for _ in range(2):
            status = None
            for statement in statements:
                if statement.strip():
                    cur.execute(statement)
                    if cur.with_rows:
                        rows = cur.fetchall()
                        if cur.column_names == ('owner_status',):
                            status = rows[0][0]
            assert status == ('OWNER_ENABLED' if owner_exists else 'ACCOUNT_NOT_FOUND')
        cur.execute('SELECT role,disabled,daily_limit FROM account_access WHERE user_id=%s', (uid,))
        assert cur.fetchone() == (('admin', 0, 17) if owner_exists else ('member', 1, 17))
        cur.execute('SELECT hashed_password FROM users WHERE id=%s', (uid,))
        assert cur.fetchone()[0] == 'existing-hash-unchanged'
        cur.execute('SELECT role FROM account_access WHERE user_id=%s', (other_id,))
        assert cur.fetchone()[0] == 'vip'
        cur.execute('SELECT used FROM access_usage')
        assert cur.fetchone()[0] == 12
        cur.execute("SELECT COUNT(*) FROM access_audit WHERE action='provision_admin' AND target_id=%s", (uid,))
        assert cur.fetchone()[0] == (2 if owner_exists else 0)
    finally:
        conn.rollback()
        if created:
            assert re.fullmatch(r'qa_owner_[a-f0-9]{32}', name)
            cur.execute(f'DROP DATABASE `{name}`')
        cur.close()
        conn.close()
