"""Hostile requests never cross account boundaries or consume unbounded resources."""
import asyncio
from contextlib import ExitStack
import io
import json
from unittest.mock import Mock

import bcrypt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from starlette.websockets import WebSocketDisconnect

from app.avatar_image import sanitize_avatar
from app.security import SecurityEnvelope
from app.routers import achievements, user, examples
from app.store import ExpiringStore


@pytest.fixture
def account_client(monkeypatch):
    sessions = ExpiringStore(60, 10)
    sessions['alice-session'] = 'alice'
    sessions['alice-other'] = 'alice'
    sessions['bob-session'] = 'bob'
    for router in (achievements, user):
        monkeypatch.setattr(router, 'SESSION_STORE', sessions)
    app = FastAPI()
    app.include_router(achievements.router, prefix='/api')
    app.include_router(user.router, prefix='/api')
    connection = Mock()
    cursor = connection.cursor.return_value
    monkeypatch.setattr(achievements,'get_db_connection',lambda:connection)
    monkeypatch.setattr(user,'get_db_connection',lambda:connection)
    with TestClient(app) as client:
        yield client, sessions, connection, cursor


def test_achievements_cannot_read_or_overwrite_other_accounts(account_client):
    client, sessions, conn, cursor = account_client
    payload={'username':'bob','achievement_id':'tutorial','progress':1,'unlocked':True}
    assert client.get('/api/achievements/list?username=bob').status_code == 401
    assert client.post('/api/achievements/upsert',json=payload).status_code == 401
    client.cookies.set('auth_session','alice-session')
    assert client.get('/api/achievements/list?username=bob').status_code == 403
    assert client.post('/api/achievements/upsert',json=payload).status_code == 403
    cursor.execute.assert_not_called()
    payload['username']='alice'
    assert client.post('/api/achievements/upsert',json=payload).status_code == 200
    assert cursor.execute.call_args.args[1][0] == 'alice'
    payload['achievement_id']='unbounded-arbitrary-key'
    assert client.post('/api/achievements/upsert',json=payload).status_code == 422


def test_guest_can_still_read_public_achievement_definitions(account_client):
    client, _, _, cursor=account_client
    response=client.get('/api/achievements/list')
    assert response.status_code==200 and response.json()['data']
    cursor.execute.assert_not_called()


def test_password_change_revokes_every_old_session(account_client):
    client, sessions, conn, cursor=account_client
    cursor.fetchone.return_value={'hashed_password':bcrypt.hashpw(b'old-password',bcrypt.gensalt(rounds=4)).decode()}
    client.cookies.set('auth_session','alice-session')
    response=client.put('/api/user/password',json={'current_password':'old-password','new_password':'new-password'})
    assert response.status_code==200 and response.json()['reauthenticate']
    assert sessions.get('alice-session') is None and sessions.get('alice-other') is None
    assert sessions['bob-session']=='bob'
    assert 'FOR UPDATE' in cursor.execute.call_args_list[0].args[0]
    assert bcrypt.checkpw(b'new-password',cursor.execute.call_args_list[1].args[1][0].encode())
    conn.commit.assert_called_once()


def test_wrong_and_overlong_password_do_not_change_account(account_client):
    client,sessions,conn,cursor=account_client
    cursor.fetchone.return_value={'hashed_password':bcrypt.hashpw(b'old-password',bcrypt.gensalt(rounds=4)).decode()}
    client.cookies.set('auth_session','alice-session')
    assert client.put('/api/user/password',json={'current_password':'wrong','new_password':'new-password'}).status_code==401
    assert client.put('/api/user/password',json={'current_password':'old-password','new_password':'数'*30}).status_code==400
    assert sessions['alice-session']=='alice'
    conn.commit.assert_not_called()


def test_database_exception_does_not_leak_credentials(account_client):
    client,_,_,cursor=account_client
    client.cookies.set('auth_session','alice-session')
    cursor.execute.side_effect=RuntimeError('password=private-token /server/private/path')
    response=client.get('/api/user/settings')
    assert response.status_code==500
    assert 'private' not in response.text and 'password' not in response.text


def test_avatar_rejects_fake_image_and_pixel_bomb():
    for data in [b'<html><script>alert(1)</script>',b'',b'x'*(2*1024*1024+1)]:
        with pytest.raises(ValueError): sanitize_avatar(data)
    image=Image.new('1',(3000,3000))
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    with pytest.raises(ValueError,match='像素'): sanitize_avatar(buffer.getvalue())


def test_avatar_reencodes_and_discards_appended_payload():
    image=Image.new('RGB',(700,700),'red')
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    clean=sanitize_avatar(buffer.getvalue()+b'<script>private-marker</script>')
    assert b'private-marker' not in clean
    with Image.open(io.BytesIO(clean)) as result:
        assert result.format=='PNG' and result.size==(512,512)


def test_failed_avatar_database_write_cleans_file(account_client,monkeypatch,tmp_path):
    client,_,_,cursor=account_client
    client.cookies.set('auth_session','alice-session')
    monkeypatch.setattr(user,'AVATAR_DIR',str(tmp_path))
    cursor.execute.side_effect=RuntimeError('database unavailable')
    data=io.BytesIO();Image.new('RGB',(16,16)).save(data,format='PNG')
    assert client.post('/api/user/avatar',files={'file':('image.png',data.getvalue(),'image/png')}).status_code==500
    assert list(tmp_path.iterdir())==[]


@pytest.mark.parametrize('old_owner', ['alice', 'bob'])
def test_avatar_replacement_cleans_only_own_generated_file(account_client,monkeypatch,tmp_path,old_owner):
    client,_,_,cursor=account_client
    client.cookies.set('auth_session','alice-session')
    monkeypatch.setattr(user,'AVATAR_DIR',str(tmp_path))
    old_name=old_owner+'_'+'a'*32+'.png'
    (tmp_path/old_name).write_bytes(b'old')
    cursor.fetchone.side_effect=[(1,),('/static/avatars/'+old_name,)]
    data=io.BytesIO();Image.new('RGB',(16,16)).save(data,format='PNG')
    response=client.post('/api/user/avatar',files={'file':('image.png',data.getvalue(),'image/png')})
    assert response.status_code==200
    assert (tmp_path/old_name).exists()==(old_owner!='alice')
    assert (tmp_path/response.json()['avatar_url'].split('/')[-1]).exists()


def test_profile_cannot_select_another_accounts_avatar(account_client):
    client,_,conn,cursor=account_client
    client.cookies.set('auth_session','alice-session')
    cursor.fetchone.return_value=('/static/avatars/alice.png',)
    assert client.put('/api/user/profile',json={'avatar_url':'/static/avatars/bob.png'}).status_code==400
    conn.commit.assert_not_called()


def test_first_avatar_works_with_empty_profile(account_client,monkeypatch,tmp_path):
    client,_,_,cursor=account_client
    client.cookies.set('auth_session','alice-session')
    monkeypatch.setattr(user,'AVATAR_DIR',str(tmp_path))
    cursor.fetchone.side_effect=[(1,),(None,)]
    data=io.BytesIO();Image.new('RGB',(16,16)).save(data,format='PNG')
    assert client.post('/api/user/avatar',files={'file':('image.png',data.getvalue(),'image/png')}).status_code==200


def security_app():
    app=FastAPI()
    app.include_router(examples.router,prefix='/api')
    app.add_api_route('/api/probe',lambda:{'ok':True})
    app.add_api_route('/healthz',lambda:{'status':'ok'})
    app.add_middleware(SecurityEnvelope)
    return app


def test_read_request_rate_limit_leaves_health_and_headers_available():
    with TestClient(security_app()) as client:
        for _ in range(300): assert client.get('/api/probe').status_code==200
        limited=client.get('/api/probe')
        assert limited.status_code==429 and limited.headers['retry-after']=='60'
        assert limited.headers['x-content-type-options']=='nosniff'
        assert "object-src 'none'" in limited.headers['content-security-policy']
        assert client.get('/healthz').status_code==200


def test_rate_memory_is_bounded_and_expires():
    guard=SecurityEnvelope(None)
    for i in range(4096): assert guard.allow_rate(('ip',str(i)),300,0)
    assert not guard.allow_rate(('ip','another'),300,1)
    assert guard.allow_rate(('ip','another'),300,61)
    assert len(guard.windows)==1


def test_websocket_cross_origin_rejected_and_malformed_json_survives():
    with TestClient(security_app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/api/examples/ws/demo',headers={'origin':'https://attacker.invalid'}):pass
        with client.websocket_connect('/api/examples/ws/demo',headers={'origin':'http://testserver'}) as ws:
            assert ws.receive_json()['type']=='viewer_count'
            ws.send_json([])
            ws.send_json({'type':'ping'})
            assert ws.receive_json()=={'type':'pong'}
            ws.send_text('x'*4097)
            with pytest.raises(WebSocketDisconnect): ws.receive_json()
    assert not examples._ws_rooms


def test_websocket_capacity_released_on_disconnect():
    with TestClient(security_app()) as client:
        with ExitStack() as stack:
            for i in range(6):
                ws=stack.enter_context(client.websocket_connect('/api/examples/ws/demo'+str(i)))
                assert ws.receive_json()['type']=='viewer_count'
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect('/api/examples/ws/overflow'):pass
        with client.websocket_connect('/api/examples/ws/recovered') as ws:
            assert ws.receive_json()['type']=='viewer_count'
    assert not examples._ws_rooms


def test_hsts_only_on_https():
    with TestClient(security_app(),base_url='https://testserver') as client:
        assert client.get('/healthz').headers['strict-transport-security']=='max-age=31536000'
    with TestClient(security_app()) as client:
        assert 'strict-transport-security' not in client.get('/healthz').headers


def test_global_exception_is_generic_and_private():
    app=security_app()
    async def broken(): raise RuntimeError('password=never-return-this')
    app.add_api_route('/api/broken',broken)
    with TestClient(app) as client:
        result=client.get('/api/broken')
        assert result.status_code==500 and 'never-return' not in result.text
        assert result.headers['cache-control']=='private, no-store'


def test_validation_response_never_echoes_account_secrets():
    from fastapi.exceptions import RequestValidationError
    from app.models import AuthModel
    from app.security import safe_validation_error
    app=security_app()
    app.add_exception_handler(RequestValidationError, safe_validation_error)
    @app.post('/api/validate')
    def validate(data: AuthModel): return {'ok':True}
    with TestClient(app) as client:
        result=client.post('/api/validate',json={'username':'alice','password':{'secret':'private-password'}})
        assert result.status_code==422
        assert 'private-password' not in result.text and 'input' not in result.text
        assert result.json()['detail'][0]['loc']==['body','password']


def test_saturated_api_rejects_early_and_recovers_without_blocking_health():
    async def scenario():
        entered=asyncio.Event(); release=asyncio.Event()
        async def slow(scope,receive,send):
            entered.set()
            if scope['path'].startswith('/api/'): await release.wait()
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        guard=SecurityEnvelope(slow)
        async def request(path='/api/probe'):
            messages=[]
            async def send(message):messages.append(message)
            async def receive(): return {'type':'http.request','body':b''}
            await guard({'type':'http','path':path,'headers':[], 'scheme':'http','client':('1.2.3.4',80)},receive,send)
            return messages[0]['status']
        tasks=[]
        try:
            for _ in range(guard.max_per_ip):
                entered.clear();tasks.append(asyncio.create_task(request()));await entered.wait()
            assert await request()==429
            assert await request('/healthz')==200
        finally:
            release.set();await asyncio.gather(*tasks)
        assert guard.total==0 and not guard.active
        assert await request()==200
    asyncio.run(scenario())
