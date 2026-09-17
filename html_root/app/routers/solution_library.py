"""Saved step-by-step solutions in the existing formula library."""
import json
from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field, constr, model_validator

from ..config import get_db_connection
from ..solution_models import Solution, SolutionStep
from ..store import SESSION_STORE

router = APIRouter(prefix='/formulas/solutions', tags=['formulas'])


class Chapter(BaseModel):
    title: constr(max_length=240)
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)


class SavedVideo(BaseModel):
    url: constr(pattern=r'^/videos/solution_[a-f0-9]+\.mp4$')
    chapters: list[Chapter] = Field(min_length=2, max_length=12)


class SavedSolution(BaseModel):
    id: Optional[int] = Field(default=None, gt=0)
    problem: constr(strip_whitespace=True, min_length=1, max_length=6000)
    context: constr(max_length=4000) = ''
    solution: Solution
    video: Optional[SavedVideo] = None

    @model_validator(mode='after')
    def valid_chapters(self):
        if self.video:
            if len(self.video.chapters) != len(self.solution.steps):
                raise ValueError('视频章节与解题步骤不一致')
            for index, chapter in enumerate(self.video.chapters):
                if chapter.start != index * 5 or chapter.end != (index + 1) * 5:
                    raise ValueError('视频章节时间无效')
        return self


def ensure_solution_table(cursor):
    # Run before writes: MySQL DDL commits the preceding transaction implicitly.
    cursor.execute('''CREATE TABLE IF NOT EXISTS formula_solutions (
        formula_id INT PRIMARY KEY,
        title VARCHAR(240) NOT NULL,
        step_count INT NOT NULL,
        video_url VARCHAR(128) NULL,
        payload LONGTEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_solution_formula FOREIGN KEY (formula_id) REFERENCES formulas(id) ON DELETE CASCADE
    )''')


def username_for_session(session):
    username = SESSION_STORE.get(session or '')
    if not username:
        raise HTTPException(401, '请先登录后保存或阅读题解。')
    return username


@router.post('')
def save_solution(data: SavedSolution, auth_session: Optional[str] = Cookie(None)):
    username = username_for_session(auth_session)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from .formulas import _ensure_topics_tables, _heuristic_tags
        ensure_solution_table(cursor)
        _ensure_topics_tables(cursor)
        formula_id = data.id
        if formula_id:
            cursor.execute('SELECT f.id FROM formulas f JOIN formula_solutions s ON s.formula_id=f.id WHERE f.id=%s AND f.user_id=%s FOR UPDATE', (formula_id, username))
            if not cursor.fetchone():
                raise HTTPException(404, '题解不存在或无权修改。')
            cursor.execute('UPDATE formulas SET latex=%s, note=%s WHERE id=%s', (data.problem, data.solution.title, formula_id))
        else:
            cursor.execute('INSERT INTO formulas (user_id, latex, note) VALUES (%s,%s,%s)', (username, data.problem, data.solution.title))
            formula_id = cursor.lastrowid
        cursor.execute('''INSERT INTO formula_solutions (formula_id,title,step_count,video_url,payload)
            VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE title=VALUES(title),
            step_count=VALUES(step_count),video_url=VALUES(video_url),payload=VALUES(payload)''',
            (formula_id, data.solution.title, len(data.solution.steps), data.video.url if data.video else None, data.model_dump_json(exclude={'id'})))
        cursor.execute('DELETE FROM formula_topics WHERE formula_id=%s AND user_id=%s', (formula_id, username))
        topics = _heuristic_tags(data.problem + ' ' + ' '.join(step.formula for step in data.solution.steps)) or ['数学推导']
        cursor.executemany('INSERT INTO formula_topics (user_id,formula_id,tag,weight) VALUES (%s,%s,%s,1)', [(username, formula_id, tag) for tag in topics])
        conn.commit()
        return {'status':'success', 'id':formula_id, 'username':username, 'message':'已保存到我的算式'}
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


@router.get('/{formula_id}')
def get_solution(formula_id: int, auth_session: Optional[str] = Cookie(None)):
    username = username_for_session(auth_session)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        ensure_solution_table(cursor)
        cursor.execute('SELECT s.payload,s.updated_at FROM formula_solutions s JOIN formulas f ON f.id=s.formula_id WHERE f.id=%s AND f.user_id=%s', (formula_id, username))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, '题解不存在或无权阅读。')
        payload = json.loads(row['payload'])
        for step in payload.get('solution', {}).get('steps', []):
            step['formula'] = SolutionStep.normalize_formula(step.get('formula', ''))
        return {'status':'success', 'data':{**payload, 'id':formula_id, 'username':username, 'updated_at':row['updated_at'].isoformat()}}
    finally:
        cursor.close()
        conn.close()


@router.delete('/{formula_id}')
def delete_solution(formula_id: int, auth_session: Optional[str] = Cookie(None)):
    username = username_for_session(auth_session)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        ensure_solution_table(cursor)
        cursor.execute('DELETE f FROM formulas f JOIN formula_solutions s ON s.formula_id=f.id WHERE f.id=%s AND f.user_id=%s', (formula_id, username))
        if not cursor.rowcount:
            raise HTTPException(404, '题解不存在或无权删除。')
        cursor.execute('DELETE FROM formula_topics WHERE formula_id=%s AND user_id=%s', (formula_id, username))
        conn.commit()
        return {'status':'success'}
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
