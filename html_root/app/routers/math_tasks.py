from fastapi import APIRouter, Request, HTTPException

from ..task_models import MathJobRequest
from ..usage_guard import identity, UsageDenied
from ..math_jobs import manager
from ..access import AccessDenied

router=APIRouter(prefix='/agent/tasks',tags=['math tasks'])


def caller():
    who=identity.get()
    if not who or not who[1]:raise HTTPException(status_code=401,detail='请先登录，题目已保留，登录后可继续拆解。')
    return who


@router.get('')
async def list_tasks():
    who=caller();await manager.start()
    jobs=sorted((j for j in manager.jobs.values() if j['owner']==who[1]),key=lambda j:j['created'],reverse=True)
    return {'items':[manager.public(j) for j in jobs[:30]],'owner':who[1]}


@router.post('',status_code=202)
async def create_task(data:MathJobRequest):
    who=caller()
    if not data.problem.strip():raise HTTPException(status_code=422,detail='请填写完整题目。')
    from logic.single_problem import multiple_problems, SINGLE_PROBLEM_MESSAGE
    if multiple_problems(data.problem): raise HTTPException(status_code=422,detail=SINGLE_PROBLEM_MESSAGE)
    try:return await manager.submit(data,who)
    except AccessDenied:raise
    except UsageDenied as error:raise HTTPException(status_code=429,detail=str(error),headers={'Retry-After':str(error.retry_after)}) from error


@router.get('/{ident}')
async def read_task(ident:str):
    who=caller();await manager.start()
    try:return manager.public(manager.owned(ident,who[1]),detail=True)
    except KeyError:raise HTTPException(status_code=404,detail='任务不存在')


@router.post('/{ident}/cancel')
async def cancel_task(ident:str):
    who=caller();await manager.start()
    try:return await manager.cancel(ident,who[1])
    except KeyError:raise HTTPException(status_code=404,detail='任务不存在')


@router.post('/{ident}/retry')
async def retry_task(ident:str):
    who=caller();await manager.start()
    try:return await manager.retry(ident,who)
    except AccessDenied:raise
    except KeyError:raise HTTPException(status_code=404,detail='任务不存在')
    except UsageDenied as error:raise HTTPException(status_code=429,detail=str(error)) from error
