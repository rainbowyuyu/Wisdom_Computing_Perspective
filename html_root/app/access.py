"""Server-side roles and atomic feature quotas. Passwords are never stored here."""
import asyncio
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
import hashlib
import threading
import time
from mysql.connector.errors import PoolError

from .database import transaction
from .usage_guard import UsageDenied, identity

OWNER_USERNAME='rainbow_yu'


def is_owner(principal):
    return bool(principal and principal.get('role')=='admin' and principal.get('username')==OWNER_USERNAME)


guest_id=ContextVar('guest_id',default=None)
feature_authorized=ContextVar('feature_authorized',default=False)
FEATURES={'calculate':'计算','recognize':'图片识别','assistant':'智能体','code':'创作助手','render':'动画'}
GUEST_LIMITS={'calculate':3,'recognize':2,'assistant':2,'code':2,'render':3}
_quota_slots=threading.BoundedSemaphore(4)
_principal_slots=threading.BoundedSemaphore(4)


class AccessDenied(UsageDenied):
    def __init__(self,message,status=403,code='access_denied'):
        super().__init__(message);self.status=status;self.code=code


def today():
    return datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')


def load_principal(username):
    if not username:return {'role':'guest','username':None,'id':None,'disabled':False,'daily_limit':None,'email':None,'email_verified':False,'email_verified_at':None}
    if not _principal_slots.acquire(timeout=3):raise AccessDenied('账户校验繁忙，请稍后重试。',503)
    try:
        for attempt in range(4):
            try:return _load_principal(username)
            except PoolError:
                if attempt==3:raise AccessDenied('账户校验繁忙，请稍后重试。',503)
                time.sleep(.05*(attempt+1))
    finally:_principal_slots.release()


def _load_principal(username):
    with transaction() as (_,cur):
        cur.execute('''SELECT u.id,u.username,u.email,COALESCE(u.email_verified,0) AS email_verified,
            u.email_verified_at,COALESCE(a.role,'member') AS role,
            COALESCE(a.disabled,0) AS disabled,a.daily_limit
            FROM users u LEFT JOIN account_access a ON a.user_id=u.id WHERE BINARY u.username=BINARY %s''',(username,))
        row=cur.fetchone()
    if not row:raise AccessDenied('账户不存在，请重新登录。',401,'login_required')
    if row['disabled']:raise AccessDenied('此账户已停用，请联系作者。',403,'account_disabled')
    return row


def settings(cur):
    cur.execute('SELECT daily_limit,contact_email FROM access_settings WHERE id=1')
    row=cur.fetchone()
    if not row:raise AccessDenied('账户配置暂不可用，请稍后重试。',503)
    return row


def buckets(who,principal,guest):
    if principal['id'] is not None:return ['u:'+str(principal['id'])]
    if not who:raise AccessDenied('无法确认试用来源，请刷新后重试。',401,'login_required')
    # Both dimensions must pass: refreshing cookies or changing networks alone
    # does not replenish trials. Shared public IPs share the trial allowance.
    values=['gip:'+hashlib.sha256(who[0].encode()).hexdigest()]
    if guest:values.append('g:'+hashlib.sha256(guest.encode()).hexdigest())
    return sorted(values)


def consume(feature,who=None,guest=None):
    if not _quota_slots.acquire(timeout=3):raise AccessDenied('额度校验繁忙，请稍后重试。',503)
    try:
        for attempt in range(4):
            try:return _consume(feature,who,guest)
            except UsageDenied:raise
            except Exception as error:
                if attempt<3 and (isinstance(error,PoolError) or getattr(error,'errno',None) in {1205,1213}):
                    time.sleep(.05*(attempt+1));continue
                raise AccessDenied('额度服务暂不可用，本次未开始生成，请稍后重试。',503) from error
    finally:_quota_slots.release()


def _consume(feature,who=None,guest=None):
    who=who or identity.get();guest=guest or guest_id.get()
    principal=load_principal(who[1] if who else None)
    if principal['id'] is not None and not principal.get('email_verified'):
        raise AccessDenied('请先完成邮箱验证，再继续使用完整功能。',403,'email_verification_required')
    if principal['role'] in {'vip','admin'}:return
    period='lifetime' if principal['role']=='guest' else today()
    counter=feature if principal['role']=='guest' else 'all'
    with transaction() as (_,cur):
        config=settings(cur)
        maximum=GUEST_LIMITS[feature] if principal['role']=='guest' else (principal['daily_limit'] if principal['daily_limit'] is not None else config['daily_limit'])
        keys=buckets(who,principal,guest)
        for key in keys:
            cur.execute('INSERT INTO access_usage(principal,period,feature) VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE used=used',(key,period,counter))
            cur.execute('SELECT used FROM access_usage WHERE principal=%s AND period=%s AND feature=%s FOR UPDATE',(key,period,counter))
            if cur.fetchone()['used']>=maximum:
                if principal['role']=='guest':raise AccessDenied(f'游客{FEATURES[feature]}试用已用完（共 {maximum} 次）。请登录后使用完整功能。',401,'trial_exhausted')
                raise AccessDenied(f'今日额度已用完（{maximum} 次），北京时间明日 00:00 恢复；可联系作者开通 VIP，免个人日额度限制。',429,'daily_exhausted')
        for key in keys:
            cur.execute('UPDATE access_usage SET used=used+1 WHERE principal=%s AND period=%s AND feature=%s',(key,period,counter))


async def consume_async(feature):
    return await asyncio.to_thread(consume,feature,identity.get(),guest_id.get())


def status(who,guest=None):
    principal=load_principal(who[1] if who else None)
    period='lifetime' if principal['role']=='guest' else today()
    with transaction() as (_,cur):
        config=settings(cur);keys=buckets(who,principal,guest)
        quotas={}
        for feature in (FEATURES if principal['role']=='guest' else ['all']):
            count=0
            for key in keys:
                cur.execute('SELECT used FROM access_usage WHERE principal=%s AND period=%s AND feature=%s',(key,period,feature))
                row=cur.fetchone();count=max(count,row['used'] if row else 0)
            maximum=GUEST_LIMITS[feature] if principal['role']=='guest' else None if principal['role'] in {'vip','admin'} else (principal['daily_limit'] if principal['daily_limit'] is not None else config['daily_limit'])
            quotas[feature]={'used':count,'limit':maximum,'remaining':None if maximum is None else max(0,maximum-count)}
    from .email_service import mask_email
    return {'username':principal['username'],'role':principal['role'],'can_manage':is_owner(principal) and bool(principal.get('email_verified')),
            'email':mask_email(principal.get('email')),
            'email_address':principal.get('email') or '',
            'email_verified':bool(principal.get('email_verified')),
            'quotas':quotas,'contact_email':config['contact_email'],'reset_timezone':'Asia/Shanghai'}
