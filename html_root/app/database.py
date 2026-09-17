"""Versioned, additive MySQL migrations and transaction-scoped connections."""
import hashlib
import re
from contextlib import contextmanager
from pathlib import Path
from .config import get_db_connection

MIGRATIONS = Path(__file__).resolve().parents[1] / 'database' / 'migrations'


@contextmanager
def transaction():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SET time_zone = '+00:00'")
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def backfill_legacy(cursor):
    cursor.execute("SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='user_wrongbook'")
    if not cursor.fetchone()['n']:
        return
    # Retain every legacy record verbatim, including duplicate time points.
    cursor.execute("""INSERT IGNORE INTO learning_wrongbook
        (owner_id,legacy_id,source_type,video_id,time_sec,title,problem,answer,note,fingerprint,created_at)
        SELECT u.id,w.id,'video',w.video_id,GREATEST(w.time_sec,0),
            COALESCE(w.title,''),COALESCE(w.title,''),'',COALESCE(w.note,''),
            SHA2(CONCAT('legacy:',w.id),256),COALESCE(w.created_at,CURRENT_TIMESTAMP)
        FROM user_wrongbook w JOIN users u ON u.username=w.user_id""")


INDEXES = {
    'example_video_danmaku': [('ix_danmaku_video_time','video_id,time,id')],
    'example_video_comments': [('ix_comments_video_created','video_id,created_at,id')],
    'example_video_notes': [('ix_notes_owner_video_time','user_id,video_id,time_sec,id')],
    'course_packs': [('ix_packs_owner_created','user_id,created_at,id')],
    'course_pack_videos': [('ix_pack_order','pack_id,sort_order')],
    'formulas': [('ix_formulas_owner_created','user_id,created_at,id')],
    'animation_scripts': [('ix_scripts_owner_created','user_id,created_at,id')],
    'agent_templates': [('ix_templates_owner_created','user_id,created_at,id')],
}


def apply_migrations():
    with transaction() as (conn, cursor):
        cursor.execute("SELECT GET_LOCK(CONCAT(DATABASE(),':wisdom-migrations'),30) AS acquired")
        if cursor.fetchone()['acquired'] != 1:
            raise RuntimeError('无法取得数据库迁移锁')
        try:
            cursor.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
                version VARCHAR(128) PRIMARY KEY, checksum CHAR(64) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            for path in sorted(MIGRATIONS.glob('*.sql')):
                sql=path.read_text(encoding='utf-8');checksum=hashlib.sha256(sql.encode()).hexdigest()
                cursor.execute('SELECT checksum FROM schema_migrations WHERE version=%s',(path.name,))
                previous=cursor.fetchone()
                if previous:
                    if previous['checksum']!=checksum:
                        raise RuntimeError('已执行的迁移内容被修改：'+path.name)
                    continue
                for statement in sql.split(';'):
                    if not statement.strip():continue
                    if path.name=='003_teaching_relations.sql' and 'ADD CONSTRAINT' in statement:
                        constraint=re.search(r'ADD CONSTRAINT (\w+)',statement).group(1)
                        cursor.execute('SELECT COUNT(*) AS n FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME=%s',(constraint,))
                        if cursor.fetchone()['n']:continue
                    if path.name=='002_account_rename.sql':
                        table=re.search(r'ALTER TABLE (\w+)',statement).group(1)
                        cursor.execute('''SELECT rc.CONSTRAINT_NAME,rc.UPDATE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS rc
                            JOIN information_schema.KEY_COLUMN_USAGE k ON rc.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA
                            AND rc.TABLE_NAME=k.TABLE_NAME AND rc.CONSTRAINT_NAME=k.CONSTRAINT_NAME
                            WHERE rc.CONSTRAINT_SCHEMA=DATABASE() AND rc.TABLE_NAME=%s
                            AND k.COLUMN_NAME='user_id' AND k.REFERENCED_TABLE_NAME='users' AND k.REFERENCED_COLUMN_NAME='username' ''',(table,))
                        fk=cursor.fetchone()
                        if fk and fk['UPDATE_RULE']=='CASCADE':continue
                        if fk:statement=re.sub(r'DROP FOREIGN KEY \w+', 'DROP FOREIGN KEY `'+fk['CONSTRAINT_NAME'].replace('`','``')+'`',statement)
                        else:statement=re.sub(r'DROP FOREIGN KEY \w+,\s*','',statement)
                    cursor.execute(statement)
                if path.name=='001_learning_records.sql': backfill_legacy(cursor)
                cursor.execute('INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)',(path.name,checksum))
                conn.commit()
            for table,indexes in INDEXES.items():
                cursor.execute('SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s',(table,))
                if not cursor.fetchone()['n']: continue
                for name,columns in indexes:
                    cursor.execute('SELECT COUNT(*) AS n FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s',(table,name))
                    if not cursor.fetchone()['n']: cursor.execute(f'ALTER TABLE `{table}` ADD INDEX `{name}` ({columns})')
        finally:
            cursor.execute("SELECT RELEASE_LOCK(CONCAT(DATABASE(),':wisdom-migrations'))")
            cursor.fetchone()
