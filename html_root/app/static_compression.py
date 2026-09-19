"""Compress site text assets without buffering SSE or recompressing videos."""
from starlette.middleware.gzip import GZipMiddleware


class StaticCompression:
    def __init__(self, app):
        self.app=app
        self.compressed=GZipMiddleware(app,minimum_size=1000,compresslevel=4)

    async def __call__(self,scope,receive,send):
        path=scope.get('path','')
        text_asset=path=='/' or (not path.startswith('/api/') and path.endswith(('.js','.css','.html','.svg','.md')))
        handler=self.compressed if scope['type']=='http' and text_asset else self.app
        await handler(scope,receive,send)
