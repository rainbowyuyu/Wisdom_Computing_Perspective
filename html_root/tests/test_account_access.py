"""Real database access controls, isolated users and guest identities."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hashlib
import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from app import access,usage_guard
from app.database import transaction,apply_migrations
from app.request_guard import RequestGuard
from app.routers import accounts,auth
from app.store import SESSION_STORE,CAPTCHA_STORE

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS')!='1',reason='Requires configured MySQL')


@pytest.fixture
def environment(tmp_path,monkeypatch):
    apply_migrations();suffix=uuid.uuid4().hex[:12];users={};sessions={}
    import bcrypt
    password=bcrypt.hashpw(b'Test-access-password',bcrypt.gensalt()).decode()
    with transaction() as (_,cur):
        for role in ['admin','member','vip']:
            username='qa_access_'+role+'_'+suffix
            cur.execute('INSERT INTO users(username,hashed_password) VALUES(%s,%s)',(username,password));ident=cur.lastrowid
            cur.execute('INSERT INTO account_access(user_id,role,daily_limit) VALUES(%s,%s,2)',(ident,role))
            users[role]={'id':ident,'username':username};session=uuid.uuid4().hex;sessions[role]=session;SESSION_STORE[session]=username
    monkeypatch.setattr(access,'OWNER_USERNAME',users['admin']['username'])
    ledger=usage_guard.UsageLedger(tmp_path/'usage.sqlite3')
    monkeypatch.setattr(usage_guard,'ledger',ledger);monkeypatch.setattr('app.request_guard.ledger',ledger)
    monkeypatch.setenv('API_REQUESTS_PER_MINUTE','500')
    app=FastAPI();app.add_middleware(RequestGuard);app.include_router(accounts.router,prefix='/api');app.include_router(auth.router,prefix='/api')
    reached=[]
    @app.post('/api/solve/stream')
    def solve():reached.append('calculate');return {'ok':True}
    @app.post('/api/detect')
    def detect():reached.append('recognize');return {'ok':True}
    @app.post('/api/devtools/run_manim')
    def code():return {'ok':True}
    @app.exception_handler(access.AccessDenied)
    async def denied(req,error):return JSONResponse(status_code=error.status,content={'message':str(error),'code':error.code})
    guest_ip='qa-ip-'+suffix
    try:yield app,users,sessions,reached,guest_ip
    finally:
        from app.request_records import journal
        journal.flush()
        for session in sessions.values():SESSION_STORE.pop(session,None)
        with transaction() as (_,cur):
            for user in users.values():
                cur.execute('DELETE FROM request_records WHERE owner_id=%s',(user['id'],))
                cur.execute('DELETE FROM access_usage WHERE principal=%s',('u:'+str(user['id']),))
                cur.execute('DELETE FROM access_audit WHERE actor_id=%s OR target_id=%s',(user['id'],user['id']))
                cur.execute('DELETE FROM users WHERE id=%s',(user['id'],))
            cur.execute('DELETE FROM access_usage WHERE principal=%s',('gip:'+hashlib.sha256(guest_ip.encode()).hexdigest(),))


def test_summary_counts_are_small_and_session_owned(environment):
    from app.routers import user
    app,users,sessions,_,_=environment
    app.include_router(user.router,prefix='/api')
    username=users['member']['username']
    try:
        with transaction() as (_,cur):
            cur.execute('INSERT INTO formulas(user_id,latex,note) VALUES(%s,%s,%s)',(username,'x=1','private-note'))
        with TestClient(app) as client:
            assert client.get('/api/user/stats').status_code==401
            client.cookies.set('auth_session',sessions['member'])
            result=client.get('/api/user/stats?username='+users['vip']['username'])
            assert result.status_code==200 and result.json()['data']=={'formulas':1,'scripts':0,'templates':0,'wrongbook':0}
            assert len(result.content)<200 and 'private-note' not in result.text
            client.cookies.set('auth_session',sessions['vip'])
            assert client.get('/api/user/stats?username='+username).json()['data']['formulas']==0
    finally:
        with transaction() as (_,cur):cur.execute('DELETE FROM formulas WHERE user_id=%s',(username,))


def test_guest_three_trials_atomic_persistent_and_cookie_reset_does_not_bypass(environment):
    app,users,sessions,reached,ip=environment
    def attempt(_):
        try:access.consume('calculate',(ip,None));return True
        except access.AccessDenied:return False
    with ThreadPoolExecutor(8) as pool:assert sum(pool.map(attempt,range(8)))==3
    with pytest.raises(access.AccessDenied,match='登录'):access.consume('calculate',(ip,None),'new-cookie')
    status=access.status((ip,None))
    assert status['quotas']['calculate']['remaining']==0
    assert status['quotas']['recognize']['remaining']==2
    access.consume('recognize',(ip,None))


def test_member_limit_vip_change_no_ip_sharing_admin_and_disabled(environment):
    app,users,sessions,reached,ip=environment
    with TestClient(app) as client:
        client.cookies.set('auth_session',sessions['member'])
        assert client.get('/api/admin/users').status_code==403
        assert client.patch('/api/admin/users/'+str(users['member']['id']),json={'role':'vip'}).status_code==403
        assert client.post('/api/solve/stream',json={'problem':'x=1'}).status_code==200
        assert client.post('/api/solve/stream',json={'problem':'x=2'}).status_code==200
        exhausted=client.post('/api/solve/stream',json={'problem':'x=3'})
        assert exhausted.status_code==429 and exhausted.json()['code']=='daily_exhausted'
        assert len(reached)==2
        assert client.post('/api/devtools/run_manim',json={}).status_code==403
        client.cookies.set('auth_session',sessions['vip'])
        for _ in range(5):assert client.post('/api/solve/stream',json={'problem':'x=1'}).status_code==200
        assert client.get('/api/account/access').json()['quotas']['all']['limit'] is None
        assert client.post('/api/devtools/run_manim',json={}).status_code==403
        client.cookies.set('auth_session',sessions['admin'])
        assert client.post('/api/devtools/run_manim',json={'code':'pass'}).status_code==200
        listed=client.get('/api/admin/users',params={'q':users['member']['username']})
        assert listed.status_code==200 and len(listed.json()['items'])==1
        assert 'hashed_password' not in listed.text and 'password' not in listed.text
        assert client.patch('/api/admin/users/'+str(users['admin']['id']),json={'role':'member','disabled':True}).status_code==403
        url='/api/admin/users/'+str(users['member']['id'])
        assert client.patch(url,json={'role':'admin'}).status_code==200
        client.cookies.set('auth_session',sessions['member'])
        assert client.get('/api/account/access').json()['can_manage'] is False
        for endpoint in ['/api/admin/users','/api/admin/access-audit','/api/admin/requests']:
            assert client.get(endpoint).status_code==403
        assert client.patch(url,json={'role':'vip'}).status_code==403
        assert client.post('/api/devtools/run_manim',json={'code':'pass'}).status_code==403
        client.cookies.set('auth_session',sessions['admin'])
        assert client.patch(url,json={'role':'member'}).status_code==200
        assert client.patch(url,json={'role':'vip'},headers={'origin':'https://evil.invalid'}).status_code==403
        assert client.patch(url,json={'role':'vip'}).status_code==200
        client.cookies.set('auth_session',sessions['member'])
        assert client.post('/api/solve/stream',json={'problem':'x=4'}).status_code==200
        client.cookies.set('auth_session',sessions['admin'])
        assert client.patch(url,json={'role':'member','daily_limit':2}).status_code==200
        client.cookies.set('auth_session',sessions['member'])
        assert client.post('/api/solve/stream',json={'problem':'x=5'}).status_code==429
        client.cookies.set('auth_session',sessions['admin'])
        assert client.patch(url,json={'role':'member','daily_limit':2,'reset_today':True}).status_code==200
        client.cookies.set('auth_session',sessions['member'])
        assert client.post('/api/solve/stream',json={'problem':'x=6'}).status_code==200
        client.cookies.set('auth_session',sessions['admin'])
        assert client.patch(url,json={'role':'member','disabled':True}).status_code==200
        client.cookies.set('auth_session',sessions['member'])
        assert client.get('/api/account/access').status_code==403
        assert client.post('/api/solve/stream',json={'problem':'x=7'}).status_code==403
        CAPTCHA_STORE['test-disabled-login']='ABCD'
        login=client.post('/api/login',json={'username':users['member']['username'],'password':'Test-access-password','captcha_id':'test-disabled-login','captcha':'ABCD'})
        assert login.status_code==403


def test_guest_denial_has_login_signal_and_no_handler_execution(environment,monkeypatch):
    app,users,sessions,reached,ip=environment
    monkeypatch.setattr('app.request_guard.client_ip',lambda *args:ip)
    with TestClient(app) as client:
        state=client.get('/api/account/access')
        assert state.status_code==200 and state.json()['role']=='guest'
        assert client.cookies.get('wisdom_trial')
        assert 'httponly' in state.headers['set-cookie'].lower()
        for _ in range(3):assert client.post('/api/solve/stream',json={'problem':'x=1'}).status_code==200
        client.cookies.clear()
        fourth=client.post('/api/solve/stream',json={'problem':'x=1'})
        assert fourth.status_code==401 and fourth.headers['x-wisdom-access']=='trial_exhausted'
        assert len(reached)==3


def test_vip_still_obeys_global_cost_and_concurrency_guards(environment,monkeypatch):
    app,users,sessions,reached,ip=environment
    monkeypatch.setenv('AI_GLOBAL_DAILY_CALLS','1')
    lease=usage_guard.ledger.admit('ai',(ip,users['vip']['username']),100)
    usage_guard.ledger.release(lease)
    with pytest.raises(usage_guard.UsageDenied,match='额度'):usage_guard.ledger.admit('ai',(ip,users['vip']['username']),100)


def test_daily_reset_and_default_settings_permissions(environment,monkeypatch):
    app,users,sessions,reached,ip=environment
    who=(ip,users['member']['username'])
    monkeypatch.setattr(access,'today',lambda:'2099-01-01')
    try:
        access.consume('calculate',who);access.consume('recognize',who)
        with pytest.raises(access.AccessDenied):access.consume('assistant',who)
        monkeypatch.setattr(access,'today',lambda:'2099-01-02')
        assert access.status(who)['quotas']['all']['remaining']==2
        with TestClient(app) as client:
            client.cookies.set('auth_session',sessions['member'])
            assert client.put('/api/admin/access-settings',json={'daily_limit':20,'contact_email':'author@example.com'}).status_code==403
            client.cookies.set('auth_session',sessions['admin'])
            settings=client.get('/api/admin/users').json()['settings']
            assert client.put('/api/admin/access-settings',json=settings).status_code==200
            assert client.put('/api/admin/access-settings',json={'daily_limit':-1,'contact_email':'author@example.com'}).status_code==422
            assert client.put('/api/admin/access-settings',json={'daily_limit':20,'contact_email':'javascript:alert(1)'}).status_code==422
            assert client.get('/api/admin/access-audit').json()['items']
    finally:
        with transaction() as (_,cur):cur.execute('DELETE FROM access_usage WHERE principal=%s',('u:'+str(users['member']['id']),))


def test_unmetered_provider_entry_cannot_bypass_member_quota(environment):
    _,users,_,_,ip=environment
    from types import SimpleNamespace
    calls=[]
    provider=SimpleNamespace(api_key='test',base_url='test',chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:calls.append(kw))))
    provider.with_options=lambda **_:provider
    token=usage_guard.identity.set((ip,users['member']['username']))
    try:
        client=usage_guard.GuardedClient(provider)
        client.create(messages=[]);client.create(messages=[])
        with pytest.raises(access.AccessDenied):client.create(messages=[])
        assert len(calls)==2
    finally:usage_guard.identity.reset(token)
