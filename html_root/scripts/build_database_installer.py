"""Regenerate the idempotent upgrade tail of the single phpMyAdmin installer."""
import ast
import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = '-- 8. 可重复执行的旧库升级'


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def manifest(base):
    """Read the canonical CREATE definitions without importing app configuration."""
    tables = []
    for match in re.finditer(r'CREATE TABLE IF NOT EXISTS `?(\w+)`?\s*\((.*?)\) ENGINE=', base, re.S):
        table, body = match.groups()
        columns = []
        indexes = []
        foreign_keys = []
        for line in body.splitlines():
            line = line.strip().rstrip(',')
            if not line:
                continue
            column = re.match(r'`?(\w+)`?\s+', line).group(1)
            if column.upper() not in {'PRIMARY', 'UNIQUE', 'KEY', 'INDEX', 'CONSTRAINT'}:
                columns.append(column)
                if 'PRIMARY KEY' in line.upper():
                    indexes.append({'name': 'PRIMARY', 'columns': column, 'unique': 1})
            key = re.match(r'(PRIMARY KEY|UNIQUE KEY|KEY|INDEX)\s*(?:`?(\w+)`?)?\s*\(([^)]+)\)', line, re.I)
            if key:
                kind, name, fields = key.groups()
                indexes.append({'name': name or 'PRIMARY', 'columns': re.sub(r'[\s`]', '', fields),
                                'unique': int(kind.upper() in {'PRIMARY KEY', 'UNIQUE KEY'})})
            fk = re.search(r'FOREIGN KEY\s*\(`?(\w+)`?\) REFERENCES `?(\w+)`?\s*\(`?(\w+)`?\) ON DELETE (CASCADE|SET NULL)', line, re.I)
            if fk:
                field, parent, parent_field, delete_rule = fk.groups()
                foreign_keys.append({'column': field, 'parent': parent, 'parent_column': parent_field,
                                     'delete_rule': delete_rule, 'update_cascade': int('ON UPDATE CASCADE' in line)})
        tables.append({'table': table, 'columns': columns, 'indexes': indexes, 'foreign_keys': foreign_keys})
    return tables


def derived_rows(columns, rows):
    """Emit a read-only manifest supported without JSON_TABLE or temp-table privileges."""
    selects = []
    for row in rows:
        values = [str(value) if isinstance(value, int) else literal(value) for value in row]
        if not selects:
            values = [f'{value} AS `{column}`' for column, value in zip(columns, values)]
        selects.append('SELECT ' + ', '.join(values))
    if not selects:
        return '(SELECT ' + ', '.join(f'NULL AS `{column}`' for column in columns) + ' WHERE 1=0)'
    return '(\n    ' + '\n    UNION ALL '.join(selects) + '\n)'


def completion_sql(base):
    tables = manifest(base)
    versions = [{'version': p.name, 'checksum': hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()}
                for p in sorted((ROOT / 'database/migrations').glob('*.sql'))]
    columns_sql = derived_rows(('table_name', 'column_name'),
                              [(t['table'], c) for t in tables for c in t['columns']])
    indexes_sql = derived_rows(('table_name', 'index_name', 'column_names', 'is_unique'),
                              [(t['table'], i['name'], i['columns'], i['unique'])
                               for t in tables for i in t['indexes']])
    relations_sql = derived_rows(('table_name', 'column_name', 'parent_table', 'parent_column', 'delete_rule', 'update_cascade'),
                                [(t['table'], f['column'], f['parent'], f['parent_column'], f['delete_rule'], f['update_cascade'])
                                 for t in tables for f in t['foreign_keys']])
    versions_sql = derived_rows(('version', 'checksum'), [(v['version'], v['checksum']) for v in versions])
    return f"""-- 9. 结构自检与升级版本登记（由 scripts/build_database_installer.py 同步生成）
-- 缺少字段、索引、关联或历史校验和冲突时，不登记新版本，不覆盖已有记录。
-- 使用只读 SELECT / UNION ALL 清单，兼容没有 JSON_TABLE 的数据库，无需临时表权限。

SELECT COUNT(*) INTO @wisdom_missing_columns
FROM {columns_sql} required_column
WHERE NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS c
    WHERE c.TABLE_SCHEMA=DATABASE() AND c.TABLE_NAME=required_column.table_name AND c.COLUMN_NAME=required_column.column_name);

SELECT COUNT(*) INTO @wisdom_missing_indexes
FROM {indexes_sql} required_index
WHERE required_index.index_name IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS s
    WHERE s.TABLE_SCHEMA=DATABASE() AND s.TABLE_NAME=required_index.table_name AND s.INDEX_NAME=required_index.index_name
    GROUP BY s.INDEX_NAME
    HAVING GROUP_CONCAT(s.COLUMN_NAME ORDER BY s.SEQ_IN_INDEX)=required_index.column_names
        AND MAX(s.NON_UNIQUE)=1-required_index.is_unique
);

SELECT COUNT(*) INTO @wisdom_missing_relations
FROM {relations_sql} required_fk
WHERE required_fk.column_name IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM information_schema.KEY_COLUMN_USAGE k
    JOIN information_schema.REFERENTIAL_CONSTRAINTS r
      ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.TABLE_NAME=k.TABLE_NAME AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
    WHERE k.CONSTRAINT_SCHEMA=DATABASE() AND k.TABLE_NAME=required_fk.table_name AND k.COLUMN_NAME=required_fk.column_name
      AND k.REFERENCED_TABLE_NAME=required_fk.parent_table AND k.REFERENCED_COLUMN_NAME=required_fk.parent_column
      AND r.DELETE_RULE=required_fk.delete_rule AND (required_fk.update_cascade=0 OR r.UPDATE_RULE='CASCADE')
);

SELECT COUNT(*) INTO @wisdom_migration_conflicts
FROM {versions_sql} expected
JOIN schema_migrations existing ON existing.version=expected.version COLLATE utf8mb4_general_ci
WHERE BINARY existing.checksum<>BINARY expected.checksum;

SELECT COUNT(*) INTO @wisdom_pending_legacy
FROM user_wrongbook w JOIN users u ON BINARY u.username=BINARY w.user_id
WHERE NOT EXISTS (SELECT 1 FROM learning_wrongbook n WHERE n.legacy_id=w.id);

SET @wisdom_upgrade_ok = (@wisdom_missing_columns=0 AND @wisdom_missing_indexes=0
    AND @wisdom_missing_relations=0 AND @wisdom_migration_conflicts=0 AND @wisdom_pending_legacy=0);

INSERT INTO schema_migrations(version,checksum)
SELECT expected.version,expected.checksum
FROM {versions_sql} expected
WHERE @wisdom_upgrade_ok AND NOT EXISTS (SELECT 1 FROM schema_migrations existing WHERE existing.version=expected.version COLLATE utf8mb4_general_ci);
COMMIT;

-- OK 且执行过程无报错才表示完成。非零缺项或校验和冲突需要核对，不要清空业务表重建。
SELECT IF(@wisdom_upgrade_ok, 'OK', 'NEEDS_ATTENTION') AS upgrade_status,
    DATABASE() AS current_database,
    (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()) AS total_tables,
    @wisdom_missing_columns AS missing_columns,
    @wisdom_missing_indexes AS missing_indexes,
    @wisdom_missing_relations AS missing_relations,
    @wisdom_migration_conflicts AS migration_conflicts,
    (SELECT COUNT(*) FROM schema_migrations WHERE version COLLATE utf8mb4_general_ci IN (
        SELECT version COLLATE utf8mb4_general_ci FROM {versions_sql} expected
    )) AS applied_migrations,
    @wisdom_pending_legacy AS pending_legacy_wrongbook,
    (SELECT COUNT(*) FROM user_wrongbook w WHERE NOT EXISTS (SELECT 1 FROM learning_wrongbook n WHERE n.legacy_id=w.id)) AS unmatched_legacy_wrongbook;
"""


def build(check=False):
    path = ROOT / 'visdom_db.sql'
    base = path.read_text(encoding='utf-8').split(MARKER)[0].rstrip()
    sections = [base, MARKER,
                '-- 使用普通 SQL 和会话级 PREPARE，不需要 SOURCE、DELIMITER 或存储过程权限。',
                '-- 如有不合法的旧关联，添加外键会报错并保留数据，请修正归属后重试。']

    def execute(expression):
        sections.extend([f'SET @wisdom_ddl = {expression};',
                         'PREPARE wisdom_statement FROM @wisdom_ddl;',
                         'EXECUTE wisdom_statement;',
                         'DEALLOCATE PREPARE wisdom_statement;'])

    # Real historical player schemas predate color/mode. Preserve existing choices.
    for column, definition in [('color', 'INT DEFAULT 16777215 AFTER `time`'),
                               ('mode', 'SMALLINT DEFAULT 1 AFTER `color`')]:
        ddl = f'ALTER TABLE `example_video_danmaku` ADD COLUMN `{column}` {definition}'
        execute(f"IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='example_video_danmaku' AND COLUMN_NAME='{column}'), 'DO 0', {literal(ddl)})")

    # 旧库的 users 表没有邮箱字段；使用会话级 PREPARE 兼容 MySQL 5.7，
    # 新库则保持幂等，不重复添加字段或索引。
    for column, definition in [
        ('email', 'VARCHAR(254) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER `hashed_password`'),
        ('email_verified', 'TINYINT(1) NOT NULL DEFAULT 0 AFTER `email`'),
        ('email_verified_at', 'TIMESTAMP NULL DEFAULT NULL AFTER `email_verified`'),
    ]:
        ddl = f'ALTER TABLE `users` ADD COLUMN `{column}` {definition}'
        execute(f"IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND COLUMN_NAME='{column}'), 'DO 0', {literal(ddl)})")
    ddl = 'ALTER TABLE `users` ADD UNIQUE KEY `uq_users_email` (`email`)'
    execute("IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND INDEX_NAME='uq_users_email'), 'DO 0', " + literal(ddl) + ")")

    # 已有安装的邮箱验证码表需要扩展用途枚举，支持更换绑定邮箱。
    ddl = "ALTER TABLE `account_email_codes` MODIFY COLUMN `purpose` ENUM('register','verify','reset','change_email') NOT NULL"
    execute("IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='account_email_codes' AND COLUMN_NAME='purpose'), " + literal(ddl) + ", 'DO 0')")

    module = ast.parse((ROOT / 'app/database.py').read_text(encoding='utf-8'))
    indexes = next(ast.literal_eval(node.value) for node in module.body
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'INDEXES' for t in node.targets))
    for table, entries in indexes.items():
        for name, columns in entries:
            ddl = f'ALTER TABLE `{table}` ADD INDEX `{name}` ({columns})'
            execute(f"IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='{table}' AND INDEX_NAME='{name}'), 'DO 0', {literal(ddl)})")

    for table in ('formulas', 'animation_scripts', 'agent_templates', 'user_profiles'):
        sections.append(f"""SET @wisdom_fk = NULL;
SET @wisdom_fk_update = NULL;
SELECT rc.CONSTRAINT_NAME, rc.UPDATE_RULE INTO @wisdom_fk, @wisdom_fk_update
FROM information_schema.REFERENTIAL_CONSTRAINTS rc
JOIN information_schema.KEY_COLUMN_USAGE k
  ON rc.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND rc.TABLE_NAME=k.TABLE_NAME AND rc.CONSTRAINT_NAME=k.CONSTRAINT_NAME
WHERE rc.CONSTRAINT_SCHEMA=DATABASE() AND rc.TABLE_NAME='{table}'
  AND k.COLUMN_NAME='user_id' AND k.REFERENCED_TABLE_NAME='users' AND k.REFERENCED_COLUMN_NAME='username'
LIMIT 1;""")
        addition = f'ADD CONSTRAINT fk_{table}_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE'
        execute(f"IF(@wisdom_fk_update='CASCADE', 'DO 0', CONCAT('ALTER TABLE `{table}` ', IF(@wisdom_fk IS NULL, '', CONCAT('DROP FOREIGN KEY `', REPLACE(@wisdom_fk, '`', '``'), '`, ')), {literal(addition)}))")

    for table, column, parent, name in (
        ('course_pack_documents', 'pack_id', 'course_packs', 'fk_pack_document'),
        ('course_pack_videos', 'pack_id', 'course_packs', 'fk_pack_video'),
        ('formula_topics', 'formula_id', 'formulas', 'fk_topic_formula'),
    ):
        ddl = f'ALTER TABLE `{table}` ADD CONSTRAINT `{name}` FOREIGN KEY(`{column}`) REFERENCES `{parent}`(id) ON DELETE CASCADE'
        execute(f"IF(EXISTS(SELECT 1 FROM information_schema.KEY_COLUMN_USAGE WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='{table}' AND COLUMN_NAME='{column}' AND REFERENCED_TABLE_NAME='{parent}'), 'DO 0', {literal(ddl)})")

    sections.append("""-- 保留原错题表，将可匹配账户的记录导入新错题本，重复执行不重复导入。
INSERT INTO learning_wrongbook
    (owner_id,legacy_id,source_type,video_id,time_sec,title,problem,answer,note,fingerprint,created_at)
SELECT u.id,w.id,'video',w.video_id,GREATEST(w.time_sec,0),
    COALESCE(w.title,''),COALESCE(w.title,''),'',COALESCE(w.note,''),
    SHA2(CONCAT('legacy:',w.id),256),COALESCE(w.created_at,CURRENT_TIMESTAMP)
FROM user_wrongbook w JOIN users u
    ON BINARY u.username = BINARY w.user_id
WHERE NOT EXISTS (SELECT 1 FROM learning_wrongbook n WHERE n.legacy_id=w.id);
""")
    sections.append(completion_sql(base))
    result = '\n\n'.join(sections)
    if check:
        if path.read_text(encoding='utf-8') != result:
            raise SystemExit('visdom_db.sql 已过期，请运行 python scripts/build_database_installer.py')
    else:
        path.write_text(result, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check generated SQL without writing files')
    build(check=parser.parse_args().check)
