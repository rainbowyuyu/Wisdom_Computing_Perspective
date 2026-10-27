"""Public hosting boundaries; all model and OAuth calls are isolated/mocked."""
from fastapi.testclient import TestClient
from test_api import api, isolated, bootstrap, wait_job
from server.site import SiteConfig
from server.public_guard import PublicLimiter


def make_public(monkeypatch):
    monkeypatch.setenv('PUBLIC_SITE_URL', 'https://www.wiscomper.com')
    monkeypatch.setattr(api, 'SITE', SiteConfig.from_settings({}))
    monkeypatch.setattr(api, 'PUBLIC_LIMITER', PublicLimiter())


def test_public_host_origin_cookies_and_private_indexing(isolated, monkeypatch):
    make_public(monkeypatch)
    with TestClient(api.app, base_url='https://www.wiscomper.com') as client:
        r=client.get('/api/bootstrap')
        headers={'X-CSRF-Token':r.json()['csrf']}
        assert client.cookies.get(api.COOKIE)
        assert 'Secure' in r.headers['set-cookie']
        assert 'SameSite=lax' in r.headers['set-cookie']
        assert r.json()['public_mode'] is True
        assert 'noindex' in r.headers['x-robots-tag']
        assert 'noindex' not in client.get('/').headers['x-robots-tag']
        assert client.get('/',headers={'Host':'attacker.example'}).status_code==403
        payload={'sample':'projectile','request_key':'public-sample'}
        assert client.post('/api/jobs',headers={**headers,'Origin':'https://other.example'},json=payload).status_code==403
        response=client.post('/api/jobs',headers={**headers,'Origin':'https://www.wiscomper.com'},json=payload)
        assert response.status_code==202,response.text
        wait_job(client,response.json()['job']['id'])


def test_reverse_proxy_http_connection_still_issues_secure_cookie(isolated,monkeypatch):
    make_public(monkeypatch)
    with TestClient(api.app,base_url='http://www.wiscomper.com') as client:
        response=client.get('/api/bootstrap')
        assert 'Secure' in response.headers['set-cookie']
        assert response.headers['strict-transport-security']=='max-age=31536000'


def test_public_guest_can_explore_but_cannot_spend_model_or_render_budget(isolated,monkeypatch):
    make_public(monkeypatch)
    with TestClient(api.app,base_url='https://www.wiscomper.com') as client:
        headers=bootstrap(client)
        assert client.post('/api/jobs',headers=headers,json={'prompt':'describe a wave','request_key':'private-generate'}).status_code==401
        assert not api.STORE.list('job')
        # No model budget was reserved on an unauthenticated request.
        with api.STORE.connect() as db:assert db.execute('select count(*) from budget').fetchone()[0]==0
        job=client.post('/api/jobs',headers=headers,json={'sample':'projectile','request_key':'guest-demo'}).json()['job']
        pid=wait_job(client,job['id'])['project_id']
        assert client.get(f'/api/projects/{pid}').status_code==200
        assert client.post(f'/api/projects/{pid}/export',headers=headers,json={'engine':'browser','fps':15}).status_code==401
        assert client.get('/api/auth/session').json()['authenticated'] is False


def test_public_limiter_bounds_memory_and_expires_without_dropping_live_budget():
    limiter=PublicLimiter(limit=2,window=60,capacity=2)
    assert limiter.allow('one',0) and limiter.allow('one',1)
    assert not limiter.allow('one',2)
    assert limiter.allow('two',3)
    assert not limiter.allow('three',4)
    assert len(limiter.entries)==2
    assert limiter.allow('three',64)
    assert limiter.allow('one',65)


def test_export_uses_scoped_temporary_cookie_then_revokes_it(isolated,monkeypatch):
    from pathlib import Path
    captured=[]
    def exporter(scene,output,**options):
        sid=options['cookie_value'];captured.append(sid)
        internal=TestClient(api.app,base_url='http://127.0.0.1')
        internal.cookies.set(api.COOKIE,sid)
        assert internal.get('/render.html').status_code==200
        assert internal.get('/api/export-scene/'+options['job_id']).status_code==200
        assert internal.get('/api/projects').status_code==403
        assert internal.get('/api/auth/session').status_code==403
        internal.close()
        Path(output).write_bytes(b'isolated-export-placeholder')
    monkeypatch.setattr('server.exporter.export_video',exporter)
    with TestClient(api.app) as client:
        headers=bootstrap(client)
        job=client.post('/api/jobs',headers=headers,json={'sample':'fan','request_key':'scoped-export'}).json()['job']
        pid=wait_job(client,job['id'])['project_id']
        job=client.post('/api/projects/'+pid+'/export',headers=headers,json={'engine':'browser','fps':15}).json()['job']
        assert wait_job(client,job['id'])['status']=='completed'
        assert captured and api.STORE.session(captured[0]) is None
        assert client.get('/api/projects/'+pid).status_code==200
