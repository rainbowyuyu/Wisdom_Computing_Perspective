import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app import usage_guard as guard
from app.request_guard import RequestGuard, client_ip
from app.store import SESSION_STORE, ExpiringStore
from logic.manim_generator import render_matrix_animation, parse_latex_to_list


@pytest.fixture(autouse=True)
def fake_access(monkeypatch):
    monkeypatch.setattr('app.access.load_principal',lambda user:{'id':1 if user else None,'username':user,'role':'member' if user else 'guest','disabled':False,'daily_limit':40,'email_verified':True})
    monkeypatch.setattr('app.access.consume',lambda *args,**kwargs:None)


@pytest.fixture
def ledger(tmp_path,monkeypatch):
    value=guard.UsageLedger(tmp_path/'usage.sqlite3')
    monkeypatch.setattr(guard,'ledger',value)
    monkeypatch.setattr('app.request_guard.ledger',value)
    monkeypatch.setenv('AI_REQUIRE_LOGIN','1')
    monkeypatch.setenv('AI_USER_DAILY_CALLS','40')
    monkeypatch.setenv('AI_IP_DAILY_CALLS','80')
    monkeypatch.setenv('AI_GLOBAL_DAILY_CALLS','300')
    monkeypatch.setenv('AI_CALLS_PER_MINUTE','6')
    return value


def test_login_and_atomic_persistent_limits(ledger,monkeypatch):
    with pytest.raises(guard.UsageDenied,match='登录'):ledger.admit('ai',('1.2.3.4',None),100)
    monkeypatch.setenv('AI_GLOBAL_DAILY_CALLS','2')
    def request(i):
        try:return ledger.admit('ai',(str(i),str(i)),100)
        except guard.UsageDenied:return None
    with ThreadPoolExecutor(8) as pool:results=list(pool.map(request,range(8)))
    accepted=[r for r in results if r]
    assert len(accepted)==2
    for lease in accepted:ledger.release(lease)
    restarted=guard.UsageLedger(ledger.path)
    with pytest.raises(guard.UsageDenied,match='额度'):restarted.admit('ai',('new','new'),100)


def test_budget_failure_does_not_call_provider_and_options_cannot_bypass(ledger,monkeypatch):
    calls=[]
    class Provider:
        api_key='test';base_url='test'
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:calls.append(kw)))
        def with_options(self,**kw):
            assert kw=={'timeout':70,'max_retries':0}
            return self
    client=guard.GuardedClient(Provider())
    token=guard.identity.set(('ip','student'))
    try:
        monkeypatch.setenv('AI_GLOBAL_DAILY_CALLS','1')
        client.with_options(max_retries=99).chat.completions.create(messages=[{'role':'user','content':'题目'}],max_tokens=100000)
        assert calls[0]['max_tokens']==7000
        with pytest.raises(guard.UsageDenied):client.chat.completions.create(messages=[])
        assert len(calls)==1
    finally:guard.identity.reset(token)


def test_tokens_fail_closed_on_database_error(tmp_path):
    invalid=guard.UsageLedger(tmp_path)  # a directory cannot be a database
    with pytest.raises(guard.UsageDenied,match='未调用'):invalid.admit('ai',('ip','student'),100)


def test_image_and_message_limits():
    with pytest.raises(guard.UsageDenied):guard.bounded_request({'messages':[{'content':'x'*160001}]})
    with pytest.raises(guard.UsageDenied):guard.bounded_request({'messages':[{'content':[{'type':'image_url','image_url':{'url':'https://example.com/private'}}]}]})
    with pytest.raises(guard.UsageDenied):guard.bounded_request({'messages':[],'n':10})


def test_proxy_headers_cannot_spoof_direct_remote_peer():
    assert client_ip({'client':('8.8.8.8',20)},{'x-real-ip':'127.0.0.1','x-forwarded-for':'1.1.1.1'})=='8.8.8.8'
    assert client_ip({'client':('127.0.0.1',20)},{'x-real-ip':'8.8.8.8'})=='8.8.8.8'


def test_guard_rejects_cross_origin_oversized_and_code_execution(ledger):
    app=FastAPI();app.add_middleware(RequestGuard)
    reached=[]
    @app.post('/api/devtools/run_manim')
    async def code():reached.append(True);return {'ok':True}
    @app.post('/api/solve/stream')
    async def stream(request:Request):
        await request.json()
        async def generate():
            assert guard.identity.get() is not None
            yield 'data: {"type":"complete"}\n\n'
        return StreamingResponse(generate())
    with TestClient(app) as client:
        assert client.post('/api/devtools/run_manim',json={'code':'pass'}).status_code==403
        assert not reached
        assert client.post('/api/solve/stream',json={},headers={'origin':'https://evil.invalid'}).status_code==403
        assert client.post('/api/solve/stream',content=b'x'*2000001).status_code==413
        good=client.post('/api/solve/stream',json={'problem':'x=1'})
        assert good.status_code==200 and 'complete' in good.text
        assert good.headers['x-content-type-options']=='nosniff'
        assert client.get('/static/videos/unsafe.py').status_code==404
        assert client.get('/.env').status_code==404
    with sqlite3.connect(ledger.path) as db:assert db.execute('SELECT COUNT(*) FROM leases').fetchone()[0]==0


def test_context_survives_legacy_executor(ledger):
    async def scenario():
        token=guard.identity.set(('ip','student'))
        try:assert await guard.run_with_context(None,guard.identity.get)==('ip','student')
        finally:guard.identity.reset(token)
    asyncio.run(scenario())


def test_sessions_expire_server_side(monkeypatch):
    clock=[100]
    monkeypatch.setattr('app.store.time.monotonic',lambda:clock[0])
    store=ExpiringStore(5,2);store['one']='u';clock[0]=106
    assert store.get('one') is None
    assert len(store)==0


def test_legacy_matrix_renderer_rejects_code_before_subprocess():
    with pytest.raises(ValueError):render_matrix_animation('1','1','"; malicious()', 'test')
    for matrix in ['bad', 'nan', 'inf', '1&2\\\\3']:
        with pytest.raises(ValueError):parse_latex_to_list(matrix)


def test_async_capacity_waiting_does_not_repeatedly_charge(ledger,monkeypatch):
    monkeypatch.setenv('AI_MAX_CONCURRENT','1')
    async def scenario():
        calls=[]
        async def create(**kwargs):calls.append(kwargs);return 'answer'
        provider=SimpleNamespace(api_key='test',base_url='test',chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        provider.with_options=lambda **_:provider
        client=guard.GuardedClient(provider,asynchronous=True)
        occupied=ledger.admit('ai',('other-ip','other-user'),100)
        token=guard.identity.set(('ip','student'))
        try:
            task=asyncio.create_task(client.acreate(messages=[]))
            await asyncio.sleep(.1)
            assert not calls and not task.done()
            ledger.release(occupied)
            assert await asyncio.wait_for(task,2)=='answer'
            with sqlite3.connect(ledger.path) as db:
                assert db.execute("SELECT value FROM usage WHERE bucket='ai:global'").fetchone()[0]==2
                assert db.execute('SELECT COUNT(*) FROM leases').fetchone()[0]==0
        finally:guard.identity.reset(token)
    asyncio.run(scenario())


def test_cancel_queued_call_never_reaches_provider(ledger,monkeypatch):
    monkeypatch.setenv('AI_MAX_CONCURRENT','1')
    async def scenario():
        async def forbidden(**_):raise AssertionError('cancelled wait must not call provider')
        provider=SimpleNamespace(api_key='test',base_url='test',chat=SimpleNamespace(completions=SimpleNamespace(create=forbidden)))
        provider.with_options=lambda **_:provider
        occupied=ledger.admit('ai',('ip','first'),100)
        token=guard.identity.set(('ip','second'))
        try:
            task=asyncio.create_task(guard.GuardedClient(provider,asynchronous=True).acreate(messages=[]))
            await asyncio.sleep(.1);task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            with sqlite3.connect(ledger.path) as db:
                assert db.execute("SELECT value FROM usage WHERE bucket='ai:global'").fetchone()[0]==1
            ledger.release(occupied)
        finally:guard.identity.reset(token)
    asyncio.run(scenario())
