"""Exercise a selected database with the original 18 tables and real old records."""
import os
import re
import uuid
from pathlib import Path

import mysql.connector
import pytest
from app import config

ROOT = Path(__file__).resolve().parents[1]
LEGACY = {
    'users', 'user_profiles', 'user_settings', 'formulas', 'formula_topics',
    'animation_scripts', 'agent_templates', 'user_achievements', 'course_packs',
    'course_pack_videos', 'example_play_history', 'example_video_comments',
    'example_video_danmaku', 'example_video_likes', 'example_video_notes',
    'user_favorites', 'user_wrongbook', 'watch_later',
}


def run_installer(cursor):
    sql = (ROOT / 'visdom_db.sql').read_text(encoding='utf-8')
    sql = re.sub(r'^\s*--[^\n]*', '', sql, flags=re.M)
    result = None
    for statement in sql.split(';'):
        if statement.strip():
            cursor.execute(statement)
            if cursor.with_rows:
                rows = cursor.fetchall()
                if cursor.column_names[0] == 'upgrade_status':
                    result = dict(zip(cursor.column_names, rows[0]))
    return result


def test_panel_sql_does_not_switch_database_or_need_routines():
    sql = (ROOT / 'visdom_db.sql').read_text(encoding='utf-8')
    assert not re.search(r'^\s*(?:USE |CREATE DATABASE|DELIMITER|SOURCE |DROP TABLE|TRUNCATE|DELETE FROM)', sql, re.M | re.I)
    assert 'FOREIGN_KEY_CHECKS' not in sql


@pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS') != '1', reason='Requires disposable MySQL database')
@pytest.mark.parametrize('collation', ['utf8mb4_general_ci', 'utf8mb4_0900_ai_ci'])
def test_upgrade_18_tables_preserves_data_and_is_repeatable(collation):
    name = 'qa_baota_' + uuid.uuid4().hex
    conn = mysql.connector.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                                   user=config.MYSQL_USER, password=config.MYSQL_PASSWORD)
    cursor = conn.cursor()
    created = False
    try:
        cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE {collation}')
        created = True
        cursor.execute(f'USE `{name}`')
        cursor.execute("SET time_zone = '+00:00'")
        sql = (ROOT / 'visdom_db.sql').read_text(encoding='utf-8').split('-- 8.')[0]
        for match in re.finditer(r'CREATE TABLE IF NOT EXISTS `?(\w+)`? \([\s\S]*?\) ENGINE=InnoDB[^;\n]*', sql):
            table = match.group(1)
            if table not in LEGACY:
                continue
            statement = match.group(0).split("', 'WISDOM_USERNAME_COLLATION'")[0]
            if 'WISDOM_USERNAME_COLLATION' in statement:
                statement = statement.replace("''", "'")
            statement = statement.replace('WISDOM_USERNAME_COLLATION', collation).replace('utf8mb4_general_ci', collation)
            # Old tables have no new indexes/parent constraints and use original FK names.
            statement = re.sub(r'^\s*(?:KEY `ix_[^\n]+|CONSTRAINT `fk_(?:topic_formula)[^\n]+)\n', '', statement, flags=re.M)
            statement = re.sub(r'^\s*CONSTRAINT `fk_pack_video`[^\n]+\n', '', statement, flags=re.M)
            statement = statement.replace(' ON UPDATE CASCADE', '')
            if table == 'example_video_danmaku':
                statement = re.sub(r'^\s*`(?:color|mode)`[^\n]+\n', '', statement, flags=re.M)
            statement = re.sub(r'`fk_\w+_username`', f'`{table}_ibfk_1`', statement)
            statement = re.sub(r',\s*\) ENGINE', '\n) ENGINE', statement)
            cursor.execute(statement)
        cursor.execute('SHOW TABLES')
        assert {r[0] for r in cursor.fetchall()} == LEGACY
        cursor.execute("INSERT INTO users(username,hashed_password) VALUES('原用户','preserved-hash')")
        cursor.execute("INSERT INTO formulas(user_id,latex,note) VALUES('原用户',%s,'旧备注')", (r'\frac{1}{2}',))
        fid = cursor.lastrowid
        cursor.execute("INSERT INTO formula_topics(user_id,formula_id,tag) VALUES('原用户',%s,'分数')", (fid,))
        cursor.execute("INSERT INTO course_packs(user_id,name) VALUES('原用户','原课包')")
        pack = cursor.lastrowid
        cursor.execute("INSERT INTO course_pack_videos(pack_id,video_id) VALUES(%s,'old-video')", (pack,))
        cursor.execute("INSERT INTO user_wrongbook(user_id,video_id,title,note) VALUES('原用户','v','旧错题','旧订正'),('原用户','v','旧错题','另一条'),('不存在的用户','v','孤立旧题','保留')")
        cursor.execute("INSERT INTO example_video_danmaku(video_id,user_id,text,time) VALUES('v','原用户','旧弹幕',1.5)")
        conn.commit()
        before = {}
        original_columns = {}
        for table in LEGACY:
            cursor.execute(f'SELECT * FROM `{table}`')
            before[table] = cursor.fetchall()
            original_columns[table] = ','.join('`' + column + '`' for column in cursor.column_names)
        for _ in range(2):
            result = run_installer(cursor)
            assert result['upgrade_status'] == 'OK', result
            assert result['applied_migrations'] == 6
            assert result['unmatched_legacy_wrongbook'] == 1
        cursor.execute('SELECT DATABASE()')
        assert cursor.fetchone()[0] == name
        cursor.execute('SHOW TABLES')
        assert len(cursor.fetchall()) == 30
        for table in LEGACY:
            cursor.execute(f'SELECT {original_columns[table]} FROM `{table}`')
            assert cursor.fetchall() == before[table], table
        cursor.execute('SELECT color,mode FROM example_video_danmaku')
        assert cursor.fetchall() == [(16777215, 1)]
        cursor.execute('SELECT note FROM learning_wrongbook ORDER BY legacy_id')
        assert cursor.fetchall() == [('旧订正',), ('另一条',)]
        cursor.execute("SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND INDEX_NAME='ix_packs_owner_created'")
        assert cursor.fetchone()[0] == 3
        cursor.execute("UPDATE users SET username='新用户名' WHERE username='原用户'")
        cursor.execute('SELECT user_id FROM formulas WHERE id=%s', (fid,))
        assert cursor.fetchone()[0] == '新用户名'
        cursor.execute('INSERT INTO course_pack_documents(pack_id,description,lesson_json) VALUES(%s,%s,%s)', (pack, '教案', '{}'))
        cursor.execute('INSERT INTO formula_solutions(formula_id,title,step_count,payload) VALUES(%s,%s,1,%s)', (fid, '题解', '{}'))
        cursor.execute("INSERT INTO course_pack_resources(pack_id,kind,formula_id,snapshot,sort_order) VALUES(%s,'solution',%s,'{}',0)", (pack, fid))
        conn.commit()
    finally:
        conn.rollback()
        if created:
            assert re.fullmatch(r'qa_baota_[a-f0-9]{32}', name)
            cursor.execute(f'DROP DATABASE `{name}`')
        cursor.close()
        conn.close()
