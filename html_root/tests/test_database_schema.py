"""Execute the shipped bootstrap and migrations in an isolated temporary schema."""
import os
import uuid
from pathlib import Path
import pytest
import mysql.connector
from app import config,database


@pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS')!='1',reason='Requires MySQL schema privileges')
def test_fresh_sql_and_repeatable_migrations_preserve_legacy(monkeypatch):
    name='qa_wisdom_schema_'+uuid.uuid4().hex[:12]
    options=dict(host=config.MYSQL_HOST,port=config.MYSQL_PORT,user=config.MYSQL_USER,password=config.MYSQL_PASSWORD)
    admin=mysql.connector.connect(**options);cursor=admin.cursor()
    try:
        cursor.execute('CREATE DATABASE `'+name+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
        cursor.execute('USE `'+name+'`')
        sql=Path('visdom_db.sql').read_text(encoding='utf-8')
        for statement in sql.split(';'):
            meaningful='\n'.join(line for line in statement.splitlines() if not line.strip().startswith('--')).strip()
            if meaningful and not meaningful.startswith(('CREATE DATABASE','USE ')):
                cursor.execute(meaningful)
                if cursor.with_rows: cursor.fetchall()
        cursor.execute("INSERT INTO users(username,hashed_password) VALUES('schema_test','not-a-login-hash')")
        cursor.execute("INSERT INTO user_wrongbook(user_id,video_id,title,time_sec,note) VALUES('schema_test','example','旧题',4,'原始笔记')")
        admin.commit()
        monkeypatch.setattr(database,'get_db_connection',lambda:mysql.connector.connect(**options,database=name))
        database.apply_migrations();database.apply_migrations()
        admin.commit()  # End the old transaction before observing migration writes.
        cursor.execute('SELECT title,note FROM learning_wrongbook');assert cursor.fetchall()==[('旧题','原始笔记')]
        cursor.execute('SELECT COUNT(*) FROM schema_migrations');assert cursor.fetchone()[0]==len(list(database.MIGRATIONS.glob('*.sql')))
        cursor.execute("INSERT INTO formulas(user_id,latex) VALUES('schema_test','x^2')");fid=cursor.lastrowid
        cursor.execute("UPDATE users SET username='schema_renamed' WHERE username='schema_test'")
        cursor.execute('SELECT user_id FROM formulas WHERE id=%s',(fid,));assert cursor.fetchone()[0]=='schema_renamed'
        cursor.execute('SELECT COUNT(*) FROM learning_wrongbook');assert cursor.fetchone()[0]==1
    finally:
        admin.rollback()
        assert name.startswith('qa_wisdom_schema_') and len(name)==29
        cursor.execute('DROP DATABASE `'+name+'`');cursor.close();admin.close()
