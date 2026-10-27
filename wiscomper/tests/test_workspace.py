from concurrent.futures import ThreadPoolExecutor
import json
import time
import uuid

from fastapi.testclient import TestClient
import pytest

from server.storage import Store
from test_api import api, isolated, bootstrap


def create_study(client, headers, **updates):
    data = dict(kind='wrongbook', title='单摆复习', problem='小角度周期如何随摆长变化？', answer='周期正比于摆长平方根。', tags=['力学'])
    data.update(updates)
    response = client.post('/api/learning', headers=headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()['item']


def project(store, owner, **updates):
    data = dict(id=uuid.uuid4().hex, owner=owner, title='我的摆', prompt='研究摆动', revision=1,
                proposal={'recipe': 'pendulum'}, scene={'duration': 20, 'summary': '条件：固定摆长', 'frames': ['scene-heavy-data']*1000})
    data.update(updates)
    store.put('project', data)
    return data


def test_preferences_defaults_partial_updates_cas_and_privacy(isolated, monkeypatch):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        assert a.get('/api/preferences').status_code == 401
        ah, bh = bootstrap(a), bootstrap(b)
        defaults = a.get('/api/preferences').json()
        assert defaults['revision'] == 0 and defaults['preferences']['autoplay']
        assert defaults['preferences']['floating_x'] is None
        assert a.put('/api/preferences', json={'expected_revision': 0, 'preferences': {'theme': 'dark'}}).status_code == 403
        result = a.put('/api/preferences', headers=ah, json={'expected_revision': 0, 'preferences': {'theme': 'dark', 'floating_size': 80, 'floating_x': .4, 'floating_y': .6}})
        assert result.status_code == 200, result.text
        assert result.json()['revision'] == 1 and result.json()['preferences']['default_speed'] == 1
        assert a.put('/api/preferences', headers=ah, json={'expected_revision': 0, 'preferences': {'theme': 'light'}}).status_code == 409
        result = a.put('/api/preferences', headers=ah, json={'expected_revision': 1, 'preferences': {'autoplay': False}}).json()
        assert result['preferences']['theme'] == 'dark' and result['preferences']['floating_size'] == 80
        assert not result['preferences']['autoplay'] and result['revision'] == 2
        monkeypatch.setattr(api, 'STORE', Store(api.STORE.path))
        assert a.get('/api/preferences').json() == result
        assert b.get('/api/preferences').json() == defaults


@pytest.mark.parametrize('changes', [{'theme': 'custom'}, {'floating_size': 10}, {'floating_opacity': .1},
                                    {'floating_x': 100}, {'floating_y': -1}, {'autoplay': 'false'},
                                    {'default_speed': 9}, {'default_input': 'shell'}, {'unknown': True}])
def test_preferences_strict_bounds(isolated, changes):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        assert client.put('/api/preferences', headers=headers, json={'expected_revision': 0, 'preferences': changes}).status_code == 422
        assert client.get('/api/preferences').json()['revision'] == 0


def test_learning_links_timestamps_dedup_and_cas_archive(isolated):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        owner = api.STORE.session_owner(a.cookies.get(api.COOKIE))
        p = project(api.STORE, owner)
        data = dict(kind='favorite', title='收藏作品', project_id=p['id'], time_sec=3.5)
        response = a.post('/api/learning', headers=ah, json=data)
        assert response.status_code == 201, response.text
        item = response.json()['item']
        assert a.post('/api/learning', headers=ah, json=data).json()['duplicate']
        assert b.post('/api/learning', headers=bh, json=data).status_code == 404
        assert a.post('/api/learning', headers=ah, json={**data, 'time_sec': 21}).status_code == 422
        assert a.post('/api/learning', headers=ah, json={'kind': 'note', 'title': '无关联时间', 'time_sec': 3}).status_code == 422
        assert b.get('/api/learning/'+item['id']).status_code == 404
        patch = {'expected_revision': 1, 'note': '我自己的理解', 'archived': True}
        assert a.patch('/api/learning/'+item['id'], headers=ah, json=patch).status_code == 200
        assert a.patch('/api/learning/'+item['id'], headers=ah, json=patch).status_code == 409
        assert not a.get('/api/learning').json()['items']
        assert a.get('/api/learning?status=archived').json()['items'][0]['note'] == '我自己的理解'
        assert a.patch('/api/learning/'+item['id'], headers=ah, json={'expected_revision': 2, 'archived': False}).status_code == 200
        assert a.get('/api/learning?q=理解').json()['items'][0]['id'] == item['id']


def test_review_schedule_real_counts_bounded_history_and_conflicts(isolated):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        item = create_study(client, headers)
        assert client.get('/api/learning?status=due').json()['stats']['due'] == 1
        review_url = '/api/learning/'+item['id']+'/review'
        result = client.post(review_url, headers=headers, json={'expected_revision': 1, 'grade': 'again', 'note': '还要再想'}).json()['item']
        assert result['review_count'] == 1 and result['next_review_at'] > time.time()+500
        assert result['status'] == 'reviewing' and result['reviews'][0]['note'] == '还要再想'
        assert client.post(review_url, headers=headers, json={'expected_revision': 1, 'grade': 'good'}).status_code == 409
        easy = client.post(review_url, headers=headers, json={'expected_revision': 2, 'grade': 'easy'}).json()['item']
        assert easy['status'] == 'mastered' and easy['next_review_at'] is None
        assert client.get('/api/learning?status=due').json()['items'] == []
        assert client.get('/api/learning?status=mastered').json()['items'][0]['id'] == item['id']
        owner = api.STORE.session_owner(client.cookies.get(api.COOKIE))
        saved = api.STORE.get('learning', item['id'], owner)
        saved['reviews'] = saved['reviews']*50
        saved['review_count'] = 100
        api.STORE.put('learning', saved)
        reviewed = client.post(review_url, headers=headers, json={'expected_revision': 3, 'grade': 'hard'}).json()['item']
        assert reviewed['review_count'] == 101 and len(reviewed['reviews']) == 100
        assert reviewed['status'] == 'reviewing' and reviewed['interval_days'] == 1
        assert 'reviews' not in client.get('/api/learning').json()['items'][0]
        assert client.patch('/api/learning/'+item['id'], headers=headers, json={'expected_revision': 4, 'archived': True}).status_code == 200
        assert client.post(review_url, headers=headers, json={'expected_revision': 5, 'grade': 'good'}).status_code == 409


def test_learning_import_roundtrip_is_portable_idempotent_and_not_fabricated_review_history(isolated):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        p = project(api.STORE, api.STORE.session_owner(a.cookies.get(api.COOKIE)))
        item = create_study(a, ah, project_id=p['id'], time_sec=10)
        a.post('/api/learning/'+item['id']+'/review', headers=ah, json={'expected_revision': 1, 'grade': 'easy'})
        exported = a.get('/api/learning/export').json()
        assert exported['items'][0]['project_id'] is None and exported['items'][0]['time_sec'] is None
        assert 'review_count' not in exported['items'][0]
        copied = b.post('/api/learning/import', headers=bh, json=exported)
        assert copied.status_code == 201 and copied.json()['imported'] == 1
        assert copied.json()['items'][0]['review_count'] == 0
        assert b.post('/api/learning/import', headers=bh, json=exported).json()['skipped'] == 1
        assert a.post('/api/learning/import', headers=ah, json=exported).json()['skipped'] == 1
        bad = {'format': 'wiscomper-learning', 'version': 1, 'items': [{'kind':'note','title':'should roll back'}, {'kind':'note','title':'foreign','project_id':p['id']}]}
        assert b.post('/api/learning/import', headers=bh, json=bad).status_code == 404
        assert len(b.get('/api/learning').json()['items']) == 1


def test_course_pack_order_ownership_export_portability_and_idempotence(isolated, monkeypatch):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        p = project(api.STORE, api.STORE.session_owner(a.cookies.get(api.COOKIE)))
        formula = a.post('/api/library', headers=ah, json={'title':'周期','latex':r'T=2\pi\sqrt{L/g}','note':'小角度'}).json()['item']
        learning = create_study(a, ah)
        data = {'title': '摆动的一节课', 'description':'观察与复习', 'lesson':{'audience':'高中','procedure':'先观察，后讨论'},
                'items':[{'kind':'sample','id':'pendulum'}, {'kind':'project','id':p['id'],'note':'观察3秒'},
                         {'kind':'formula','id':formula['id']}, {'kind':'learning','id':learning['id']}]}
        result = a.post('/api/course-packs', headers=ah, json=data)
        assert result.status_code == 201, result.text
        item = result.json()['item']
        assert [entry['kind'] for entry in item['items']] == ['sample','project','formula','learning']
        assert item['items'][1]['snapshot']['prompt'] == p['prompt']
        assert 'scene-heavy-data' not in str(item)
        assert a.get('/api/course-packs').json()['items'][0]['item_count'] == 4
        assert b.get('/api/course-packs/'+item['id']).status_code == 404
        assert b.post('/api/course-packs', headers=bh, json=data).status_code == 404
        url = '/api/course-packs/'+item['id']
        exported = a.get(url+'/export').json()
        assert [entry['id'] for entry in exported['pack']['items']] == ['pendulum', None, None, None]
        assert a.post('/api/course-packs/import', headers=ah, json=exported).json()['skipped'] == 1
        copied = b.post('/api/course-packs/import', headers=bh, json=exported)
        assert copied.status_code == 201 and copied.json()['imported'] == 1
        assert b.post('/api/course-packs/import', headers=bh, json=exported).json()['skipped'] == 1
        b_id = copied.json()['item']['id']
        assert b.get('/api/course-packs/'+b_id+'/export').json() == exported
        reversed_items = list(reversed(item['items']))
        assert a.patch(url, headers=ah, json={'expected_revision':1, 'items':reversed_items}).status_code == 200
        assert a.patch(url, headers=ah, json={'expected_revision':1, 'description':'stale'}).status_code == 409
        assert a.get(url).json()['item']['items'][0]['kind'] == 'learning'
        assert a.patch(url, headers=ah, json={'expected_revision':2, 'archived':True}).status_code == 200
        assert not a.get('/api/course-packs').json()['items']
        assert a.get('/api/course-packs?archived=true').json()['items'][0]['id'] == item['id']


def test_workspace_limits_and_validation_reject_control_characters_unknown_fields_and_oversize(isolated, monkeypatch):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        for body in [{'kind':'wrongbook','title':'empty problem'}, {'kind':'note','title':' '},
                     {'kind':'note','title':'bad','owner':'foreign'}, {'kind':'note','title':'bad','tags':['x']*9},
                     {'kind':'note','title':'bad','tags':['\n']}, {'kind':'note','title':'bad','note':'n'*4001},
                     {'kind':'note','title':'bad','sample_id':'nonexistent'}]:
            assert client.post('/api/learning',headers=headers,json=body).status_code in {404,422}
        for body in [{'title':' '}, {'title':'bad','items':[{'kind':'project','id':'foreign'}]},
                     {'title':'bad','items':[{'kind':'sample','id':'pendulum'}]*41},
                     {'title':'bad','items':[{'kind':'sample'}]}, {'title':'bad','lesson':{'duration':0}},
                     {'title':'bad','items':[{'kind':'project','snapshot':{'title':'a','script':'exec'}}]}]:
            assert client.post('/api/course-packs',headers=headers,json=body).status_code in {404,422}
        monkeypatch.setattr('server.workspace.MAX_LEARNING', 1)
        create_study(client, headers)
        assert client.post('/api/learning',headers=headers,json={'kind':'note','title':'full'}).status_code == 409
        monkeypatch.setattr('server.workspace.MAX_PACKS', 1)
        assert client.post('/api/course-packs',headers=headers,json={'title':'one'}).status_code == 201
        assert client.post('/api/course-packs',headers=headers,json={'title':'two'}).status_code == 409


def test_preferences_and_learning_survive_github_owner_migration(isolated):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        client.put('/api/preferences', headers=headers, json={'expected_revision':0,'preferences':{'theme':'dark'}})
        item = create_study(client, headers)
        sid = client.cookies.get(api.COOKIE)
        new_sid, csrf = uuid.uuid4().hex, uuid.uuid4().hex
        _, owner, identity = api.STORE.login_github(sid, '987654', {'id':987654,'login':'test-user','name':'Test'}, new_sid, csrf)
        client.cookies.set(api.COOKIE, new_sid)
        assert client.get('/api/preferences').json()['preferences']['theme'] == 'dark'
        assert client.get('/api/learning/'+item['id']).json()['item']['title'] == '单摆复习'
        result = client.put('/api/preferences', headers={'X-CSRF-Token':csrf}, json={'expected_revision':1,'preferences':{'autoplay':False}})
        assert result.status_code == 200, result.text
        assert api.STORE.list('preferences',owner)[0]['preferences']['theme'] == 'dark'
        assert not api.STORE.list('preferences',sid)


def test_actual_achievement_counts_and_release_provenance(isolated, monkeypatch):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        baseline = a.get('/api/achievements').json()
        assert not any(item['unlocked'] for item in baseline['items'])
        owner = api.STORE.session_owner(a.cookies.get(api.COOKIE))
        project(api.STORE,owner)
        api.STORE.put('job',dict(id=uuid.uuid4().hex,owner=owner,kind='export',status='failed'))
        api.STORE.put('job',dict(id=uuid.uuid4().hex,owner=owner,kind='export',status='completed'))
        project(api.STORE,api.STORE.session_owner(b.cookies.get(api.COOKIE)))
        original_list = api.STORE.list
        def no_projects(kind,*args,**kwargs):
            assert kind != 'project'
            return original_list(kind,*args,**kwargs)
        monkeypatch.setattr(api.STORE,'list',no_projects)
        result = a.get('/api/achievements').json()
        assert result['metrics']['projects'] == 1 and result['metrics']['exports'] == 1
        assert result['metrics']['formulas'] == 0 and result['metrics']['reviews'] == 0
        assert '不代表知识掌握' in result['note']
        releases = a.get('/api/releases').json()
        assert releases['items'][0]['version'] == releases['current']
        assert all(item.get('source') and '不是本工程' in item['source'] for item in releases['items'] if item['channel']=='legacy')


def test_concurrent_preference_writes_only_one_commits(isolated):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        def change(theme):
            return client.put('/api/preferences',headers=headers,json={'expected_revision':0,'preferences':{'theme':theme}})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(change,['dark','light']))
        assert sorted(response.status_code for response in responses) == [200,409]
        assert client.get('/api/preferences').json()['revision'] == 1


def test_course_pack_patch_preserves_existing_snapshot_and_validates_replacement(isolated):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        own = project(api.STORE, api.STORE.session_owner(a.cookies.get(api.COOKIE)))
        foreign = project(api.STORE, api.STORE.session_owner(b.cookies.get(api.COOKIE)))
        response = a.post('/api/course-packs',headers=ah,json={'title':'原始快照','items':[{'kind':'project','id':own['id']}]})
        pack = response.json()['item']; url = '/api/course-packs/'+pack['id']
        own['prompt'] = '源项目已经更新'
        api.STORE.put('project',own)
        changed = a.patch(url,headers=ah,json={'expected_revision':1,'description':'只改教案描述'}).json()['item']
        assert changed['items'][0]['snapshot']['prompt'] == '研究摆动'
        assert a.patch(url,headers=ah,json={'expected_revision':2,'items':[{'kind':'project','id':foreign['id'],'snapshot':{'title':'伪造可读快照'}}]}).status_code == 404
        assert a.get(url).json()['item']['revision'] == 2
        updated = a.patch(url,headers=ah,json={'expected_revision':2,'items':[{'kind':'project','id':own['id']}]}).json()['item']
        assert updated['items'][0]['snapshot']['prompt'] == '源项目已经更新'


def test_workspace_rejects_bad_utf8_and_large_imports_without_mutation(isolated):
    with TestClient(api.app) as client:
        headers = {**bootstrap(client),'Content-Type':'application/json'}
        for field in ('title','note'):
            body = {'kind':'note','title':'test',field:'\ud800'}
            assert client.post('/api/learning',headers=headers,content=json.dumps(body)).status_code == 422
        learning = ' '*5_000_001 + '{"format":"wiscomper-learning","version":1,"items":[]}'
        assert client.post('/api/learning/import',headers=headers,content=learning).status_code == 413
        pack = ' '*1_500_001 + '{"format":"wiscomper-course-pack","version":1,"pack":{"title":"oversized"}}'
        assert client.post('/api/course-packs/import',headers=headers,content=pack).status_code == 413
        assert not client.get('/api/learning').json()['items']
        assert not client.get('/api/course-packs').json()['items']


def test_portable_content_budgets_reject_whole_transaction(isolated, monkeypatch):
    monkeypatch.setattr('server.workspace.LEARNING_EXPORT_BUDGET', 900)
    monkeypatch.setattr('server.workspace.PACK_EXPORT_BUDGET', 900)
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        assert client.post('/api/learning',headers=headers,json={'kind':'note','title':'too large','note':'长'*500}).status_code == 409
        assert not client.get('/api/learning').json()['items']
        payload = {'format':'wiscomper-learning','version':1,'items':[{'kind':'note','title':str(i),'note':'long'*80} for i in range(3)]}
        assert client.post('/api/learning/import',headers=headers,json=payload).status_code == 409
        assert not client.get('/api/learning').json()['items']
        assert client.post('/api/course-packs',headers=headers,json={'title':'too large','description':'长'*500}).status_code == 409
        assert not client.get('/api/course-packs').json()['items']
