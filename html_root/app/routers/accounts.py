"""Private entitlement status and audited administrator account management."""
import json
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from .. import access
from ..database import transaction
from ..usage_guard import identity

router=APIRouter(tags=['accounts'])


def administrator():
    who=identity.get()
    if not who or not who[1]:raise HTTPException(401,'请先登录管理员账户。')
    user=access.load_principal(who[1])
    if not access.is_owner(user):raise HTTPException(403,'管理后台仅限主账号 rainbow_yu 使用。')
    return user


@router.get('/account/access')
def account_access():
    return access.status(identity.get(),access.guest_id.get())


@router.get('/admin/users')
def list_users(q:str=Query('',max_length=80),page:int=Query(1,ge=1,le=10000)):
    administrator()
    with transaction() as (_,cur):
        pattern='%'+q.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        cur.execute("SELECT COUNT(*) AS total FROM users WHERE username LIKE %s ESCAPE '!'",(pattern,));total=cur.fetchone()['total']
        cur.execute('''SELECT u.id,u.username,u.created_at,u.email,u.email_verified,u.email_verified_at,COALESCE(a.role,'member') AS role,
            COALESCE(a.disabled,0) AS disabled,a.daily_limit,COALESCE(t.used,0) AS used
            FROM users u LEFT JOIN account_access a ON a.user_id=u.id
            LEFT JOIN access_usage t ON t.principal=CONCAT('u:',u.id) AND t.period=%s AND t.feature='all'
            WHERE u.username LIKE %s ESCAPE '!' ORDER BY u.id DESC LIMIT 20 OFFSET %s''',(access.today(),pattern,(page-1)*20))
        users=cur.fetchall();config=access.settings(cur)
        from ..email_service import mask_email
        for user in users:user['email']=mask_email(user.get('email'))
    return {'items':users,'total':total,'page':page,'settings':config}


class UserAccessUpdate(BaseModel):
    role:Literal['member','vip','admin']
    disabled:bool=False
    daily_limit:int|None=Field(default=None,ge=0,le=10000)
    reset_today:bool=False


@router.patch('/admin/users/{user_id}')
def update_user(user_id:int,data:UserAccessUpdate):
    admin=administrator()
    with transaction() as (_,cur):
        cur.execute('''SELECT u.id,u.username,COALESCE(a.role,'member') AS role FROM users u
            LEFT JOIN account_access a ON a.user_id=u.id WHERE u.id=%s FOR UPDATE''',(user_id,))
        user=cur.fetchone()
        if not user:raise HTTPException(404,'账户不存在。')
        if user['username']==access.OWNER_USERNAME:raise HTTPException(403,'主管理员账户受保护，不能在此降权或停用。')
        cur.execute('''INSERT INTO account_access(user_id,role,disabled,daily_limit) VALUES(%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE role=VALUES(role),disabled=VALUES(disabled),daily_limit=VALUES(daily_limit)''',
            (user_id,data.role,data.disabled,data.daily_limit))
        if data.reset_today:cur.execute("UPDATE access_usage SET used=0 WHERE principal=%s AND period=%s AND feature='all'",('u:'+str(user_id),access.today()))
        cur.execute('INSERT INTO access_audit(actor_id,target_id,action,details) VALUES(%s,%s,%s,%s)',(admin['id'],user_id,'update_user',data.model_dump_json()))
    return {'status':'success','message':'用户权限已更新，后续请求立即生效。'}


class SettingsUpdate(BaseModel):
    daily_limit:int=Field(ge=0,le=10000)
    contact_email:str=Field(max_length=254,pattern=r'^[a-zA-Z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


@router.put('/admin/access-settings')
def update_settings(data:SettingsUpdate):
    admin=administrator()
    with transaction() as (_,cur):
        cur.execute('UPDATE access_settings SET daily_limit=%s,contact_email=%s WHERE id=1',(data.daily_limit,data.contact_email))
        cur.execute('INSERT INTO access_audit(actor_id,action,details) VALUES(%s,%s,%s)',(admin['id'],'update_settings',data.model_dump_json()))
    return {'status':'success'}


@router.get('/admin/access-audit')
def audit_log():
    administrator()
    with transaction() as (_,cur):
        cur.execute('SELECT actor_id,target_id,action,details,created_at FROM access_audit ORDER BY id DESC LIMIT 50')
        items=cur.fetchall()
    return {'items':items}


@router.get('/admin/requests')
def list_requests(q:str=Query('',max_length=200),user_id:int|None=Query(None,ge=1),
                  feature:str=Query('',max_length=24),status:str=Query('',max_length=24),
                  days:int=Query(7,ge=1,le=90),page:int=Query(1,ge=1,le=10000)):
    administrator()
    from ..request_records import ROUTES, STATUSES, journal
    if feature and feature not in set(ROUTES.values()):raise HTTPException(422,'请求类型无效')
    if status and status not in STATUSES:raise HTTPException(422,'请求状态无效')
    filters=['created_at >= UTC_TIMESTAMP() - INTERVAL %s DAY'];params=[days]
    for column,value in [('owner_id',user_id),('feature',feature),('status',status)]:
        if value is not None and value!='':filters.append(column+'=%s');params.append(value)
    if q:
        pattern='%'+q.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
        filters.append("(username LIKE %s ESCAPE '!' OR problem LIKE %s ESCAPE '!')");params.extend([pattern,pattern])
    where=' AND '.join(filters)
    with transaction() as (_,cur):
        cur.execute('SELECT COUNT(*) AS total FROM request_records WHERE '+where,params);total=cur.fetchone()['total']
        cur.execute('''SELECT id,owner_id,username,role,feature,endpoint,LEFT(problem,240) AS preview,
            has_image,content_truncated,device,status,http_status,duration_ms,job_id,created_at,updated_at
            FROM request_records WHERE '''+where+' ORDER BY created_at DESC,id DESC LIMIT 20 OFFSET %s',[*params,(page-1)*20])
        items=cur.fetchall()
    return {'items':items,'total':total,'page':page,'retention_days':90,'timezone':'UTC',
            'recording':{'pending':journal.queue.qsize(),'dropped':journal.dropped,'failed':journal.failed}}


@router.get('/admin/requests/{record_id}')
def read_request(record_id:str):
    administrator()
    import re
    if not re.fullmatch('[a-f0-9]{32}',record_id):raise HTTPException(404,'请求记录不存在')
    with transaction() as (_,cur):
        cur.execute('SELECT * FROM request_records WHERE id=%s AND created_at >= UTC_TIMESTAMP() - INTERVAL 90 DAY',(record_id,))
        item=cur.fetchone()
    if not item:raise HTTPException(404,'请求记录不存在或已过期')
    return {'item':item,'timezone':'UTC'}
