"""Cheap admission before database work; bounded state and safe response headers."""
from collections import OrderedDict, Counter
import logging
import os
import time

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from .request_origin import origin_allowed, public_scheme


async def safe_validation_error(request, exc):
    # Pydantic's default response includes the submitted value and error context.
    # Neither belongs in browser telemetry, especially for account endpoints.
    return JSONResponse({'status': 'error', 'message': '输入格式不正确或内容过长，请检查后重试。',
                         'detail': [{'loc': list(error['loc']), 'type': error['type']}
                                    for error in exc.errors()[:32]]}, status_code=422)


class SecurityEnvelope:
    def __init__(self, app):
        self.app = app
        self.windows = OrderedDict()
        self.active = Counter()
        self.sockets = Counter()
        self.total = 0
        def setting(name, default, ceiling):
            try: return max(1, min(ceiling, int(os.getenv(name, str(default)))))
            except ValueError: return default
        self.max_active = setting('API_HTTP_MAX_CONCURRENT', 16, 64)
        self.max_per_ip = setting('API_HTTP_MAX_PER_IP', 8, self.max_active)

    def allow_rate(self, key, limit, now):
        while self.windows and next(iter(self.windows.values()))[0] <= now - 60:
            self.windows.popitem(last=False)
        start, count = self.windows.get(key, (now, 0))
        if count >= limit:
            return False
        if key not in self.windows and len(self.windows) >= 4096:
            return False
        self.windows[key] = (start, count + 1)
        return True

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        from .request_guard import client_ip
        headers = Headers(scope=scope)
        ip = client_ip(scope, headers)
        if scope['type'] == 'websocket':
            # HTTP middleware does not run for WebSocket handshakes.
            origin_scope = {**scope, 'scheme': 'https' if scope.get('scheme') == 'wss' else 'http'}
            if (not origin_allowed(origin_scope, headers) or self.sockets[ip] >= 6
                    or sum(self.sockets.values()) >= 100
                    or not self.allow_rate(('ws', ip), 30, time.monotonic())):
                return await send({'type':'websocket.close', 'code':1008})
            self.sockets[ip] += 1
            try:
                return await self.app(scope, receive, send)
            finally:
                self.sockets[ip] -= 1
                if not self.sockets[ip]: del self.sockets[ip]

        async def secured(message):
            if message['type'] == 'http.response.start':
                message = dict(message)
                additions = {
                    b'x-content-type-options': b'nosniff',
                    b'x-frame-options': b'SAMEORIGIN',
                    b'referrer-policy': b'strict-origin-when-cross-origin',
                    b'content-security-policy': b"object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
                }
                if public_scheme(scope, headers) == 'https':
                    additions[b'strict-transport-security'] = b'max-age=31536000'
                media_response = (scope['path'].startswith('/api/v1/player/stream/')
                                  and message['status'] in {200, 206, 304})
                if scope['path'].startswith('/api/') and not media_response:
                    additions[b'cache-control'] = b'private, no-store'
                message['headers'] = [(k,v) for k,v in message['headers'] if k.lower() not in additions] + list(additions.items())
            await send(message)

        if not scope['path'].startswith('/api/'):
            return await self.app(scope, receive, secured)
        now = time.monotonic()
        if (self.total >= self.max_active or self.active[ip] >= self.max_per_ip
                or not self.allow_rate(('all',), 2000, now)
                or not self.allow_rate(('ip', ip), 300, now)):
            response = JSONResponse({'status':'error','message':'请求过于频繁，请稍后再试。','retryable':False},
                                    status_code=429, headers={'Retry-After':'60'})
            return await response(scope, receive, secured)
        self.total += 1
        self.active[ip] += 1
        started = False
        async def tracked(message):
            nonlocal started
            if message['type'] == 'http.response.start': started = True
            await secured(message)
        try:
            await self.app(scope, receive, tracked)
        except Exception as error:
            logging.getLogger(__name__).error('API request failed (%s)', type(error).__name__)
            if started: raise
            await JSONResponse({'status':'error','message':'服务暂不可用，请稍后重试。'},status_code=500)(scope,receive,secured)
        finally:
            self.total -= 1
            self.active[ip] -= 1
            if not self.active[ip]: del self.active[ip]
