"""Offline OAuth contract/security tests; no real credentials or GitHub login."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit
import uuid

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from server import auth
from server.storage import Store, LoginBusy, SessionExpired, ACTIVE_JOB_STATUSES


@pytest.fixture
def harness(tmp_path,monkeypatch):
    store=Store(tmp_path/'auth.sqlite3');transfers=[];exchanges=[]
    settings={'GITHUB_CLIENT_ID':'synthetic-client','GITHUB_CLIENT_SECRET':'synthetic-client-secret',
              'PUBLIC_SITE_URL':'https://wiscomper.example'}
    account={'id':42,'login':'author','name':'作者'}
    async def user(config,code,verifier,redirect_uri):
        exchanges.append({'code':code,'verifier':verifier,'redirect_uri':redirect_uri})
        return account['id'],{'login':account['login'],'name':account['name'],
            'avatar_url':f'https://avatars.githubusercontent.com/u/{account["id"]}?v=4',
            'profile_url':'https://github.com/'+account['login']}
    monkeypatch.setattr(auth,'github_user',user)
    manager=auth.AuthManager(lambda:store,lambda:settings,on_transfer=lambda old,new:transfers.append((old,new)))
    app=FastAPI();app.include_router(manager.router)
    @app.get('/api/projects')
    async def projects(request:Request):return {'projects':store.list('project',manager.owner(request))}
    @app.get('/api/private')
    async def private(request:Request):return {'owner':manager.require_authenticated(request)}
    @app.get('/api/assets/{ident}')
    async def asset(ident:str,request:Request):
        value=store.get('asset',ident,manager.owner(request))
        if not value:raise HTTPException(404)
        return value
    @app.get('/api/export-scene/{ident}')
    async def scene(ident:str,request:Request):
        value=store.get('job',ident,manager.owner(request))
        if not value:raise HTTPException(404)
        return value
    @app.get('/render.html')
    async def render(request:Request):return {'owner':manager.owner(request)}
    return app,manager,store,settings,account,transfers,exchanges


def client_for(harness,base='https://wiscomper.example'):
    return TestClient(harness[0],base_url=base,follow_redirects=False)


def begin(client):
    session=client.get('/api/auth/session');assert session.status_code==200
    response=client.get('/api/auth/github/start');assert response.status_code==302,response.text
    query=parse_qs(urlsplit(response.headers['location']).query)
    return session.json(),query


def finish(client,query,**values):
    return client.get('/api/auth/github/callback',params={'state':query['state'][0],'code':'synthetic-code',**values})


def seed(store,owner,record_kind='project',**extra):
    value={'id':uuid.uuid4().hex,'owner':owner,'updated':time.time(),**extra}
    store.put(record_kind,value);return value


def test_preferences_merge_advances_revision_without_deleting_either_source(tmp_path):
    store=Store(tmp_path/'merge.sqlite3')
    store.create_session('initial','initial-csrf')
    _,account,_=store.login_github('initial',42,{'login':'author'},'member','member-csrf')
    old=seed(store,account,'preferences',revision=4,preferences={'theme':'dark'},updated=time.time()-10)
    store.create_session('guest','guest-csrf')
    newer=seed(store,'guest','preferences',revision=4,preferences={'theme':'light'})
    store.login_github('guest',42,{'login':'author'},'joined','joined-csrf')
    merged=store.list('preferences',account)
    assert len(merged)==2 and merged[0]['id']==newer['id']
    assert merged[0]['revision']==5 and merged[0]['preferences']['theme']=='light'
    assert store.get('preferences',old['id'],account)['preferences']['theme']=='dark'
    assert not store.list('preferences','guest')


def test_unconfigured_status_is_explicit_and_no_oauth_request(harness):
    harness[3].clear()
    with client_for(harness,'http://testserver') as client:
        response=client.get('/api/auth/session');value=response.json()
        assert value['authenticated'] is False and value['user'] is None and value['github']['configured'] is False
        assert '尚未配置' in value['github']['message'] and value['csrf']
        cookie=response.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=lax' in cookie and 'secure' not in cookie
        assert client.get('/api/auth/github/start').headers['location']=='/?auth_error=not_configured'
        assert not harness[6] and client.get('/api/private').status_code==401


def test_state_is_hashed_session_bound_single_use_and_pkce_s256(harness):
    _,manager,store,_,_,_,exchanges=harness
    with client_for(harness) as client,client_for(harness) as other:
        session,query=begin(client);sid=client.cookies.get(manager.cookie)
        assert query['scope']==['read:user'] and query['code_challenge_method']==['S256']
        assert query['redirect_uri']==['https://wiscomper.example/api/auth/github/callback']
        assert 'synthetic-client-secret' not in json.dumps(query)
        with store.connect() as db:row=db.execute('SELECT state_hash,session_id,verifier FROM oauth_states').fetchone()
        assert row[0]==hashlib.sha256(query['state'][0].encode()).hexdigest() and row[1]==sid
        challenge=base64.urlsafe_b64encode(hashlib.sha256(row[2].encode()).digest()).rstrip(b'=').decode()
        assert query['code_challenge']==[challenge] and row[2] not in json.dumps(query)
        other.get('/api/auth/session')
        assert finish(other,query).headers['location']=='/?auth_error=state' and exchanges==[]
        response=finish(client,query);assert response.status_code==303 and response.headers['location']=='/'
        assert 'secure' in response.headers['set-cookie'].lower()
        assert client.cookies.get(manager.cookie)!=sid and store.session(sid) is None
        logged=client.get('/api/auth/session').json()
        assert logged['authenticated'] and logged['user']['login']=='author' and logged['csrf']!=session['csrf']
        assert exchanges[0]['verifier']==row[2]
        assert finish(client,query).headers['location']=='/?auth_error=state' and len(exchanges)==1
        assert client.get('/api/auth/github/start').headers['location']=='/?auth_error=already_signed_in'


@pytest.mark.parametrize('case,expected',[('expired','state'),('denied','denied'),('missing','state'),('wrong','state')])
def test_invalid_callback_never_exchanges_and_never_reflects_error(harness,case,expected):
    with client_for(harness) as client:
        _,query=begin(client)
        if case=='expired':
            with harness[2].connect() as db:db.execute('UPDATE oauth_states SET expires=0')
        if case=='wrong':query['state']=['x'*43]
        values={'error':'access_denied','error_description':'private-provider-diagnostic'} if case=='denied' else {}
        if case=='missing':values={'code':''}
        response=finish(client,query,**values)
        assert response.headers['location']=='/?auth_error='+expected and 'private-provider' not in response.text
        assert harness[6]==[]


def test_login_transfers_all_records_and_history_to_stable_account(harness):
    _,manager,store,_,account,transfers,_=harness
    with client_for(harness) as first,client_for(harness) as second,client_for(harness) as foreign:
        _,query=begin(first);old=first.cookies.get(manager.cookie)
        records=[seed(store,old,kind,**({'status':'completed','_base_project':{'owner':old}} if kind=='job' else {}))
                 for kind in ['project','asset','revision','job']]
        assert finish(first,query).headers['location']=='/'
        owner=store.session_owner(first.cookies.get(manager.cookie));assert owner.startswith('account:') and owner!=old
        assert transfers==[(old,owner)]
        for kind,record in zip(['project','asset','revision','job'],records):
            assert store.get(kind,record['id'],old) is None
            assert store.get(kind,record['id'],owner)['owner']==owner
        assert store.get('job',records[-1]['id'],owner)['_base_project']['owner']==owner
        with pytest.raises(SessionExpired):seed(store,old)
        _,second_query=begin(second);second_old=second.cookies.get(manager.cookie);extra=seed(store,second_old)
        account['login']='renamed-author'
        assert finish(second,second_query).headers['location']=='/'
        assert store.session_owner(second.cookies.get(manager.cookie))==owner
        assert len(first.get('/api/projects').json()['projects'])==2
        assert first.get('/api/auth/session').json()['user']['login']=='renamed-author'
        account['id']=99;account['login']='another-author'
        _,foreign_query=begin(foreign);assert finish(foreign,foreign_query).headers['location']=='/'
        assert foreign.get('/api/projects').json()['projects']==[]
        assert foreign.get('/api/assets/'+records[1]['id']).status_code==404
        assert store.session_owner(foreign.cookies.get(manager.cookie))!=owner
        foreign.cookies.clear();foreign.cookies.set(manager.cookie,owner)
        assert foreign.get('/api/projects').status_code==401,'account owner is never a session credential'


def test_active_jobs_block_start_and_atomic_final_merge(harness):
    _,manager,store,_,_,_,exchanges=harness
    with client_for(harness) as client:
        client.get('/api/auth/session');sid=client.cookies.get(manager.cookie)
        job=seed(store,sid,'job',status='queued')
        assert client.get('/api/auth/github/start').headers['location']=='/?auth_error=busy'
        with store.connect() as db:assert db.execute('SELECT count(*) FROM oauth_states').fetchone()[0]==0
        job['status']='completed';store.put('job',job)
        _,query=begin(client)
        job['status']='rendering';store.put('job',job)
        assert finish(client,query).headers['location']=='/?auth_error=busy'
        assert len(exchanges)==1 and store.session(sid) and store.get('job',job['id'],sid)['status']=='rendering'
        with store.connect() as db:assert db.execute('SELECT count(*) FROM accounts').fetchone()[0]==0
        job['status']='completed';store.put('job',job)
        assert finish(client,query).headers['location']=='/?auth_error=state'


def test_logout_rotates_session_csrf_and_keeps_account_projects_private(harness):
    _,manager,store,_,_,_,_=harness
    with client_for(harness) as client:
        before,query=begin(client);seed(store,client.cookies.get(manager.cookie))
        finish(client,query);logged=client.get('/api/auth/session').json();old_sid=client.cookies.get(manager.cookie)
        assert client.post('/api/auth/logout').status_code==403
        assert client.post('/api/auth/logout',headers={'X-CSRF-Token':before['csrf']}).status_code==403
        headers={'X-CSRF-Token':logged['csrf']}
        assert client.post('/api/auth/logout',headers={**headers,'Origin':'https://evil.example'}).status_code==403
        response=client.post('/api/auth/logout',headers=headers);assert response.status_code==200
        value=response.json();assert not value['authenticated'] and value['csrf']!=logged['csrf']
        assert client.cookies.get(manager.cookie)!=old_sid and store.session(old_sid) is None
        assert client.get('/api/projects').json()['projects']==[]
        assert client.get('/api/private').status_code==401


def test_oauth_failure_after_exchange_does_not_persist_tokens(harness,monkeypatch):
    async def failed(*args):raise auth.OAuthUnavailable('private-provider-diagnostic')
    monkeypatch.setattr(auth,'github_user',failed)
    with client_for(harness) as client:
        _,query=begin(client);response=finish(client,query)
        assert response.headers['location']=='/?auth_error=upstream' and 'private-provider' not in response.text
        assert not client.get('/api/auth/session').json()['authenticated']
        assert finish(client,query).headers['location']=='/?auth_error=state'


def test_legacy_session_schema_migrates_without_losing_ownership(tmp_path):
    path=tmp_path/'legacy.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY,csrf TEXT NOT NULL,created REAL NOT NULL)')
        db.execute('INSERT INTO sessions VALUES (?,?,?)',('legacy-id','legacy-csrf',time.time()))
    store=Store(path)
    assert store.session('legacy-id')=='legacy-csrf' and store.session_owner('legacy-id')=='legacy-id'
    assert store.session_identity('legacy-id')['kind']=='browser'
    with store.connect() as db:db.execute('UPDATE sessions SET expires=0')
    assert store.session('legacy-id') is None


def test_existing_session_reads_do_not_overwrite_rotated_cookies_and_legacy_start_upgrades(harness):
    _,manager,store,_,_,_,_=harness
    with client_for(harness) as client:
        client.get('/api/auth/session')
        assert 'set-cookie' not in client.get('/api/auth/session').headers
        assert 'set-cookie' not in client.get('/api/auth/github/start').headers
        with store.connect() as db:db.execute('UPDATE sessions SET owner=NULL WHERE id=?',(client.cookies.get(manager.cookie),))
        response=client.get('/api/auth/github/start')
        assert 'samesite=lax' in response.headers['set-cookie'].lower()
        assert not store.session_identity(client.cookies.get(manager.cookie))['legacy_cookie']


def test_local_oauth_uses_only_loopback_callback_without_public_config(harness):
    harness[3]['PUBLIC_SITE_URL']=''
    with client_for(harness,'http://127.0.0.1:3088') as client:
        _,query=begin(client)
        assert query['redirect_uri']==['http://127.0.0.1:3088/api/auth/github/callback']
        response=finish(client,query)
        assert response.headers['location']=='/' and 'secure' not in response.headers['set-cookie'].lower()


def test_login_migration_is_atomic_on_storage_failure(tmp_path):
    store=Store(tmp_path/'atomic.sqlite3');store.create_session('source','csrf');record=seed(store,'source')
    with store.connect() as db:
        db.execute("CREATE TRIGGER fail_migration BEFORE UPDATE ON records BEGIN SELECT RAISE(ABORT,'synthetic rollback'); END")
    with pytest.raises(sqlite3.IntegrityError):store.login_github('source',42,{'login':'author'},'next','new-csrf')
    assert store.session('source')=='csrf' and store.session('next') is None
    assert store.get('project',record['id'],'source')==record
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM accounts').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM retired_owners').fetchone()[0]==0


@pytest.mark.parametrize('status',ACTIVE_JOB_STATUSES)
def test_every_active_job_state_blocks_store_transfer(tmp_path,status):
    store=Store(tmp_path/'busy.sqlite3');store.create_session('source','csrf');seed(store,'source','job',status=status)
    with pytest.raises(LoginBusy):store.login_github('source',42,{'login':'author'},'next','new-csrf')
    assert store.session('source')=='csrf'


def test_global_and_account_budgets_reserve_together_under_concurrency(tmp_path):
    store=Store(tmp_path/'budgets.sqlite3')
    def reserve(_):
        try:store.reserve(3,30,owner='account:a',owner_limit=9);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=6) as executor:assert sum(executor.map(reserve,range(15)))==3
    store.reserve(3,30,owner='account:b',owner_limit=9)
    with pytest.raises(ValueError):store.reserve(3,12,owner='account:b',owner_limit=9)
    with store.connect() as db:
        assert db.execute('SELECT reserved FROM budget').fetchone()[0]==12
        assert dict(db.execute('SELECT owner,reserved FROM account_budget'))=={'account:a':9,'account:b':3}
    store.reserve(3,30)
    with store.connect() as db:assert db.execute('SELECT reserved FROM budget').fetchone()[0]==15


def test_state_can_be_consumed_only_once_across_store_instances(tmp_path):
    path=tmp_path/'state.sqlite3';store=Store(path);store.create_session('source','csrf')
    store.begin_oauth('source','state-hash','verifier','https://wiscomper.example/api/auth/github/callback',time.time()+600)
    other=Store(path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        values=list(executor.map(lambda current:current.consume_oauth('source','state-hash'),[store,other]))
    assert sum(value is not None for value in values)==1


def test_render_session_is_scoped_short_lived_and_revocable(harness):
    _,manager,store,_,_,_,_=harness
    with client_for(harness) as user:
        _,query=begin(user);finish(user,query);owner=store.session_owner(user.cookies.get(manager.cookie))
    asset=seed(store,owner,'asset');other_asset=seed(store,owner,'asset')
    job=seed(store,owner,'job',kind='export',status='rendering',export_scene={'objects':[{'asset_id':asset['id']}]})
    token=manager.render_session(owner,job['id'])
    with client_for(harness,'http://testserver') as render:
        render.cookies.set(manager.cookie,token)
        assert render.get('/render.html').status_code==200
        assert render.get('/api/export-scene/'+job['id']).status_code==200
        assert render.get('/api/assets/'+asset['id']).status_code==200
        for path in ['/api/projects','/api/assets/'+other_asset['id'],'/api/export-scene/'+uuid.uuid4().hex,'/api/auth/session']:
            assert render.get(path).status_code==403
        assert render.post('/api/auth/logout').status_code==401
        manager.revoke_session(token)
        assert render.get('/render.html').status_code==401
    token=manager.render_session(owner,job['id'])
    with store.connect() as db:db.execute('UPDATE sessions SET expires=0 WHERE id=?',(token,))
    assert store.session(token) is None


def test_official_token_exchange_is_bounded_pkce_and_not_persisted(monkeypatch):
    calls=[];original=httpx.AsyncClient
    def handler(request):
        calls.append(request)
        if str(request.url)==auth.GITHUB_TOKEN:
            assert request.method=='POST'
            body=parse_qs(request.content.decode())
            assert body['code_verifier']==['verifier'] and body['client_secret']==['synthetic-secret']
            assert request.headers.get('authorization') is None
            return httpx.Response(200,json={'access_token':'synthetic-access-token','token_type':'bearer','scope':'read:user'})
        assert str(request.url)==auth.GITHUB_USER and request.method=='GET'
        assert request.headers['authorization']=='Bearer synthetic-access-token'
        return httpx.Response(200,json={'id':42,'login':'author','name':'Author','avatar_url':'https://evil.example/track','html_url':'javascript:bad'})
    def factory(**kwargs):
        assert kwargs=={'timeout':10,'follow_redirects':False,'trust_env':False}
        return original(transport=httpx.MockTransport(handler),**kwargs)
    monkeypatch.setattr(auth.httpx,'AsyncClient',factory)
    ident,profile=asyncio.run(auth.github_user(auth.AuthConfig('client','synthetic-secret'), 'code','verifier','https://wiscomper.example/api/auth/github/callback'))
    assert ident==42 and len(calls)==2 and profile['profile_url']=='https://github.com/author'
    assert profile['avatar_url'].startswith('https://avatars.githubusercontent.com/')
    assert 'synthetic-access-token' not in json.dumps(profile)


@pytest.mark.parametrize('response',[
    httpx.Response(302,headers={'location':'https://evil.example/steal'}),
    httpx.Response(401,text='private-provider-error synthetic-secret'),
    httpx.Response(200,json={'error':'bad_verification_code','error_description':'private-provider-error'}),
    httpx.Response(200,content=b'x'*65_537),
])
def test_oauth_remote_failures_are_safe_no_redirect_or_retry(monkeypatch,response):
    original=httpx.AsyncClient;calls=[]
    def handler(request):calls.append(request);return response
    monkeypatch.setattr(auth.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(auth.OAuthUnavailable) as error:
        asyncio.run(auth.github_user(auth.AuthConfig('client','synthetic-secret'),'code','verifier','https://wiscomper.example/api/auth/github/callback'))
    assert len(calls)==1 and 'private-provider' not in str(error.value) and 'synthetic-secret' not in str(error.value)


@pytest.mark.parametrize('site',['http://public.example','https://user:pass@public.example','https://public.example/path',
    'https://public.example?q=1','https://127.0.0.1','https://public.example:8443','https://@public.example',
    'https://public.example/#','https://public.example/?','https://public.example:'])
def test_invalid_public_site_never_enables_oauth(site):
    config=auth.load_config({'GITHUB_CLIENT_ID':'client','GITHUB_CLIENT_SECRET':'synthetic-secret','PUBLIC_SITE_URL':site})
    assert not config.configured and 'synthetic-secret' not in repr(config)


def test_usage_shows_local_site_and_public_account_limits_without_reserving(harness):
    _,manager,store,settings,_,_,_=harness
    settings['PUBLIC_SITE_URL']='';settings['VISUALIZE_DAILY_CALLS']='12'
    with client_for(harness,'http://testserver') as local:
        response=local.get('/api/auth/session').json();usage=response['usage']
        assert not response['public_mode'] and usage['scope']=='site'
        assert (usage['total'],usage['used'],usage['remaining'],usage['available'])==(4,0,4,4)
        assert not usage['requires_login'] and usage['reset_at'].endswith('T00:00:00Z')
        store.reserve(3,12)
        usage=local.get('/api/auth/session').json()['usage']
        assert (usage['total'],usage['used'],usage['remaining'])==(4,1,3)
    settings['PUBLIC_SITE_URL']='https://wiscomper.example';settings['PUBLIC_ACCOUNT_DAILY_TASKS']='2'
    with client_for(harness) as client:
        response,query=begin(client)
        assert response['public_mode'] and response['usage']['requires_login'] and response['usage']['available']==0
        finish(client,query);owner=store.session_owner(client.cookies.get(manager.cookie))
        store.reserve(3,12,owner=owner,owner_limit=6)
        value=client.get('/api/auth/session').json();usage=value['usage']
        assert (usage['scope'],usage['total'],usage['used'],usage['remaining'],usage['available'])==('account',2,1,1,1)
        assert usage['site_remaining']==2 and not usage['requires_login']
        assert owner not in json.dumps(value) and 'synthetic-client-secret' not in json.dumps(value)
        for _ in range(3):client.get('/api/auth/session')
        assert store.usage(owner)['site_reserved']==6 and store.usage(owner)['account_reserved']==3
        store.reserve(6,12,owner='account:another',owner_limit=9)
        usage=client.get('/api/auth/session').json()['usage']
        assert usage['remaining']==1 and usage['available']==0 and usage['site_remaining']==0


def test_account_usage_survives_logout_and_same_github_relogin_and_is_private(harness):
    _,manager,store,_,account,_,_=harness
    with client_for(harness) as client:
        _,query=begin(client);finish(client,query);logged=client.get('/api/auth/session').json()
        owner=store.session_owner(client.cookies.get(manager.cookie));store.reserve(6,30,owner=owner,owner_limit=9)
        out=client.post('/api/auth/logout',headers={'X-CSRF-Token':logged['csrf']}).json()
        assert out['usage']['used']==0 and out['usage']['requires_login']
        _,query=begin(client);finish(client,query)
        assert client.get('/api/auth/session').json()['usage']['used']==2
    account['id']=99;account['login']='another'
    with client_for(harness) as other:
        _,query=begin(other);finish(other,query)
        assert other.get('/api/auth/session').json()['usage']['used']==0


def test_new_oauth_start_invalidates_an_older_callback_already_exchanging(harness,monkeypatch):
    _,manager,store,_,_,_,_=harness
    started=__import__('threading').Event();release=__import__('threading').Event()
    async def slow_exchange(*args):
        started.set();await asyncio.to_thread(release.wait,3)
        return 42,{'login':'older-account','name':None}
    monkeypatch.setattr(auth,'github_user',slow_exchange)
    with client_for(harness) as client:
        _,first=begin(client);sid=client.cookies.get(manager.cookie)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending=executor.submit(finish,client,first)
            assert started.wait(2)
            second=client.get('/api/auth/github/start');assert second.status_code==302
            release.set();result=pending.result(timeout=3)
        assert result.headers['location']=='/?auth_error=session' and store.session(sid)
        assert not client.get('/api/auth/session').json()['authenticated']
        with store.connect() as db:assert db.execute('SELECT count(*) FROM accounts').fetchone()[0]==0


def test_logout_while_callback_exchanges_cannot_reauthenticate_old_session(harness,monkeypatch):
    started=__import__('threading').Event();release=__import__('threading').Event()
    async def slow_exchange(*args):
        started.set();await asyncio.to_thread(release.wait,3)
        return 42,{'login':'older-account','name':None}
    monkeypatch.setattr(auth,'github_user',slow_exchange)
    with client_for(harness) as client:
        session,first=begin(client)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending=executor.submit(finish,client,first);assert started.wait(2)
            out=client.post('/api/auth/logout',headers={'X-CSRF-Token':session['csrf']});assert out.status_code==200
            release.set();response=pending.result(timeout=3)
        assert response.headers['location']=='/?auth_error=session'
        assert not client.get('/api/auth/session').json()['authenticated']
