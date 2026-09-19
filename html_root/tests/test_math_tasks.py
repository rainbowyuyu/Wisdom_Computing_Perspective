import asyncio
from collections import Counter
from contextlib import asynccontextmanager
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import math_jobs, usage_guard
from app.math_jobs import MathJobManager,JobStore,ACTIVE
from app.task_models import MathJobRequest,MathTaskPlan
from app.routers import math_tasks,solve
from app.request_guard import RequestGuard
from app.store import SESSION_STORE
from app.solution_models import SolveRequest
from logic.solution_engine import local_solution


@pytest.fixture(autouse=True)
def fake_access(monkeypatch):
    monkeypatch.setattr('app.request_records.journal.put',lambda *args:False)
    monkeypatch.setattr('app.access.load_principal',lambda user:{'id':1,'username':user,'role':'member','disabled':False,'daily_limit':40,'email_verified':True})
    monkeypatch.setattr('app.access.consume',lambda *args,**kwargs:None)


def request(text='复杂题',key='request01',render=False):
    return MathJobRequest(problem=text,request_key=key,auto_render=render)


def plan():
    return MathTaskPlan(title='有依赖的分步任务',tasks=[
        {'title':'第一问','goal':'求第一个量'},
        {'title':'第二问','goal':'独立求第二个量'},
        {'title':'综合结论','goal':'联立前两问结论','depends_on':[0,1]},
    ])


async def until(check,seconds=4):
    async def wait():
        while not check():await asyncio.sleep(.01)
    await asyncio.wait_for(wait(),seconds)


@pytest.mark.parametrize('dependencies', [[0],[-1],[True],[1]])
def test_plan_refuses_self_forward_negative_or_boolean_dependencies(dependencies):
    with pytest.raises(ValidationError):MathTaskPlan(title='invalid',tasks=[{'title':'a','goal':'b','depends_on':dependencies}])


def test_parallelism_dependency_order_fairness_and_render_separation(tmp_path,monkeypatch):
    async def scenario():
        manager=MathJobManager(JobStore(tmp_path/'jobs.db'))
        running=Counter();peak=Counter();rendering=0;max_rendering=0;order=[]
        async def planner(*_):return plan()
        async def solver(job,node):
            owner=job['owner'];running[owner]+=1;running['all']+=1
            peak[owner]=max(peak[owner],running[owner]);peak['all']=max(peak['all'],running['all']);order.append(owner)
            assert all(job['nodes'][d]['status']=='done' for d in node['depends_on'])
            assert usage_guard.identity.get()[1]==owner
            await asyncio.sleep(.06)
            running[owner]-=1;running['all']-=1
            return local_solution('x^2=1')
        async def render(job,index):
            nonlocal rendering,max_rendering
            rendering+=1;max_rendering=max(max_rendering,rendering)
            await asyncio.sleep(.1)
            rendering-=1;job['nodes'][index]['render_status']='done'
        monkeypatch.setattr(math_jobs,'plan_problem',planner);monkeypatch.setattr(math_jobs,'solve_subtask',solver)
        monkeypatch.setattr(manager,'render_node',render)
        try:
            first=await manager.submit(request('A',render=True),('ip1','a'))
            second=await manager.submit(request('B',render=True),('ip2','b'))
            third=await manager.submit(request('C',render=True),('ip3','c'))
            await until(lambda:all(j['status']=='done' for j in manager.jobs.values()))
            assert 2<=peak['all']<=4
            assert all(peak[o]<=2 for o in ['a','b','c'])
            assert max_rendering<=2
            assert set(order[:4])>={'a','b'}
            assert all(n['solution']['task_goal']==n['goal'] for j in manager.jobs.values() for n in j['nodes'])
            assert first['id']!=second['id']!=third['id']
        finally:await manager.close()
    asyncio.run(scenario())


def test_cancel_is_scoped_failure_blocks_dependents_and_retry_preserves_done(tmp_path,monkeypatch):
    async def scenario():
        manager=MathJobManager(JobStore(tmp_path/'jobs.db'));calls=Counter();fail=[True]
        async def planner(*_):return plan()
        async def solver(job,node):
            key=(job['problem'],node['title']);calls[key]+=1
            if job['problem']=='slow':await asyncio.sleep(60)
            if node['title']=='第二问' and fail[0]:raise ValueError('invalid derivation')
            return local_solution('x^2=1')
        monkeypatch.setattr(math_jobs,'plan_problem',planner);monkeypatch.setattr(math_jobs,'solve_subtask',solver)
        try:
            slow=await manager.submit(request('slow','slow-key1'),('ip','a'))
            fast=await manager.submit(request('fast','fast-key1'),('ip','b'))
            await until(lambda:manager.jobs[fast['id']]['status']=='error')
            assert manager.jobs[fast['id']]['nodes'][2]['status']=='blocked'
            await manager.cancel(slow['id'],'a')
            assert manager.jobs[slow['id']]['status']=='cancelled'
            fail[0]=False
            await manager.retry(fast['id'],('ip','b'))
            await until(lambda:manager.jobs[fast['id']]['status']=='done')
            assert calls['fast','第一问']==1
            assert calls['fast','第二问']==2
            assert calls['fast','综合结论']==1
            assert manager.jobs[slow['id']]['status']=='cancelled'
        finally:await manager.close()
    asyncio.run(scenario())


def test_restart_marks_interrupted_and_resumes_only_missing_work(tmp_path,monkeypatch):
    async def scenario():
        store=JobStore(tmp_path/'jobs.db');manager=MathJobManager(store);calls=Counter();pause=[True]
        async def planner(*_):return plan()
        async def solver(job,node):
            calls[node['title']]+=1
            if node['title']=='第二问' and pause[0]:await asyncio.sleep(60)
            return local_solution('x^2=1')
        monkeypatch.setattr(math_jobs,'plan_problem',planner);monkeypatch.setattr(math_jobs,'solve_subtask',solver)
        job=await manager.submit(request(),('ip','a'))
        await until(lambda:manager.jobs[job['id']]['nodes'] and manager.jobs[job['id']]['nodes'][0]['status']=='done')
        await manager.close()
        restarted=MathJobManager(store)
        try:
            await restarted.start()
            restored=restarted.owned(job['id'],'a')
            assert restored['status']=='interrupted'
            assert restored['nodes'][0]['solution']
            assert not restarted.work
            pause[0]=False
            await restarted.retry(job['id'],('ip','a'))
            await until(lambda:restored['status']=='done')
            assert calls['第一问']==1
        finally:await restarted.close()
    asyncio.run(scenario())


def test_duplicate_admission_and_per_user_bound(tmp_path,monkeypatch):
    async def scenario():
        manager=MathJobManager(JobStore(tmp_path/'jobs.db'))
        async def planner(*_):await asyncio.sleep(60)
        monkeypatch.setattr(math_jobs,'plan_problem',planner)
        try:
            first=await manager.submit(request(),('ip','a'))
            duplicate=await manager.submit(request(key='different1'),('ip','a'))
            assert first['id']==duplicate['id']
            await manager.submit(request('second','request02'),('ip','a'))
            await manager.submit(request('third','request03'),('ip','a'))
            with pytest.raises(usage_guard.UsageDenied):await manager.submit(request('fourth','request04'),('ip','a'))
            other=await manager.submit(request(),('ip','b'))
            assert other['id']!=first['id']
            with pytest.raises(KeyError):manager.owned(first['id'],'b')
        finally:await manager.close()
    asyncio.run(scenario())


def test_tasks_api_is_private_and_health_remains_responsive(tmp_path,monkeypatch):
    manager=MathJobManager(JobStore(tmp_path/'jobs.db'))
    ledger=usage_guard.UsageLedger(tmp_path/'quota.db')
    monkeypatch.setattr(math_tasks,'manager',manager)
    monkeypatch.setattr('app.request_guard.ledger',ledger)
    async def planner(*_):await asyncio.sleep(60)
    monkeypatch.setattr(math_jobs,'plan_problem',planner)
    @asynccontextmanager
    async def lifespan(_):
        yield
        await manager.close()
    app=FastAPI(lifespan=lifespan);app.add_middleware(RequestGuard);app.include_router(math_tasks.router,prefix='/api')
    @app.get('/health')
    def health():return {'ok':True}
    SESSION_STORE['test-task-a']='student-a';SESSION_STORE['test-task-b']='student-b'
    try:
        with TestClient(app) as c:
            assert c.get('/api/agent/tasks').status_code==401
            c.cookies.set('auth_session','test-task-a')
            result=c.post('/api/agent/tasks',json=request().model_dump());assert result.status_code==202
            ident=result.json()['id']
            for _ in range(8):assert c.get('/health').status_code==200
            listed=c.get('/api/agent/tasks');assert 'no-store' in listed.headers['cache-control']
            assert len(listed.json()['items'])==1
            c.cookies.set('auth_session','test-task-b')
            assert c.get('/api/agent/tasks').json()['items']==[]
            assert c.get('/api/agent/tasks/'+ident).status_code==404
            assert c.post('/api/agent/tasks/'+ident+'/cancel').status_code==404
            c.cookies.set('auth_session','test-task-a')
            assert c.post('/api/agent/tasks/'+ident+'/cancel').json()['status']=='cancelled'
    finally:
        SESSION_STORE.pop('test-task-a',None);SESSION_STORE.pop('test-task-b',None)


def test_complex_solver_handoff_is_terminal_without_model_call(monkeypatch):
    async def scenario():
        async def forbidden(_):raise AssertionError('must not invoke solver before decomposition')
        monkeypatch.setattr(solve,'ai_solution',forbidden)
        class Connection:
            async def is_disconnected(self):return False
        response=await solve.solve_stream(SolveRequest(problem='已知f(x)=x^2。（1）定义域（2）值域（3）最小值'),Connection())
        events=[json.loads(frame[6:]) async for frame in response.body_iterator]
        assert events[-1]['type']=='handoff'
    asyncio.run(scenario())


def test_partial_result_never_becomes_dependency_evidence(tmp_path,monkeypatch):
    async def scenario():
        manager=MathJobManager(JobStore(tmp_path/'jobs.db'));called=[]
        async def planner(*_):return plan()
        async def solver(job,node):
            called.append(node['title']);result=local_solution('x^2=1')
            if node['title']=='第一问':result.completion='partial';result.next_tasks=['补充范围']
            return result
        monkeypatch.setattr(math_jobs,'plan_problem',planner);monkeypatch.setattr(math_jobs,'solve_subtask',solver)
        try:
            job=await manager.submit(request(),('ip','a'))
            await until(lambda:manager.jobs[job['id']]['status']=='partial')
            nodes=manager.jobs[job['id']]['nodes']
            assert nodes[0]['solution'] and nodes[1]['status']=='done'
            assert nodes[2]['status']=='blocked' and '综合结论' not in called
            with pytest.raises(usage_guard.UsageDenied):await manager.retry(job['id'],('ip','a'))
        finally:await manager.close()
    asyncio.run(scenario())


def test_persistence_failure_pauses_before_more_paid_work(tmp_path,monkeypatch):
    async def scenario():
        store=JobStore(tmp_path/'jobs.db');manager=MathJobManager(store);calls=[]
        save=store.save;writes=[0];failing=[True]
        def flaky(job):
            writes[0]+=1
            if failing[0] and writes[0]>=3:raise OSError('storage unavailable')
            save(job)
        async def planner(*_):return plan()
        async def solver(job,node):calls.append(node['title']);return local_solution('x^2=1')
        monkeypatch.setattr(store,'save',flaky)
        monkeypatch.setattr(math_jobs,'plan_problem',planner);monkeypatch.setattr(math_jobs,'solve_subtask',solver)
        try:
            job=await manager.submit(request(),('ip','a'))
            await until(lambda:manager.jobs[job['id']]['status']=='error')
            assert not calls
            assert '存储' in manager.jobs[job['id']]['message']
            failing[0]=False;await manager.retry(job['id'],('ip','a'))
            await until(lambda:manager.jobs[job['id']]['status']=='done')
            assert len(calls)==3
        finally:await manager.close()
    asyncio.run(scenario())
