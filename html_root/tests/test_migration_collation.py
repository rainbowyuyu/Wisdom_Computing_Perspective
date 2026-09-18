"""BaoTa collation fallback must preserve migration hashes and existing records."""
import hashlib
import os
import re
import uuid
from contextlib import contextmanager
from unittest.mock import Mock

import mysql.connector
import pytest
from fastapi.testclient import TestClient
from app import config, database


@pytest.mark.parametrize('names,expected', [
    (['utf8mb4_general_ci'], 'utf8mb4_general_ci'),
    (['utf8mb4_general_ci', 'utf8mb4_0900_ai_ci'], 'utf8mb4_0900_ai_ci'),
])
def test_select_supported_collation(names, expected):
    cursor = Mock()
    cursor.fetchall.return_value = [{'name': name} for name in names]
    assert database.migration_collation(cursor) == expected


def test_missing_utf8_support_has_actionable_error():
    cursor = Mock()
    cursor.fetchall.return_value = []
    with pytest.raises(RuntimeError, match='utf8mb4'):
        database.migration_collation(cursor)


@pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS') != '1', reason='Requires disposable MySQL database')
@pytest.mark.parametrize('supports_0900', [False, True])
def test_real_migration_and_startup_with_server_capability_filter(monkeypatch, tmp_path, supports_0900):
    name = 'qa_collation_' + uuid.uuid4().hex
    options = dict(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                   user=config.MYSQL_USER, password=config.MYSQL_PASSWORD)
    admin = mysql.connector.connect(**options)
    cursor = admin.cursor()
    created = False
    source = database.MIGRATIONS / '001_learning_records.sql'
    original = source.read_text(encoding='utf-8')
    migrations = tmp_path / 'migrations'
    migrations.mkdir()
    (migrations / source.name).write_text(original, encoding='utf-8')

    class CapabilityCursor:
        """Run real SQL, but emulate an older server's available collations."""
        def __init__(self, real):
            self.real = real

        def execute(self, statement, params=None):
            if 'FROM information_schema.COLLATIONS' in statement and not supports_0900:
                statement = "SELECT 'utf8mb4_general_ci' AS name"
            elif not supports_0900 and re.search(r'COLLATE\s*=\s*utf8mb4_0900_ai_ci', statement, re.I):
                raise mysql.connector.DatabaseError("Unknown collation: 'utf8mb4_0900_ai_ci'", errno=1273)
            return self.real.execute(statement, params)

        def __getattr__(self, name):
            return getattr(self.real, name)

    @contextmanager
    def isolated_transaction():
        conn = mysql.connector.connect(**options, database=name)
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SET time_zone = '+00:00'")
            yield conn, CapabilityCursor(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    try:
        cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
        created = True
        cursor.execute(f'USE `{name}`')
        cursor.execute('CREATE TABLE users(id INT PRIMARY KEY, username VARCHAR(255) NOT NULL) ENGINE=InnoDB')
        cursor.execute('CREATE TABLE formulas(id INT PRIMARY KEY) ENGINE=InnoDB')
        cursor.execute('''CREATE TABLE user_wrongbook(id INT PRIMARY KEY, user_id VARCHAR(255),
            video_id VARCHAR(256), time_sec INT, title VARCHAR(512), note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB''')
        cursor.execute("INSERT INTO users VALUES(1,'original_user')")
        cursor.execute("INSERT INTO user_wrongbook(id,user_id,video_id,time_sec,title,note) VALUES(1,'original_user','video',4,'旧错题','原笔记')")
        admin.commit()
        monkeypatch.setattr(database, 'transaction', isolated_transaction)
        monkeypatch.setattr(database, 'MIGRATIONS', migrations)
        monkeypatch.setattr(database, 'INDEXES', {})
        # This is the actual FastAPI lifespan that failed in the supplied traceback.
        import main
        monkeypatch.setattr(config, 'db_pool', object())
        for _ in range(2):
            with TestClient(main.app) as client:
                assert client.get('/').status_code == 200
                assert client.get('/api/captcha').status_code == 200
        admin.commit()
        cursor.execute('SELECT title,note FROM learning_wrongbook')
        assert cursor.fetchall() == [('旧错题', '原笔记')]
        cursor.execute('SELECT COUNT(*) FROM user_wrongbook')
        assert cursor.fetchone()[0] == 1
        cursor.execute('SELECT version,checksum FROM schema_migrations')
        assert cursor.fetchall() == [(source.name, hashlib.sha256(original.encode()).hexdigest())]
        cursor.execute("SELECT TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 'learning_wrongbook%'")
        assert {row[0] for row in cursor.fetchall()} == {'utf8mb4_0900_ai_ci' if supports_0900 else 'utf8mb4_general_ci'}
        cursor.execute("SELECT COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='learning_wrongbook' AND COLUMN_NAME='fingerprint'")
        assert cursor.fetchone()[0] == 'ascii_bin'
        assert source.read_text(encoding='utf-8') == original
    finally:
        admin.rollback()
        if created:
            assert re.fullmatch(r'qa_collation_[a-f0-9]{32}', name)
            cursor.execute(f'DROP DATABASE `{name}`')
        cursor.close()
        admin.close()
