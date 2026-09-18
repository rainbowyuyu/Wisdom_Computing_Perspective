"""Regenerate the idempotent upgrade tail of the single phpMyAdmin installer."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = '-- 8. 可重复执行的旧库升级'


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def build():
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
COMMIT;

-- phpMyAdmin 最后显示当前库、已建表数量和保留待处理的旧错题数量。
SELECT DATABASE() AS current_database,
    (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()) AS total_tables,
    (SELECT COUNT(*) FROM user_wrongbook w WHERE NOT EXISTS (SELECT 1 FROM learning_wrongbook n WHERE n.legacy_id=w.id)) AS unmatched_legacy_wrongbook;
""")
    path.write_text('\n\n'.join(sections), encoding='utf-8')


if __name__ == '__main__':
    build()
