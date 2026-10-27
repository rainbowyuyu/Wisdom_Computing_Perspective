"""Read old owned text, copy validated records once, preserve every source row."""
import hashlib
import time

from fastapi import HTTPException
from pydantic import ValidationError

from .legacy_accounts import AccountError
from .library import FormulaInput, MAX_ITEMS
from .workspace import StudyInput, MAX_LEARNING, _study_new, _check_learning_budget


def _exists(service, cur, table):
    if cur.sqlite:
        return bool(cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=%s", (table,)).fetchone())
    return bool(cur.execute('SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s', (table,)).fetchone())


def read_content(service, user_id):
    user = service.get_user(user_id)
    result = {'formulas': [], 'notes': [], 'wrongbook': [], 'truncated': []}
    with service.transaction() as cur:
        # Table/column identifiers are fixed code; the owner is always a bound
        # parameter obtained from the verified database ID, never caller text.
        queries = [
            ('formulas', 'formulas', 'id,latex,note', 'BINARY user_id=BINARY %s', user['username'], 201),
            ('example_video_notes', 'notes', 'id,video_id,time_sec,content', 'BINARY user_id=BINARY %s', user['username'], 301),
            ('learning_wrongbook', 'wrongbook', 'id,legacy_id,title,problem,answer,note,video_id,time_sec', 'owner_id=%s', user_id, 301),
        ]
        for table, key, columns, condition, value, cap in queries:
            if not _exists(service, cur, table): continue
            rows = cur.execute(f'SELECT {columns} FROM {table} WHERE {condition} ORDER BY id LIMIT %s', (value, cap)).fetchall()
            if len(rows) == cap:
                result['truncated'].append(table)
            result[key] = [{**row, '_table': table} for row in rows[:cap-1]]
        if _exists(service, cur, 'user_wrongbook'):
            rows = cur.execute('SELECT id,title,note,video_id,time_sec FROM user_wrongbook WHERE BINARY user_id=BINARY %s ORDER BY id LIMIT 301', (user['username'],)).fetchall()
            represented = {row.get('legacy_id') for row in result['wrongbook']}
            result['wrongbook'].extend({**row, 'problem': row['title'], 'answer': '', '_table': 'user_wrongbook'} for row in rows[:300] if row['id'] not in represented)
            if len(rows) == 301: result['truncated'].append('user_wrongbook')
    return result


def import_library(service, user_id, owner):
    store = service.get_store()
    if store.get_legacy_user_id(owner, namespace=service.namespace) != user_id:
        raise AccountError('资料不属于当前登录账户。', 403, 'ownership_required')
    source = read_content(service, user_id)
    imported, skipped, warnings = 0, 0, []
    if source['truncated']:
        warnings.append('旧资料超出本次读取上限，未读取的内容仍完整保留在旧数据库。')
    values = []
    for row in source['formulas']:
        try:
            data = FormulaInput(title=f'旧站公式 #{row["id"]}', latex=row['latex'], note=row.get('note') or '', tags=['旧站迁入']).model_dump()
            values.append(('formula', row, data, MAX_ITEMS))
        except ValidationError:
            skipped += 1
            warnings.append('部分旧公式超出新编辑器长度或格式限制，原内容保留在旧库。')
    for row in [*source['notes'], *source['wrongbook']]:
        try:
            wrongbook = row['_table'] != 'example_video_notes'
            title = row.get('title') or ('旧站错题' if wrongbook else '旧站视频笔记') + f' #{row["id"]}'
            note = row.get('note') if wrongbook else row.get('content')
            # Old video IDs are not new private project IDs. Retain provenance
            # as inert text instead of making a broken/external playback link.
            provenance = f'旧站来源：{row.get("video_id") or "手动资料"}；记录时间 {row.get("time_sec", 0)} 秒'
            data = StudyInput(kind='wrongbook' if wrongbook else 'note', title=title,
                              problem=(row.get('problem') or title) if wrongbook else '',
                              answer=row.get('answer') or '', note=(note or '') + '\n\n' + provenance,
                              tags=['旧站迁入']).model_dump()
            values.append(('learning', row, _study_new(data), MAX_LEARNING))
        except ValidationError:
            skipped += 1
            warnings.append('部分旧笔记或错题超出新编辑器长度或格式限制，原内容保留在旧库。')
    with store.lock, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for kind, row, data, cap in values:
            ident = hashlib.sha256(f'legacy:{service.namespace}:{user_id}:{row["_table"]}:{row["id"]}'.encode()).hexdigest()[:32]
            existing = db.execute('SELECT owner,kind FROM records WHERE id=?', (ident,)).fetchone()
            if existing:
                if existing != (owner, kind):
                    raise AccountError('资料身份冲突，未覆盖任何记录。', 409, 'migration_conflict')
                skipped += 1
                continue
            count = db.execute('SELECT COUNT(*) FROM records WHERE owner=? AND kind=?', (owner, kind)).fetchone()[0]
            if count >= cap:
                skipped += 1
                warnings.append('当前空间容量不足，剩余资料保留在旧数据库。')
                continue
            now = time.time()
            item = dict(**data, id=ident, owner=owner, revision=1, created=now, updated=now)
            db.execute('SAVEPOINT import_record')
            try:
                store._write(db, kind, item)
                if kind == 'learning': _check_learning_budget(db, owner)
            except HTTPException:
                db.execute('ROLLBACK TO import_record')
                skipped += 1
                warnings.append('当前空间文本容量不足，剩余资料保留在旧数据库。')
            else:
                imported += 1
            finally:
                db.execute('RELEASE import_record')
    return dict(imported=imported, skipped=skipped, warnings=list(dict.fromkeys(warnings)))
