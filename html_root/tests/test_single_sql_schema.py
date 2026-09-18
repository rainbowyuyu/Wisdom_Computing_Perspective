"""Execute the standalone installer in a disposable database, never the user DB."""
import os
import re
import uuid
from pathlib import Path
import mysql.connector
import pytest
from app import config, database

ROOT=Path(__file__).resolve().parents[1]

def test_installer_contains_every_declared_table():
    script=(ROOT/'visdom_db.sql').read_text(encoding='utf-8')
    declared=set(re.findall(r'^CREATE TABLE IF NOT EXISTS\s+`?(\w+)',script,re.I|re.M))
    application='\n'.join(p.read_text(encoding='utf-8') for directory in ('app','database/migrations') for p in (ROOT/directory).rglob('*') if p.suffix in ('.py','.sql'))
    required=set(re.findall(r'CREATE TABLE IF NOT EXISTS\s+`?(\w+)',application,re.I))
    assert required<=declared,required-declared
    assert len(declared)==25
    assert not re.search(r'^\s*(SOURCE|DROP|TRUNCATE)\b',script,re.M|re.I)

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
        cursor.execute('SHOW TABLES');tables=[r[0] for r in cursor.fetchall()]
        assert len(tables)==25
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
        cursor.execute('SELECT COUNT(*) FROM schema_migrations');assert cursor.fetchone()[0]==len(list(database.MIGRATIONS.glob('*.sql')))
        cursor.execute("SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=%s",(name,));assert cursor.fetchone()[0]>=14
    finally:
        if created:
            assert re.fullmatch(r'qa_schema_[a-f0-9]{32}',name)
            cursor.execute(f'DROP DATABASE `{name}`')
        cursor.close();connection.close()
