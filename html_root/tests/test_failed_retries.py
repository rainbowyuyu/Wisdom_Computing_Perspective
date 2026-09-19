"""Failure injection: personal quota is separate from provider admission."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse, JSONResponse

from app import access, usage_guard
from app.request_guard import RequestGuard
from app.store import SESSION_STORE
from logic.solution_engine import local_solution
from test_cost_protection import ledger


@pytest.mark.parametrize('path,payload', [
    ('/api/solve/stream', {'problem':'x^2=1'}),
    ('/api/solve/render', {'solution':local_solution('x^2=1').model_dump()}),
    ('/api/agent/execute', {'prompt':'解方程 x^2=1'}),
])
def test_failed_retry_is_free_successful_repeat_is_not(ledger,monkeypatch,path,payload):
    charged=[];mode=['error'];provider_calls=[]
    monkeypatch.setattr(access,'consume',lambda *a,**k:charged.append(a[0]))
    app=FastAPI();app.add_middleware(RequestGuard)
    async def handler():
        assert access.feature_authorized.get()
        # Even quota-free retries must still pass the provider's token budget.
        lease=ledger.admit('ai',usage_guard.identity.get(),100)
        provider_calls.append(True);ledger.release(lease)
        if path.endswith('execute'):return {'status':mode[0]}
        async def events():
            yield 'data: '+json.dumps({'type':'complete' if mode[0]=='success' else 'error'})+'\n\n'
        return StreamingResponse(events(),media_type='text/event-stream')
    app.post(path)(handler)
    with TestClient(app) as client:
        assert client.post(path,json=payload,headers={'X-Wisdom-Retry':'1'}).status_code==409
        assert not charged and not provider_calls
        assert client.post(path,json=payload).status_code==200
        assert len(charged)==1
        mode[0]='success'
        assert client.post(path,json=payload,headers={'X-Wisdom-Retry':'1'}).status_code==200
        assert len(charged)==1 and len(provider_calls)==2
        # A successful result cannot mint another free request.
        assert client.post(path,json=payload,headers={'X-Wisdom-Retry':'1'}).status_code==409
        assert client.post(path,json=payload).status_code==200
        assert len(charged)==2


def test_credit_bound_to_owner_body_and_endpoint_and_capped(ledger,monkeypatch):
    charged=[]
    monkeypatch.setattr(access,'consume',lambda *a,**k:charged.append(True))
    monkeypatch.setattr(access,'load_principal',lambda user:{'id':1 if user=='alice' else 2,'username':user,'email_verified':True})
    SESSION_STORE['retry-alice']='alice';SESSION_STORE['retry-bob']='bob'
    app=FastAPI();app.add_middleware(RequestGuard)
    @app.post('/api/solve/stream')
    async def handler():return JSONResponse({'status':'error'},status_code=503)
    try:
        with TestClient(app) as client:
            client.cookies.set('auth_session','retry-alice')
            assert client.post('/api/solve/stream',json={'problem':'x=1'}).status_code==503
            client.cookies.set('auth_session','retry-bob')
            assert client.post('/api/solve/stream',json={'problem':'x=1'},headers={'X-Wisdom-Retry':'1'}).status_code==409
            client.cookies.set('auth_session','retry-alice')
            assert client.post('/api/solve/stream',json={'problem':'x=2'},headers={'X-Wisdom-Retry':'1'}).status_code==409
            for _ in range(2):
                assert client.post('/api/solve/stream',json={'problem':'x=1'},headers={'X-Wisdom-Retry':'1'}).status_code==503
            denied=client.post('/api/solve/stream',json={'problem':'x=1'},headers={'X-Wisdom-Retry':'1'})
            assert denied.status_code==429 and '未扣额外额度' in denied.json()['message']
            assert len(charged)==1
            # No silent debit if the button or request omits the retry marker.
            assert client.post('/api/solve/stream',json={'problem':'x=1'}).status_code==429
            assert len(charged)==1
    finally:
        SESSION_STORE.pop('retry-alice',None);SESSION_STORE.pop('retry-bob',None)


def test_guest_credit_does_not_transfer_to_other_cookie(ledger,monkeypatch):
    monkeypatch.setattr(access,'consume',lambda *a,**k:None)
    app=FastAPI();app.add_middleware(RequestGuard)
    @app.post('/api/agent/execute')
    def handler():return {'status':'error'}
    with TestClient(app) as client:
        client.post('/api/agent/execute',json={'prompt':'求解'})
        cookie=client.cookies.get('wisdom_trial')
        client.cookies.clear()
        assert client.post('/api/agent/execute',json={'prompt':'求解'},headers={'X-Wisdom-Retry':'1'}).status_code==409
        client.cookies.clear();client.cookies.set('wisdom_trial',cookie)
        assert client.post('/api/agent/execute',json={'prompt':'求解'},headers={'X-Wisdom-Retry':'1'}).status_code==200


def test_retry_receipt_survives_restart_and_atomic_claims(ledger):
    key='test-digest';ledger.finish_failed_retry(key,True)
    restored=usage_guard.UsageLedger(ledger.path)
    def claim():
        try:return restored.claim_failed_retry(key)
        except usage_guard.UsageDenied:return False
    with ThreadPoolExecutor(8) as pool:assert sum(pool.map(lambda _:claim(),range(8)))==2
    with restored.connection() as db:db.execute('UPDATE failed_requests SET expires=0')
    assert not restored.claim_failed_retry(key)


def test_exhausted_personal_quota_can_retry_but_provider_budget_still_blocks(ledger,monkeypatch):
    charges=[]
    def consume(*a,**k):
        if charges:raise access.AccessDenied('今日个人额度已用完')
        charges.append(True)
    monkeypatch.setattr(access,'consume',consume)
    app=FastAPI();app.add_middleware(RequestGuard)
    @app.post('/api/agent/execute')
    def handler():
        try:lease=ledger.admit('ai',usage_guard.identity.get(),100)
        except usage_guard.UsageDenied as error:return JSONResponse({'status':'error','message':str(error)},status_code=429)
        ledger.release(lease)
        return {'status':'error','message':'模拟模型故障'}
    with TestClient(app) as client:
        assert client.post('/api/agent/execute',json={'prompt':'原问题'}).status_code==200
        assert client.post('/api/agent/execute',json={'prompt':'新问题'}).status_code==403
        assert client.post('/api/agent/execute',json={'prompt':'原问题'},headers={'X-Wisdom-Retry':'1'}).status_code==200
        monkeypatch.setenv('AI_GLOBAL_DAILY_CALLS','2')
        denied=client.post('/api/agent/execute',json={'prompt':'原问题'},headers={'X-Wisdom-Retry':'1'})
        assert denied.status_code==429 and 'AI 使用额度' in denied.json()['message']
        assert len(charges)==1


def test_plan_repairs_invalid_json_once_without_hiding_exhaustion(monkeypatch):
    from app.routers import agent
    calls=[];outputs=iter(['{"steps":', '{"steps":[{"section":"chat","reply":"已修复"}]}'])
    def create(**kw):
        calls.append(list(kw['messages']))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=next(outputs)))])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client.with_options=lambda **kw:client
    monkeypatch.setattr(agent,'client',client)
    assert agent.generate_plan('原题')['steps'][0]['reply']=='已修复'
    assert len(calls)==2 and '格式检查失败' in calls[1][-1]['content']
    outputs=iter(['[]','{}']);calls.clear()
    with pytest.raises(ValueError,match='修复后仍不可用'):agent.generate_plan('原题')
    assert len(calls)==2
