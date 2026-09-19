"""ASGI guard keeps request identity and resource leases through the entire SSE body."""
import asyncio
import ipaddress
import os
import re
import uuid
import hashlib
import threading

from starlette.requests import Request
from starlette.responses import JSONResponse

from .store import SESSION_STORE
from .request_origin import origin_allowed, public_scheme, trusted_proxy
from .usage_guard import identity, ledger, UsageDenied, request_cancelled
from . import access
from .request_records import ROUTES, RequestRecord, request_record_id
from pydantic import ValidationError
from .models import AgentRequest,CalcModel,ManimCodeModel,ManimCodeEditModel,ManimKeyframeModel
from .solution_models import SolveRequest,RenderRequest

INPUT_MODELS={'/api/solve/stream':SolveRequest,'/api/solve/render':RenderRequest,
    '/api/agent/execute':AgentRequest,'/api/animate':CalcModel,'/api/animate/stream':CalcModel,
    '/api/devtools/edit_code':ManimCodeEditModel,'/api/devtools/generate_video_copy':ManimCodeModel,
    '/api/devtools/run_manim':ManimCodeModel,'/api/devtools/run_manim_stream':ManimCodeModel,
    '/api/devtools/render_keyframe':ManimKeyframeModel}

FEATURE_ROUTES={'/api/solve/stream':'calculate','/api/animate':'calculate','/api/detect':'recognize',
    '/api/agent/execute':'assistant','/api/devtools/edit_code':'code','/api/devtools/generate_video_copy':'code',
    '/api/solve/render':'render'}

CODE_ROUTES = {'/api/devtools/run_manim', '/api/devtools/run_manim_stream', '/api/devtools/render_keyframe', '/api/animate/stream'}
EXPENSIVE = CODE_ROUTES | {'/api/solve/stream', '/api/solve/render', '/api/agent/execute', '/api/detect', '/api/animate', '/api/devtools/edit_code', '/api/devtools/generate_video_copy', '/api/login', '/api/register'}
EXPENSIVE |= {'/api/email/send-code', '/api/email/verify', '/api/email/change', '/api/password/forgot/request', '/api/password/forgot/reset'}

# 未完成邮箱验证的账户只保留恢复账户所需的基础接口。
EMAIL_RECOVERY_ROUTES = {
    '/api/login', '/api/logout', '/api/register', '/api/captcha',
    '/api/user/me', '/api/account/access', '/api/user/check-username', '/api/email/send-code',
    '/api/email/verify', '/api/email/change', '/api/password/forgot/request', '/api/password/forgot/reset',
}


def client_ip(scope, headers):
    peer = (scope.get('client') or ('unknown', 0))[0]
    # Nginx must OVERWRITE X-Real-IP. Never take an arbitrary X-Forwarded-For entry.
    value = headers.get('x-real-ip', '') if trusted_proxy(scope) else peer
    try:
        return str(ipaddress.ip_address(value or peer))
    except ValueError:
        return peer


class RequestGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = request.url.path.rstrip('/')
        method = request.method
        headers = request.headers
        user = SESSION_STORE.get(request.cookies.get('auth_session', ''))
        who = (client_ip(scope, headers), user)
        token = identity.set(who)
        cancelled=threading.Event()
        cancel_token=request_cancelled.set(cancelled)
        guest=request.cookies.get('wisdom_trial','')
        new_guest=not re.fullmatch(r'[a-f0-9]{32}',guest)
        if new_guest:guest=uuid.uuid4().hex
        guest_token=access.guest_id.set(guest)
        feature_token=access.feature_authorized.set(False)
        record=None
        record_token=request_record_id.set(None)
        original_send=send
        async def recorded_send(message):
            if record:record.observe(message)
            await original_send(message)
        send=recorded_send
        lease = None
        duplicate = None
        async def reject(message, status=429, retry=60,code='access_denied'):
            response = JSONResponse({'status':'error', 'message':message,'code':code}, status_code=status,
                headers={'Retry-After': str(retry), 'Cache-Control':'no-store','X-Wisdom-Access':code})
            await response(scope, receive, send)
        try:
            principal=None
            if user and path.startswith('/api/') and path not in {'/api/login','/api/logout','/api/register','/api/captcha','/api/user/check-username','/api/password/forgot/request','/api/password/forgot/reset'}:
                try:principal=await asyncio.to_thread(access.load_principal,user)
                except access.AccessDenied as error:return await reject(str(error),error.status,code=error.code)
                except Exception:return await reject('账户服务暂不可用，请稍后重试。',503)
            if (user and principal and path.startswith('/api/') and
                    not principal.get('email_verified') and path not in EMAIL_RECOVERY_ROUTES):
                return await reject('请先完成邮箱验证，验证后即可继续使用完整功能。', 403, code='email_verification_required')
            if any(part.startswith('.') for part in path.split('/') if part) or (path.startswith(('/videos/', '/static/videos/')) and path.lower().endswith(('.py', '.json', '.log', '.tex', '.aux'))):
                return await reject('Not Found', 404)
            if path.startswith('/api/') and method not in {'GET','HEAD','OPTIONS'}:
                if not origin_allowed(scope, headers):
                    return await reject('请求来源不受支持，请从本站页面操作。', 403)
                if path in CODE_ROUTES:
                    runners = {v.strip() for v in os.getenv('WISDOM_CODE_RUNNERS', '').split(',') if v.strip()}
                    if not user or not access.is_owner(principal) and user not in runners:
                        return await reject('自定义 Python 渲染仅对管理员开放。请使用数学运算中的分步动画；代码助手仍可生成和下载代码。', 403)
                if path in EXPENSIVE or path.startswith(('/api/agent/tasks','/api/admin/')):
                    try:
                        admission=asyncio.create_task(asyncio.to_thread(ledger.admit,'request',who))
                        try:lease=await asyncio.shield(admission)
                        except asyncio.CancelledError:
                            try:lease=await admission
                            except UsageDenied:pass
                            raise
                    except UsageDenied as error:
                        return await reject(str(error), retry=error.retry_after)
                maximum = 9_000_000 if path in {'/api/detect','/api/agent/execute'} else 2_000_000
                chunks, size = [], 0
                try:
                    if int(headers.get('content-length', '0')) > maximum:
                        return await reject('提交内容过大，请压缩图片或缩短输入。', 413)
                    async def upload():
                        nonlocal size
                        while True:
                            message = await receive()
                            if message['type'] == 'http.disconnect':
                                return 'disconnected'
                            size += len(message.get('body', b''))
                            if size > maximum:
                                return 'oversized'
                            chunks.append(message)
                            if not message.get('more_body', False):
                                break
                    result = await asyncio.wait_for(upload(), timeout=20)
                    if result == 'disconnected':
                        return
                    if result == 'oversized':
                        return await reject('提交内容过大，请压缩图片或缩短输入。', 413)
                except (ValueError, asyncio.TimeoutError):
                    return await reject('请求内容未能完整上传，请重试。', 408)
                if path in ROUTES:
                    record=RequestRecord(path,principal,b''.join(c.get('body',b'') for c in chunks),headers.get('content-type',''),headers.get('user-agent',''))
                    request_record_id.set(record.id)
                validated=None
                if path in INPUT_MODELS:
                    try:validated=INPUT_MODELS[path].model_validate_json(b''.join(c.get('body',b'') for c in chunks))
                    except (ValidationError,ValueError):return await reject('输入格式不正确或内容过长，请检查后重试；本次未扣功能额度。',422,code='invalid_input')
                    if path=='/api/agent/execute' and not validated.prompt.strip() and not validated.image_base64:
                        return await reject('请填写需求或上传题目图片。',422,code='invalid_input')
                    canonical=validated.model_dump_json()
                    owner='u:'+str(principal['id']) if principal else 'ip:'+who[0]
                    digest=hashlib.sha256((owner+'\0'+path+'\0'+canonical).encode()).hexdigest()
                    reservation=asyncio.create_task(asyncio.to_thread(ledger.reserve_duplicate,digest))
                    try:duplicate=await asyncio.shield(reservation)
                    except asyncio.CancelledError:
                        try:duplicate=await reservation
                        except UsageDenied:pass
                        raise
                    except UsageDenied as error:return await reject(str(error),409,retry=error.retry_after,code='duplicate_request')
                original_receive = receive
                async def replay():
                    return chunks.pop(0) if chunks else await original_receive()
                receive = replay
                feature=FEATURE_ROUTES.get(path)
                if path=='/api/solve/stream':
                    from logic.task_planning import needs_agent
                    if needs_agent(validated.problem):feature=None
                if feature:
                    try:await access.consume_async(feature)
                    except access.AccessDenied as error:return await reject(str(error),error.status,code=error.code)
                    access.feature_authorized.set(True)
            async def secure_send(message):
                if message['type'] == 'http.response.start':
                    message = dict(message)
                    message['headers'] = list(message['headers']) + [
                        (b'x-content-type-options', b'nosniff'),
                        (b'referrer-policy', b'strict-origin-when-cross-origin'),
                        (b'x-frame-options', b'SAMEORIGIN'),
                    ]
                    if path in EMAIL_RECOVERY_ROUTES or path.startswith(('/api/agent/tasks','/api/account/','/api/admin/','/api/user/')):
                        message['headers'].append((b'cache-control', b'private, no-store'))
                    if new_guest and path.startswith('/api/'):
                        secure=public_scheme(scope, headers)=='https'
                        cookie=f'wisdom_trial={guest}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax'+('; Secure' if secure else '')
                        message['headers'].append((b'set-cookie',cookie.encode('ascii')))
                await send(message)
            await self.app(scope, receive, secure_send)
        finally:
            cancelled.set()
            if record:record.finish()
            request_record_id.reset(record_token)
            from .async_cleanup import finish_cleanup
            async def cleanup():
                if duplicate: await asyncio.to_thread(ledger.release,duplicate)
                if lease: await asyncio.to_thread(ledger.release,lease)
            try:
                await finish_cleanup(cleanup())
            finally:
                identity.reset(token)
                access.guest_id.reset(guest_token)
                access.feature_authorized.reset(feature_token)
                request_cancelled.reset(cancel_token)
