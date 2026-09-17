"""Account-owned error notebook, source snapshots and spaced review history."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Cookie, HTTPException, Query
from pydantic import BaseModel, Field, constr, field_validator, model_validator
from mysql.connector import IntegrityError
from ..database import transaction
from ..store import SESSION_STORE
from .solution_library import SavedSolution

router=APIRouter(prefix='/wrongbook',tags=['wrongbook'])


class EntryWrite(BaseModel):
    username: str | None = None
    source_type: Literal['manual','video','solution']='manual'
    video_id: constr(max_length=256)=''
    formula_id: int | None = Field(default=None,gt=0)
    time_sec: int = Field(default=0,ge=0,le=86400)
    title: constr(strip_whitespace=True,max_length=512)=''
    problem: constr(strip_whitespace=True,max_length=12000)=''
    answer: constr(max_length=60000)=''
    note: constr(max_length=12000)=''
    tags: list[constr(strip_whitespace=True,min_length=1,max_length=64)] = Field(default_factory=list,max_length=12)
    difficulty: int = Field(default=3,ge=1,le=5)
    snapshot: SavedSolution | None = None
    revision: int | None = Field(default=None,ge=1)

    @field_validator('tags')
    @classmethod
    def unique_tags(cls,tags):return list(dict.fromkeys(t.lower() for t in tags))

    @model_validator(mode='after')
    def source(self):
        if self.video_id:self.source_type='video'
        elif self.snapshot or self.formula_id:self.source_type='solution'
        if self.source_type=='video' and not self.video_id:raise ValueError('视频错题缺少来源')
        if not self.problem:self.problem=self.snapshot.problem if self.snapshot else self.title
        if not self.problem:raise ValueError('请填写题目或视频标题')
        if not self.title:self.title=self.problem[:100]
        return self


class ReviewWrite(BaseModel):
    revision: int = Field(ge=1)
    grade: Literal['again','good','mastered']
    note: constr(max_length=4000)=''


class LegacyUpdate(BaseModel):
    id: int = Field(gt=0)
    username: str | None = None
    title: constr(max_length=512) | None = None
    note: constr(max_length=12000) | None = None
    time_sec: int | None = Field(default=None,ge=0,le=86400)
    revision: int | None = Field(default=None,ge=1)


def owner(cursor,session,claimed=None):
    name=SESSION_STORE.get(session or '')
    if not name:raise HTTPException(401,'请先登录后使用错题本')
    if claimed is not None and claimed!=name:raise HTTPException(403,'不能访问其他账户的错题本')
    cursor.execute('SELECT id FROM users WHERE username=%s',(name,));row=cursor.fetchone()
    if not row:raise HTTPException(401,'账户已失效，请重新登录')
    return row['id']


def require(cursor,ident,user,lock=False):
    cursor.execute('SELECT * FROM learning_wrongbook WHERE id=%s AND owner_id=%s'+(' FOR UPDATE' if lock else ''),(ident,user))
    row=cursor.fetchone()
    if not row:raise HTTPException(404,'错题不存在或无权访问')
    return row


def fingerprint(data):
    content=[data.source_type,data.video_id,data.formula_id,data.time_sec,data.title,data.problem,data.note]
    return hashlib.sha256(json.dumps(content,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def serialize(row):
    result={k:v for k,v in row.items() if k not in ('owner_id','fingerprint','legacy_id','solution_snapshot')}
    for k,v in result.items():
        if isinstance(v,datetime):result[k]=v.isoformat()+'Z'
    raw=row.get('solution_snapshot');result['snapshot']=json.loads(raw) if isinstance(raw,str) else raw
    return result


def attach_tags(cursor,rows):
    if not rows:return []
    ids=[r['id'] for r in rows];marks=','.join(['%s']*len(ids))
    cursor.execute(f'SELECT entry_id,tag FROM learning_wrongbook_tags WHERE entry_id IN ({marks}) ORDER BY tag',ids)
    mapping={ident:[] for ident in ids}
    for row in cursor.fetchall():mapping[row['entry_id']].append(row['tag'])
    return [{**serialize(row),'tags':mapping[row['id']]} for row in rows]


def write_tags(cursor,ident,tags):
    cursor.execute('DELETE FROM learning_wrongbook_tags WHERE entry_id=%s',(ident,))
    if tags:cursor.executemany('INSERT INTO learning_wrongbook_tags(entry_id,tag) VALUES(%s,%s)',[(ident,t) for t in tags])


@router.get('/list')
def list_entries(auth_session: str|None=Cookie(None),username: str|None=None,
                 video_id: str='',q: str=Query('',max_length=200),tag: str=Query('',max_length=64),
                 status: Literal['all','due','new','reviewing','mastered']='all',
                 page: int=Query(1,ge=1),page_size: int=Query(20,ge=1,le=100)):
    with transaction() as (_,c):
        user=owner(c,auth_session,username);where=['w.owner_id=%s'];params=[user]
        if video_id:where.append('w.video_id=%s');params.append(video_id)
        if q:
            needle='%'+q.replace('=','==').replace('%','=%').replace('_','=_')+'%'
            where.append("(w.title LIKE %s ESCAPE '=' OR w.problem LIKE %s ESCAPE '=' OR w.note LIKE %s ESCAPE '=')");params.extend([needle]*3)
        if tag:where.append('EXISTS(SELECT 1 FROM learning_wrongbook_tags t WHERE t.entry_id=w.id AND t.tag=%s)');params.append(tag)
        if status=='due':where.append("w.status!='mastered' AND w.next_review_at<=UTC_TIMESTAMP()")
        elif status!='all':where.append('w.status=%s');params.append(status)
        condition=' AND '.join(where)
        c.execute('SELECT COUNT(*) AS total FROM learning_wrongbook w WHERE '+condition,params);total=c.fetchone()['total']
        order='next_review_at,id' if status=='due' else 'updated_at DESC,id DESC'
        c.execute('SELECT * FROM learning_wrongbook w WHERE '+condition+' ORDER BY '+order+' LIMIT %s OFFSET %s',params+[page_size,(page-1)*page_size])
        records=attach_tags(c,c.fetchall())
        c.execute("""SELECT COUNT(*) AS total,COALESCE(SUM(status='mastered'),0) AS mastered,
            COALESCE(SUM(status!='mastered' AND next_review_at<=UTC_TIMESTAMP()),0) AS due,
            COALESCE(SUM(review_count),0) AS reviews FROM learning_wrongbook WHERE owner_id=%s""",(user,))
        stats={k:int(v) for k,v in c.fetchone().items()}
        c.execute('SELECT DISTINCT t.tag FROM learning_wrongbook_tags t JOIN learning_wrongbook w ON w.id=t.entry_id WHERE w.owner_id=%s ORDER BY t.tag',(user,))
        return {'status':'success','username':SESSION_STORE.get(auth_session),'data':records,'total':total,'page':page,'page_size':page_size,'stats':stats,'tags':[r['tag'] for r in c.fetchall()]}


@router.post('/add')
def create_entry(data:EntryWrite,auth_session:str|None=Cookie(None)):
    with transaction() as (_,c):
        user=owner(c,auth_session,data.username)
        if data.formula_id:
            c.execute('SELECT id FROM formulas WHERE id=%s AND user_id=%s',(data.formula_id,SESSION_STORE.get(auth_session)))
            if not c.fetchone():raise HTTPException(404,'来源题解不存在或不属于当前账户')
        fp=fingerprint(data)
        c.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(user,));c.fetchone()
        c.execute('SELECT id FROM learning_wrongbook WHERE owner_id=%s AND fingerprint=%s',(user,fp));existing=c.fetchone()
        if existing:return {'status':'success','id':existing['id'],'duplicate':True}
        c.execute('''INSERT INTO learning_wrongbook(owner_id,source_type,video_id,formula_id,time_sec,title,problem,answer,note,solution_snapshot,fingerprint,difficulty,next_review_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP())''',
            (user,data.source_type,data.video_id,data.formula_id,data.time_sec,data.title,data.problem,data.answer,data.note,data.snapshot.model_dump_json() if data.snapshot else None,fp,data.difficulty))
        ident=c.lastrowid;write_tags(c,ident,data.tags)
        return {'status':'success','id':ident,'duplicate':False}


@router.get('/export')
def export_entries(auth_session:str|None=Cookie(None)):
    with transaction() as (_,c):
        user=owner(c,auth_session)
        c.execute('SELECT * FROM learning_wrongbook WHERE owner_id=%s ORDER BY id',(user,));rows=attach_tags(c,c.fetchall())
        c.execute('SELECT r.* FROM learning_wrongbook_reviews r JOIN learning_wrongbook w ON w.id=r.entry_id WHERE w.owner_id=%s ORDER BY r.id',(user,));reviews=c.fetchall()
        for r in reviews:
            for k,v in r.items():
                if isinstance(v,datetime):r[k]=v.isoformat()+'Z'
        return {'status':'success','format':'wisdom-wrongbook','version':1,'data':rows,'reviews':reviews}


@router.get('/{ident:int}')
def read_entry(ident:int,auth_session:str|None=Cookie(None)):
    with transaction() as (_,c):
        row=require(c,ident,owner(c,auth_session));result=attach_tags(c,[row])[0]
        c.execute('SELECT id,grade,note,interval_days,next_review_at,reviewed_at FROM learning_wrongbook_reviews WHERE entry_id=%s ORDER BY id DESC LIMIT 100',(ident,))
        result['reviews']=[{k:v.isoformat()+'Z' if isinstance(v,datetime) else v for k,v in r.items()} for r in c.fetchall()]
        return {'status':'success','data':result}


@router.put('/{ident:int}')
def update_entry(ident:int,data:EntryWrite,auth_session:str|None=Cookie(None)):
    with transaction() as (_,c):
        user=owner(c,auth_session,data.username);row=require(c,ident,user,True)
        if data.revision!=row['revision']:raise HTTPException(409,'错题已更新，请重新打开后编辑；当前输入已保留')
        # Source references and the original solution snapshot remain immutable.
        data.source_type=row['source_type'];data.video_id=row['video_id'];data.formula_id=row['formula_id'];data.time_sec=row['time_sec']
        try:
            c.execute('''UPDATE learning_wrongbook SET title=%s,problem=%s,answer=%s,note=%s,difficulty=%s,fingerprint=%s,revision=revision+1
                WHERE id=%s AND owner_id=%s''',(data.title,data.problem,data.answer,data.note,data.difficulty,fingerprint(data),ident,user))
        except IntegrityError as error:raise HTTPException(409,'已有相同内容的错题，请检查后再保存') from error
        write_tags(c,ident,data.tags)
        return {'status':'success','id':ident,'revision':row['revision']+1}


@router.post('/{ident:int}/review')
def review_entry(ident:int,data:ReviewWrite,auth_session:str|None=Cookie(None)):
    with transaction() as (_,c):
        user=owner(c,auth_session);row=require(c,ident,user,True)
        if row['revision']!=data.revision:raise HTTPException(409,'此题已有新的修改或复习记录，请重新打开')
        days=1 if data.grade=='again' else min(90,max(3,row['interval_days']*2)) if data.grade=='good' else 0
        now=datetime.now(timezone.utc).replace(tzinfo=None);due=now+timedelta(days=days) if days else None
        state='mastered' if data.grade=='mastered' else 'reviewing'
        c.execute('INSERT INTO learning_wrongbook_reviews(entry_id,grade,note,interval_days,next_review_at,reviewed_at) VALUES(%s,%s,%s,%s,%s,%s)',(ident,data.grade,data.note,days,due,now))
        c.execute('''UPDATE learning_wrongbook SET status=%s,review_count=review_count+1,interval_days=%s,next_review_at=%s,
            last_reviewed_at=%s,revision=revision+1 WHERE id=%s''',(state,days,due,now,ident))
        return {'status':'success','revision':row['revision']+1,'next_review_at':due.isoformat()+'Z' if due else None}


@router.delete('/{ident:int}')
def delete_entry(ident:int,auth_session:str|None=Cookie(None)):
    with transaction() as (_,c):
        user=owner(c,auth_session);require(c,ident,user,True)
        c.execute('DELETE FROM learning_wrongbook WHERE id=%s AND owner_id=%s',(ident,user))
    return {'status':'success'}


@router.delete('/delete')
def legacy_delete(id:int,username:str|None=None,auth_session:str|None=Cookie(None)):
    with transaction() as (_,c):owner(c,auth_session,username)
    return delete_entry(id,auth_session)


@router.put('/update')
def legacy_update(data:LegacyUpdate,auth_session:str|None=Cookie(None)):
    with transaction() as (_,c):
        user=owner(c,auth_session,data.username);row=require(c,data.id,user)
        if data.time_sec is not None and data.time_sec!=row['time_sec']:
            raise HTTPException(422,'来源时间点不能直接修改，请重新收录正确的时间点')
        record=attach_tags(c,[row])[0]
    record.update(data.model_dump(exclude_unset=True,exclude={'id','username','time_sec'}))
    return update_entry(data.id,EntryWrite(**record),auth_session)
