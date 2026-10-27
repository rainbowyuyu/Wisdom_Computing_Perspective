"""Private visualization workbench with opt-in public hosting and bounded workers."""
import asyncio
import base64
import copy
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager

from configuration import load_settings, data_directory, server_port, ai_enabled
from fastapi import FastAPI,Request,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image,ImageOps,UnidentifiedImageError
from starlette.requests import ClientDisconnect
from .storage import Store,public,RevisionConflict,ProjectMissing,SessionExpired
from .schema import CreateRequest,UploadRequest,RecomputeRequest,ExportRequest,Proposal,Scene,InteractionStateRequest,RestoreRequest
from .builders import SAMPLES,sample_proposal,build_scene
from .interactions import prepare_project,validate_exploration,bake_scene
from .site import SiteConfig, install_site
from .auth import AuthManager
from .public_guard import PublicLimiter
from .legacy_accounts import LegacyAccounts
from .model_access import restrict_capabilities

ROOT=Path(__file__).resolve().parents[1]
settings=load_settings(ROOT)
DATA=data_directory(settings,ROOT)
DATA.mkdir(parents=True,exist_ok=True)
STORE=Store(DATA/'workbench.sqlite3')
COOKIE='visualize_session'
PORT=server_port(settings)
MAX_CALLS=int(os.getenv('VISUALIZE_DAILY_CALLS') or settings.get('VISUALIZE_DAILY_CALLS') or '30')
SITE=SiteConfig.from_settings(settings)
ACCOUNT_DAILY_TASKS=max(1,min(100,int(os.getenv('PUBLIC_ACCOUNT_DAILY_TASKS') or settings.get('PUBLIC_ACCOUNT_DAILY_TASKS') or '3')))
PUBLIC_LIMITER=PublicLimiter()
ACTIVE={'queued','planning','validating','building','rendering'}
tasks={};cancellations={};jobs={};slot=asyncio.Semaphore(2);render_slot=asyncio.Semaphore(1);mutation=asyncio.Lock();upload_slot=asyncio.Semaphore(2)
log=logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    for job in STORE.list('job',limit=10000):
        if job['status'] in ACTIVE:
            job.update(status='failed',stage='interrupted',message='服务已重启，未自动重放请求。已有作品可继续查看。',updated=time.time(),progress=None)
            STORE.put('job',job)
    try:
        yield
    finally:
        pending=list(tasks.values())
        for ident in list(cancellations):request_cancel(ident)
        if pending:
            await asyncio.gather(*pending,return_exceptions=True)

app=FastAPI(title='Wiscomper 智算视界 · Wisdom Computer Perspective',lifespan=lifespan,docs_url=None,redoc_url=None)

def transferred(old_owner,new_owner):
    for ident,job in list(jobs.items()):
        if job.get('owner')==old_owner:jobs.pop(ident,None)

def login_settings():
    return {'PUBLIC_SITE_URL':SITE.public_origin,'VISUALIZE_DAILY_CALLS':str(MAX_CALLS),'PUBLIC_ACCOUNT_DAILY_TASKS':str(ACCOUNT_DAILY_TASKS),**{key:os.environ.get(key,settings.get(key) or '') for key in ('GITHUB_CLIENT_ID','GITHUB_CLIENT_SECRET')}}

ACCOUNTS=LegacyAccounts(lambda:{**settings,**os.environ},lambda:STORE)
AUTH=AuthManager(get_store=lambda:STORE,get_settings=login_settings,get_mutation=lambda:mutation,on_transfer=transferred,cookie=COOKIE,get_accounts=lambda:ACCOUNTS)
app.include_router(AUTH.router)

@app.exception_handler(SessionExpired)
async def expired_session(request,error):
    return JSONResponse({'detail':'登录状态已变化，请刷新工作台后继续。'},status_code=401)

@app.exception_handler(RequestValidationError)
async def invalid_input(request, error):
    # Do not serialize raw input: e.g. an overflowed JSON number is not JSON-safe.
    return JSONResponse({'detail':'输入格式或数值范围不正确，请检查后重试。'},status_code=422)


@app.middleware('http')
async def local_guard(request:Request,call_next):
    authority=request.headers.get('host','')
    if not SITE.is_allowed_authority(authority):
        return JSONResponse({'detail':'访问域名未配置。'},status_code=403)
    if request.url.path.startswith('/api/'):
        # Role/password changes in the original database take effect on the
        # next request. Keep database I/O off the ASGI event loop.
        try:await asyncio.to_thread(AUTH._session,request)
        except HTTPException as exc:
            # Session discovery/logout stay reachable for disabled/stale users.
            if request.url.path not in {'/api/auth/logout','/api/auth/session','/api/bootstrap'}:
                return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
            if exc.status_code==503:return JSONResponse({'detail':exc.detail},status_code=503)
            STORE.revoke_session(request.cookies.get(COOKIE,''))
    heavy_request=request.method=='POST' and (request.url.path in {'/api/jobs','/api/assets'} or request.url.path.endswith('/export'))
    if SITE.public_origin and heavy_request:
        # Ignore forwarded IP headers: the trusted proxy performs per-IP limits.
        key=request.client.host if request.client else 'unknown'
        if not PUBLIC_LIMITER.allow(key):
            return JSONResponse({'detail':'操作较频繁，请稍等一分钟后重试。'},status_code=429,headers={'Retry-After':'60'})
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        if origin and origin!=SITE.allowed_origin(authority,request.url.scheme):
            return JSONResponse({'detail':'请求来源不匹配。'},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'请从本站工作台提交。'},status_code=403)
        csrf=STORE.session(request.cookies.get(COOKIE,''))
        if not csrf or not secrets.compare_digest(csrf,request.headers.get('x-csrf-token','')):
            return JSONResponse({'detail':'页面会话已失效，请刷新后重试。'},status_code=403)
        length=request.headers.get('content-length','0')
        if len(length)>10 or not length.isascii() or not length.isdigit() or int(length)>7_100_000:return JSONResponse({'detail':'请求内容过大。'},status_code=413)
        # Bound chunked requests too; JSON input is replayed to the route.
        body=bytearray()
        try:
            async with asyncio.timeout(15):
                async for part in request.stream():
                    if len(body)+len(part)>7_100_000:return JSONResponse({'detail':'请求内容过大。'},status_code=413)
                    body.extend(part)
        except TimeoutError:return JSONResponse({'detail':'请求上传超时，请重试。'},status_code=408)
        except ClientDisconnect:return JSONResponse({'detail':'上传连接已断开。'},status_code=400)
        request._body=bytes(body)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers.setdefault('Referrer-Policy','same-origin')
    response.headers['Cross-Origin-Resource-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="base-uri 'self'; object-src 'none'; frame-ancestors 'none'"
    if SITE.public_origin and request.url.hostname==SITE.public_host:
        response.headers['Strict-Transport-Security']='max-age=31536000'
    response.headers['X-Robots-Tag']=SITE.robots_header(request.url.path)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='private, no-store'
    elif request.url.path.endswith(('.js','.css','.html')) or request.url.path=='/':response.headers['Cache-Control']='no-cache'
    return response

def owner(request):
    return AUTH.owner(request)

def require_public_login(request):
    if SITE.public_origin:AUTH.require_authenticated(request)

def record(kind,ident,sid):
    if not re.fullmatch(r'[a-f0-9]{32}',ident):raise HTTPException(404,'记录不存在或不属于当前会话。')
    value=jobs.get(ident) if kind=='job' else None
    if not value or value.get('owner')!=sid:value=STORE.get(kind,ident,sid)
    if not value:raise HTTPException(404,'记录不存在或不属于当前会话。')
    if kind=='project':value=prepare_project(value)
    return value

def require_revision(project,expected):
    if expected is not None and project.get('revision',1)!=expected:
        raise HTTPException(409,'项目已有新版本，请刷新后继续；本次修改没有覆盖当前作品。')

def require_editable(ident,sid):
    if STORE.active_project_job(sid,ident):
        raise HTTPException(409,'此项目正在生成新版本，请等待完成或取消任务后再修改。')

def revision_metadata(project,*,current=False):
    return dict(revision=project.get('revision',1),title=project.get('title',''),prompt=project.get('prompt',''),
        change_summary=project.get('change_summary',project.get('prompt','')[:240]),
        action=project.get('action','create' if project.get('revision',1)==1 else 'recompute'),
        updated=project.get('updated',project.get('created')),is_current=current,restored_from=project.get('restored_from'))

def stored_revision(ident,revision,sid,current):
    value=current if revision==current.get('revision',1) else STORE.revision(ident,revision,sid)
    if value is None:raise HTTPException(404,'此版本不存在或不属于当前项目。')
    return prepare_project(value)

def capacity():
    if shutil.disk_usage(DATA).free<512*1024**2:raise ValueError('磁盘可用空间不足，先清理不再需要的导出文件。')
    if len(tasks)>=6:raise ValueError('已有多个任务处理中，请稍后再试。')

def persist(job,stage=None,message=None,progress=None):
    if stage:
        job['stage']=stage;job['message']=message or stage;job['progress']=progress
        job['events']=(job['events']+[{'time':time.time(),'stage':stage,'message':message or stage}])[-60:]
    job['updated']=time.time();STORE.put('job',job)

def completed_project_job(job,project_id,revision):
    now=time.time();message='新版本已保存，可以播放、调整参数或继续描述修改。'
    return {**job,'status':'completed','stage':'completed','message':message,'progress':100,
        'updated':now,'project_id':project_id,'result_revision':revision,
        'events':(job['events']+[{'time':now,'stage':'completed','message':message}])[-60:]}

async def worker_thread(cancel,fn,*args,**kwargs):
    worker=asyncio.create_task(asyncio.to_thread(fn,*args,**kwargs))
    try:return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel.set();await asyncio.gather(worker,return_exceptions=True);raise

def start_job(job,request,export=False):
    cancel=threading.Event();jobs[job['id']]=job;cancellations[job['id']]=cancel
    task=asyncio.create_task(run(job,request,cancel,export));tasks[job['id']]=task
    def settled(done):
        # A task cancelled before its coroutine first runs cannot execute finally.
        if tasks.get(job['id']) is done:
            tasks.pop(job['id'],None);cancellations.pop(job['id'],None)
            if cancel.is_set():job.update(status='cancelled');persist(job,'cancelled','已停止任务，原作品保持可用。')
    task.add_done_callback(settled)

def request_cancel(ident):
    cancel=cancellations.get(ident);task=tasks.get(ident)
    if cancel is not None and not cancel.is_set():
        cancel.set()
        if task is not None:task.cancel()

async def run(job,request,cancel,export):
    ident=job['id'];loop=asyncio.get_running_loop()
    def on_event(event):
        def apply():
            if not cancel.is_set() and job['status'] in ACTIVE:persist(job,event.get('stage','planning'),str(event.get('message','处理中'))[:220],event.get('progress'))
        loop.call_soon_threadsafe(apply)
    try:
        async with slot:
            if cancel.is_set():return
            if export:
                from .exporter import export_video
                async with render_slot:
                    if cancel.is_set():return
                    job['status']='rendering';persist(job,'rendering','逐帧绘制动画，预览与导出使用相同时间轴。',0)
                    output=DATA/'media'/f'{ident}.mp4';output.parent.mkdir(exist_ok=True)
                    asset_ids=[obj.get('asset_id') for obj in job['export_scene'].get('objects',[]) if obj.get('asset_id')]
                    render_sid=AUTH.render_session(job['owner'],ident,asset_ids)
                    try:
                        await worker_thread(cancel,export_video,job['export_scene'],output,engine=request.engine,fps=request.fps,
                            base_url=f'http://127.0.0.1:{PORT}',job_id=ident,cookie_name=COOKIE,cookie_value=render_sid,asset_root=DATA/'assets',cancelled=cancel,on_event=on_event)
                    finally:AUTH.revoke_session(render_sid)
                if cancel.is_set():return
                job.update(status='completed',video_url=f'/api/media/{ident}');persist(job,'completed','视频已导出，可以播放或下载。',100)
                return
            if request.sample:
                proposal=sample_proposal(request.sample,request.duration);job['status']='building';persist(job,'building','从本地案例建立可交互模型，不调用大模型。')
            else:
                from runtime.planner import plan
                previous=copy.deepcopy(job.get('_base_project'))
                asset=STORE.get('asset',request.asset_id,job['owner']) if request.asset_id else None
                job['status']='planning';persist(job,'planning','正在理解输入，选择推演工具与表现方式。')
                raw=await worker_thread(cancel,plan,request.prompt,request.provider,
                    asset_path=DATA/'assets'/f'{asset["id"]}.png' if asset else None,duration=request.duration,
                    previous={'proposal':previous['proposal'],'scene':previous['scene'],'exploration':previous['exploration']} if previous else None,cancelled=cancel,on_event=on_event)
                if cancel.is_set():return
                proposal=Proposal.model_validate(raw)
            if proposal.needs_clarification:
                job.update(status='needs_input');persist(job,'needs_input',proposal.question or '请补充要解释的对象或更清晰的图片。');return
            proposal.duration=request.duration
            job['status']='validating';persist(job,'validating','检查图层、时间轴、图片引用和参数范围。')
            if proposal.selection:
                engine={'threejs':'Three.js 三维建模','canvas2d':'Canvas 二维绘制','manim':'Manim 数学动画'}[proposal.selection.engine]
                job['status']='building';persist(job,'building',f'已选择 {engine}：{proposal.selection.reason}')
            scene=await worker_thread(cancel,build_scene,proposal,request.asset_id)
            if cancel.is_set():return
            now=time.time()
            content=dict(title=scene.title,prompt=request.prompt,change_summary=request.prompt[:240],
                asset_id=request.asset_id,provider='local' if request.sample else request.provider,
                proposal=proposal.model_dump(),scene=scene.model_dump())
            async with mutation:
                if cancel.is_set():return
                if request.parent_id:
                    def apply_iteration(current):
                        current.setdefault('initial_prompt',current.get('prompt',''))
                        current.update(content,action='iterate')
                        current.pop('restored_from',None)
                        return prepare_project(current)
                    finished=completed_project_job(job,request.parent_id,job['base_revision']+1)
                    project=STORE.commit_project(request.parent_id,job['owner'],job['base_revision'],apply_iteration,completed_job=finished)
                else:
                    project=prepare_project(dict(id=uuid.uuid4().hex,owner=job['owner'],created=now,updated=now,revision=1,
                        initial_prompt=request.prompt,action='create',parent_id=None,**content))
                    finished=completed_project_job(job,project['id'],project['revision'])
                    STORE.create_project(project,finished)
                job.update(finished)
    except Exception as error:
        if not cancel.is_set():
            log.warning('Job failed: %s',type(error).__name__)
            # Only known validation / adapter exceptions are safe for the UI.
            from pydantic import ValidationError
            message='本次任务未完成，已有作品不受影响。请调整描述或稍后重试。'
            if isinstance(error,(RevisionConflict,ProjectMissing)):message=str(error)[:300]
            elif type(error) is ValueError:message=str(error)[:300]
            elif isinstance(error,ValidationError):message='场景结构未通过检查，请把描述集中在一个核心对象或变化过程。'
            elif type(error).__module__ in {'runtime.planner','server.exporter'}:message=str(error)[:300]
            job.update(status='failed',error=type(error).__name__);persist(job,'failed',message)
    finally:
        if cancel.is_set():job.update(status='cancelled');persist(job,'cancelled','已停止任务，原作品保持可用。')
        if export and job['status']!='completed':
            (DATA/'media'/f'{ident}.mp4').unlink(missing_ok=True)
        tasks.pop(ident,None);cancellations.pop(ident,None)
        # Persisted records are authoritative, keep live dictionary bounded.
        if len(jobs)>100:
            for key,value in list(jobs.items()):
                if value['status'] not in ACTIVE:jobs.pop(key)
                if len(jobs)<=80:break

@app.get('/healthz')
def health():return {'status':'ok','app':'visualize-dsh'}

@app.get('/api/bootstrap')
async def bootstrap(request:Request):
    session=AUTH.public_session(request);csrf=session['csrf']
    from runtime.planner import capabilities
    from .exporter import renderer_capabilities
    access=AUTH.access(request)
    providers=restrict_capabilities(await asyncio.to_thread(capabilities),access)
    response=JSONResponse({'csrf':csrf,'public_mode':bool(SITE.public_origin),'model_access':access,'providers':providers,'samples':SAMPLES,'renderers':renderer_capabilities(),'limits':{'daily_calls':MAX_CALLS,'model_steps_per_task':3,'concurrent_tasks':2,'account_daily_tasks':ACCOUNT_DAILY_TASKS if SITE.public_origin else None}})
    AUTH.apply_cookie(response,request)
    return response

def clean_image(value):
    match=re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',value)
    if not match:raise ValueError('仅支持PNG、JPEG、WebP图片。')
    try:
        raw=base64.b64decode(match[1],validate=True)
        if len(raw)>5_000_000:raise ValueError('图片请控制在5MB以内。')
        with Image.open(io.BytesIO(raw),formats=['PNG','JPEG','WEBP']) as source:
            if source.width*source.height>12_000_000:raise ValueError('图片像素过大，请裁剪后再上传。')
            im=ImageOps.exif_transpose(source);im.thumbnail((1600,1600));im=im.convert('RGB');out=io.BytesIO();im.save(out,format='PNG');return out.getvalue(),im.size
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError):raise ValueError('这张图片无法读取，请重新上传。') from None

@app.post('/api/assets')
async def upload(data:UploadRequest,request:Request):
    require_public_login(request)
    sid=owner(request)
    try:
        capacity()
        async with upload_slot:content,size=await asyncio.to_thread(clean_image,data.data_url)
    except ValueError as e:raise HTTPException(422,str(e)) from e
    ident=uuid.uuid4().hex;directory=DATA/'assets';directory.mkdir(exist_ok=True)
    async with mutation:
        sid=owner(request);require_public_login(request)
        await asyncio.to_thread((directory/f'{ident}.png').write_bytes,content)
        STORE.put('asset',dict(id=ident,owner=sid,width=size[0],height=size[1],updated=time.time()))
    return {'asset_id':ident,'url':f'/api/assets/{ident}','width':size[0],'height':size[1]}

@app.get('/api/assets/{ident}')
def asset(ident:str,request:Request):
    item=record('asset',ident,owner(request));return FileResponse(DATA/'assets'/f'{item["id"]}.png',media_type='image/png')

@app.post('/api/jobs',status_code=202)
async def create(data:CreateRequest,request:Request):
    sid=owner(request)
    if not data.sample:require_public_login(request)
    if not data.sample:AUTH.require_provider(request,data.provider)
    if not data.sample and not ai_enabled(load_settings(ROOT)):
        raise HTTPException(503,'模型创作暂时关闭，已有作品与示例仍可使用。')
    if not data.sample and not data.prompt.strip() and not data.asset_id:raise HTTPException(422,'请描述想看懂的内容，或上传图片。')
    if data.asset_id:record('asset',data.asset_id,sid)
    digest=hashlib.sha256(data.model_dump_json().encode()).hexdigest()
    async with mutation:
        sid=owner(request)
        if not data.sample:require_public_login(request)
        if not data.sample:AUTH.require_provider(request,data.provider)
        old=STORE.find_request(sid,data.request_key)
        if old:
            if old['digest']!=digest:raise HTTPException(409,'提交标识已用于其它内容，请重新创建。')
            return {'job':public(old)}
        base=record('project',data.parent_id,sid) if data.parent_id else None
        if base:
            require_revision(base,data.expected_revision)
            require_editable(base['id'],sid)
            if data.asset_id is None and base.get('asset_id'):
                record('asset',base['asset_id'],sid)
                data=data.model_copy(update={'asset_id':base['asset_id']})
        try:
            capacity()
            if sum(jobs[k]['owner']==sid for k in tasks)>=2:raise ValueError('已有两个任务进行中，请完成或停止后再提交。')
            if SITE.public_origin and data.sample and not AUTH.public_session(request)['authenticated'] and len(STORE.list('project',sid,24))>=24:
                raise ValueError('访客空间已保存24个示例，请登录保留作品并继续探索；已有作品仍可打开。')
            if data.sample:sample_proposal(data.sample)
            else:
                from runtime.planner import capabilities
                configured=next((p for p in await asyncio.to_thread(capabilities) if p['id']==data.provider),None)
                if not configured or not configured['available']:raise ValueError((configured or {}).get('message','模型尚未配置。'))
                STORE.reserve(3,MAX_CALLS,owner=sid if SITE.public_origin else None,owner_limit=AUTH.account_limit(request) if SITE.public_origin else None)
        except ValueError as e:raise HTTPException(429,str(e)) from e
        now=time.time();job=dict(id=uuid.uuid4().hex,owner=sid,kind='create',status='queued',stage='queued',message='任务已进入队列。',progress=None,events=[],created=now,updated=now,project_id=None,request_key=data.request_key,digest=digest)
        if base:job.update(target_project_id=base['id'],base_revision=base['revision'],_base_project=copy.deepcopy(base))
        persist(job,'queued','任务已进入队列。');start_job(job,data)
        return {'job':public(job)}

@app.get('/api/jobs')
def list_jobs(request:Request):return {'jobs':[public(j) for j in STORE.list('job',owner(request),40)]}
@app.get('/api/jobs/{ident}')
def get_job(ident:str,request:Request):return {'job':public(record('job',ident,owner(request)))}
@app.post('/api/jobs/{ident}/cancel')
async def cancel_job(ident:str,request:Request):
    job=record('job',ident,owner(request))
    if job['status'] in ACTIVE:
        request_cancel(ident);persist(job,'cancelling','正在停止任务并释放资源。')
    return {'job':public(job)}

@app.get('/api/projects')
def projects(request:Request):
    return {'projects':[{k:v for k,v in public(p).items() if k not in {'scene','proposal'}} for p in STORE.list('project',owner(request),100)]}
@app.get('/api/projects/{ident}')
def project(ident:str,request:Request):return {'project':public(record('project',ident,owner(request)))}

@app.get('/api/projects/{ident}/revisions')
def project_revisions(ident:str,request:Request):
    sid=owner(request);current=record('project',ident,sid)
    history=STORE.revisions(ident,sid)
    entries=[revision_metadata(current,current=True)]+[item for item in history if item['revision']!=current['revision']]
    return {'project_id':ident,'current_revision':current['revision'],'revisions':sorted(entries,key=lambda item:item['revision'],reverse=True)}

@app.get('/api/projects/{ident}/revisions/{revision:int}')
def project_revision(ident:str,revision:int,request:Request):
    sid=owner(request);current=record('project',ident,sid)
    value=stored_revision(ident,revision,sid,current)
    return {'project':{**public(value),'viewed_revision':revision}}

@app.post('/api/projects/{ident}/restore')
async def restore_project(ident:str,data:RestoreRequest,request:Request):
    sid=owner(request)
    async with mutation:
        sid=owner(request)
        current=record('project',ident,sid)
        require_revision(current,data.expected_revision);require_editable(ident,sid)
        saved=stored_revision(ident,data.revision,sid,current)
        if saved.get('asset_id'):record('asset',saved['asset_id'],sid)
        def apply_restore(latest):
            restored=copy.deepcopy(saved)
            restored.update(id=ident,owner=sid,initial_prompt=latest.get('initial_prompt',latest.get('prompt','')),
                action='restore',restored_from=data.revision,change_summary=f'恢复到 v{data.revision}')
            restored.pop('viewed_revision',None)
            return prepare_project(restored)
        try:updated=STORE.commit_project(ident,sid,current['revision'],apply_restore)
        except RevisionConflict as error:raise HTTPException(409,str(error)) from error
        return {'project':public(updated)}

@app.post('/api/projects/{ident}/interaction-state')
async def interaction_state(ident:str,data:InteractionStateRequest,request:Request):
    async with mutation:
        p=record('project',ident,owner(request))
        require_revision(p,data.expected_revision)
        try:exploration=validate_exploration(Scene.model_validate(p['scene']),data)
        except ValueError as e:raise HTTPException(422,str(e)) from e
        def apply_state(current):
            current['exploration']=exploration
            return prepare_project(current)
        try:p=STORE.update_project_state(ident,p['owner'],p['revision'],apply_state)
        except RevisionConflict as error:raise HTTPException(409,str(error)) from error
        return {'project':public(p)}

@app.post('/api/projects/{ident}/recompute')
async def recompute(ident:str,data:RecomputeRequest,request:Request):
    async with mutation:
        p=record('project',ident,owner(request));allowed={c['id']:c for c in p['scene']['controls']}
        require_revision(p,data.expected_revision);require_editable(ident,p['owner'])
        for key,value in data.parameters.items():
            if key not in allowed or not allowed[key]['min']<=value<=allowed[key]['max']:raise HTTPException(422,'参数超出当前模型可调整范围。')
        proposed=Proposal.model_validate(p['proposal']);proposed.parameters.update(data.parameters)
        try:scene=await asyncio.to_thread(build_scene,proposed,p.get('asset_id'))
        except ValueError as e:raise HTTPException(422,str(e)) from e
        def apply_recompute(current):
            current.setdefault('initial_prompt',current.get('prompt',''))
            current.update(scene=scene.model_dump(),proposal=proposed.model_dump(),action='recompute',
                change_summary=('调整参数：'+' · '.join(f'{allowed[key]["label"]} {value:g}{allowed[key].get("unit", "")}' for key,value in data.parameters.items()))[:240])
            current.pop('restored_from',None)
            return prepare_project(current)
        try:p=STORE.commit_project(ident,p['owner'],p['revision'],apply_recompute)
        except RevisionConflict as error:raise HTTPException(409,str(error)) from error
        return {'project':public(p)}

@app.get('/api/projects/{ident}/scene')
def scene_download(ident:str,request:Request,bundle:bool=False):
    p=record('project',ident,owner(request))
    # JSON keeps the interactive source and saved exploration together; video
    # exports below materialize the current state for deterministic playback.
    content={'format':'visualize-project','version':1,'scene':p['scene'],'exploration':p['exploration']} if bundle else p['scene']
    return JSONResponse(content,headers={'Content-Disposition':f'attachment; filename="scene-{p["id"][:8]}.json"'})

@app.post('/api/projects/{ident}/export',status_code=202)
async def export(ident:str,data:ExportRequest,request:Request):
    require_public_login(request)
    sid=owner(request);p=record('project',ident,sid)
    from .exporter import renderer_capabilities
    if not renderer_capabilities().get(data.engine):raise HTTPException(503,'所选导出引擎尚未安装，请查看运行说明。')
    if data.engine=='manim' and p['scene']['mode']!='2d':raise HTTPException(422,'三维场景请使用浏览器视频导出。')
    async with mutation:
        sid=owner(request);require_public_login(request)
        try:
            p=record('project',ident,sid)
            snapshot=bake_scene(p['scene'],p['exploration']).model_dump()
            capacity()
            if sum(jobs[k]['owner']==sid for k in tasks)>=2:raise ValueError('已有两个任务进行中。')
        except ValueError as e:raise HTTPException(429,str(e)) from e
        now=time.time();job=dict(id=uuid.uuid4().hex,owner=sid,kind='export',status='queued',stage='queued',message='等待导出。',progress=None,events=[],created=now,updated=now,project_id=p['id'],export_scene=snapshot)
        persist(job,'queued','等待导出。');start_job(job,data,True);return {'job':public(job)}

@app.get('/api/export-scene/{ident}')
def export_scene(ident:str,request:Request):
    job=record('job',ident,owner(request))
    if job['kind']!='export':raise HTTPException(404,'导出记录不存在。')
    return job['export_scene']

@app.get('/api/media/{ident}')
def video(ident:str,request:Request,download:bool=False):
    job=record('job',ident,owner(request));path=DATA/'media'/f'{job["id"]}.mp4'
    if job['status']!='completed' or not path.is_file():raise HTTPException(404,'视频尚未完成。')
    return FileResponse(path,media_type='video/mp4',filename=f'visualize-{ident[:8]}.mp4' if download else None)

@app.get('/')
def index():return SITE.render_index(ROOT/'web'/'index.html')
@app.get('/render.html')
def render_page(request:Request):owner(request);return FileResponse(ROOT/'web'/'render.html')

from .library import install_library
from .knowledge import install_knowledge
from .workspace import install_workspace
from .search import install_search
install_library(app,lambda:STORE,owner)
install_knowledge(app,lambda:STORE,owner)
install_workspace(app,lambda:STORE,owner)
install_search(app,lambda:STORE,owner)
install_site(app,lambda:SITE,ROOT)

app.mount('/web',StaticFiles(directory=ROOT/'web'),name='web')
# Only necessary browser bundles are public; no runtime, source or data mounts.
if (ROOT/'node_modules'/'three'/'build').exists():app.mount('/vendor/three',StaticFiles(directory=ROOT/'node_modules'/'three'/'build'),name='three')
if (ROOT/'node_modules'/'katex'/'dist').exists():app.mount('/vendor/katex',StaticFiles(directory=ROOT/'node_modules'/'katex'/'dist'),name='katex')
