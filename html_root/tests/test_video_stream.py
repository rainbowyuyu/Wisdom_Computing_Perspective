"""Seekable video delivery without downloading real teaching media."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import examples
from app.security import SecurityEnvelope


@pytest.fixture
def video(tmp_path, monkeypatch):
    contents = bytes(range(256)) * 8
    (tmp_path / 'test-clip.mp4').write_bytes(contents)
    monkeypatch.setattr(examples, 'STORAGE_DIR', str(tmp_path))
    monkeypatch.setattr(examples, 'VIDEO_TOKEN_SECRET', 'test-only-video-signature')
    token, expires = examples._sign_video_token('test-clip')
    app = FastAPI()
    app.add_middleware(SecurityEnvelope)
    app.include_router(examples.router, prefix='/api')
    with TestClient(app) as client:
        yield client, f'/api/v1/player/stream/test-clip?token={token}&expires={expires}', contents


def test_video_play_seek_resume_and_authorization(video):
    client, url, contents = video
    whole = client.get(url)
    assert whole.status_code == 200 and whole.content == contents
    assert whole.headers['accept-ranges'] == 'bytes'
    assert whole.headers['cache-control']=='public, max-age=3600'
    for value, expected in [('bytes=20-49', contents[20:50]), ('bytes=2000-', contents[2000:]),
                            ('bytes=-20', contents[-20:]), ('bytes=2000-9999', contents[2000:])]:
        part = client.get(url, headers={'Range': value})
        assert part.status_code == 206 and part.content == expected
        assert int(part.headers['content-length']) == len(expected)
        assert part.headers['content-range'].endswith('/2048')
    for value in ['bytes=9999-', 'bytes=20-10', 'bytes=-0', 'bytes=0-1,4-5']:
        assert client.get(url, headers={'Range': value}).status_code == 416
    assert client.get('/api/v1/player/stream/test-clip').status_code == 403
    assert client.get(url, headers={'If-None-Match': whole.headers['etag']}).status_code == 304


def test_changed_video_does_not_resume_using_stale_cached_bytes(video):
    client, url, contents = video
    whole = client.get(url)
    fresh = client.get(url, headers={'Range': 'bytes=20-', 'If-Range': whole.headers['etag']})
    assert fresh.status_code == 206 and fresh.content == contents[20:]
    stale = client.get(url, headers={'Range': 'bytes=20-', 'If-Range': '"previous-video"'})
    assert stale.status_code == 200 and stale.content == contents
