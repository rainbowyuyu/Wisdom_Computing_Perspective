"""Project history and concurrent edits use local deterministic planner stubs."""
import copy
import asyncio
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from test_api import api, isolated, bootstrap, create_sample, wait_job
from server.builders import sample_proposal
from server.storage import RevisionConflict, Store


def editable(client,headers,sample='projectile'):
    job=client.post('/api/jobs',headers=headers,json={'sample':sample,'request_key':uuid.uuid4().hex}).json()['job']
    ident=wait_job(client,job['id'])['project_id']
    return client.get('/api/projects/'+ident).json()['project']


def iterate(client,headers,project,**overrides):
    return client.post('/api/jobs',headers=headers,json={
        'parent_id':project['id'],'expected_revision':project['revision'],
        'prompt':'增加清晰标注','request_key':uuid.uuid4().hex,**overrides})


def test_iteration_keeps_identity_archives_and_restores_without_model_call(isolated,monkeypatch):
    calls=[]
    def plan(*args,**kwargs):
        calls.append(kwargs['previous'])
        proposal=sample_proposal('projectile').model_dump();proposal['title']='持续修改后的作品'
        return proposal
    monkeypatch.setattr('runtime.planner.plan',plan)
    with TestClient(api.app) as client:
        headers=bootstrap(client);before=editable(client,headers)
        response=iterate(client,headers,before,prompt='把标题和说明更新')
        assert response.status_code==202,response.text
        queued=response.json()['job']
        assert queued['target_project_id']==before['id'] and queued['base_revision']==1
        assert '_base_project' not in queued
        completed=wait_job(client,queued['id'])
        assert completed['project_id']==before['id'] and completed['result_revision']==2
        current=client.get('/api/projects/'+before['id']).json()['project']
        assert current['revision']==2 and current['created']==before['created']
        assert current['initial_prompt']==before['prompt'] and current['prompt']=='把标题和说明更新'
        assert len(client.get('/api/projects').json()['projects'])==1
        url=f'/api/projects/{before["id"]}'
        history=client.get(url+'/revisions').json()
        assert [item['revision'] for item in history['revisions']]==[2,1]
        assert [item['is_current'] for item in history['revisions']]==[True,False]
        old=client.get(url+'/revisions/1').json()['project']
        assert old['id']==before['id'] and old['viewed_revision']==1 and old['scene']==before['scene']
        restored=client.post(url+'/restore',headers=headers,json={'revision':1,'expected_revision':2})
        assert restored.status_code==200,restored.text
        result=restored.json()['project']
        assert result['revision']==3 and result['scene']==before['scene'] and result['restored_from']==1
        assert result['created']==before['created'] and result['action']=='restore'
        assert [item['revision'] for item in client.get(url+'/revisions').json()['revisions']]==[3,2,1]
        assert len(calls)==1
        assert client.get(url+'/revisions/2').json()['project']['scene']==current['scene']
        assert client.get(url+'/revisions/999').status_code==404


def test_queued_iteration_uses_immutable_base_and_merges_latest_exploration(isolated,monkeypatch):
    started=threading.Event();release=threading.Event();seen=[]
    def plan(*args,**kwargs):
        seen.append(copy.deepcopy(kwargs['previous']));started.set();assert release.wait(3)
        return sample_proposal('fan').model_dump()
    monkeypatch.setattr('runtime.planner.plan',plan)
    with TestClient(api.app) as client:
        headers=bootstrap(client);before=editable(client,headers,'fan');url='/api/projects/'+before['id']
        monkeypatch.setattr(api,'slot',asyncio.Semaphore(0))
        response=iterate(client,headers,before)
        job=response.json()['job'];assert not started.is_set()
        try:
            assert iterate(client,headers,before).status_code==409
            assert client.post(url+'/recompute',headers=headers,json={'parameters':{'pitch':30},'expected_revision':1}).status_code==409
            assert client.post(url+'/restore',headers=headers,json={'revision':1,'expected_revision':1}).status_code==409
            state={'values':{'rotor-angle':52,'guards-visible':0},'camera':None,'expected_revision':1}
            saved=client.post(url+'/interaction-state',headers=headers,json=state)
            assert saved.status_code==200 and saved.json()['project']['revision']==1
            private=api.STORE.get('job',job['id'],api.STORE.list('project')[0]['owner'])
            assert private['_base_project']['exploration']==before['exploration']
            assert '_base_project' not in client.get('/api/jobs/'+job['id']).json()['job']
            client.portal.call(api.slot.release)
            assert started.wait(2)
            assert seen[0]['exploration']==before['exploration']
        finally:release.set()
        assert wait_job(client,job['id'])['status']=='completed'
        current=client.get(url).json()['project']
        assert current['revision']==2 and current['exploration']['values']==state['values']
        assert client.get(url+'/revisions/1').json()['project']['exploration']['values']==state['values']


def test_old_revision_cannot_recompute_restore_or_save_exploration(isolated,monkeypatch):
    monkeypatch.setattr('runtime.planner.plan',lambda *a,**kw:sample_proposal('fan').model_dump())
    with TestClient(api.app) as client:
        headers=bootstrap(client);before=editable(client,headers,'fan');url='/api/projects/'+before['id']
        response=client.post(url+'/recompute',headers=headers,json={'parameters':{'pitch':30},'expected_revision':1})
        assert response.status_code==200
        current=response.json()['project']
        for path,payload in (
            ('/recompute',{'parameters':{'pitch':20},'expected_revision':1}),
            ('/interaction-state',{'values':{'rotor-angle':90},'expected_revision':1}),
            ('/restore',{'revision':1,'expected_revision':1}),
        ):
            assert client.post(url+path,headers=headers,json=payload).status_code==409
        assert iterate(client,headers,before).status_code==409
        assert client.get(url).json()['project']==current
        assert len(api.STORE.list('revision'))==1
        # Legacy requests still capture the current revision before committing.
        assert client.post(url+'/recompute',headers=headers,json={'parameters':{'pitch':25}}).status_code==200


@pytest.mark.parametrize('outcome',['failed','needs_input','cancelled'])
def test_unfinished_iteration_preserves_current_project_and_history(isolated,monkeypatch,outcome):
    started=threading.Event()
    def plan(*args,cancelled,**kwargs):
        started.set()
        if outcome=='failed':raise ValueError('Synthetic planning failure')
        if outcome=='needs_input':return {'title':'需要补充','recipe':'diagram','needs_clarification':True,'question':'请补充目标'}
        assert cancelled.wait(3)
        return sample_proposal('projectile').model_dump()
    monkeypatch.setattr('runtime.planner.plan',plan)
    with TestClient(api.app) as client:
        headers=bootstrap(client);before=editable(client,headers);url='/api/projects/'+before['id']
        job=iterate(client,headers,before).json()['job'];assert started.wait(2)
        if outcome=='cancelled':client.post('/api/jobs/'+job['id']+'/cancel',headers=headers)
        assert wait_job(client,job['id'])['status']==outcome
        assert client.get(url).json()['project']==before
        assert not api.STORE.list('revision')


def test_iteration_inherits_image_and_history_is_session_private(isolated,monkeypatch):
    import base64
    import io
    from PIL import Image
    calls=[]
    def plan(*args,**kwargs):
        calls.append(kwargs)
        return {'title':'图片说明','recipe':'image','labels':['部件']}
    monkeypatch.setattr('runtime.planner.plan',plan)
    with TestClient(api.app) as client:
        headers=bootstrap(client)
        image=io.BytesIO();Image.new('RGB',(10,10)).save(image,format='PNG')
        asset=client.post('/api/assets',headers=headers,json={'data_url':'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()}).json()['asset_id']
        job=client.post('/api/jobs',headers=headers,json={'prompt':'看图','asset_id':asset,'request_key':uuid.uuid4().hex}).json()['job']
        ident=wait_job(client,job['id'])['project_id'];url='/api/projects/'+ident
        before=client.get(url).json()['project']
        job=iterate(client,headers,before).json()['job']
        assert wait_job(client,job['id'])['status']=='completed'
        after=client.get(url).json()['project']
        assert after['asset_id']==asset and calls[-1]['asset_path'].stem==asset
        assert next(item for item in after['scene']['objects'] if item['kind']=='image')['asset_id']==asset
        assert client.get(url+'/revisions/1').json()['project']['asset_id']==asset
        client.cookies.clear();other=bootstrap(client)
        assert client.get(url+'/revisions').status_code==404
        assert client.get(url+'/revisions/1').status_code==404
        assert client.post(url+'/restore',headers=other,json={'revision':1,'expected_revision':2}).status_code==404


def test_job_cas_rejects_late_result_without_overwriting_newer_scene(isolated,monkeypatch):
    started=threading.Event();release=threading.Event()
    def plan(*args,**kwargs):
        started.set();assert release.wait(3)
        return sample_proposal('projectile').model_dump()
    monkeypatch.setattr('runtime.planner.plan',plan)
    with TestClient(api.app) as client:
        headers=bootstrap(client);before=editable(client,headers);url='/api/projects/'+before['id']
        job=iterate(client,headers,before).json()['job'];assert started.wait(2)
        owner=api.STORE.list('project')[0]['owner']
        def change(project):project['title']='其他已保存版本';return project
        api.STORE.commit_project(before['id'],owner,1,change)
        release.set()
        result=wait_job(client,job['id'])
        assert result['status']=='failed' and '新版本' in result['message']
        current=client.get(url).json()['project']
        assert current['revision']==2 and current['title']=='其他已保存版本'
        assert len(api.STORE.list('revision'))==1


def test_store_commit_rolls_back_snapshot_and_sql_history_does_not_truncate(tmp_path):
    store=Store(tmp_path/'versions.sqlite3');ident=uuid.uuid4().hex
    original={'id':ident,'owner':'one','revision':1,'created':1,'updated':1,'title':'original','prompt':'goal'}
    store.put('project',original)
    with pytest.raises(RevisionConflict):store.commit_project(ident,'one',2,lambda current:current)
    assert store.get('project',ident,'one')==original and not store.list('revision')
    with store.connect() as db:
        db.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON records WHEN NEW.kind='project' BEGIN SELECT RAISE(ABORT,'synthetic write failure'); END")
    with pytest.raises(Exception,match='synthetic write failure'):
        store.commit_project(ident,'one',1,lambda current:current)
    assert store.get('project',ident,'one')==original and not store.list('revision')
    with store.connect() as db:db.execute('DROP TRIGGER fail_update')
    job={'id':uuid.uuid4().hex,'owner':'one','status':'queued','updated':1}
    store.put('job',job)
    with store.connect() as db:
        db.execute("CREATE TRIGGER fail_job BEFORE UPDATE ON records WHEN NEW.kind='job' BEGIN SELECT RAISE(ABORT,'synthetic completion failure'); END")
    with pytest.raises(Exception,match='synthetic completion failure'):
        store.commit_project(ident,'one',1,lambda current:current,completed_job={**job,'status':'completed'})
    assert store.get('project',ident,'one')==original and not store.list('revision')
    assert store.get('job',job['id'],'one')['status']=='queued'
    with store.connect() as db:db.execute('DROP TRIGGER fail_job')
    for revision in range(1,106):store.commit_project(ident,'one',revision,lambda current:current)
    for revision in range(1,110):
        store.put('revision',{'id':uuid.uuid4().hex,'owner':'two','project_id':ident,'revision':revision,'updated':99999})
    assert len(store.revisions(ident,'one'))==105
    assert store.revision(ident,1,'one')['id']==ident
    assert store.revisions(uuid.uuid4().hex,'one')==[]


def test_sample_cannot_replace_project_and_duplicate_request_is_idempotent(isolated,monkeypatch):
    calls=[]
    def plan(*args,**kwargs):calls.append(1);return sample_proposal('projectile').model_dump()
    monkeypatch.setattr('runtime.planner.plan',plan)
    with TestClient(api.app) as client:
        headers=bootstrap(client);before=editable(client,headers)
        assert iterate(client,headers,before,sample='fan').status_code==422
        request_key=uuid.uuid4().hex
        first=iterate(client,headers,before,request_key=request_key).json()['job']
        assert wait_job(client,first['id'])['status']=='completed'
        repeated=iterate(client,headers,before,request_key=request_key)
        assert repeated.status_code==202 and repeated.json()['job']['id']==first['id']
        assert len(calls)==1 and len(api.STORE.list('project'))==1 and len(api.STORE.list('revision'))==1
