"""Single-process, fair, bounded DAG scheduler with private persistent snapshots."""
import asyncio
from contextlib import suppress, contextmanager
import copy
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
import uuid

from .usage_guard import identity, limit, UsageDenied, request_cancelled
from .task_models import MathJobRequest
from .llm_errors import llm_error_message, recoverable_error
from logic.task_planning import plan_problem, solve_subtask

ACTIVE = {'queued','planning','running'}
RETRYABLE = {'error','blocked','cancelled','interrupted'}
logger=logging.getLogger(__name__)

class TaskRenderError(ValueError):
    def __init__(self,message,retryable=True):
        super().__init__(message)
        self.retryable=retryable


class JobStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS math_jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL)')
                yield db
        finally:
            db.close()

    def save(self, job):
        with self.connect() as db:
            db.execute('INSERT INTO math_jobs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,payload=excluded.payload',
                       (job['id'],job['owner'],job['updated'],json.dumps(job,ensure_ascii=False)))

    def load(self):
        with self.connect() as db:
            db.execute('DELETE FROM math_jobs WHERE updated < ?', (time.time()-7*86400,))
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM math_jobs ORDER BY updated')]

    def delete(self, ids):
        with self.connect() as db:
            db.executemany('DELETE FROM math_jobs WHERE id=?', [(ident,) for ident in ids])


class MathJobManager:
    def __init__(self, store):
        self.store = store
        self.jobs = {}
        self.journal_states = {}
        self.callers = {}
        self.work = {}
        self.driver = None
        self.wake = asyncio.Event()
        self.lock = asyncio.Lock()
        self.persistence = asyncio.Lock()
        self.last_owner = {'solve':None,'render':None}
        self.closing = False

    async def persist(self, job):
        async with self.persistence:
            job['updated'] = time.time()
            await asyncio.to_thread(self.store.save, copy.deepcopy(job))
            from .request_records import job_progress
            if self.journal_states.get(job['id'])!=job['status']:
                job_progress(job);self.journal_states[job['id']]=job['status']

    async def start(self):
        async with self.lock:
            if self.driver is not None:
                return
            self.closing = False
            self.wake = asyncio.Event()
            self.jobs = {job['id']:job for job in await asyncio.to_thread(self.store.load)}
            for job in self.jobs.values():
                if job['status'] in ACTIVE:
                    job['status']='interrupted'
                    job['message']='服务曾重启，已完成结果保留。点击继续任务，仅重试未完成部分。'
                    for node in job['nodes']:
                        if node['status'] in {'queued','running'}:node['status']='interrupted'
                        if node['render_status'] in {'queued','running'}:node['render_status']='interrupted'
                    await self.persist(job)
            self.driver=asyncio.create_task(self.dispatch())

    async def close(self):
        self.closing=True
        # Preserve restart semantics before cancelled workers settle their jobs.
        interrupted=[job for job in self.jobs.values() if job['status'] in ACTIVE]
        for job in interrupted:
            job['status']='interrupted';job['message']='服务重启，已完成结果保留，请继续未完成部分。'
            for node in job['nodes']:
                if node['status'] in {'queued','running'}:node['status']='interrupted'
                if node['render_status'] in {'queued','running'}:node['render_status']='interrupted'
        if self.driver:
            self.driver.cancel()
            with suppress(asyncio.CancelledError):await self.driver
        for task in list(self.work.values()):task.cancel()
        await asyncio.gather(*list(self.work.values()),return_exceptions=True)
        self.work.clear()
        for job in interrupted:
            await self.persist(job)
        self.driver=None

    async def submit(self, data: MathJobRequest, who):
        await self.start()
        async with self.lock:
            owner=who[1]
            for job in self.jobs.values():
                if job['owner']==owner and (job['request_key']==data.request_key or (
                    job['status'] in ACTIVE and job['problem']==data.problem.strip() and job['context']==data.context and job['auto_render']==data.auto_render)):
                    return self.public(job)
            if sum(j['status'] in ACTIVE for j in self.jobs.values()) >= 24:
                raise UsageDenied('任务队列已满，请稍后提交；当前没有调用模型。')
            if sum(j['status'] in ACTIVE and j['owner']==owner for j in self.jobs.values()) >= 3:
                raise UsageDenied('你已有 3 道题在处理，请先完成或取消其中一道。')
            from .access import consume
            await asyncio.to_thread(consume,'calculate',who)
            from .request_records import request_record_id
            job={'journal_id':request_record_id.get(),'id':uuid.uuid4().hex,'owner':owner,'request_key':data.request_key,'problem':data.problem.strip(),
                 'context':data.context,'auto_render':data.auto_render,'force_decompose':data.force_decompose,'title':'等待拆解题目','status':'queued',
                 'message':'已加入队列，排队期间不调用模型。','nodes':[],'created':time.time(),'updated':time.time()}
            await self.persist(job)
            self.jobs[job['id']]=job;self.callers[job['id']]=who
            old=[j for j in self.jobs.values() if j['status'] not in ACTIVE]
            old.sort(key=lambda j:j['updated'],reverse=True)
            remove=[j['id'] for j in old[100:]]
            if remove:
                await asyncio.to_thread(self.store.delete,remove)
                for ident in remove:self.jobs.pop(ident,None);self.callers.pop(ident,None);self.journal_states.pop(ident,None)
            self.wake.set()
            return self.public(job)

    def owned(self, ident, owner):
        job=self.jobs.get(ident)
        if job is None or job['owner']!=owner:
            raise KeyError(ident)
        return job

    def public(self, job, detail=False):
        result={k:v for k,v in job.items() if k not in {'owner','request_key','journal_id'}}
        result['nodes']=[{k:v for k,v in n.items() if detail or k not in {'solution','video'}} for n in job['nodes']]
        result['completed']=sum(n['status']=='done' for n in job['nodes'])
        return copy.deepcopy(result)

    async def cancel(self, ident, owner):
        async with self.lock:
            return await self._cancel(ident,owner)

    async def _cancel(self, ident, owner):
        job=self.owned(ident,owner)
        if job['status'] not in ACTIVE:return self.public(job)
        job['status']='cancelled';job['message']='已停止本题，其他任务继续；已完成的题解保留。'
        cancelled=[]
        for key, task in list(self.work.items()):
            if key[0]==ident:task.cancel();cancelled.append(task)
        await asyncio.gather(*cancelled,return_exceptions=True)
        for node in job['nodes']:
            if node['status'] in {'queued','running'}:node['status']='cancelled'
            if node['render_status'] in {'queued','running'}:node['render_status']='cancelled'
        await self.persist(job);self.wake.set()
        return self.public(job)

    async def retry(self, ident, who):
        async with self.lock:
            job=self.owned(ident,who[1])
            if job['status'] in ACTIVE:return self.public(job)
            if job['status'] in {'done','needs_information','partial'}:
                raise UsageDenied('请补充条件后作为新题提交；当前已完成的结果仍可阅读。')
            if sum(j['status'] in ACTIVE for j in self.jobs.values())>=24 or sum(j['status'] in ACTIVE and j['owner']==who[1] for j in self.jobs.values())>=3:
                raise UsageDenied('当前任务已达上限，请稍后继续。')
            # The immutable, owned job has already been charged at submission.
            # Resume only missing work; never silently debit a failed retry.
            if job.get('retry_count',0)>=2:
                raise UsageDenied('本题已继续两次仍未完成，未扣额外额度。请检查条件或拆分后重新提交。')
            job['retry_count']=job.get('retry_count',0)+1
            for node in job['nodes']:
                if node['status'] in RETRYABLE:node.update(status='queued',message='等待执行')
                if node['render_status'] in RETRYABLE:node['render_status']='queued' if node['status']=='done' else 'pending'
            job.update(status='running' if job['nodes'] else 'queued',message='正在重试未完成部分，不重复扣额度，已完成结果保留。')
            self.settle(job)
            self.callers[ident]=who
            await self.persist(job);self.wake.set()
            return self.public(job)

    def candidates(self, kind):
        candidates=[]
        for job in self.jobs.values():
            if job['status'] not in ACTIVE:continue
            if kind=='solve' and job['status']=='queued':candidates.append((job,-1));continue
            for i,node in enumerate(job['nodes']):
                if kind=='solve' and node['status']=='queued' and all(job['nodes'][d]['status']=='done' for d in node['depends_on']):
                    candidates.append((job,i))
                if kind=='render' and node['status']=='done' and node['render_status']=='queued':candidates.append((job,i))
        # Prefer a different account each dispatch, then oldest job.
        candidates.sort(key=lambda v:(v[0]['owner']==self.last_owner[kind],v[0]['created']))
        return candidates

    async def dispatch(self):
        while True:
            await self.wake.wait();self.wake.clear()
            for kind, maximum in [('solve',max(1,min(4,limit('AI_MAX_CONCURRENT',4)))),('render',2)]:
                while sum(k[2]==kind for k in self.work)<maximum:
                    choice=None
                    for job,index in self.candidates(kind):
                        owner=job['owner']
                        count=sum(k[2]==kind and self.jobs[k[0]]['owner']==owner for k in self.work)
                        if count<(2 if kind=='solve' else 1):choice=(job,index);break
                    if choice is None:break
                    job,index=choice;self.last_owner[kind]=job['owner']
                    if index==-1:job.update(status='planning',message='智能体正在识别条件与子任务依赖。')
                    elif kind=='solve':job['nodes'][index].update(status='running',message='正在等待资源或生成分步解答…')
                    else:job['nodes'][index]['render_status']='running'
                    key=(job['id'],index,kind)
                    self.work[key]=asyncio.create_task(self.execute(key))

    async def recover(self, job, target, stage, operation):
        """Persist the stage budget before retry; completed siblings never rerun."""
        counter='auto_'+stage+'_retries'
        while True:
            try:return await operation()
            except Exception as error:
                if (not recoverable_error(error) or (isinstance(error,(sqlite3.Error,OSError)) and not isinstance(error,TimeoutError))
                        or target.get(counter,0)>=2 or self.closing or job['status'] not in ACTIVE):raise
                target[counter]=target.get(counter,0)+1
                message=f"正在自动修复并继续（{target[counter]}/2），不重复扣额度，已完成结果保留。"
                target['render_message' if stage=='render' else 'message']=message
                await self.persist(job)
                await asyncio.sleep(target[counter])

    async def execute(self, key):
        ident,index,kind=key;job=self.jobs[ident]
        token=identity.set(self.callers[ident])
        from .access import feature_authorized
        feature_token=feature_authorized.set(True)
        cancel_token=request_cancelled.set(None)
        try:
            from .access import load_principal
            await asyncio.to_thread(load_principal,job['owner'])
            await self.persist(job)
            if index==-1:
                plan=await self.recover(job,job,'plan',lambda:asyncio.wait_for(plan_problem(job['problem'],job['context'],job.get('force_decompose',False)),150))
                if plan.status=='needs_information':
                    job.update(title=plan.title,status='needs_information',message=plan.message)
                else:
                    job.update(title=plan.title,status='running',message='独立子任务可并行，有依赖的子任务按顺序执行。',
                        nodes=[{**t.model_dump(),'status':'queued','message':'等待前置任务' if t.depends_on else '等待执行',
                                'solution':None,'video':None,'render_status':'pending' if job['auto_render'] else 'skipped',
                                'render_message':'','render_completed':0,'render_total':0} for t in plan.tasks])
            elif kind=='solve':
                node=job['nodes'][index]
                solution=await self.recover(job,node,'solve',lambda:asyncio.wait_for(solve_subtask(job,node),210))
                solution.task_goal=node['goal']
                node['solution']=solution.model_dump()
                node['status']='done' if solution.completion=='solved' else 'partial'
                node['message']='解答已完成' if node['status']=='done' else '当前推导尚不完整，请补充条件；后续依赖任务不会据此继续。'
                node['render_status']='queued' if node['status']=='done' and job['auto_render'] else 'skipped'
            else:
                await self.recover(job,job['nodes'][index],'render',lambda:self.render_node(job,index))
        except asyncio.CancelledError:
            if index>=0:
                node=job['nodes'][index]
                if kind=='render':node['render_status']='interrupted' if self.closing else 'cancelled'
                else:node['status']='interrupted' if self.closing else 'cancelled'
            raise
        except Exception as error:
            message=str(error) if isinstance(error,TaskRenderError) else llm_error_message(error)
            if index<0:job.update(status='error',message=message)
            elif kind=='solve':job['nodes'][index].update(status='error',message=message,render_status='skipped')
            else:job['nodes'][index].update(render_status='error',render_message=message)
        finally:
            identity.reset(token)
            feature_authorized.reset(feature_token)
            request_cancelled.reset(cancel_token)
            self.work.pop(key,None)
            self.settle(job)
            try:
                await self.persist(job)
            except (sqlite3.Error,OSError):
                # Do not bill subsequent nodes when their durable state cannot be saved.
                if job['status'] in ACTIVE:job['status']='error'
                job['message']='任务存储暂不可用，已暂停后续生成；当前结果仍可阅读，请稍后重试。'
                logger.error('Unable to persist math task %s', ident)
            finally:self.wake.set()

    def settle(self, job):
        if job['status'] not in ACTIVE or not job['nodes']:return
        for node in job['nodes']:
            if node['status']=='queued' and any(job['nodes'][d]['status'] in {'error','partial','blocked','cancelled','interrupted'} for d in node['depends_on']):
                node.update(status='blocked',message='前置任务未完整完成，已暂停后续推导，避免错误传播。',render_status='skipped')
        if any(n['status'] in {'queued','running'} or n['render_status'] in {'queued','running'} for n in job['nodes']):return
        if any(n['status']=='partial' for n in job['nodes']):job.update(status='partial',message='部分子题需要补充条件，已完成结果可阅读。')
        elif any(n['status']!='done' or n['render_status']=='error' for n in job['nodes']):job.update(status='error',message='部分任务未完成，可只重试失败部分。')
        else:job.update(status='done',message='本题全部子任务已完成，可逐项阅读、保存和继续探索。')

    async def render_node(self, job, index):
        from .routers.solve import render_solution
        from .solution_models import RenderRequest
        node=job['nodes'][index]
        class Connection:
            async def is_disconnected(_):return job['status']=='cancelled'
        response=await render_solution(RenderRequest(solution=node['solution']),Connection())
        try:
            async for frame in response.body_iterator:
                event=json.loads(frame[6:])
                if event['type']=='error':
                    raise TaskRenderError(event['message'],event.get('retryable',True))
                if event['type']=='complete':
                    if event.get('repaired') and event.get('solution'):node['solution']=event['solution']
                    node.update(render_status='done',render_message='动画已完成',video={'url':event['video_url'],'chapters':event['chapters']})
                elif event['type']=='progress':
                    node.update(render_completed=event['chapter'],render_total=event['total'],render_message=event.get('message',''))
                    await self.persist(job)
                elif event['type']=='status':
                    node['render_message']=event.get('message','');await self.persist(job)
            if node['render_status']=='running':raise TaskRenderError('动画未完整返回，题解已保留。')
        finally:
            await response.body_iterator.aclose()


manager=MathJobManager(JobStore(os.getenv('MATH_TASK_DB_PATH',str(Path(__file__).resolve().parents[1]/'var'/'math-tasks.sqlite3'))))
