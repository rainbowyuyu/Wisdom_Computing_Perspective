"""Disposable math workers: a timed-out SymPy call must actually stop running."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def setting(name, default, maximum):
    try:return max(1,min(maximum,int(os.getenv(name,str(default)))))
    except ValueError:return default


SLOTS = threading.BoundedSemaphore(setting('MATH_MAX_WORKERS',1,2))


class MathCapacityError(RuntimeError):
    retryable=False


class MathDeadlineExceeded(TimeoutError):
    retryable=False


class MathWorkerError(RuntimeError):
    retryable=False


def command():
    return [sys.executable,'-X','utf8','-m','app.math_worker']


def environment():
    return {**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}


def payload(operation, data, timeout):
    return json.dumps({'operation':operation,'data':data,'timeout':timeout,
        'memory_mb':setting('MATH_WORKER_MEMORY_MB',384,1024)},ensure_ascii=False).encode('utf-8')


def unpack(stdout, returncode):
    if returncode or len(stdout)>2_000_000:
        raise MathWorkerError('本题的计算进程已停止，网站仍可使用。请缩小计算范围或拆分题目后再试。')
    try:result=json.loads(stdout)
    except (ValueError,UnicodeError) as error:
        raise MathWorkerError('本题计算未完整返回，请拆分题目后再试。') from error
    if result.get('error'):
        if result['error']=='resource':raise MathWorkerError('本题超过单次计算资源上限，请拆分后再试。')
        raise ValueError(result.get('message','计算数据无效'))
    return result['result']


def run_math_sync(operation, data, timeout=10):
    """For FastAPI sync handlers; shares capacity with async/background callers."""
    from .host_resources import require_capacity
    require_capacity()
    if not SLOTS.acquire(blocking=False):raise MathCapacityError('数学计算资源正在使用，请稍后再试；其他页面仍可正常使用。')
    proc=None
    try:
        try:
            proc=subprocess.Popen(command(),cwd=ROOT,env=environment(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except OSError as error:
            raise MathWorkerError('计算资源暂不可用，请稍后再试。') from error
        from .host_resources import require_emergency_capacity
        deadline=time.monotonic()+timeout; message=payload(operation,data,timeout)
        while True:
            require_emergency_capacity()
            remaining=deadline-time.monotonic()
            if remaining<=0: raise MathDeadlineExceeded('本题计算超时，已终止计算进程，请缩小计算范围后重试。')
            try:
                stdout,_=proc.communicate(message,timeout=min(.5,remaining));break
            except subprocess.TimeoutExpired: message=None
        return unpack(stdout,proc.returncode)
    finally:
        try:
            if proc:
                if proc.poll() is None:proc.kill()
                proc.communicate()
        finally:SLOTS.release()


async def run_math(operation, data, timeout=10):
    from .host_resources import require_capacity
    require_capacity()
    if not SLOTS.acquire(blocking=False):raise MathCapacityError('数学计算资源正在使用，请稍后再试；其他页面仍可正常使用。')
    proc=None;launch=None;communication=None
    try:
        # Shield process creation so cancellation cannot orphan a newly spawned worker.
        launch=asyncio.create_task(asyncio.create_subprocess_exec(*command(),cwd=ROOT,env=environment(),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        try:proc=await asyncio.shield(launch)
        except OSError as error:
            raise MathWorkerError('计算资源暂不可用，请稍后再试。') from error
        communication=asyncio.create_task(proc.communicate(payload(operation,data,timeout)))
        from .host_resources import require_emergency_capacity
        deadline=time.monotonic()+timeout
        while not communication.done():
            require_emergency_capacity()
            remaining=deadline-time.monotonic()
            if remaining<=0:raise MathDeadlineExceeded('本题计算超时，已终止计算进程，请缩小计算范围后重试。')
            await asyncio.wait({communication},timeout=min(.5,remaining))
        stdout,_=communication.result()
        return unpack(stdout,proc.returncode)
    finally:
        from .async_cleanup import finish_cleanup
        async def cleanup():
            nonlocal proc
            try:
                if proc is None and launch is not None:
                    try:proc=await launch
                    except OSError:pass
                if proc:
                    if proc.returncode is None:
                        try:proc.kill()
                        except ProcessLookupError:pass
                    if communication:
                        await asyncio.gather(communication,return_exceptions=True)
                    else:await proc.wait()
            finally:SLOTS.release()
        await finish_cleanup(cleanup())
