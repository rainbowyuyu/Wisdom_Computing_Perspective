"""Owned, ordered teaching packs with editable lesson plans."""
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field, constr
from ..config import get_db_connection, STORAGE_DIR
from .solution_library import username_for_session, SavedSolution
from .examples import _ensure_tables

router = APIRouter(prefix='/examples/course-packs', tags=['teaching'])
Text = constr(strip_whitespace=True, max_length=12000)


class LessonPlan(BaseModel):
    audience: constr(max_length=200) = ''
    duration: int = Field(default=45, ge=1, le=480)
    objectives: Text = ''
    key_points: Text = ''
    preparation: Text = ''
    procedure: Text = ''
    exercises: Text = ''
    reflection: Text = ''


class MaterialSnapshot(BaseModel):
    title: constr(max_length=512)
    problem: constr(max_length=12000)
    answer: constr(max_length=60000) = ''
    note: constr(max_length=12000) = ''
    solution: SavedSolution | None = None


class PackResource(BaseModel):
    kind: Literal['solution', 'wrongbook']
    source_id: int | None = Field(default=None, gt=0)
    snapshot: MaterialSnapshot | None = None


class PackWrite(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=128)
    description: constr(max_length=2000) = ''
    lesson: LessonPlan = Field(default_factory=LessonPlan)
    video_ids: list[constr(min_length=1, max_length=128)] = Field(default_factory=list, max_length=100)
    revision: int | None = Field(default=None, ge=1)
    resources: list[PackResource] | None = Field(default=None, max_length=100)


@contextmanager
def database():
    conn=get_db_connection(); cursor=conn.cursor(dictionary=True)
    try:
        _ensure_tables(cursor)
        cursor.execute('''CREATE TABLE IF NOT EXISTS course_pack_documents (
            pack_id INT PRIMARY KEY, description TEXT NOT NULL, lesson_json LONGTEXT NOT NULL,
            revision INT NOT NULL DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )''')
        yield conn,cursor
    except Exception:
        conn.rollback(); raise
    finally:
        cursor.close(); conn.close()


def require_pack(cursor, ident, username, lock=False):
    cursor.execute('SELECT id,name,created_at FROM course_packs WHERE id=%s AND user_id=%s'+(' FOR UPDATE' if lock else ''),(ident,username))
    pack=cursor.fetchone()
    if not pack: raise HTTPException(404,'课包不存在或无权访问')
    return pack


def validate_videos(ids):
    if len(set(ids)) != len(ids): raise HTTPException(422,'课包不能重复添加同一视频')
    root=Path(STORAGE_DIR).resolve()
    for vid in ids:
        file=(root/(vid+'.mp4')).resolve()
        if file.parent!=root or not file.is_file(): raise HTTPException(422,'视频不存在：'+vid)


def write_resources(cursor, ident, resources, username):
    rows = []
    seen = set()
    for resource in resources:
        snapshot = resource.snapshot
        if resource.source_id:
            key = (resource.kind, resource.source_id)
            if key in seen:
                raise HTTPException(422, '不能重复添加同一份学习材料')
            seen.add(key)
            if resource.kind == 'solution':
                cursor.execute('SELECT s.payload FROM formula_solutions s JOIN formulas f ON f.id=s.formula_id WHERE f.id=%s AND f.user_id=%s', (resource.source_id, username))
                row = cursor.fetchone()
                if not row: raise HTTPException(404, '题解不存在或无权访问')
                record = json.loads(row['payload'])
                if snapshot is None:
                    snapshot = MaterialSnapshot(title=record['solution']['title'], problem=record['problem'], answer=record['solution']['summary'], solution=record)
            else:
                cursor.execute('SELECT w.* FROM learning_wrongbook w JOIN users u ON u.id=w.owner_id WHERE w.id=%s AND u.username=%s', (resource.source_id, username))
                row = cursor.fetchone()
                if not row: raise HTTPException(404, '错题不存在或无权访问')
                if snapshot is None:
                    snapshot = MaterialSnapshot(title=row['title'], problem=row['problem'], answer=row['answer'], note=row['note'], solution=json.loads(row['solution_snapshot']) if row['solution_snapshot'] else None)
        if snapshot is None: raise HTTPException(422, '请提供材料来源或内容快照')
        # Imported snapshots never carry an actionable formula id from another account.
        if snapshot.solution: snapshot.solution.id = None
        rows.append((ident, resource.kind, resource.source_id if resource.kind=='solution' else None,
                     resource.source_id if resource.kind=='wrongbook' else None,
                     json.dumps(snapshot.model_dump(), ensure_ascii=False), len(rows)))
    cursor.execute('DELETE FROM course_pack_resources WHERE pack_id=%s', (ident,))
    if rows:
        cursor.executemany('INSERT INTO course_pack_resources(pack_id,kind,formula_id,wrongbook_id,snapshot,sort_order) VALUES(%s,%s,%s,%s,%s,%s)', rows)


def write_content(cursor, ident, data, revision, username):
    cursor.execute('''INSERT INTO course_pack_documents(pack_id,description,lesson_json,revision)
        VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE description=VALUES(description),lesson_json=VALUES(lesson_json),revision=VALUES(revision)''',
        (ident,data.description,json.dumps(data.lesson.model_dump(),ensure_ascii=False),revision))
    if data.resources is not None: write_resources(cursor,ident,data.resources,username)
    cursor.execute('DELETE FROM course_pack_videos WHERE pack_id=%s',(ident,))
    if data.video_ids:
        cursor.executemany('INSERT INTO course_pack_videos(pack_id,video_id,sort_order) VALUES(%s,%s,%s)',[(ident,vid,i) for i,vid in enumerate(data.video_ids)])


@router.get('')
def list_packs(auth_session: str | None = Cookie(None)):
    username=username_for_session(auth_session)
    with database() as (_,cursor):
        cursor.execute('''SELECT p.id,p.name,p.created_at,COALESCE(d.description,'') AS description,
            COALESCE(d.revision,1) AS revision,COUNT(v.video_id) AS video_count,
            (SELECT COUNT(*) FROM course_pack_resources r WHERE r.pack_id=p.id) AS resource_count
            FROM course_packs p LEFT JOIN course_pack_documents d ON d.pack_id=p.id
            LEFT JOIN course_pack_videos v ON v.pack_id=p.id WHERE p.user_id=%s
            GROUP BY p.id,p.name,p.created_at,d.description,d.revision ORDER BY p.id DESC''',(username,))
        return {'status':'success','data':cursor.fetchall()}


@router.post('')
def create_pack(data: PackWrite, auth_session: str | None = Cookie(None)):
    username=username_for_session(auth_session);validate_videos(data.video_ids)
    with database() as (conn,cursor):
        cursor.execute('INSERT INTO course_packs(user_id,name) VALUES(%s,%s)',(username,data.name));ident=cursor.lastrowid
        write_content(cursor,ident,data,1,username);conn.commit()
        return {'status':'success','id':ident,'revision':1}


@router.get('/{ident}')
def read_pack(ident: int, auth_session: str | None = Cookie(None)):
    username=username_for_session(auth_session)
    with database() as (_,cursor):
        pack=require_pack(cursor,ident,username)
        cursor.execute('SELECT description,lesson_json,revision FROM course_pack_documents WHERE pack_id=%s',(ident,));doc=cursor.fetchone() or {}
        pack.update(description=doc.get('description',''),lesson=json.loads(doc.get('lesson_json') or '{}'),revision=doc.get('revision',1))
        cursor.execute('SELECT video_id FROM course_pack_videos WHERE pack_id=%s ORDER BY sort_order,video_id',(ident,))
        pack['video_ids']=[r['video_id'] for r in cursor.fetchall()]
        cursor.execute('SELECT kind,COALESCE(formula_id,wrongbook_id) AS source_id,snapshot FROM course_pack_resources WHERE pack_id=%s ORDER BY sort_order,id',(ident,))
        pack['resources']=[{**r,'snapshot':json.loads(r['snapshot'])} for r in cursor.fetchall()]
        return {'status':'success','data':pack}


@router.put('/{ident}')
def update_pack(ident: int, data: PackWrite, auth_session: str | None = Cookie(None)):
    username=username_for_session(auth_session);validate_videos(data.video_ids)
    with database() as (conn,cursor):
        require_pack(cursor,ident,username,True)
        cursor.execute('SELECT revision FROM course_pack_documents WHERE pack_id=%s',(ident,));doc=cursor.fetchone() or {'revision':1}
        if data.revision != doc['revision']: raise HTTPException(409,'课包已被更新，请重新打开后编辑，避免覆盖其他修改。')
        revision=doc['revision']+1
        cursor.execute('UPDATE course_packs SET name=%s WHERE id=%s',(data.name,ident))
        write_content(cursor,ident,data,revision,username);conn.commit()
        return {'status':'success','id':ident,'revision':revision}


@router.delete('/{ident}')
def delete_pack(ident: int, auth_session: str | None = Cookie(None)):
    username=username_for_session(auth_session)
    with database() as (conn,cursor):
        require_pack(cursor,ident,username,True)
        cursor.execute('DELETE FROM course_pack_videos WHERE pack_id=%s',(ident,))
        cursor.execute('DELETE FROM course_pack_documents WHERE pack_id=%s',(ident,))
        cursor.execute('DELETE FROM course_packs WHERE id=%s',(ident,));conn.commit()
    return {'status':'success'}
