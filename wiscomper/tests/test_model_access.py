"""Authorization tests never contact a model, SMTP, GitHub or production DB."""
import asyncio
import importlib
import uuid

import bcrypt
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from server.legacy_accounts import LegacyAccounts
from server.model_access import local_access, model_access, restrict_capabilities
from server.site import SiteConfig
from server.storage import Store


def request(host='127.0.0.1:3088', peer='127.0.0.1', headers=()):
    return Request({'type':'http','method':'GET','scheme':'http','path':'/api/jobs',
                    'query_string':b'','server':('127.0.0.1',3088),'client':(peer,12345),
                    'headers':[(b'host',host.encode()),*[(k.encode(),v.encode()) for k,v in headers]]})


@pytest.mark.parametrize('host,peer,headers,public,expected',[
    ('127.0.0.1:3088','127.0.0.1',(),'',True),
    ('localhost:3088','::1',(),'',True),
    ('[::1]:3088','::1',(),'',True),
    ('localhost:3088','198.51.100.3',(),'',False),
    ('wiscomper.com','127.0.0.1',(),'',False),
    ('localhost:3088','127.0.0.1',(),'https://www.wiscomper.com',False),
    ('localhost:3088','127.0.0.1',(('x-forwarded-for','127.0.0.1'),),'',False),
    ('localhost:3088','127.0.0.1',(('forwarded','for=127.0.0.1'),),'',False),
    ('localhost:3088','127.0.0.1',(('x-real-ip','127.0.0.1'),),'',False),
])
def test_local_privileges_require_direct_local_deployment(host,peer,headers,public,expected):
    assert local_access(request(host,peer,headers),public) is expected


def test_claimed_user_without_authenticated_account_never_receives_premium():
    access=model_access(request(peer='192.0.2.4'),{'account_id':None,'user':{'role':'admin'}})
    assert access['allowed']==['qwen']
    values=restrict_capabilities([{'id':'claude','available':True,'model':'internal','message':'secret routing'}],access)
    claude=next(v for v in values if v['id']=='claude')
    assert not claude['available'] and not claude['permitted'] and 'model' not in claude


@pytest.fixture
def web(tmp_path,monkeypatch):
    api=importlib.import_module('server.app')
    store=Store(tmp_path/'workbench.sqlite3')
    conf={'LEGACY_ACCOUNT_BACKEND':'sqlite'}
    accounts=LegacyAccounts(lambda:conf,lambda:store)
    monkeypatch.setattr(api,'STORE',store)
    monkeypatch.setattr(api,'ACCOUNTS',accounts)
    monkeypatch.setattr(api,'SITE',SiteConfig('https://www.wiscomper.com'))
    monkeypatch.setattr(api,'mutation',asyncio.Lock())
    monkeypatch.setattr(api,'MAX_CALLS',90)
    monkeypatch.setattr(api,'tasks',{})
    monkeypatch.setattr(api,'jobs',{})
    monkeypatch.setattr(api,'start_job',lambda *args,**kwargs:None)
    monkeypatch.setattr('runtime.planner.capabilities',lambda:[{'id':p,'available':True} for p in ('qwen','chatgpt','claude')])
    hashed=bcrypt.hashpw(b'test-only-password',bcrypt.gensalt(rounds=4)).decode()
    with accounts.transaction(write=True) as cur:
        cur.execute('INSERT INTO users(username,hashed_password,email,email_verified) VALUES(%s,%s,%s,1)',('old-user',hashed,'legacy@example.com'))
        uid=cur.lastrowid
        cur.execute('INSERT INTO account_access(user_id,role) VALUES(%s,%s)',(uid,'member'))
    with TestClient(api.app,base_url='https://www.wiscomper.com',client=('192.0.2.20',1234)) as client:
        data=client.get('/api/bootstrap').json()
        headers={'x-csrf-token':data['csrf']}
        yield api,accounts,client,headers,uid


def login(web):
    api,accounts,client,headers,uid=web
    response=client.post('/api/auth/email/login',headers=headers,json={'identifier':'legacy@example.com','password':'test-only-password'})
    assert response.status_code==200,response.text
    assert '_credential_version' not in response.text and 'hashed_password' not in response.text
    data=response.json()
    headers['x-csrf-token']=data['csrf']
    return data


def test_legacy_login_preserves_guest_work_and_enforces_provider_before_budget(web):
    api,accounts,client,headers,uid=web
    guest=api.STORE.session_identity(client.cookies.get(api.COOKIE))
    formula={'id':uuid.uuid4().hex,'owner':guest['owner'],'latex':'x^2','title':'keep me'}
    api.STORE.put('formula',formula)
    session=login(web)
    assert session['model_access']['allowed']==['qwen']
    identity=api.STORE.session_identity(client.cookies.get(api.COOKIE))
    assert api.STORE.get('formula',formula['id'],identity['owner'])
    assert api.STORE.session_identity(guest['id']) is None
    for provider in ('claude','chatgpt'):
        response=client.post('/api/jobs',headers=headers,json={'prompt':'a test','provider':provider,'request_key':uuid.uuid4().hex})
        assert response.status_code==403,response.text
    assert api.STORE.usage(identity['owner'])['site_reserved']==0
    assert not api.STORE.list('job')
    response=client.post('/api/jobs',headers=headers,json={'prompt':'a test','request_key':uuid.uuid4().hex})
    assert response.status_code==202,response.text
    assert api.STORE.usage(identity['owner'])['site_reserved']==3


def test_role_grant_and_revocation_are_read_from_database(web):
    api,accounts,client,headers,uid=web
    login(web)
    with accounts.transaction(write=True) as cur:
        cur.execute('UPDATE account_access SET role=%s WHERE user_id=%s',('vip',uid))
    data=client.get('/api/auth/session').json()
    assert data['usage']['unlimited'] and data['usage']['total'] is None
    assert data['model_access']['allowed']==['qwen','chatgpt','claude']
    response=client.post('/api/jobs',headers=headers,json={'prompt':'a test','provider':'claude','request_key':uuid.uuid4().hex})
    assert response.status_code==202,response.text
    with accounts.transaction(write=True) as cur:
        cur.execute('UPDATE account_access SET role=%s WHERE user_id=%s',('member',uid))
    response=client.post('/api/jobs',headers=headers,json={'prompt':'a test','provider':'claude','request_key':uuid.uuid4().hex})
    assert response.status_code==403


def test_zero_daily_limit_and_unverified_email_cannot_start_model(web):
    api,accounts,client,headers,uid=web
    login(web)
    with accounts.transaction(write=True) as cur:
        cur.execute('UPDATE account_access SET daily_limit=0 WHERE user_id=%s',(uid,))
    response=client.post('/api/jobs',headers=headers,json={'prompt':'a test','provider':'qwen','request_key':uuid.uuid4().hex})
    assert response.status_code==429
    with accounts.transaction(write=True) as cur:
        cur.execute('UPDATE users SET email_verified=0 WHERE id=%s',(uid,))
    response=client.post('/api/jobs',headers=headers,json={'prompt':'a test','provider':'qwen','request_key':uuid.uuid4().hex})
    assert response.status_code==403
    assert not api.STORE.list('job')


def test_old_site_password_change_revokes_workbench_sessions(web):
    api,accounts,client,headers,uid=web
    login(web)
    with accounts.transaction(write=True) as cur:
        cur.execute('UPDATE users SET hashed_password=%s WHERE id=%s',
                    (bcrypt.hashpw(b'changed-password',bcrypt.gensalt(rounds=4)).decode(),uid))
    assert client.get('/api/projects').status_code==401
    assert client.get('/api/auth/session').json()['authenticated'] is False


def test_new_password_login_does_not_revalidate_an_older_device(web):
    api,accounts,client,headers,uid=web
    login(web)
    old_sid=client.cookies.get(api.COOKIE)
    original=api.STORE.session_identity(old_sid)['credential_version']
    with accounts.transaction(write=True) as cur:
        cur.execute('UPDATE users SET hashed_password=%s WHERE id=%s',
                    (bcrypt.hashpw(b'changed-password',bcrypt.gensalt(rounds=4)).decode(),uid))
    api.STORE.create_session('new-device-before-login','new-device-csrf')
    profile=accounts.authenticate('old-user','changed-password',requester_ip='192.0.2.22')
    _,_,updated=api.STORE.login_legacy('new-device-before-login',uid,profile,'new-device-signed-in','new-csrf',namespace=accounts.namespace)
    assert updated['credential_version']!=original
    assert api.STORE.session_identity(old_sid)['credential_version']==original
    assert client.get('/api/projects').status_code==401
    assert api.STORE.session_identity(old_sid) is None
    client.cookies.set(api.COOKIE,'new-device-signed-in',domain='www.wiscomper.com',path='/')
    assert client.get('/api/projects').status_code==200
    assert client.get('/api/auth/session').json()['authenticated']


def test_existing_session_without_password_stamp_requires_signin(web):
    api,_,client,_,_=web
    login(web)
    sid=client.cookies.get(api.COOKIE)
    with api.STORE.connect() as db:
        db.execute('UPDATE sessions SET credential_version=NULL WHERE id=?',(sid,))
    assert client.get('/api/projects').status_code==401


def test_email_login_requires_csrf_and_rejects_client_role(web):
    _,_,client,headers,_=web
    data={'identifier':'legacy@example.com','password':'test-only-password'}
    assert client.post('/api/auth/email/login',json=data).status_code==403
    assert client.post('/api/auth/email/login',headers=headers,json={**data,'role':'admin'}).status_code==422
    assert client.post('/api/auth/email/login',headers={**headers,'Origin':'https://foreign.example'},json=data).status_code==403


def test_existing_ai_shutdown_preserves_samples_and_does_not_charge(web, monkeypatch):
    api,_,client,headers,_=web
    login(web)
    monkeypatch.setattr(api,'load_settings',lambda *args:{'AI_ENABLED':'0'})
    response=client.post('/api/jobs',headers=headers,json={'prompt':'a test','request_key':uuid.uuid4().hex})
    assert response.status_code==503
    identity=api.STORE.session_identity(client.cookies.get(api.COOKIE))
    assert api.STORE.usage(identity['owner'])['site_reserved']==0 and not api.STORE.list('job')
    response=client.post('/api/jobs',headers=headers,json={'sample':'projectile','request_key':uuid.uuid4().hex})
    assert response.status_code==202
