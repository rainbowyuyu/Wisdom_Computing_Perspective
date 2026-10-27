"""Email routes share the existing opaque sessions and preserve anonymous work."""
import asyncio
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .public_guard import PublicLimiter
from .storage import LoginBusy, SessionExpired


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Login(Input):
    identifier: str=Field(min_length=1,max_length=255)
    password: str=Field(min_length=1,max_length=128)


class SendCode(Input):
    email: str=Field(min_length=3,max_length=254)
    purpose: str=Field(pattern='^(register|reset|verify)$')


class Register(Input):
    username: str=Field(min_length=1,max_length=64)
    email: str=Field(min_length=3,max_length=254)
    password: str=Field(min_length=6,max_length=128)
    code: str=Field(min_length=4,max_length=12)


class Reset(Input):
    email: str=Field(min_length=3,max_length=254)
    new_password: str=Field(min_length=6,max_length=128)
    code: str=Field(min_length=4,max_length=12)


class Verify(Input):
    email: str=Field(min_length=3,max_length=254)
    code: str=Field(min_length=4,max_length=12)


def install_email_routes(manager):
    from .legacy_accounts import AccountError
    limiter=PublicLimiter(limit=20,window=60,capacity=4096)
    mail_limiter=PublicLimiter(limit=5,window=60,capacity=4096)
    slots=asyncio.Semaphore(4)

    def check(request,mail=False):
        identity=manager._browser(request)
        if not secrets.compare_digest(identity['csrf'],request.headers.get('x-csrf-token','')):
            raise HTTPException(403,'页面会话已失效，请刷新后重试。')
        expected=manager.config.public_site_url or str(request.base_url).rstrip('/')
        origin=request.headers.get('origin')
        if request.headers.get('sec-fetch-site')=='cross-site' or (origin and origin!=expected):
            raise HTTPException(403,'请从本站页面完成账号操作。')
        # Never trust a forwarded address to obtain a fresh brute-force budget.
        peer=request.client.host if request.client else 'unknown'
        if not (mail_limiter if mail else limiter).allow(peer):
            raise HTTPException(429,'操作太频繁，请稍后再试。',headers={'Retry-After':'60'})
        return identity,peer

    async def call(fn,*args,**kwargs):
        try:
            await asyncio.wait_for(slots.acquire(),timeout=2)
        except TimeoutError:raise HTTPException(429,'账号服务繁忙，请稍后重试。') from None
        try:
            return await asyncio.to_thread(fn,*args,**kwargs)
        except AccountError as exc:raise HTTPException(exc.status,str(exc)) from None
        except (SessionExpired,LoginBusy) as exc:raise HTTPException(409,str(exc)) from None
        finally:slots.release()

    def require_guest(identity):
        if identity['account_id']:raise HTTPException(409,'请先退出当前账号，再切换登录。')
        if manager.store.has_active_jobs(identity['owner']):raise HTTPException(409,'请先等待当前任务完成或取消任务，再登录。')

    def legacy_id(identity):
        ident=manager.store.get_legacy_user_id(identity['owner'],namespace=manager.accounts.namespace)
        if ident is None:raise HTTPException(400,'请先使用需要验证的邮箱账号登录。')
        return ident

    async def finish(request,identity,profile):
        fresh=await call(manager.accounts.get_user,profile['id'])
        if not secrets.compare_digest(profile.get('_credential_version',''),fresh.get('_credential_version','')):
            raise HTTPException(401,'密码已更新，请重新登录。')
        profile=fresh
        old,new,updated=manager.store.login_legacy(identity['id'],profile['id'],profile,
            secrets.token_hex(32),secrets.token_hex(32),namespace=manager.accounts.namespace)
        if manager.on_transfer:manager.on_transfer(old,new)
        request.state.auth_identity=updated;request.state.auth_cookie_needed=True
        value=manager._public(updated,request)
        try:value['legacy_import']=await call(manager.accounts.import_library,profile['id'],new)
        except HTTPException:value['legacy_import']={'warning':'旧资料暂未同步，下次登录会再次检查。'}
        return manager.apply_cookie(JSONResponse(value),request)

    async def login(data:Login,request:Request):
        identity,peer=check(request)
        async with manager.get_mutation():
            require_guest(identity)
            profile=await call(manager.accounts.authenticate,data.identifier,data.password,requester_ip=peer)
            return await finish(request,identity,profile)

    async def send_code(data:SendCode,request:Request):
        identity,peer=check(request,mail=True)
        ident=legacy_id(identity) if data.purpose=='verify' else None
        if data.purpose!='verify':require_guest(identity)
        result=await call(manager.accounts.send_code,data.email,data.purpose,requester_ip=peer,user_id=ident)
        return result or {'message':'若邮箱可用于此操作，验证码将发送到邮箱，请查收。','retry_after':60}

    async def register(data:Register,request:Request):
        identity,_=check(request)
        async with manager.get_mutation():
            require_guest(identity)
            profile=await call(manager.accounts.register,data.username,data.password,data.email,data.code)
            return await finish(request,identity,profile)

    async def reset(data:Reset,request:Request):
        identity,_=check(request);require_guest(identity)
        async with manager.get_mutation():
            profile=await call(manager.accounts.reset,data.email,data.code,data.new_password)
            manager.store.revoke_legacy_sessions(profile['id'],namespace=manager.accounts.namespace)
        return {'message':'密码已更新，请使用新密码登录。'}

    async def verify(data:Verify,request:Request):
        identity,_=check(request);ident=legacy_id(identity)
        async with manager.get_mutation():
            profile=await call(manager.accounts.verify,ident,data.email,data.code)
            identity['user']=profile;request.state.auth_identity=identity
        return manager.apply_cookie(JSONResponse(manager._public(identity,request)),request)

    for path,endpoint in [('login',login),('send-code',send_code),('register',register),('reset',reset),('verify',verify)]:
        manager.router.add_api_route('/api/auth/email/'+path,endpoint,methods=['POST'])
