"""GitHub OAuth identities, bounded sessions and scoped internal render sessions.

OAuth App PKCE S256 is documented at:
https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
Only read:user is requested. GitHub access tokens are used once for /user and
never stored, returned to the browser, or logged.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import hashlib
import ipaddress
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .storage import Store, SessionExpired, LoginBusy, ANONYMOUS_SESSION_TTL, ACCOUNT_SESSION_TTL
from .model_access import model_access, PREMIUM_ROLES

GITHUB_AUTHORIZE = 'https://github.com/login/oauth/authorize'
GITHUB_TOKEN = 'https://github.com/login/oauth/access_token'
GITHUB_USER = 'https://api.github.com/user'
STATE_TTL = 600
ERROR_MESSAGES = {
    'not_configured': 'GitHub 登录尚未配置。',
    'busy': '请先等待当前任务完成或取消任务，再登录。',
    'state': '登录验证已过期或不属于当前浏览器，请重新登录。',
    'denied': '已取消 GitHub 授权。',
    'upstream': 'GitHub 登录暂时不可用，请稍后重试。',
    'session': '页面会话已失效，请刷新后重新登录。',
    'already_signed_in': '请先退出当前账号，再切换 GitHub 账号。',
}


@dataclass(frozen=True)
class AuthConfig:
    client_id: str = ''
    client_secret: str = field(default='', repr=False)
    public_site_url: str = ''
    configured: bool = False
    message: str = ERROR_MESSAGES['not_configured']


def load_config(settings):
    """Read configuration without discovery, secret logging, or network probes."""
    ident=settings.get('GITHUB_CLIENT_ID') or ''
    secret=settings.get('GITHUB_CLIENT_SECRET') or ''
    site=settings.get('PUBLIC_SITE_URL') or ''
    try:
        if not all(isinstance(value,str) for value in (ident,secret,site)):
            raise ValueError()
        if site:
            parsed=urlsplit(site)
            if (site!=site.strip() or len(site)>300 or any(c in site for c in '\r\n\x00\\?#') or parsed.scheme!='https'
                or not parsed.hostname or parsed.hostname in {'localhost','testserver'} or parsed.username is not None or parsed.password is not None
                or parsed.netloc.endswith(':')
                or parsed.port not in {None,443} or parsed.path not in {'','/'} or parsed.query or parsed.fragment):raise ValueError()
            try:ipaddress.ip_address(parsed.hostname)
            except ValueError:pass
            else:raise ValueError()
            host=parsed.hostname.encode('idna').decode('ascii').lower()
            if '.' not in host or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in host.split('.')):raise ValueError()
            site='https://'+host
        if not ident or not secret:
            return AuthConfig(public_site_url=site)
        if len(ident)>200 or len(secret)>1024 or any(ord(c)<33 for c in ident+secret):raise ValueError()
        return AuthConfig(ident,secret,site,True,'GitHub 登录已配置。')
    except (TypeError,ValueError,UnicodeError):
        return AuthConfig(message='GitHub 登录配置不完整或站点地址无效。')


class OAuthUnavailable(ValueError):
    pass


async def _bounded_json(response):
    if response.status_code!=200:raise OAuthUnavailable()
    content=bytearray()
    async for chunk in response.aiter_bytes():
        content.extend(chunk)
        if len(content)>65_536:raise OAuthUnavailable()
    import json
    value=json.loads(content)
    if not isinstance(value,dict):raise OAuthUnavailable()
    return value


async def github_user(config,code,verifier,redirect_uri):
    """Fixed official endpoints, no redirects/proxies/retries, bounded responses."""
    try:
        async with asyncio.timeout(20), httpx.AsyncClient(timeout=10,follow_redirects=False,trust_env=False) as client:
            async with client.stream('POST',GITHUB_TOKEN,
                headers={'Accept':'application/json','User-Agent':'Wiscomper'},
                data={'client_id':config.client_id,'client_secret':config.client_secret,
                      'code':code,'redirect_uri':redirect_uri,'code_verifier':verifier}) as response:
                token_data=await _bounded_json(response)
            token=token_data.get('access_token')
            if (token_data.get('error') or not isinstance(token,str) or not 1<=len(token)<=2048
                or any(ord(c)<33 for c in token) or token_data.get('token_type','').lower()!='bearer'):
                raise OAuthUnavailable()
            async with client.stream('GET',GITHUB_USER,headers={'Accept':'application/vnd.github+json',
                'User-Agent':'Wiscomper','X-GitHub-Api-Version':'2022-11-28','Authorization':'Bearer '+token}) as response:
                user=await _bounded_json(response)
        ident=user.get('id');login=user.get('login');name=user.get('name')
        if type(ident) is not int or not 0<ident<2**63 or not isinstance(login,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',login):
            raise OAuthUnavailable()
        if not isinstance(name,str):name=None
        else:name=''.join(c for c in name if ord(c)>=32)[:100] or None
        # Derive official profile/media URLs; ignore any provider-returned URL.
        profile={'login':login,'name':name,'avatar_url':f'https://avatars.githubusercontent.com/u/{ident}?v=4',
                 'profile_url':'https://github.com/'+login}
        return ident,profile
    except Exception:
        raise OAuthUnavailable(ERROR_MESSAGES['upstream']) from None


class AuthManager:
    """Dependencies are callables so app tests can swap Store/locks/settings.

    bootstrap: auth=manager.public_session(request); include auth/csrf in JSON;
    then manager.apply_cookie(response,request). owner() always resolves the
    opaque session to its account/anonymous owner, never treats an account as a
    cookie. on_transfer(old_owner,new_owner) clears or updates the host job cache.
    """
    def __init__(self,get_store,get_settings,get_mutation=None,on_transfer=None,*,cookie='visualize_session',get_accounts=None):
        self.get_store=get_store;self.get_settings=get_settings
        self._lock=asyncio.Lock();self.get_mutation=get_mutation or (lambda:self._lock)
        self.on_transfer=on_transfer;self.cookie=cookie
        self.get_accounts=get_accounts
        self.router=APIRouter()
        self.router.add_api_route('/api/auth/session',self.get_session,methods=['GET'])
        self.router.add_api_route('/api/auth/github/start',self.start,methods=['GET'])
        self.router.add_api_route('/api/auth/github/callback',self.callback,methods=['GET'])
        self.router.add_api_route('/api/auth/logout',self.logout,methods=['POST'])
        if get_accounts:
            from .email_auth import install_email_routes
            install_email_routes(self)

    @property
    def store(self)->Store:return self.get_store()
    @property
    def config(self):return load_config(self.get_settings())

    @property
    def accounts(self):return self.get_accounts() if self.get_accounts else None

    def _session(self,request):
        if hasattr(request.state,'auth_identity'):
            return request.state.auth_identity
        identity=self.store.session_identity(request.cookies.get(self.cookie,''))
        if identity and identity['account_id'] and self.accounts:
            user_id=self.store.get_legacy_user_id(identity['owner'],namespace=self.accounts.namespace)
            if user_id is None and (identity.get('user') or {}).get('auth_provider')=='email':
                raise HTTPException(401,'账户数据库已切换，请重新登录。')
            if user_id is not None:
                from .legacy_accounts import AccountError
                try:
                    fresh=self.accounts.get_user(user_id)
                    prior=identity.get('credential_version') or ''
                    if not prior or not secrets.compare_digest(prior,fresh.get('_credential_version','')):
                        # A stale device must not log out a newer device that
                        # has already authenticated with the changed password.
                        self.store.revoke_session(identity['id'])
                        raise HTTPException(401,'密码已更新，请重新登录。')
                    identity['user']=fresh
                except AccountError as exc:raise HTTPException(exc.status,str(exc)) from None
        if identity:request.state.auth_identity=identity
        return identity

    def _browser(self,request):
        identity=self._session(request)
        if not identity or identity['kind']!='browser':raise HTTPException(401,ERROR_MESSAGES['session'])
        return identity

    def _ensure_session(self,request):
        existing=getattr(request.state,'auth_identity',None)
        if existing:return existing
        identity=self._session(request)
        if identity and identity['kind']!='browser':raise HTTPException(403,'内部渲染会话不能登录或管理账号。')
        if not identity:
            sid=secrets.token_hex(32);csrf=secrets.token_hex(32)
            self.store.create_session(sid,csrf)
            identity=self.store.session_identity(sid)
            request.state.auth_cookie_needed=True
        request.state.auth_identity=identity
        return identity

    def _public(self,identity,request=None):
        settings=self.get_settings();config=load_config(settings)
        public_mode=bool(config.public_site_url)
        def number(key,default,lower,upper):
            try:return max(lower,min(upper,int(settings.get(key,default))))
            except (TypeError,ValueError):return default
        daily_steps=number('VISUALIZE_DAILY_CALLS',30,0,1_000_000_000)
        daily_tasks=number('PUBLIC_ACCOUNT_DAILY_TASKS',3,1,100)
        counters=self.store.usage(identity['owner'])
        site_remaining=max(0,(daily_steps-counters['site_reserved'])//3)
        steps=counters['account_reserved'] if public_mode else counters['site_reserved']
        user=identity.get('user') or {}
        unlimited=public_mode and bool(identity.get('account_id')) and user.get('role') in PREMIUM_ROLES
        if user.get('daily_limit') is not None:
            daily_tasks=max(0,int(user['daily_limit']))
        total=None if unlimited else daily_tasks if public_mode else daily_steps//3
        remaining=None if unlimited else max(0,(daily_tasks*3-steps)//3) if public_mode else site_remaining
        requires_login=public_mode and not identity['account_id']
        usage={'day':counters['day'],'reset_at':counters['reset_at'],'scope':'account' if public_mode else 'site',
               'total':total,'used':(steps+2)//3,'remaining':remaining,
               'available':0 if requires_login else site_remaining if unlimited else min(remaining,site_remaining),
               'site_remaining':site_remaining,'requires_login':bool(requires_login),
               'steps_per_task':3,'unit':'model_tasks','unlimited':unlimited}
        safe_user={k:v for k,v in identity['user'].items() if not k.startswith('_')} if identity['user'] else None
        value={'authenticated':bool(identity['account_id']),'user':safe_user,
                'github':{'configured':config.configured,'message':config.message},'csrf':identity['csrf'],
                'public_mode':public_mode,'usage':usage}
        if self.accounts:value['email']=self.accounts.email_status()
        if request is not None:value['model_access']=model_access(request,identity,config.public_site_url)
        return value

    def public_session(self,request):return self._public(self._ensure_session(request),request)

    def access(self,request):
        return model_access(request,self._ensure_session(request),self.config.public_site_url)

    def require_provider(self,request,provider):
        identity=self._browser(request);access=model_access(request,identity,self.config.public_site_url)
        user=identity.get('user') or {}
        if user.get('disabled'):raise HTTPException(403,'当前账号已停用，请联系管理员。')
        if not access['local'] and user.get('auth_provider')=='email' and not user.get('email_verified'):
            raise HTTPException(403,'请先绑定并验证邮箱，再开始创作。')
        if provider not in access['allowed']:
            raise HTTPException(403,'此模型需 VIP、管理员权限，或在本机工作台使用。当前可选择 Qwen。')
        return access

    def account_limit(self,request):
        identity=self._browser(request);user=identity.get('user') or {}
        if user.get('role') in PREMIUM_ROLES:return None
        if user.get('daily_limit') is not None:return max(0,int(user['daily_limit']))*3
        return max(1,min(100,int(self.get_settings().get('PUBLIC_ACCOUNT_DAILY_TASKS',3))))*3

    def apply_cookie(self,response,request,*,force=False):
        identity=self._ensure_session(request)
        # An older in-flight bootstrap/session read must not overwrite a newly
        # rotated login cookie. Existing sessions need no repeated Set-Cookie.
        if force or getattr(request.state,'auth_cookie_needed',False):
            response.set_cookie(self.cookie,identity['id'],max_age=ACCOUNT_SESSION_TTL if identity['account_id'] else ANONYMOUS_SESSION_TTL,
                httponly=True,secure=bool(self.config.public_site_url) or request.url.scheme=='https',samesite='lax',path='/')
        response.headers['Cache-Control']='private, no-store'
        response.headers['Referrer-Policy']='no-referrer'
        return response

    def owner(self,request):
        identity=self._session(request)
        if not identity:raise HTTPException(401,ERROR_MESSAGES['session'])
        if identity['kind']=='render':
            scope=identity['scope'];path=request.url.path
            allowed=path=='/render.html' or path=='/api/export-scene/'+scope.get('job_id','')
            if path.startswith('/api/assets/'):
                allowed=path.removeprefix('/api/assets/') in scope.get('asset_ids',[])
            peer=request.client.host if request.client else ''
            if request.method not in {'GET','HEAD'} or peer not in {'127.0.0.1','::1','localhost','testclient'} or request.url.hostname not in {'127.0.0.1','localhost','::1','testserver'} or not allowed:
                raise HTTPException(403,'内部渲染会话只能读取当前导出内容。')
        elif identity['kind']!='browser':raise HTTPException(401,ERROR_MESSAGES['session'])
        return identity['owner']

    def require_authenticated(self,request):
        identity=self._browser(request)
        if not identity['account_id']:raise HTTPException(401,'请先使用邮箱或 GitHub 登录，再使用此功能。')
        return identity['owner']

    def render_session(self,owner,job_id,asset_ids=None,ttl=900):
        if asset_ids is None:
            job=self.store.get('job',job_id,owner)
            asset_ids=[item['asset_id'] for item in (job or {}).get('export_scene',{}).get('objects',[]) if item.get('asset_id')]
        return self.store.render_session(owner,job_id,asset_ids,ttl)

    def revoke_session(self,sid):self.store.revoke_session(sid)

    def _redirect_uri(self,request,config):
        if config.public_site_url:return config.public_site_url+'/api/auth/github/callback'
        if request.url.scheme not in {'http','https'} or request.url.hostname not in {'localhost','127.0.0.1','::1','testserver'}:
            raise OAuthUnavailable()
        url=urlsplit(str(request.base_url))
        if url.username or url.password or url.query or url.fragment:raise OAuthUnavailable()
        return f'{url.scheme}://{url.netloc}/api/auth/github/callback'

    def _failure(self,code):
        if code not in ERROR_MESSAGES:code='upstream'
        return RedirectResponse('/?'+urlencode({'auth_error':code}),status_code=303,
            headers={'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer'})

    async def get_session(self,request:Request):
        return self.apply_cookie(JSONResponse(self.public_session(request)),request)

    async def start(self,request:Request):
        config=self.config
        if not config.configured:return self._failure('not_configured')
        # Login starts from this site's own UI. Callback is intentionally exempt
        # because GitHub's top-level navigation is cross-site.
        if request.headers.get('sec-fetch-site')=='cross-site':return self._failure('state')
        try:
            async with self.get_mutation():
                identity=self._browser(request)
                if identity['account_id']:return self._failure('already_signed_in')
                redirect_uri=self._redirect_uri(request,config)
                state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
                self.store.begin_oauth(identity['id'],hashlib.sha256(state.encode()).hexdigest(),verifier,redirect_uri,time.time()+STATE_TTL)
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode('ascii')
            query={'client_id':config.client_id,'redirect_uri':redirect_uri,'scope':'read:user','state':state,
                   'code_challenge':challenge,'code_challenge_method':'S256'}
            # Upgrade a pre-OAuth legacy SameSite=Strict cookie before leaving
            # the site, so GitHub's callback sends this bound session cookie.
            return self.apply_cookie(RedirectResponse(GITHUB_AUTHORIZE+'?'+urlencode(query),status_code=302,
                headers={'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer'}),request,force=identity['legacy_cookie'])
        except LoginBusy:return self._failure('busy')
        except (SessionExpired,HTTPException):return self._failure('session')
        except (OAuthUnavailable,ValueError):return self._failure('not_configured')

    async def callback(self,request:Request):
        config=self.config
        if not config.configured:return self._failure('not_configured')
        try:
            identity=self._browser(request)
            state=request.query_params.get('state','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{43}',state):return self._failure('state')
            pending=self.store.consume_oauth(identity['id'],hashlib.sha256(state.encode()).hexdigest())
            if not pending or pending['redirect_uri']!=self._redirect_uri(request,config):return self._failure('state')
            if request.query_params.get('error'):return self._failure('denied')
            code=request.query_params.get('code','')
            if not re.fullmatch(r'[A-Za-z0-9._~-]{1,512}',code):return self._failure('state')
            github_id,profile=await github_user(config,code,pending['verifier'],pending['redirect_uri'])
            async with self.get_mutation():
                new_sid=secrets.token_hex(32);new_csrf=secrets.token_hex(32)
                old_owner,new_owner,updated=self.store.login_github(identity['id'],github_id,profile,new_sid,new_csrf,
                    expected_flow=hashlib.sha256(state.encode()).hexdigest())
                if self.on_transfer:self.on_transfer(old_owner,new_owner)
                request.state.auth_identity=updated
                request.state.auth_cookie_needed=True
            return self.apply_cookie(RedirectResponse('/',status_code=303),request)
        except LoginBusy:return self._failure('busy')
        except (SessionExpired,HTTPException):return self._failure('session')
        except (OAuthUnavailable,ValueError):return self._failure('upstream')

    async def logout(self,request:Request):
        identity=self._browser(request)
        if not secrets.compare_digest(identity['csrf'],request.headers.get('x-csrf-token','')):
            raise HTTPException(403,'页面会话已失效，请刷新后重试。')
        origin=request.headers.get('origin')
        expected=self.config.public_site_url or str(request.base_url).rstrip('/')
        if request.headers.get('sec-fetch-site')=='cross-site' or (origin and origin!=expected):
            raise HTTPException(403,'请求来源不匹配。')
        async with self.get_mutation():
            try:updated=self.store.logout_session(identity['id'],secrets.token_hex(32),secrets.token_hex(32))
            except SessionExpired:raise HTTPException(401,ERROR_MESSAGES['session']) from None
            request.state.auth_identity=updated
            request.state.auth_cookie_needed=True
        return self.apply_cookie(JSONResponse(self._public(updated,request)),request)
