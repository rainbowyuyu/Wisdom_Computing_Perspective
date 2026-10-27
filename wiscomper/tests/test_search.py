from contextlib import contextmanager
import json
import uuid

from fastapi.testclient import TestClient
import pytest

from test_api import api, bootstrap, isolated  # noqa: F401


def put_record(store, owner, kind, **fields):
    value = dict(id=uuid.uuid4().hex, owner=owner, title='待搜索资料', updated=1, archived=False)
    value.update(fields)
    store.put(kind, value)
    return value


def test_search_requires_owner_and_returns_public_destinations(isolated):
    with TestClient(api.app) as client:
        assert client.get('/api/search').status_code == 401
        bootstrap(client)
        defaults = client.get('/api/search').json()
        assert defaults['items'] and defaults['limit'] == 24
        assert any(item['kind'] == 'feature' for item in defaults['items'])
        features = client.get('/api/search', params={'q': '悬浮球'}).json()['items']
        assert any(item['action'] == {'type': 'navigate', 'id': 'settings'} for item in features)
        for query, target in [('手写', 'sketch'), ('全站搜索', 'search')]:
            found = client.get('/api/search', params={'q': query}).json()['items']
            assert any(item['action'] == {'type': 'navigate', 'id': target} for item in found)
        formulas = client.get('/api/search', params={'q': '全反射'}).json()['items']
        assert any(item['action'] == {'type': 'formula', 'id': 'builtin-critical-angle'} for item in formulas)
        samples = client.get('/api/search', params={'q': '电机'}).json()['items']
        assert any(item['action'] == {'type': 'sample', 'id': 'model3d'} for item in samples)


@pytest.mark.parametrize('params', [{'q': 'x'*201}, {'limit': 0}, {'limit': 41}, {'limit': 'invalid'}])
def test_search_rejects_unbounded_inputs(isolated, params):
    with TestClient(api.app) as client:
        bootstrap(client)
        assert client.get('/api/search', params=params).status_code == 422


def test_private_search_is_owner_scoped_and_excludes_archived_records(isolated):
    with TestClient(api.app) as a, TestClient(api.app) as b:
        bootstrap(a), bootstrap(b)
        ao = api.STORE.session_owner(a.cookies.get(api.COOKIE))
        bo = api.STORE.session_owner(b.cookies.get(api.COOKIE))
        created = {}
        for kind in ['project', 'formula', 'learning', 'course-pack']:
            created[kind] = put_record(api.STORE, ao, kind, title=f'SAFFRON 私有 {kind}', note='自己的资料')
            put_record(api.STORE, bo, kind, title=f'saffron 其他用户 {kind}', note='foreign secret')
            put_record(api.STORE, ao, kind, title=f'saffron 已归档 {kind}', archived=True)
        result = a.get('/api/search', params={'q': 'saffron'}).json()
        assert len(result['items']) == 4
        assert {item['kind'] for item in result['items']} == set(created)
        for item in result['items']:
            assert item['action'] == {'type': item['kind'], 'id': created[item['kind']]['id']}
            assert item['id'] == f'{item["kind"]}:{created[item["kind"]]["id"]}'
            assert 'owner' not in item
        assert not a.get('/api/search', params={'q': 'foreign secret'}).json()['items']
        assert not b.get('/api/search', params={'q': '自己的资料'}).json()['items']


def test_search_uses_all_terms_casefold_and_content_beyond_result_preview(isolated):
    with TestClient(api.app) as client:
        bootstrap(client)
        owner = api.STORE.session_owner(client.cookies.get(api.COOKIE))
        project = put_record(api.STORE, owner, 'project', title='Straße 探索', prompt='前文'*1300 + 'needle 条件')
        put_record(api.STORE, owner, 'project', title='只有 STRASSE', prompt='无相关条件')
        response = client.get('/api/search', params={'q': '  STRASSE   needle  '}).json()
        assert [item['action']['id'] for item in response['items']] == [project['id']]
        assert len(response['items'][0]['description']) <= 240
        assert response['query'] == 'STRASSE   needle'
        note = put_record(api.STORE, owner, 'learning', title='分类学习', answer='维度审查', tags=['有限元'])
        result = client.get('/api/search', params={'q': '有限元 维度'}).json()['items']
        assert result[0]['action']['id'] == note['id']
        pack = put_record(api.STORE, owner, 'course-pack', title='教程文本', lesson={'procedure': '这是近似的适用边界'})
        result = client.get('/api/search', params={'q': '近似 适用边界'}).json()['items']
        assert result[0]['action']['id'] == pack['id']


def test_search_is_literal_json_data_not_sql_or_markup(isolated):
    with TestClient(api.app) as client:
        bootstrap(client)
        owner = api.STORE.session_owner(client.cookies.get(api.COOKIE))
        title = '<img src=x onerror="window.searchXss=1">'
        value = put_record(api.STORE, owner, 'learning', title=title, note='<script>alert(1)</script>')
        response = client.get('/api/search', params={'q': 'img'})
        assert response.headers['content-type'].startswith('application/json')
        result = response.json()['items']
        assert result[0]['title'] == title and result[0]['action']['id'] == value['id']
        for query in ["' OR 1=1 --", '%', 'unmatched-mystery-term']:
            assert client.get('/api/search', params={'q': query}).json()['items'] == []
        # Underscores occur literally in builtin LaTeX subscripts; they must
        # not act as SQL LIKE's any-character wildcard over private entries.
        underscore = client.get('/api/search', params={'q': '_'}).json()['items']
        assert all(item['kind'] == 'formula' for item in underscore)
        assert value['id'] not in {item['action']['id'] for item in underscore}


def test_limits_rank_recent_results_but_search_older_matching_records(isolated):
    with TestClient(api.app) as client:
        bootstrap(client)
        owner = api.STORE.session_owner(client.cookies.get(api.COOKIE))
        oldest = put_record(api.STORE, owner, 'project', title='oldest unique needle', updated=0)
        records = [put_record(api.STORE, owner, 'project', title=f'bounded match {i}', updated=100+i) for i in range(50)]
        found = client.get('/api/search', params={'q': 'oldest needle'}).json()['items']
        assert [item['action']['id'] for item in found] == [oldest['id']]
        found = client.get('/api/search', params={'q': 'bounded match', 'limit': 3}).json()
        assert len(found['items']) == 3 and found['has_more']
        assert found['items'][0]['action']['id'] == records[-1]['id']
        defaults = client.get('/api/search', params={'limit': 8}).json()['items']
        assert len(defaults) == 8 and sum(item['kind'] == 'feature' for item in defaults) == 2
        assert defaults[0]['action']['id'] == records[-1]['id']


def test_search_never_decodes_bulk_scenes_course_materials_or_review_histories(isolated, monkeypatch):
    with TestClient(api.app) as client:
        bootstrap(client)
        owner = api.STORE.session_owner(client.cookies.get(api.COOKIE))
        put_record(api.STORE, owner, 'project', title='metadata only', scene={'summary': '模型条件', 'frames': ['excluded-frame-secret']*4000})
        put_record(api.STORE, owner, 'learning', title='metadata only', note='资料摘要', reviews=[{'note': 'excluded-review-secret'}]*1000)
        put_record(api.STORE, owner, 'course-pack', title='metadata only', items=[{'snapshot': {'note': 'excluded-pack-secret'*500}}]*40)
        original = api.STORE.connect
        statements = []

        @contextmanager
        def traced_connect():
            with original() as db:
                db.set_trace_callback(statements.append)
                yield db

        monkeypatch.setattr(api.STORE, 'connect', traced_connect)
        monkeypatch.setattr(api.STORE, 'list', lambda *args, **kwargs: pytest.fail('Search must not load complete records.'))
        monkeypatch.setattr(api.STORE, 'get', lambda *args, **kwargs: pytest.fail('Search must not load complete records.'))
        result = client.get('/api/search', params={'q': 'metadata only'}).json()
        assert len(result['items']) == 3
        assert 'excluded-' not in json.dumps(result)
        for query in ['excluded-frame-secret', 'excluded-review-secret', 'excluded-pack-secret']:
            assert client.get('/api/search', params={'q': query}).json()['items'] == []
        assert not any('SELECT PAYLOAD' in sql.upper() for sql in statements)
