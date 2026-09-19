"""A stuck calculation must die without occupying web workers or retrying forever."""
import asyncio
import json
import subprocess
import sys
import threading
from types import SimpleNamespace

import httpx
import pytest

from app import math_runtime as runtime
from app.process_output import log_tail, resource_failure


@pytest.fixture(autouse=True)
def single_slot(monkeypatch):
    monkeypatch.setattr(runtime, 'SLOTS', threading.BoundedSemaphore(1))


def assert_slot_released():
    assert runtime.SLOTS.acquire(blocking=False)
    runtime.SLOTS.release()


def test_real_local_worker_preserves_result():
    result = runtime.run_math_sync('local', {'problem': 'x^2-5*x+6=0'})
    assert result['completion'] == 'solved'
    assert len(result['steps']) >= 2
    assert '2' in result['summary'] and '3' in result['summary']
    assert_slot_released()


def test_sync_timeout_reaps_process(monkeypatch):
    processes = []
    original = subprocess.Popen
    def launch(*args, **kwargs):
        proc = original(*args, **kwargs)
        processes.append(proc)
        return proc
    monkeypatch.setattr(runtime.subprocess, 'Popen', launch)
    monkeypatch.setattr(runtime, 'command', lambda: [sys.executable, '-c', 'while True: pass'])
    with pytest.raises(runtime.MathDeadlineExceeded):
        runtime.run_math_sync('local', {}, timeout=.2)
    assert len(processes) == 1 and processes[0].poll() is not None
    assert_slot_released()


@pytest.mark.parametrize('cancel', [False, True])
def test_async_stuck_worker_reaped_and_health_responds(monkeypatch, cancel):
    from main import app
    async def scenario():
        spawned = asyncio.Event()
        processes = []
        original = asyncio.create_subprocess_exec
        async def launch(*args, **kwargs):
            proc = await original(*args, **kwargs)
            processes.append(proc)
            spawned.set()
            return proc
        monkeypatch.setattr(runtime.asyncio, 'create_subprocess_exec', launch)
        monkeypatch.setattr(runtime, 'command', lambda: [sys.executable, '-c', 'while True: pass'])
        task = asyncio.create_task(runtime.run_math('local', {}, timeout=2))
        await asyncio.wait_for(spawned.wait(), 3)
        with pytest.raises(runtime.MathCapacityError):
            await runtime.run_math('local', {})
        with pytest.raises(runtime.MathCapacityError):
            runtime.run_math_sync('local', {})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await asyncio.wait_for(client.get('/healthz'), 1)
            assert response.status_code == 200 and response.json() == {'status': 'ok'}
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else runtime.MathDeadlineExceeded):
            await task
        assert len(processes) == 1 and processes[0].returncode is not None
        assert_slot_released()
    asyncio.run(scenario())


def test_cancel_during_spawn_waits_for_child_and_reaps(monkeypatch):
    async def scenario():
        started = asyncio.Event()
        proceed = asyncio.Event()
        processes = []
        original = asyncio.create_subprocess_exec
        async def delayed(*args, **kwargs):
            started.set()
            await proceed.wait()
            proc = await original(*args, **kwargs)
            processes.append(proc)
            return proc
        monkeypatch.setattr(runtime.asyncio, 'create_subprocess_exec', delayed)
        monkeypatch.setattr(runtime, 'command', lambda: [sys.executable, '-c', 'while True: pass'])
        task = asyncio.create_task(runtime.run_math('local', {}))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        proceed.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert len(processes) == 1 and processes[0].returncode is not None
        assert_slot_released()
    asyncio.run(scenario())


def test_crashed_worker_is_not_retryable_and_frees_slot(monkeypatch):
    from app.llm_errors import recoverable_error
    monkeypatch.setattr(runtime, 'command', lambda: [sys.executable, '-c', 'raise SystemExit(1)'])
    with pytest.raises(runtime.MathWorkerError) as failure:
        asyncio.run(runtime.run_math('local', {}))
    assert not recoverable_error(failure.value)
    assert_slot_released()


def test_spawn_failure_frees_slot(monkeypatch):
    monkeypatch.setattr(runtime, 'command', lambda: ['__missing_math_worker_executable__'])
    with pytest.raises(runtime.MathWorkerError):
        asyncio.run(runtime.run_math('local', {}))
    assert_slot_released()


def test_large_log_only_reads_tail(tmp_path):
    path = tmp_path / 'render.log'
    with path.open('wb') as stream:
        stream.seek(32 * 1024 * 1024)
        stream.write(b'WISDOM_CHAPTER:2\n')
    assert log_tail(path, 17) == 'WISDOM_CHAPTER:2\n'
    assert resource_failure(-9, '')
    assert resource_failure(1, 'MemoryError\nValueError: latex error')
    assert not resource_failure(1, 'ValueError: latex error')


def test_exited_render_parent_still_cleans_posix_children(monkeypatch):
    from app.routers import solve
    killed = []
    waited = []
    monkeypatch.setattr(solve.sys, 'platform', 'linux')
    monkeypatch.setattr(solve.signal, 'SIGKILL', 9, raising=False)
    monkeypatch.setattr(solve.os, 'killpg', lambda pid, signal: killed.append(pid), raising=False)
    process = SimpleNamespace(pid=12345, poll=lambda: 1, wait=lambda: waited.append(True))
    solve.stop_process(process)
    assert killed == [12345] and waited == [True]


def test_resource_failure_skips_model_repair_even_with_tex_diagnostic(monkeypatch):
    from app.routers import solve
    from app.solution_models import RenderRequest
    from logic.solution_engine import local_solution
    from starlette.responses import StreamingResponse
    calls = []
    async def once(data, request):
        calls.append(True)
        async def frames():
            yield solve.event('error', message='资源上限', retryable=False,
                              _failure='ValueError: LaTeX error', _diagnostic={'code': 'syntax', 'step': 1})
        return StreamingResponse(frames())
    async def disconnected(): return False
    monkeypatch.setattr(solve, '_render_solution_once', once)
    async def scenario():
        response = await solve.render_solution(RenderRequest(solution=local_solution('x^2=1')),
                                              SimpleNamespace(is_disconnected=disconnected))
        events = [json.loads(frame[6:]) async for frame in response.body_iterator]
        assert events == [{'type': 'error', 'message': '资源上限', 'retryable': False}]
    asyncio.run(scenario())
    assert len(calls) == 1


def test_ai_validation_deadline_is_not_automatically_retried(monkeypatch):
    from app.routers import solve
    from app.solution_models import SolveRequest
    async def disconnected(): return False
    async def no_local(*args, **kwargs): return None
    async def limited(data): raise runtime.MathDeadlineExceeded('计算超时，已停止')
    monkeypatch.setattr(solve, 'run_math', no_local)
    monkeypatch.setattr(solve, 'ai_solution', limited)
    monkeypatch.setattr(solve, 'cached_solution', lambda data: None)
    monkeypatch.setattr(solve, 'api_key', 'test')
    async def scenario():
        response = await solve.solve_stream(SolveRequest(problem='证明一个几何结论'),
                                            SimpleNamespace(is_disconnected=disconnected))
        events = [json.loads(frame[6:]) async for frame in response.body_iterator]
        assert events[-1] == {'type':'error', 'message':'计算超时，已停止', 'retryable':False}
    asyncio.run(scenario())
