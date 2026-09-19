"""A bad optional plot or unresponsive provider must not trap a solve task."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, AuthenticationError

from app.routers import solve
from app.solution_models import SolveRequest, Visual
from logic.solution_engine import local_solution, resolve_visual_functions


def test_parameter_plot_preserves_solution_and_other_drawings():
    solution = local_solution('x^2=1')
    solution.source = 'ai'
    original = solution.model_copy(deep=True)
    solution.steps[0].visual = Visual(kind='plot', functions=[{'expression':'x^2+2*x+m'}])
    solution.steps[1].visual = Visual(kind='plot', functions=[{'expression':'x^2'}])
    result = resolve_visual_functions(solution)
    assert result.summary == original.summary
    assert [s.formula for s in result.steps] == [s.formula for s in original.steps]
    assert result.steps[0].visual.kind == 'reasoning'
    assert '参数' in result.steps[0].visual.caption
    assert not result.steps[0].visual.functions
    assert len(result.steps[1].visual.curves[0].points) == 161
    assert result.source == 'ai'


def test_ai_parameter_response_returns_without_discarding_answer(monkeypatch):
    answer = local_solution('x^2=1')
    answer.steps[0].visual = Visual(kind='plot', functions=[{'expression':'x^2+2*x+m'}])
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer.model_dump_json()))])
    monkeypatch.setattr(solve, 'ai_client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = asyncio.run(solve.ai_solution(SolveRequest(problem='已知抛物线 y=x^2+2x+m 与 x 轴交于 A、B 两点，求以线段 AB 为直径的圆的方程。')))
    assert result.summary == answer.summary
    assert result.steps[0].visual.kind == 'reasoning'
    assert len(calls) == 1


def test_whole_task_deadline_cancels_a_provider_that_never_returns(monkeypatch):
    async def scenario():
        cancelled = asyncio.Event()
        async def pending(_):
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        class Request:
            async def is_disconnected(self): return False
        monkeypatch.setattr(solve, 'api_key', 'test')
        monkeypatch.setattr(solve, 'ai_solution', pending)
        async def no_local_result(*args, **kwargs): return None
        monkeypatch.setattr(solve, 'run_math', no_local_result)
        monkeypatch.setattr(solve, 'SOLVE_TIMEOUT', .03)
        monkeypatch.setattr(solve, 'HEARTBEAT_INTERVAL', .005)
        response = await solve.solve_stream(SolveRequest(problem='证明一个几何结论'), Request())
        events = [json.loads(frame[6:]) async for frame in response.body_iterator]
        assert events[-1]['type'] == 'error'
        assert '超时' in events[-1]['message']
        assert any(e['type'] == 'heartbeat' for e in events)
        assert not any(e['type'] == 'complete' for e in events)
        assert cancelled.is_set()
    asyncio.run(asyncio.wait_for(scenario(), 2))


@pytest.mark.parametrize('authentication', [False, True])
def test_transient_connection_retry_is_bounded_but_auth_is_not_retried(monkeypatch, authentication):
    count = 0
    expected = local_solution('x^2=1')
    request = httpx.Request('POST', 'https://example.invalid')
    async def create(**kwargs):
        nonlocal count
        count += 1
        if authentication:
            raise AuthenticationError('bad key', response=httpx.Response(401, request=request), body={})
        if count == 1: raise APIConnectionError(request=request)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=expected.model_dump_json()))])
    monkeypatch.setattr(solve, 'ai_client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    if authentication:
        with pytest.raises(AuthenticationError): asyncio.run(solve.ai_solution(SolveRequest(problem='数学题')))
        assert count == 1
    else:
        result = asyncio.run(solve.ai_solution(SolveRequest(problem='数学题')))
        assert result.summary == expected.summary and count == 2


def test_render_queue_times_out_without_acquiring_a_slot(monkeypatch):
    async def scenario():
        class Request:
            async def is_disconnected(self): return False
        slots = asyncio.Semaphore(0)
        monkeypatch.setattr(solve, 'RENDER_SLOTS', slots)
        monkeypatch.setattr(solve, 'RENDER_QUEUE_TIMEOUT', .02)
        monkeypatch.setattr(solve.importlib.util, 'find_spec', lambda _: True)
        response = await solve.render_solution(solve.RenderRequest(solution=local_solution('x^2=1')), Request())
        events = [json.loads(frame[6:]) async for frame in response.body_iterator]
        assert events[-1]['type'] == 'error' and '排队已超时' in events[-1]['message']
        assert slots._value == 0
    asyncio.run(asyncio.wait_for(scenario(), 2))


def test_render_cancellation_cleans_process_before_releasing_slot(monkeypatch):
    async def scenario():
        slots=asyncio.Semaphore(1);started=asyncio.Event();stopped=[]
        class Request:
            async def is_disconnected(self):return False
        class Process:
            def poll(self):return None
        def launch(*args,**kwargs):started.set();return Process()
        monkeypatch.setattr(solve,'RENDER_SLOTS',slots)
        monkeypatch.setattr(solve.importlib.util,'find_spec',lambda _:True)
        monkeypatch.setattr(solve.subprocess,'Popen',launch)
        def stop(proc):
            assert slots._value==0
            stopped.append(proc)
        monkeypatch.setattr(solve,'stop_process',stop)
        response=await solve.render_solution(solve.RenderRequest(solution=local_solution('x^2=1')),Request())
        async def consume():
            async for _ in response.body_iterator:pass
        task=asyncio.create_task(consume());await started.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert len(stopped)==1 and slots._value==1
    asyncio.run(asyncio.wait_for(scenario(),3))
