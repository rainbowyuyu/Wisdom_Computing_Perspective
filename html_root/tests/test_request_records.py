import asyncio
import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app import request_records as records
from app.database import transaction
from app.request_guard import RequestGuard
from app.routers import accounts
from tests.test_account_access import environment


class MemoryJournal:
    def __init__(self):self.items=[]
    def put(self,kind,data):self.items.append((kind,data));return True


def test_input_is_whitelisted_bounded_and_credentials_redacted():
    text,image,truncated=records.input_summary('/api/solve/stream',json.dumps({
        'problem':'求导 x^2 api_key=secret123 token=abc123 Bearer abcdefghijkl sk-abcdefghijklm',
        'password':'private-password','history':['private-history'],'code':'private-code',
        'context':'附加条件'}).encode(),'application/json')
    assert '求导 x^2' in text and '附加条件' in text
    for secret in ['secret123','abc123','abcdefghijkl','private-password','private-history','private-code']:assert secret not in text
    text,_,truncated=records.input_summary('/api/agent/tasks',json.dumps({'problem':'题'*13000}).encode(),'application/json')
    assert len(text)==12000 and truncated
    assert records.input_summary('/api/detect',b'raw-private-image','multipart/form-data')==('',True,False)
    assert records.input_summary('/api/devtools/run_manim',b'{"code":"secret-script"}','application/json')==('',False,False)
    assert '/api/login' not in records.ROUTES and '/api/register' not in records.ROUTES


@pytest.mark.parametrize('kind,completion,expected',[('error',None,'failed'),('handoff',None,'handoff'),('complete','partial','partial'),('complete','solved','completed')])
def test_sse_status_even_with_split_utf8_frames(monkeypatch,kind,completion,expected):
    memory=MemoryJournal();monkeypatch.setattr(records,'journal',memory)
    record=records.RequestRecord('/api/solve/stream',None,b'{"problem":"x=1"}','application/json','Mozilla/Windows Chrome/1')
    record.observe({'type':'http.response.start','status':200,'headers':[(b'content-type',b'text/event-stream')]})
    raw=('data: '+json.dumps({'type':kind,'message':'中文消息','solution':{'completion':completion}},ensure_ascii=False)+'\n\n').encode()
    for i in range(0,len(raw),7):record.observe({'type':'http.response.body','body':raw[i:i+7],'more_body':True})
    record.observe({'type':'http.response.body','body':b'','more_body':False});record.finish()
    assert memory.items[-1][1]['status']==expected
    assert memory.items[0][1]['device']=='Windows / Chrome'


def test_disconnect_and_http_rejection_are_not_success(monkeypatch):
    memory=MemoryJournal();monkeypatch.setattr(records,'journal',memory)
    for code,expected in [(None,'cancelled'),(429,'rejected'),(503,'failed')]:
        record=records.RequestRecord('/api/solve/stream',None,b'{}','application/json','')
        record.code=code;record.finish()
        assert memory.items[-1][1]['status']==expected


@pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS')!='1',reason='Requires isolated MySQL accounts')
def test_real_middleware_journal_owner_permissions_search_and_task_state(environment,monkeypatch):
    _,users,sessions,_,_=environment
    journal=records.Journal();monkeypatch.setattr(records,'journal',journal)
    app=FastAPI();app.add_middleware(RequestGuard);app.include_router(accounts.router,prefix='/api')
    @app.post('/api/solve/stream')
    async def solve():
        async def body():yield 'data: {"type":"error","message":"not persisted"}\n\n'
        return StreamingResponse(body(),media_type='text/event-stream')
    try:
        with TestClient(app) as client:
            client.cookies.set('auth_session',sessions['member'])
            response=client.post('/api/solve/stream',json={'problem':'求导 x^2 token=do-not-store'})
            assert response.status_code==200 and journal.flush()
            assert client.get('/api/admin/requests').status_code==403
            client.cookies.set('auth_session',sessions['admin'])
            data=client.get('/api/admin/requests',params={'user_id':users['member']['id'],'q':'求导'}).json()
            assert data['total']==1
            row=data['items'][0];assert row['status']=='failed' and row['http_status']==200
            assert 'do-not-store' not in json.dumps(data)
            detail=client.get('/api/admin/requests/'+row['id']).json()['item']
            assert detail['owner_id']==users['member']['id'] and '[凭据已隐藏]' in detail['problem']
            assert client.get('/api/admin/requests',params={'feature':'wrong'}).status_code==422
            assert client.get('/api/admin/requests',params={'q':'%_'}).json()['total']==0
            # Delegated administrator retains no management/read access.
            target='/api/admin/users/'+str(users['member']['id'])
            assert client.patch(target,json={'role':'admin'}).status_code==200
            client.cookies.set('auth_session',sessions['member'])
            assert client.get('/api/admin/requests/'+row['id']).status_code==403
            assert client.get('/api/account/access').json()['can_manage'] is False
            client.cookies.set('auth_session',sessions['admin'])
            assert client.patch(target,json={'role':'vip'}).status_code==200
        # A queued HTTP reply cannot overwrite a job which has already failed.
        record=records.RequestRecord('/api/agent/tasks',{'id':users['member']['id'],'username':users['member']['username'],'role':'vip'},b'{"problem":"task"}','application/json','')
        job={'id':'a'*32,'journal_id':record.id,'status':'error','created':time.time()-2}
        records.job_progress(job)
        record.job_id=job['id'];record.status='queued';record.code=202;record.finished=True;record.finish()
        assert journal.flush()
        with transaction() as (_,cur):
            cur.execute('SELECT status FROM request_records WHERE id=%s',(record.id,));assert cur.fetchone()['status']=='failed'
        # Losing the HTTP reply after task acceptance must not detach the job.
        record.job_id=None;record.finished=False;record.finish()
        assert journal.flush()
        with transaction() as (_,cur):
            cur.execute('SELECT status,job_id FROM request_records WHERE id=%s',(record.id,))
            assert cur.fetchone()=={'status':'failed','job_id':job['id']}
    finally:
        journal.close()
        with transaction() as (_,cur):
            for user in users.values():cur.execute('DELETE FROM request_records WHERE owner_id=%s',(user['id'],))
