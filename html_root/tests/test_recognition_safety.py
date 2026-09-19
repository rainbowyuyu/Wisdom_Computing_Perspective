import asyncio
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from PIL import Image, ImageDraw
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import recognition, host_resources, math_runtime, math_jobs
from app.routers import detect
from app.request_guard import RequestGuard
from logic.single_problem import multiple_problems


def picture():
    image=Image.new('RGB',(200,100),'white');ImageDraw.Draw(image).text((10,10),'x + 1 = 2',fill='black')
    output=io.BytesIO();image.save(output,'PNG');return output.getvalue()


def completion(data,reason='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason,message=SimpleNamespace(content=json.dumps(data) if isinstance(data,dict) else data))])


@pytest.mark.parametrize('content',[b'',b'not-an-image',b'a'*5000001], ids=['empty','invalid','oversized'])
def test_invalid_picture_rejected(content):
    with pytest.raises(recognition.RecognitionIssue):recognition.prepare_image(content)


def test_blank_and_oversized_pixels_rejected_but_real_png_reencoded():
    import base64
    for size in [(100,100),(4000,4000)]:
        raw=io.BytesIO();Image.new('RGB',size,'white').save(raw,'PNG')
        with pytest.raises(recognition.RecognitionIssue):recognition.prepare_image(raw.getvalue())
    assert base64.b64decode(recognition.prepare_image(picture())).startswith(b'\xff\xd8')


@pytest.mark.parametrize('data',[{},'not JSON',{'quality':'unreadable'},{'quality':'clear','latex':''},
    {'quality':'multiple','problem_text':'第一题 x=1，第二题 y=2'}])
def test_unusable_output_never_becomes_a_formula(data):
    with pytest.raises(recognition.RecognitionIssue):recognition.parse_result(completion(data))


def test_unclear_formula_requires_review_and_keeps_full_statement():
    data={'quality':'clear','latex':'x^?=1','problem_text':'已知 x>0，求 x^?=1 的解','vision_prompt':'图中标记 A','uncertainties':['指数看不清']}
    result=recognition.parse_result(completion(data))
    assert result['needs_review'] and result['problem_text']==data['problem_text']
    with pytest.raises(recognition.RecognitionIssue):recognition.parse_result(completion(data,'length'))


@pytest.mark.parametrize('text,expected',[
    ('1. 求导 x^2\n2. 解方程 x=1',True),('第一题 x=1 第二题 y=2',True),
    ('已知函数f(x)，(1) 求导；(2) 求极值；(3) 求范围',False),
    (r'\begin{cases}x+y=2\\x-y=0\end{cases}',False),('1.25\n2.50',False)])
def test_one_problem_accepts_subquestions_and_systems(text,expected):
    assert multiple_problems(text)==expected


def test_ocr_invalid_image_never_calls_provider_and_releases_slot(monkeypatch):
    client=Mock()
    with pytest.raises(recognition.RecognitionIssue):recognition.recognize_sync(b'bad',client)
    client.with_options.assert_not_called()
    assert recognition.SLOTS.acquire(False);assert recognition.SLOTS.acquire(False)
    recognition.SLOTS.release();recognition.SLOTS.release()


def test_pressure_stops_new_generation_before_quota_and_keeps_reading(monkeypatch):
    monkeypatch.setattr(host_resources,'available_memory',lambda:10*1024*1024)
    debit=Mock();monkeypatch.setattr('app.access.consume_async',debit)
    app=FastAPI();app.add_middleware(RequestGuard)
    app.add_api_route('/api/solve/stream',lambda:{'should':'not execute'},methods=['POST'])
    app.add_api_route('/api/examples',lambda:{'ok':True})
    with TestClient(app) as client:
        result=client.post('/api/solve/stream',json={'problem':'x=1'})
        assert result.status_code==503 and result.json()['retryable'] is False
        assert client.get('/api/examples').status_code==200
    debit.assert_not_called()


def test_emergency_pressure_kills_worker_and_frees_capacity(monkeypatch):
    import sys
    calls=[0]
    def pressure():
        calls[0]+=1
        if calls[0]>1:raise host_resources.HostBusy('resource pressure')
    monkeypatch.setattr(host_resources,'require_capacity',lambda:None)
    monkeypatch.setattr(host_resources,'require_emergency_capacity',pressure)
    monkeypatch.setattr(math_runtime,'command',lambda:[sys.executable,'-c','import time; time.sleep(60)'])
    with pytest.raises(host_resources.HostBusy):asyncio.run(math_runtime.run_math('local',{},10))
    assert math_runtime.SLOTS.acquire(False);math_runtime.SLOTS.release()


def test_low_disk_rejects_heavy_work(monkeypatch):
    monkeypatch.setattr(host_resources,'available_memory',lambda:2**32)
    monkeypatch.setattr(host_resources.shutil,'disk_usage',lambda _:SimpleNamespace(free=1024))
    with pytest.raises(host_resources.HostBusy):host_resources.require_capacity()


def test_multiple_questions_rejected_before_charging(monkeypatch):
    monkeypatch.setattr(host_resources,'pressure_message',lambda:'')
    debit=Mock();monkeypatch.setattr('app.access.consume_async',debit)
    app=FastAPI();app.add_middleware(RequestGuard)
    app.add_api_route('/api/solve/stream',lambda:{'should':'not execute'},methods=['POST'])
    with TestClient(app) as client:
        result=client.post('/api/solve/stream',json={'problem':'第一题 求导 x^2；第二题 求导 x^3'})
        assert result.status_code==422 and result.json()['code']=='single_problem_required'
    debit.assert_not_called()


def test_agent_image_uses_one_recognition_call_and_requires_review(monkeypatch):
    import base64
    from app.routers import agent
    from app.models import AgentRequest
    client=Mock()
    client.with_options.return_value.chat.completions.create.return_value=completion({
        'quality':'clear','latex':'x+1=2','problem_text':'已知 x>0，解 x+1=2'})
    monkeypatch.setattr(agent,'client',client);monkeypatch.setattr(agent,'api_key','test-only')
    planner=Mock();monkeypatch.setattr(agent,'generate_plan',planner)
    response=agent.agent_execute(AgentRequest(prompt='解这道题',image_base64=base64.b64encode(picture()).decode()))
    assert response['steps'][0]['section']=='detect' and response['steps'][0]['trigger']=='none'
    assert 'x>0' in response['steps'][0]['recognition']['problem_text']
    assert client.with_options.return_value.chat.completions.create.call_count==1
    planner.assert_not_called()
