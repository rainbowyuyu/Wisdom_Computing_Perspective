import asyncio
import ast
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import ManimCodeEditModel, ManimCodeModel
from app.routers import devtools

CODE = 'from manim import *\n\nclass GenScene(Scene):\n    def construct(self):\n        circle = Circle(color=BLUE)\n        self.play(\n            Create(circle),\n            run_time=1\n        )\n        self.wait(1)\n'


def test_named_scene_can_run_without_rewriting_math_literals():
    original=CODE.replace('GenScene','CircleScene')+'\n# GenScene in a comment is not a class\n'
    normalized=devtools.normalize_scene_code(original)
    assert original.strip() in normalized
    assert 'class GenScene(CircleScene):' in normalized
    assert devtools.normalize_scene_code(normalized)==normalized
    devtools.validate_edit_code(normalized)
    ast.parse(devtools._apply_breakpoint(normalized,7))


def test_multiline_breakpoint_preserves_complete_statement():
    bounded = devtools._apply_breakpoint(CODE, 7)
    ast.parse(bounded)
    assert bounded.index('run_time=1') < bounded.index('return  # preview') < bounded.index('self.wait')
    assert devtools.validate_edit_code(CODE) == [9, 10]
    with pytest.raises(ValueError): devtools._apply_breakpoint(CODE, 1)


@pytest.mark.parametrize('extra', ['import os', 'from pathlib import Path', 'open("file")', '__import__("os")', 'Circle.__class__'])
def test_generated_code_rejects_unsupported_operations(extra):
    with pytest.raises(ValueError): devtools.validate_edit_code(CODE+'\n'+extra)


def test_edit_keeps_full_source_and_repairs_syntax(monkeypatch):
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        code='def broken(' if len(calls)==1 else CODE
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'code':code,'summary':'绘制圆'})))])
    monkeypatch.setattr(devtools,'api_key','test')
    monkeypatch.setattr(devtools,'ai_client',SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    long_code=CODE+'\n# '+('x'*8000)+'\n# keep-this-tail'
    result=asyncio.run(devtools.edit_manim_code(ManimCodeEditModel(code=long_code,instruction='修复语法')))
    assert result['validation']=='syntax_checked'
    assert result['code']==CODE.strip()
    assert len(calls)==2
    assert 'keep-this-tail' in calls[0]['messages'][1]['content']
    assert result['keyframe_lines']==[10]


def test_empty_source_is_valid_for_creation(monkeypatch):
    async def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'code':CODE,'summary':'创建动画'})))])
    monkeypatch.setattr(devtools,'api_key','test')
    monkeypatch.setattr(devtools,'ai_client',SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result=asyncio.run(devtools.edit_manim_code(ManimCodeEditModel(code='',instruction='画圆')))
    assert result['status']=='success'


def test_render_stream_returns_syntax_error_instead_of_success():
    app=FastAPI();app.include_router(devtools.router)
    with TestClient(app) as client:
        response=client.post('/devtools/run_manim_stream',json={'code':'def broken('})
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[-1]['type']=='error'
        assert not any(e['type']=='complete' for e in events)


def test_cancelled_stream_kills_child_and_releases_slot(monkeypatch):
    class Process:
        returncode=None
        def poll(self):return self.returncode
    process=Process()
    class Request:
        async def is_disconnected(self):return False
    async def check():
        monkeypatch.setattr(devtools,'DEV_RENDER_SLOTS',asyncio.Semaphore(1))
        monkeypatch.setattr(devtools.subprocess,'Popen',lambda *a,**kw:process)
        monkeypatch.setattr(devtools,'stop_process',lambda p:setattr(p,'returncode',-9))
        response=await devtools.run_manim_stream_endpoint(ManimCodeModel(code=CODE),Request())
        stream=response.body_iterator
        await anext(stream)
        pending=asyncio.create_task(anext(stream))
        await asyncio.sleep(.05);pending.cancel()
        with pytest.raises(asyncio.CancelledError):await pending
        assert process.returncode==-9
        assert devtools.DEV_RENDER_SLOTS._value==1
    asyncio.run(check())
