from fastapi import FastAPI
from fastapi.responses import Response,StreamingResponse
from fastapi.testclient import TestClient
from app.static_compression import StaticCompression


def test_compression_reduces_text_assets_but_preserves_sse_and_media():
    app=FastAPI();app.add_middleware(StaticCompression)
    @app.get('/static/js/example.js')
    def script():return Response('const example=1;\n'*1000,media_type='text/javascript')
    @app.get('/api/events')
    async def events():
        async def frames():yield 'data: '+('x'*2000)+'\n\n'
        return StreamingResponse(frames(),media_type='text/event-stream')
    @app.get('/videos/example.mp4')
    def video():return Response(b'x'*2000,media_type='video/mp4')
    with TestClient(app) as client:
        compressed=client.get('/static/js/example.js',headers={'Accept-Encoding':'gzip'})
        assert compressed.headers['content-encoding']=='gzip' and int(compressed.headers['content-length'])<1000
        assert compressed.text=='const example=1;\n'*1000
        for path in ('/api/events','/videos/example.mp4'):
            assert 'content-encoding' not in client.get(path,headers={'Accept-Encoding':'gzip'}).headers
