"""Execute the standalone installer in a disposable database, never the user DB."""
import os
import re
import uuid
from pathlib import Path
import mysql.connector
import pytest
from app import config, database
from scripts.build_database_installer import build, manifest
from tests.test_baota_upgrade import run_installer

ROOT=Path(__file__).resolve().parents[1]


def test_generated_upgrade_is_current():
    build(check=True)


def test_panel_upgrade_avoids_mysql8_only_manifest_queries():
    script = (ROOT / 'visdom_db.sql').read_text(encoding='utf-8')
    statements = re.sub(r'^\s*--[^\n]*', '', script, flags=re.M)
    assert not re.search(r'\bJSON_TABLE\s*\(', statements, re.I)
    assert not re.search(r'\bCREATE\s+TEMPORARY\s+TABLE\b', statements, re.I)

def test_installer_contains_every_declared_table():
    script=(ROOT/'visdom_db.sql').read_text(encoding='utf-8')
    declared=set(re.findall(r'^CREATE TABLE IF NOT EXISTS\s+`?(\w+)',script,re.I|re.M))
    application='\n'.join(p.read_text(encoding='utf-8') for directory in ('app','database/migrations') for p in (ROOT/directory).rglob('*') if p.suffix in ('.py','.sql'))
    required=set(re.findall(r'CREATE TABLE IF NOT EXISTS\s+`?(\w+)',application,re.I))
    # Provider leases and background jobs are private SQLite operational stores.
    required-={'usage','leases','math_jobs','provider_circuit','failed_requests'}
    assert required<=declared,required-declared
    assert len(declared)==32
    assert not re.search(r'^\s*(SOURCE|DROP|TRUNCATE)\b',script,re.M|re.I)


@pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS') != '1', reason='Requires disposable MySQL database')
def test_rerun_recovers_install_interrupted_before_version_registration():
    name = 'qa_schema_' + uuid.uuid4().hex
    conn = mysql.connector.connect(host=config.MYSQL_HOST, user=config.MYSQL_USER,
                                   password=config.MYSQL_PASSWORD, port=config.MYSQL_PORT)
    cursor = conn.cursor()
    created = False
    try:
        cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
        created = True
        cursor.execute(f'USE `{name}`')
        sql = (ROOT / 'visdom_db.sql').read_text(encoding='utf-8').split('-- 9.')[0]
        for statement in re.sub(r'^\s*--[^\n]*', '', sql, flags=re.M).split(';'):
            if statement.strip():
                cursor.execute(statement)
                if cursor.with_rows:
                    cursor.fetchall()
        cursor.execute("INSERT INTO users(username,hashed_password) VALUES('interrupted_probe','preserved-hash')")
        cursor.execute('SELECT COUNT(*) FROM schema_migrations')
        assert cursor.fetchone()[0] == 0
        conn.commit()
        for _ in range(2):
            result = run_installer(cursor)
            assert result['upgrade_status'] == 'OK', result
            assert result['applied_migrations'] == 8
            cursor.execute("SELECT hashed_password FROM users WHERE username='interrupted_probe'")
            assert cursor.fetchall() == [('preserved-hash',)]
    finally:
        conn.rollback()
        if created:
            assert re.fullmatch(r'qa_schema_[a-f0-9]{32}', name)
            cursor.execute(f'DROP DATABASE `{name}`')
        cursor.close()
        conn.close()


@pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS')!='1',reason='Requires MySQL create database permission')
def test_one_file_fresh_repeat_and_migration_compatibility(monkeypatch):
    name='qa_schema_'+uuid.uuid4().hex
    settings=dict(host=config.MYSQL_HOST,user=config.MYSQL_USER,password=config.MYSQL_PASSWORD,port=config.MYSQL_PORT)
    connection=mysql.connector.connect(**settings)
    cursor=connection.cursor()
    script=(ROOT/'visdom_db.sql').read_text(encoding='utf-8')
    script=re.sub(r'^\s*--[^\n]*','',script,flags=re.M)
    statements=[s.strip() for s in script.split(';') if s.strip()]
    created=False
    try:
        cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
        created=True
        cursor.execute(f'USE `{name}`')
        for statement in statements:
            cursor.execute(statement)
            if cursor.with_rows: cursor.fetchall()
        cursor.execute('SELECT @wisdom_upgrade_ok');assert cursor.fetchone()[0] == 1
        cursor.execute('SELECT version,checksum,applied_at FROM schema_migrations ORDER BY version')
        migration_records = cursor.fetchall()
        assert len(migration_records) == len(list(database.MIGRATIONS.glob('*.sql')))
        # Ensure the generated structural checker includes every actual field/index/FK.
        for expected in manifest(script):
            cursor.execute('SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', (name, expected['table']))
            assert {r[0] for r in cursor.fetchall()} == set(expected['columns'])
            cursor.execute('SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=%s AND TABLE_NAME=%s', (name, expected['table']))
            assert cursor.fetchone()[0] == len(expected['foreign_keys'])
        cursor.execute('SHOW TABLES');tables=[r[0] for r in cursor.fetchall()]
        assert len(tables)==32
        def structure():
            result={}
            for table in tables:
                cursor.execute(f'SHOW CREATE TABLE `{table}`');result[table]=cursor.fetchone()[1]
            return result
        initial=structure()
        cursor.execute("INSERT INTO users(username,hashed_password) VALUES('bootstrap_probe','not-a-login')")
        connection.commit()
        for statement in statements:
            cursor.execute(statement)
            if cursor.with_rows: cursor.fetchall()
        cursor.execute("SELECT COUNT(*) FROM users WHERE username='bootstrap_probe'");assert cursor.fetchone()[0]==1
        assert structure()==initial or all(re.sub(r' AUTO_INCREMENT=\d+','',v)==re.sub(r' AUTO_INCREMENT=\d+','',initial[k]) for k,v in structure().items())
        before_migrations=structure()
        monkeypatch.setattr(database,'get_db_connection',lambda:mysql.connector.connect(**settings,database=name))
        database.apply_migrations()
        connection.commit()
        assert structure()==before_migrations,'Application startup should not need to add missing tables or indexes'
        cursor.execute('SELECT version,checksum,applied_at FROM schema_migrations ORDER BY version')
        assert cursor.fetchall() == migration_records
        cursor.execute('SELECT COUNT(*) FROM schema_migrations');assert cursor.fetchone()[0]==len(list(database.MIGRATIONS.glob('*.sql')))
        cursor.execute("SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=%s",(name,));assert cursor.fetchone()[0]>=14
    finally:
        if created:
            assert re.fullmatch(r'qa_schema_[a-f0-9]{32}',name)
            cursor.execute(f'DROP DATABASE `{name}`')
        cursor.close();connection.close()


@pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS') != '1', reason='Requires disposable MySQL database')
@pytest.mark.parametrize('scenario', ['previous_29', 'checksum_conflict', 'missing_field'])
def test_upgrade_keeps_account_data_and_does_not_hide_incomplete_schema(scenario):
    name = 'qa_schema_' + uuid.uuid4().hex
    conn = mysql.connector.connect(host=config.MYSQL_HOST, user=config.MYSQL_USER,
                                   password=config.MYSQL_PASSWORD, port=config.MYSQL_PORT)
    cursor = conn.cursor()
    created = False
    try:
        cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
        created = True
        cursor.execute(f'USE `{name}`')
        assert run_installer(cursor)['upgrade_status'] == 'OK'
        cursor.execute("INSERT INTO users(username,hashed_password) VALUES('quota_probe','not-a-login')")
        uid = cursor.lastrowid
        cursor.execute("INSERT INTO account_access(user_id,role,disabled,daily_limit) VALUES(%s,'vip',1,17)", (uid,))
        cursor.execute("UPDATE access_settings SET daily_limit=23,contact_email='custom@example.com' WHERE id=1")
        cursor.execute("INSERT INTO access_usage(principal,period,feature,used) VALUES('user:probe','2026-09-19','calculate',11)")
        cursor.execute("INSERT INTO access_audit(actor_id,target_id,action,details) VALUES(%s,%s,'grant_vip','{}')", (uid, uid))
        cursor.execute("DELETE FROM schema_migrations WHERE version='006_request_records.sql'")
        if scenario == 'previous_29':
            cursor.execute('DROP TABLE request_records')
            cursor.execute('ALTER TABLE schema_migrations CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        elif scenario == 'checksum_conflict':
            cursor.execute("UPDATE schema_migrations SET checksum=REPEAT('f',64) WHERE version='005_account_access.sql'")
        else:
            cursor.execute('ALTER TABLE request_records DROP COLUMN device')
        conn.commit()
        preserved_tables = ('users', 'account_access', 'access_settings', 'access_usage', 'access_audit')
        before = {}
        for table in preserved_tables:
            cursor.execute(f'SELECT * FROM `{table}`')
            before[table] = cursor.fetchall()
        cursor.execute('SELECT version,checksum,applied_at FROM schema_migrations ORDER BY version')
        old_versions = cursor.fetchall()
        for _ in range(2):
            result = run_installer(cursor)
            assert result['upgrade_status'] == ('OK' if scenario == 'previous_29' else 'NEEDS_ATTENTION'), result
            assert result['applied_migrations'] == (8 if scenario == 'previous_29' else 7)
            assert result['migration_conflicts'] == int(scenario == 'checksum_conflict')
            assert result['missing_columns'] == int(scenario == 'missing_field')
            for table in preserved_tables:
                cursor.execute(f'SELECT * FROM `{table}`')
                assert cursor.fetchall() == before[table], table
            cursor.execute("SELECT version,checksum,applied_at FROM schema_migrations WHERE version<>'006_request_records.sql' ORDER BY version")
            assert cursor.fetchall() == old_versions
    finally:
        conn.rollback()
        if created:
            assert re.fullmatch(r'qa_schema_[a-f0-9]{32}', name)
            cursor.execute(f'DROP DATABASE `{name}`')
        cursor.close()
        conn.close()
