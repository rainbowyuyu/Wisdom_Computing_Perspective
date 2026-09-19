"""Bounded model decisions, renderer retries and unchanged original solutions."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.responses import StreamingResponse, JSONResponse

from app import render_repair as repair
from app.routers import solve,devtools
from app.models import ManimCodeModel,ManimKeyframeModel
from app.solution_models import RenderRequest
from logic.solution_engine import local_solution


class Request:
    async def is_disconnected(self):return False


def fake_model(monkeypatch,target,answer):
    calls=[]
    async def create(**kwargs):
        calls.append(kwargs)
        if isinstance(answer,Exception):raise answer
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(answer)),finish_reason='stop')])
    monkeypatch.setattr(target,'ai_client',SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    return calls


def stream(items,closed=None):
    async def generate():
        try:
            for item in items:yield solve.event(item['type'],**{k:v for k,v in item.items() if k!='type'})
        finally:
            if closed is not None:closed.append(True)
    return StreamingResponse(generate())


def test_formula_repair_retries_after_cleanup_and_preserves_original(monkeypatch):
    solution=local_solution('x^2=1');solution.steps[0].formula=r'\frac{1}{2'
    original=solution.model_dump();renders=[];closed=[]
    calls=fake_model(monkeypatch,solve,{'repairable':True,'formula':r'\frac{1}{2}'})
    async def once(data,request):
        renders.append(data.solution.model_dump())
        if len(renders)==1:return stream([{'type':'error','message':'排版失败','_failure':'WISDOM_LATEX_ERROR', '_diagnostic':{'code':'syntax','step':1}}],closed)
        assert closed==[True]
        return stream([{'type':'complete','video_url':'/videos/solution_a.mp4','chapters':[]}],closed)
    monkeypatch.setattr(solve,'_render_solution_once',once)
    async def scenario():
        response=await solve.render_solution(RenderRequest(solution=solution),Request())
        events=[json.loads(frame[6:]) async for frame in response.body_iterator]
        assert not any(e['type']=='error' for e in events)
        assert events[-1]['repaired'] and events[-1]['solution']['steps'][0]['formula']==r'\frac{1}{2}'
        assert any(e.get('repairing') for e in events)
    asyncio.run(scenario())
    assert solution.model_dump()==original and len(calls)==1 and len(renders)==2 and len(closed)==2


@pytest.mark.parametrize('mode',['second_failure','declined','invalid','environment','budget'])
def test_failed_repairs_stop_and_environment_does_not_call_model(monkeypatch,mode):
    solution=local_solution('x^2=1');solution.steps[0].formula=r'\frac{1}{2'
    from app.usage_guard import UsageDenied
    answer=UsageDenied('今日 AI 使用额度已达上限') if mode=='budget' else {'repairable':mode!='declined','formula':r'\frac{1}{3}' if mode=='invalid' else r'\frac{1}{2}'}
    calls=fake_model(monkeypatch,solve,answer);renders=[]
    async def once(data,request):
        renders.append(True)
        return stream([{'type':'error','message':'渲染失败','_failure':'WISDOM_LATEX_ERROR','_diagnostic':{'code':'compiler' if mode=='environment' else 'syntax','step':1}}])
    monkeypatch.setattr(solve,'_render_solution_once',once)
    async def scenario():
        response=await solve.render_solution(RenderRequest(solution=solution),Request())
        events=[json.loads(frame[6:]) async for frame in response.body_iterator]
        assert events[-1]['type']=='error'
        assert all('_failure' not in e and '_diagnostic' not in e for e in events)
    asyncio.run(scenario())
    assert len(calls)==(0 if mode=='environment' else 1)
    assert len(renders)==(2 if mode=='second_failure' else 1)


CODE='from manim import *\nclass GenScene(Scene):\n    def construct(self):\n        self.add(Circle())\n'


def test_code_repair_checks_script_and_returns_code_on_success(monkeypatch):
    renders=[];closed=[];calls=fake_model(monkeypatch,devtools,{'repairable':True,'code':CODE})
    async def once(data,request):
        renders.append(data.code)
        if len(renders)==1:return stream([{'type':'error','message':"NameError: name 'Circl' is not defined"}],closed)
        assert closed==[True]
        return stream([{'type':'complete','video_url':'/videos/a.mp4'}],closed)
    monkeypatch.setattr(devtools,'_run_manim_stream_once',once)
    async def scenario():
        response=await devtools.run_manim_stream_endpoint(ManimCodeModel(code=CODE.replace('Circle','Circl')),Request())
        events=[json.loads(frame[6:]) async for frame in response.body_iterator]
        assert events[-1]['repaired'] and events[-1]['code']==CODE
        assert any(e['type']=='repair' for e in events)
    asyncio.run(scenario())
    assert len(calls)==1 and len(renders)==2 and len(closed)==2


def test_unsafe_code_suggestion_is_never_executed(monkeypatch):
    calls=fake_model(monkeypatch,devtools,{'repairable':True,'code':'import os\n'+CODE})
    with pytest.raises(ValueError,match='导入'):
        asyncio.run(devtools.repair_code('broken','SyntaxError: invalid syntax',{'used':False}))
    assert len(calls)==1


def test_preview_and_video_share_one_repair_budget(monkeypatch):
    calls=fake_model(monkeypatch,devtools,{'repairable':True,'code':CODE});previews=[]
    async def preview(data,request):
        previews.append(data.code)
        return JSONResponse({'message':'NameError: Circl'},status_code=400) if len(previews)==1 else {'status':'success','preview_url':'/videos/a_preview.png'}
    async def video(data,request):return stream([{'type':'error','message':'ValueError: failed animation'}])
    monkeypatch.setattr(devtools,'_render_keyframe_once',preview);monkeypatch.setattr(devtools,'_run_manim_stream_once',video)
    async def scenario():
        budget={'used':False}
        result=await devtools._render_keyframe_with_repair(ManimKeyframeModel(code=CODE.replace('Circle','Circl')),Request(),budget)
        assert result['repaired'] and result['code']==CODE
        response=await devtools._run_manim_with_repair(ManimCodeModel(code=CODE),Request(),budget)
        events=[json.loads(frame[6:]) async for frame in response.body_iterator]
        assert events[-1]['type']=='error'
    asyncio.run(scenario())
    assert len(calls)==1


def test_cancelled_repair_cancels_model_and_never_retries():
    async def scenario():
        started=asyncio.Event();cancelled=asyncio.Event()
        async def pending():
            try:started.set();await asyncio.Event().wait()
            finally:cancelled.set()
        async def consume():
            async for _ in repair.repair_progress(pending,Request()):pass
        task=asyncio.create_task(consume());await started.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert cancelled.is_set()
    asyncio.run(scenario())


@pytest.mark.parametrize('text',['FileNotFoundError: latex','ModuleNotFoundError: manim','PermissionError','渲染资源繁忙，排队超时','No space left on device'])
def test_environment_and_capacity_failures_are_not_model_repairable(text):
    assert not repair.eligible(text)


def test_formula_validator_rejects_changed_relations_and_executable_tex():
    with pytest.raises(ValueError):repair.validate_formula_change(r'x\le 2',r'x\ge 2')
    with pytest.raises(ValueError):repair.validate_formula_change('x=1',r'\input{x}')
    with pytest.raises(ValueError):repair.validate_formula_change(r'\sin{x',r'\cos{x}')
    assert repair.validate_formula_change(r'\fracc{1}{2}',r'\frac{1}{2}')==r'\frac{1}{2}'


def test_repair_diagnostics_redact_credentials_and_file_paths():
    text=repair.safe_diagnostic('File "C:/private/scene.py"\nAuthorization: Bearer private-key\napi_key=secret-value')
    assert 'private' not in text and 'secret-value' not in text
