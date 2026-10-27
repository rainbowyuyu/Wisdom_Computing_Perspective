import asyncio
import base64
import importlib
import io
from pathlib import Path
import threading
import time
import uuid

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from server.storage import Store

api = importlib.import_module('server.app')


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'DATA', tmp_path)
    monkeypatch.setattr(api, 'STORE', Store(tmp_path / 'test.sqlite3'))
    monkeypatch.setattr(api, 'tasks', {})
    monkeypatch.setattr(api, 'jobs', {})
    monkeypatch.setattr(api, 'cancellations', {})
    monkeypatch.setattr(api, 'slot', asyncio.Semaphore(2))
    monkeypatch.setattr(api, 'render_slot', asyncio.Semaphore(1))
    monkeypatch.setattr(api, 'mutation', asyncio.Lock())
    monkeypatch.setattr(api, 'upload_slot', asyncio.Semaphore(2))
    monkeypatch.setattr('runtime.planner.capabilities', lambda: [{'id':'qwen','name':'Qwen','available':True,'message':'Configured'}])
    monkeypatch.setattr('server.exporter.renderer_capabilities', lambda: {'browser':True,'manim':False})
    return api


def bootstrap(client):
    response = client.get('/api/bootstrap'); assert response.status_code == 200
    return {'X-CSRF-Token':response.json()['csrf']}


def wait_job(client, ident, timeout=3):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        response = client.get('/api/jobs/' + ident); assert response.status_code == 200
        job = response.json()['job']
        if job['status'] not in api.ACTIVE:
            return job
        time.sleep(.01)
    pytest.fail('Job did not settle promptly')


def create_sample(client, headers, request_key=None):
    response = client.post('/api/jobs', headers=headers, json={'sample':'projectile','request_key':request_key or uuid.uuid4().hex})
    assert response.status_code == 202, response.text
    return response.json()['job']


def test_csrf_origin_body_and_host_guards(isolated):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        payload = {'sample':'projectile','request_key':'request-valid'}
        assert client.post('/api/jobs', json=payload).status_code == 403
        assert client.post('/api/jobs', headers={**headers,'Origin':'https://foreign.example'}, json=payload).status_code == 403
        assert client.post('/api/jobs', headers={**headers,'Sec-Fetch-Site':'cross-site'}, json=payload).status_code == 403
        assert client.get('/healthz', headers={'Host':'foreign.example'}).status_code == 403
        assert client.post('/api/jobs', headers={**headers,'Content-Length':'9' * 5000}, content='{}').status_code == 413
        # Reject actual streamed bytes even when an advertised size is smaller.
        response = client.post('/api/jobs', headers={**headers,'Content-Length':'2','Content-Type':'application/json'}, content=iter([b' ' * 3_600_000, b' ' * 3_600_000]))
        assert response.status_code == 413
        assert not api.STORE.list('job')


def test_interaction_state_is_private_persistent_and_exported_without_model_budget(isolated,monkeypatch):
    captured=[]
    def fake_export(scene,output,**kwargs):
        captured.append(scene);Path(output).write_bytes(b'test-video');return Path(output)
    monkeypatch.setattr('server.exporter.export_video',fake_export)
    with TestClient(api.app) as client:
        headers=bootstrap(client)
        job=client.post('/api/jobs',headers=headers,json={'sample':'fan','request_key':'interactive-fan'}).json()['job']
        ident=wait_job(client,job['id'])['project_id'];url=f'/api/projects/{ident}'
        state={'values':{'rotor-angle':90,'guards-visible':0},'camera':{'azimuth':1,'elevation':.4,'distance':10,'orbit':0}}
        assert client.post(url+'/interaction-state',json=state).status_code==403
        response=client.post(url+'/interaction-state',headers=headers,json=state)
        assert response.status_code==200,response.text
        assert client.get(url).json()['project']['exploration']==state
        for values in ({'rotor-angle':181},{'guards-visible':.5},{'missing':1}):
            assert client.post(url+'/interaction-state',headers=headers,json={'values':values}).status_code==422
        assert client.get(url).json()['project']['exploration']==state
        changed=client.post(url+'/recompute',headers=headers,json={'parameters':{'pitch':30}})
        assert changed.status_code==200 and changed.json()['project']['exploration']==state
        bundle=client.get(url+'/scene?bundle=true').json()
        assert bundle['format']=='visualize-project' and bundle['exploration']==state
        assert 'objects' in client.get(url+'/scene').json()
        exported=client.post(url+'/export',headers=headers,json={'engine':'browser','fps':15})
        assert wait_job(client,exported.json()['job']['id'])['status']=='completed'
        nodes={o['id']:o for o in captured[0]['objects']}
        assert nodes['front-guard']['opacity']==0 and captured[0]['camera']==state['camera']
        assert captured[0]['interactions']==[]
        with api.STORE.connect() as db:assert db.execute('SELECT COUNT(*) FROM budget').fetchone()[0]==0
        client.cookies.clear();other=bootstrap(client)
        assert client.post(url+'/interaction-state',headers=other,json=state).status_code==404


def test_project_asset_job_and_export_are_private(isolated, monkeypatch):
    def fake_export(scene, output, **kwargs):
        Path(output).write_bytes(b'private-test-video')
        return Path(output)
    monkeypatch.setattr('server.exporter.export_video', fake_export)
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        first_cookie = client.cookies.get(api.COOKIE)
        job = wait_job(client, create_sample(client, headers)['id'])
        assert job['status'] == 'completed'
        project_id = job['project_id']
        image = io.BytesIO(); Image.new('RGB',(10,10),'red').save(image,format='PNG')
        upload = client.post('/api/assets', headers=headers, json={'data_url':'data:image/png;base64,' + base64.b64encode(image.getvalue()).decode()})
        assert upload.status_code == 200
        asset_id = upload.json()['asset_id']
        exported = client.post(f'/api/projects/{project_id}/export', headers=headers, json={'engine':'browser','fps':15})
        assert exported.status_code == 202
        export_job = wait_job(client, exported.json()['job']['id'])
        assert export_job['status'] == 'completed'
        assert client.get(export_job['video_url']).content == b'private-test-video'
        for record in (job, export_job):
            assert not {'owner','digest','export_scene','request_key'}.intersection(record)
        client.cookies.clear(); second_headers = bootstrap(client)
        assert client.cookies.get(api.COOKIE) != first_cookie
        private_paths = [f'/api/jobs/{job["id"]}', f'/api/projects/{project_id}', f'/api/projects/{project_id}/scene', f'/api/assets/{asset_id}', f'/api/export-scene/{export_job["id"]}', export_job['video_url']]
        assert all(client.get(path).status_code == 404 for path in private_paths)
        assert client.get('/api/projects').json()['projects'] == []
        assert client.post('/api/jobs',headers=second_headers,json={'prompt':'inspect','asset_id':asset_id,'request_key':'wrong-owner-image'}).status_code == 404
        assert client.get('/api/assets/%2E%2E%5Cprivate').status_code == 404


def test_queue_cancel_does_not_wait_for_busy_slot(isolated, monkeypatch):
    monkeypatch.setattr(api, 'slot', asyncio.Semaphore(0))
    with TestClient(api.app) as client:
        headers = bootstrap(client); job = create_sample(client, headers)
        start = time.monotonic()
        response = client.post(f'/api/jobs/{job["id"]}/cancel', headers=headers)
        assert response.status_code == 200
        settled = wait_job(client, job['id'])
        assert settled['status'] == 'cancelled' and time.monotonic() - start < 1
        assert job['id'] not in api.tasks
        assert not api.STORE.list('project')


def test_running_worker_is_drained_and_late_events_ignored(isolated, monkeypatch):
    started, stopped = threading.Event(), threading.Event()
    def fake_plan(*args, cancelled, on_event, **kwargs):
        started.set()
        assert cancelled.wait(3)
        on_event({'stage':'late-event','message':'must not overwrite cancellation'})
        stopped.set()
        return {'title':'late','recipe':'diagram'}
    monkeypatch.setattr('runtime.planner.plan', fake_plan)
    with TestClient(api.app) as client:
        headers=bootstrap(client)
        response=client.post('/api/jobs',headers=headers,json={'prompt':'explain','request_key':'active-cancel-test'})
        assert response.status_code == 202
        ident=response.json()['job']['id']; assert started.wait(2)
        client.post(f'/api/jobs/{ident}/cancel',headers=headers)
        job=wait_job(client,ident)
        assert stopped.is_set() and job['status']=='cancelled'
        assert not any(e['stage']=='late-event' for e in job['events'])
        assert not api.tasks and not api.cancellations


def test_shutdown_cancels_queued_work_without_hanging(isolated, monkeypatch):
    monkeypatch.setattr(api, 'slot', asyncio.Semaphore(0))
    start=time.monotonic()
    with TestClient(api.app) as client:
        headers=bootstrap(client);job=create_sample(client,headers)
    assert time.monotonic()-start<2
    assert not api.tasks
    assert api.STORE.list('job')[0]['status']=='cancelled'


def test_daily_budget_and_idempotency_do_not_repeat_calls(isolated, monkeypatch):
    monkeypatch.setattr(api,'MAX_CALLS',3)
    calls=[]
    def fake_plan(*args, **kwargs):
        calls.append(1);return {'title':'bounded','recipe':'diagram'}
    monkeypatch.setattr('runtime.planner.plan',fake_plan)
    with TestClient(api.app) as client:
        headers=bootstrap(client)
        payload={'prompt':'explain','request_key':'same-external-request'}
        first=client.post('/api/jobs',headers=headers,json=payload);assert first.status_code==202
        ident=first.json()['job']['id'];assert wait_job(client,ident)['status']=='completed'
        assert client.post('/api/jobs',headers=headers,json=payload).json()['job']['id']==ident
        assert client.post('/api/jobs',headers=headers,json={**payload,'prompt':'different'}).status_code==409
        assert client.post('/api/jobs',headers=headers,json={**payload,'request_key':'new-external-request'}).status_code==429
        assert wait_job(client,create_sample(client,headers)['id'])['status']=='completed'
        assert len(calls)==1


def test_store_request_lookup_survives_long_history(isolated):
    owner='test-owner';ident=uuid.uuid4().hex
    api.STORE.put('job',{'id':ident,'owner':owner,'updated':1,'request_key':'old-request'})
    for i in range(1001):
        api.STORE.put('job',{'id':uuid.uuid4().hex,'owner':owner,'updated':i+2})
    assert api.STORE.find_request(owner,'old-request')['id']==ident
    assert api.STORE.find_request('other-owner','old-request') is None
    with pytest.raises(ValueError,match='身份'):
        api.STORE.put('job',{'id':ident,'owner':'different-owner','updated':9999})


def test_recompute_changes_physics_and_preserves_revision(isolated):
    with TestClient(api.app) as client:
        headers=bootstrap(client);job=wait_job(client,create_sample(client,headers)['id'])
        ident=job['project_id'];before=client.get('/api/projects/'+ident).json()['project']
        initial=next(o for o in before['scene']['objects'] if o['id']=='facts')['text']
        response=client.post(f'/api/projects/{ident}/recompute',headers=headers,json={'parameters':{'speed':20}})
        assert response.status_code==200,response.text
        after=response.json()['project']
        assert after['revision']==2 and before['revision']==1
        assert after['proposal']['parameters']['speed']==20
        assert next(c for c in after['scene']['controls'] if c['id']=='speed')['value']==20
        assert next(o for o in after['scene']['objects'] if o['id']=='facts')['text']!=initial
        assert len(api.STORE.list('revision'))==1
        for parameters in ({'gravity':0},{'not-a-control':1},{'speed':float('inf')}):
            if any(value==float('inf') for value in parameters.values()):
                response=client.post(f'/api/projects/{ident}/recompute',headers={**headers,'Content-Type':'application/json'},content='{"parameters":{"speed":1e999}}')
            else:response=client.post(f'/api/projects/{ident}/recompute',headers=headers,json={'parameters':parameters})
            assert response.status_code==422
        assert client.get('/api/projects/'+ident).json()['project']['revision']==2
