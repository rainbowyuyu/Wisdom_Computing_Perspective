from concurrent.futures import ThreadPoolExecutor
import json
import uuid

from fastapi.testclient import TestClient
import pytest

from server.builders import SAMPLES
from server.library import BUILTINS, MAX_ITEMS
from server.knowledge import MAX_PROJECTS, MAX_TOPICS
from server.storage import Store
from test_api import api, bootstrap, isolated


def save(client, headers, **changes):
    data = dict(title='速度关系', latex=r'v=\frac{s}{t}', note='匀速运动', tags=['力学', '运动'])
    data.update(changes)
    response = client.post('/api/library', headers=headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()['item']


def put_project(store, owner, **changes):
    item = dict(id=uuid.uuid4().hex, owner=owner, title='本地项目', prompt='考察抛体运动',
                proposal={'recipe': 'projectile'}, scene={'large_frames': ['not graph data'] * 1000})
    item.update(changes)
    store.put('project', item)
    return item


def test_formula_lifecycle_is_private_persistent_searchable_and_versioned(isolated, monkeypatch):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        saved = save(a, ah, note='匀速测试_100%', tags=['力学', '运动', ' 力学 '])
        assert saved['tags'] == ['力学', '运动']
        assert saved['revision'] == 1 and not saved['builtin']
        url = '/api/library/' + saved['id']
        assert a.patch(url, json={'expected_revision': 1, 'title': '无凭证'}).status_code == 403
        assert b.patch(url, headers=bh, json={'expected_revision': 1, 'title': '其他会话'}).status_code == 404
        assert not b.get('/api/library?scope=saved').json()['items']
        assert len(a.get('/api/library', params={'q': '测试_100%', 'scope': 'saved'}).json()['items']) == 1
        assert not a.get('/api/library', params={'q': "' OR 1=1 --", 'scope': 'saved'}).json()['items']
        assert len(a.get('/api/library', params={'q': '运动 匀速', 'scope': 'saved'}).json()['items']) == 1
        changed = a.patch(url, headers=ah, json={'expected_revision': 1, 'favorite': True, 'title': '修订标题'}).json()['item']
        assert changed['revision'] == 2 and changed['favorite']
        assert a.patch(url, headers=ah, json={'expected_revision': 1, 'latex': 'wrong'}).status_code == 409
        archived = a.patch(url, headers=ah, json={'expected_revision': 2, 'archived': True}).json()['item']
        assert archived['revision'] == 3
        assert not a.get('/api/library?scope=saved').json()['items']
        assert a.get('/api/library?scope=archived').json()['items'][0]['id'] == saved['id']
        monkeypatch.setattr(api, 'STORE', Store(api.STORE.path))
        assert a.get('/api/library?scope=archived').json()['items'][0]['latex'] == saved['latex']
        assert a.patch(url, headers=ah, json={'expected_revision': 3, 'archived': False}).status_code == 200
        restored = a.get('/api/library?scope=saved').json()['items'][0]
        assert restored['title'] == '修订标题' and restored['favorite'] and restored['revision'] == 4


def test_formula_project_links_require_current_owner_and_can_be_cleared(isolated):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        project = put_project(api.STORE, a.cookies.get(api.COOKIE))
        saved = save(a, ah, project_id=project['id'])
        response = b.post('/api/library', headers=bh, json={'latex': 'x', 'project_id': project['id']})
        assert response.status_code == 404
        assert not b.get('/api/library?scope=saved').json()['items']
        other = save(b, bh)
        assert b.patch('/api/library/'+other['id'], headers=bh, json={'expected_revision': 1, 'project_id': project['id']}).status_code == 404
        cleared = a.patch('/api/library/'+saved['id'], headers=ah, json={'expected_revision': 1, 'project_id': None})
        assert cleared.status_code == 200 and cleared.json()['item']['project_id'] is None


def test_import_legacy_export_roundtrip_and_duplicate_import_are_idempotent(isolated):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        old = dict(id=72, user_id='legacy-user', created_at='2024-01-02T10:10:10', latex='x+y=z', note='旧站备注',
                   solution_title=None, step_count=None, video_url=None)
        result = a.post('/api/library/import', headers=ah, json={'items': [old, old]})
        assert result.status_code == 201, result.text
        data = result.json()
        assert (data['imported'], data['skipped']) == (1, 1)
        item = data['items'][0]
        assert item['title'] == '旧站备注' and item['revision'] == 1
        assert item['id'] != '72' and item['id'] == data['items'][1]['id']
        assert 'user_id' not in item and 'owner' not in item
        changed = a.patch('/api/library/'+item['id'], headers=ah, json={'expected_revision': 1, 'favorite': True, 'archived': True})
        assert changed.status_code == 200
        again = a.post('/api/library/import', headers=ah, json={'items': [old]}).json()
        assert (again['imported'], again['skipped']) == (0, 1)
        assert again['items'][0]['favorite'] and again['items'][0]['archived']
        exported = a.get('/api/library/export')
        assert 'attachment' in exported.headers['content-disposition']
        portable = exported.json()
        assert len(portable['items']) == 1
        assert not {'id', 'owner', 'builtin', 'revision', 'created', 'updated'} & portable['items'][0].keys()
        copied = b.post('/api/library/import', headers=bh, json=portable)
        assert copied.status_code == 201 and copied.json()['imported'] == 1
        assert b.get('/api/library/export').json() == portable
        assert a.post('/api/library/import', headers=ah, json=portable).json()['imported'] == 0


def test_empty_export_roundtrip_and_atomic_batch_ownership_validation(isolated):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        empty = a.get('/api/library/export').json()
        assert a.post('/api/library/import', headers=ah, json=empty).json()['imported'] == 0
        foreign = put_project(api.STORE, b.cookies.get(api.COOKIE))
        data = {'items': [{'latex': 'x'}, {'latex': 'y', 'project_id': foreign['id']}]}
        assert a.post('/api/library/import', headers=ah, json=data).status_code == 404
        assert not a.get('/api/library?scope=saved').json()['items']
        assert not b.get('/api/library?scope=saved').json()['items']


@pytest.mark.parametrize('changes', [
    {'latex': ' '}, {'latex': 'x'*4001}, {'title': 't'*121}, {'note': 'n'*2001},
    {'tags': ['t']*9}, {'tags': ['t'*25]}, {'tags': [' ']}, {'tags': ['a\n']},
    {'project_id': '../secret'}, {'owner': 'another-session'}, {'favorite': 'true'},
    {'latex': '\u0000'}, {'latex': '\ud800'},
])
def test_formula_input_is_bounded_and_strict(isolated, changes):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        response = client.post('/api/library', headers={**headers, 'Content-Type': 'application/json'}, content=json.dumps({'latex': 'x', **changes}))
        assert response.status_code == 422, response.text
        assert not client.get('/api/library?scope=saved').json()['items']


def test_import_and_patch_reject_invalid_or_solution_records_without_partial_changes(isolated):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        for payload in [
            {'items': [{'latex': 'x'}, {'latex': 'y', 'solution_title': '完整题解'}]},
            {'items': [{'latex': 'x', 'owner': 'foreign'}]},
            {'items': [{'latex': 'x'}]*(MAX_ITEMS+1)},
            {'items': [{'latex': 'x'}], 'version': 2},
        ]:
            assert client.post('/api/library/import', headers=headers, json=payload).status_code == 422
        assert not client.get('/api/library?scope=saved').json()['items']
        item = save(client, headers)
        for patch in [dict(title='missing version'), dict(expected_revision=1), dict(expected_revision=True, title='bad'),
                      dict(expected_revision=1, latex=None), dict(expected_revision=1, tags=None), dict(expected_revision=1, tags=[' '])]:
            assert client.patch('/api/library/'+item['id'], headers=headers, json=patch).status_code == 422
        assert client.get('/api/library?scope=saved').json()['items'][0]['revision'] == 1
        assert client.get('/api/library', params={'q': 'q'*201}).status_code == 422
        assert client.get('/api/library?scope=unknown').status_code == 422


def test_import_quota_rolls_back_and_allows_existing_duplicates(isolated, monkeypatch):
    monkeypatch.setattr('server.library.MAX_ITEMS', 3)
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        old = save(client, headers)
        payload = {'items': [{'latex': 'new-a'}, {'latex': 'new-b'}, {'latex': 'new-c'}]}
        assert client.post('/api/library/import', headers=headers, json=payload).status_code == 409
        assert [item['id'] for item in client.get('/api/library?scope=saved').json()['items']] == [old['id']]
        for latex in ('a', 'b'):
            save(client, headers, latex=latex)
        exported = client.get('/api/library/export').json()
        result = client.post('/api/library/import', headers=headers, json=exported)
        assert result.status_code == 201 and result.json()['imported'] == 0
        assert result.json()['skipped'] == 3
        assert client.post('/api/library', headers=headers, json={'latex': 'extra'}).status_code == 409


def test_concurrent_formula_edits_have_one_winner(isolated):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        item = save(client, headers)
        def change(title):
            return client.patch('/api/library/'+item['id'], headers=headers, json={'expected_revision': 1, 'title': title})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(change, ['编辑甲', '编辑乙']))
        assert sorted(result.status_code for result in results) == [200, 409]
        current = client.get('/api/library?scope=saved').json()['items'][0]
        assert current['revision'] == 2
        assert current['title'] == next(result.json()['item']['title'] for result in results if result.status_code == 200)


def test_knowledge_graph_is_private_bounded_connected_and_does_not_load_scenes(isolated, monkeypatch):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        ah, bh = bootstrap(a), bootstrap(b)
        owner = a.cookies.get(api.COOKIE)
        for i in range(MAX_PROJECTS+2):
            project = put_project(api.STORE, owner, title=f'作品 {i}')
        foreign = put_project(api.STORE, b.cookies.get(api.COOKIE), title='他人的私密作品')
        saved = save(a, ah, title='我的关联公式', project_id=project['id'])
        archived = save(a, ah, title='已归档不进图谱', archived=True)
        other = save(b, bh, title='私密公式')
        original_list = api.STORE.list
        def metadata_only(kind, *args, **kwargs):
            assert kind != 'project', 'Graph must not deserialize all project scenes'
            return original_list(kind, *args, **kwargs)
        monkeypatch.setattr(api.STORE, 'list', metadata_only)
        graph = a.get('/api/knowledge').json()
        nodes = {node['id']: node for node in graph['nodes']}
        assert len(nodes) == len(graph['nodes'])
        assert graph['omitted']['projects'] == 2
        assert sum(node['kind'] == 'project' for node in nodes.values()) == MAX_PROJECTS
        assert sum(node['kind'] == 'topic' for node in nodes.values()) <= MAX_TOPICS
        assert 'project:'+foreign['id'] not in nodes
        assert 'formula:'+other['id'] not in nodes
        assert 'formula:'+archived['id'] not in nodes
        assert nodes['formula:'+saved['id']]['latex'] == saved['latex']
        assert nodes['formula:'+saved['id']]['project_id'] == project['id']
        assert any(link['source'] == 'formula:'+saved['id'] and link['target'] == 'project:'+project['id'] for link in graph['links'])
        assert all(link['source'] in nodes and link['target'] in nodes for link in graph['links'])
        allowed = {'create', 'samples', 'library', 'projects', 'input-text', 'input-formula', 'input-image', 'provider', 'versions', 'export', 'jobs', 'help',
                   'settings', 'learning', 'course-packs', 'achievements', 'releases', 'tutorial', 'sketch', 'search'}
        assert all(node['action']['id'] in allowed for node in nodes.values() if node['action']['type'] == 'navigate')
        assert {node['action']['id'] for node in nodes.values() if node['action']['type'] == 'sample'} == {s['id'] for s in SAMPLES}
        assert 'large_frames' not in str(graph)


def test_builtin_catalog_is_readonly_scoped_to_real_samples_and_not_an_assessment(isolated):
    with TestClient(api.app) as client:
        headers = bootstrap(client)
        result = client.get('/api/library?scope=builtin').json()
        assert len(result['items']) == len(BUILTINS) == 16
        samples = {sample['id'] for sample in SAMPLES}
        assert all(item['sample'] is None or item['sample'] in samples for item in result['items'])
        assert all(item['sample_note'] for item in result['items'] if item['sample'])
        assert all(set(topic) == {'id', 'label', 'count'} for topic in result['topics'])
        derivative = next(item for item in result['items'] if item['id'] == 'builtin-sine-derivative')
        assert derivative['sample'] is None
        assert client.patch('/api/library/'+derivative['id'], headers=headers, json={'expected_revision': 1, 'latex': 'bad'}).status_code == 404
        assert not client.get('/api/library?scope=saved').json()['items']


def test_full_library_roundtrip_large_body_guard_and_read_authentication(isolated):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        assert a.get('/api/library').status_code == 401
        assert a.get('/api/knowledge').status_code == 401
        ah, bh = bootstrap(a), bootstrap(b)
        data = {'items': [{'latex': f'x={i}', 'note': '完整导出', 'favorite': i % 2 == 0, 'archived': i % 3 == 0} for i in range(MAX_ITEMS)]}
        assert a.post('/api/library/import', headers=ah, json=data).json()['imported'] == MAX_ITEMS
        portable = a.get('/api/library/export').json()
        copied = b.post('/api/library/import', headers=bh, json=portable)
        assert copied.status_code == 201 and copied.json()['imported'] == MAX_ITEMS
        assert {item['latex'] for item in b.get('/api/library/export').json()['items']} == {item['latex'] for item in data['items']}
        oversized = ' ' * 6_000_001 + '{"items": []}'
        assert a.post('/api/library/import', headers={**ah, 'Content-Type': 'application/json'}, content=oversized).status_code == 413
