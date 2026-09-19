"""No real provider calls: fault injection for billing and request admission."""
import asyncio
import sqlite3
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import AuthenticationError,APIConnectionError,RateLimitError,BadRequestError

from app import usage_guard as guard,access
from app.request_guard import RequestGuard
from app.routers import devtools
from app.models import ManimCodeModel


@pytest.fixture
def ledger(tmp_path,monkeypatch):
    monkeypatch.setattr('app.request_records.journal.put',lambda *args:False)
    ledger=guard.UsageLedger(tmp_path/'quota.db')
    monkeypatch.setattr(guard,'ledger',ledger);monkeypatch.setattr('app.request_guard.ledger',ledger)
    monkeypatch.setattr(access,'load_principal',lambda user:{'id':1,'role':'member','username':user})
    monkeypatch.setattr(access,'consume',lambda *args,**kwargs:None)
    monkeypatch.setenv('AI_CALLS_PER_MINUTE','100');monkeypatch.setenv('API_REQUESTS_PER_MINUTE','100')
    return ledger


def provider(create):
    p=SimpleNamespace(api_key='fake',base_url='https://provider.invalid',chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    p.with_options=lambda **kwargs:p
    return p


@pytest.mark.parametrize('status,error_type,attempts',[(401,AuthenticationError,1),(429,RateLimitError,1),(503,APIConnectionError,3)])
def test_faults_open_shared_persistent_circuit_without_additional_debit(ledger,status,error_type,attempts):
    calls=[]
    def create(**kwargs):
        calls.append(True);req=httpx.Request('POST','https://provider.invalid')
        if error_type is APIConnectionError:raise APIConnectionError(request=req)
        raise error_type('private upstream text',response=httpx.Response(status,request=req),body={})
    client=guard.GuardedClient(provider(create));token=guard.identity.set(('ip','student'))
    try:
        for _ in range(attempts):
            with pytest.raises(error_type):client.create(messages=[])
        fresh=guard.GuardedClient(provider(create))
        with pytest.raises(guard.UsageDenied,match='暂停重复调用'):fresh.create(messages=[])
        assert len(calls)==attempts
        with sqlite3.connect(ledger.path) as db:
            assert db.execute("SELECT value FROM usage WHERE bucket='ai:global'").fetchone()[0]==attempts
        assert b'private upstream text' not in ledger.path.read_bytes()
        assert b'https://provider.invalid' not in ledger.path.read_bytes()
    finally:guard.identity.reset(token)


def test_circuit_recovery_does_not_allow_older_success_to_clear_new_failure(ledger,monkeypatch):
    req=httpx.Request('POST','https://provider.invalid')
    error=RateLimitError('busy',response=httpx.Response(429,request=req),body={})
    ledger.provider_result('provider',time.time(),error)
    ledger.provider_result('provider',time.time()-100)
    with pytest.raises(guard.UsageDenied):ledger.check_provider('provider')
    future=time.time()+61;monkeypatch.setattr(guard.time,'time',lambda:future)
    ledger.check_provider('provider')
    ledger.provider_result('provider',future)
    with sqlite3.connect(ledger.path) as db:assert not db.execute('SELECT * FROM provider_circuit').fetchall()


def test_bad_input_is_not_a_provider_outage(ledger):
    req=httpx.Request('POST','https://provider.invalid')
    for _ in range(4):ledger.provider_result('provider',time.time(),BadRequestError('invalid',response=httpx.Response(400,request=req),body={}))
    ledger.check_provider('provider')


def test_async_failure_also_opens_circuit(ledger):
    async def scenario():
        async def create(**kwargs):raise AuthenticationError('invalid',response=httpx.Response(401,request=httpx.Request('POST','https://provider.invalid')),body={})
        client=guard.GuardedClient(provider(create),asynchronous=True)
        token=guard.identity.set(('ip','student'))
        try:
            with pytest.raises(AuthenticationError):await client.acreate(messages=[])
            with pytest.raises(guard.UsageDenied):await client.acreate(messages=[])
        finally:guard.identity.reset(token)
    asyncio.run(scenario())


def test_cancelled_sync_queue_does_not_start_provider(ledger,monkeypatch):
    monkeypatch.setenv('AI_MAX_CONCURRENT','1')
    occupied=ledger.admit('ai',('ip','other'),100)
    calls=[];cancelled=threading.Event()
    async def scenario():
        token=guard.identity.set(('ip','student'));cancel_token=guard.request_cancelled.set(cancelled)
        try:
            task=asyncio.create_task(asyncio.to_thread(guard.GuardedClient(provider(lambda **kw:calls.append(True))).create,messages=[]))
            await asyncio.sleep(.1);cancelled.set();ledger.release(occupied)
            with pytest.raises(guard.UsageDenied,match='请求已结束'):await task
            assert not calls
        finally:guard.identity.reset(token);guard.request_cancelled.reset(cancel_token)
    asyncio.run(scenario())


def test_duplicate_is_rejected_before_quota_and_released_after_completion(ledger,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    charged=[];started=threading.Event();finish=threading.Event()
    monkeypatch.setattr(access,'consume',lambda *args,**kwargs:charged.append(True))
    app=FastAPI();app.add_middleware(RequestGuard)
    @app.post('/api/solve/stream')
    async def solve():
        started.set();await asyncio.to_thread(finish.wait,3);return {'ok':True}
    with TestClient(app) as client,ThreadPoolExecutor(2) as pool:
        first=pool.submit(client.post,'/api/solve/stream',json={'problem':'x=1'})
        assert started.wait(2)
        duplicate=client.post('/api/solve/stream',content=' { "problem": "x=1", "context": "" }',headers={'content-type':'application/json'})
        assert duplicate.status_code==409 and duplicate.json()['code']=='duplicate_request'
        assert len(charged)==1
        finish.set();assert first.result().status_code==200
        assert client.post('/api/solve/stream',json={'problem':'x=1'}).status_code==200
        assert len(charged)==2
        assert client.post('/api/solve/stream',json={'problem':''}).status_code==422
        assert client.post('/api/solve/stream',content='not-json').status_code==422
        assert len(charged)==2
    with sqlite3.connect(ledger.path) as db:assert db.execute('SELECT COUNT(*) FROM leases').fetchone()[0]==0


def test_legacy_renderer_reuses_stream_cleanup(monkeypatch):
    from starlette.responses import StreamingResponse
    closed=[]
    async def stream(data,request):
        async def events():
            try:yield 'data: {"type":"complete","video_url":"/videos/example.mp4"}\n\n'
            finally:closed.append(True)
        return StreamingResponse(events())
    monkeypatch.setattr(devtools,'run_manim_stream_endpoint',stream)
    result=asyncio.run(devtools.run_custom_manim(ManimCodeModel(code='pass'),None))
    assert result['status']=='success' and closed==[True]


def test_cleanup_holds_render_slot_until_worker_stops_even_on_repeated_cancel(monkeypatch):
    from app.async_cleanup import finish_cleanup
    async def scenario():
        slots=asyncio.Semaphore(1)
        monkeypatch.setattr(devtools,'DEV_RENDER_SLOTS',slots)
        await slots.acquire()
        started=threading.Event();finish=threading.Event();removed=[]
        def stop(proc):
            started.set();finish.wait(3)
        monkeypatch.setattr(devtools,'stop_process',stop)
        task=asyncio.create_task(finish_cleanup(devtools.cleanup_renderer(
            SimpleNamespace(poll=lambda:None),SimpleNamespace(cleanup=lambda:removed.append(True)),True)))
        assert await asyncio.to_thread(started.wait,2)
        task.cancel();await asyncio.sleep(.01);task.cancel();await asyncio.sleep(.01)
        assert slots.locked() and not removed
        finish.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert not slots.locked() and removed==[True]
    asyncio.run(scenario())


def test_matrix_render_cancellation_kills_process_and_removes_script(tmp_path,monkeypatch):
    from logic import manim_generator as matrix
    from app.routers import solve
    cancelled=threading.Event();killed=[]
    proc=SimpleNamespace(poll=lambda:None)
    def start(*args,**kwargs):
        script=tmp_path/'temp_cancelled.py'
        compile(script.read_text(encoding='utf-8'),str(script),'exec')
        cancelled.set();return proc
    monkeypatch.setattr(matrix,'BASE_DIR',str(tmp_path))
    monkeypatch.setattr(matrix.subprocess,'Popen',start)
    monkeypatch.setattr(solve,'stop_process',lambda p:killed.append(p))
    assert matrix.render_matrix_animation('1','2','add','cancelled',cancelled) is None
    assert killed==[proc] and not list(tmp_path.glob('*.py'))


def test_keyframe_queue_has_deadline_without_starting_process(monkeypatch):
    clock=iter([0,61])
    monkeypatch.setattr(devtools,'time',SimpleNamespace(monotonic=lambda:next(clock)))
    monkeypatch.setattr(devtools,'normalize_scene_code',lambda code:code)
    monkeypatch.setattr(devtools,'validate_edit_code',lambda code:None)
    from app.models import ManimKeyframeModel
    response=asyncio.run(devtools.render_keyframe(ManimKeyframeModel(code='pass'),None))
    assert response.status_code==400 and '排队超时' in response.body.decode()


def test_legacy_stream_keeps_solution_and_does_not_pay_for_auto_repair(monkeypatch):
    from app.routers import detect
    from app.models import CalcModel
    from starlette.responses import JSONResponse
    calls=[]
    def create(**kwargs):
        calls.append(True)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='solution' if len(calls)==1 else 'from manim import *'))])
    monkeypatch.setattr(detect,'client',provider(create))
    async def preview(*args):return JSONResponse({'message':'render failed'},status_code=400)
    monkeypatch.setattr(devtools,'_render_keyframe_with_repair',preview)
    async def connected():return False
    async def scenario():
        response=await detect.generate_animation_stream(CalcModel(matrixA='x=1',matrixB='',operation='normal'),SimpleNamespace(is_disconnected=connected))
        frames=[frame async for frame in response.body_iterator]
        assert any('text_result' in frame for frame in frames)
        assert 'error' in frames[-1] and '手动重试' in frames[-1]
    asyncio.run(scenario())
    assert len(calls)==2
