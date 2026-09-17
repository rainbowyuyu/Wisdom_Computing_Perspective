"""Run from html_root: python scripts/migrate_database.py [--apply]."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import apply_migrations, transaction, MIGRATIONS

parser=argparse.ArgumentParser(description='查看或应用非破坏性数据库迁移')
parser.add_argument('--apply',action='store_true',help='创建新表、迁移旧错题记录并补齐索引')
args=parser.parse_args()
if args.apply: apply_migrations()
with transaction() as (_,cursor):
    cursor.execute("SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='schema_migrations'")
    applied=[]
    if cursor.fetchone()['n']:
        cursor.execute('SELECT version FROM schema_migrations');applied=[r['version'] for r in cursor.fetchall()]
    for path in sorted(MIGRATIONS.glob('*.sql')):print(path.name, '已应用' if path.name in applied else '待应用')
    cursor.execute("SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='user_wrongbook'")
    if cursor.fetchone()['n']:
        cursor.execute('SELECT COUNT(*) AS n FROM user_wrongbook w LEFT JOIN users u ON u.username=w.user_id WHERE u.id IS NULL')
        print('保留在旧表的无对应账户记录：',cursor.fetchone()['n'])
