"""Real account-scoped persistence for the assistant's reusable outputs."""
import pytest
from fastapi.testclient import TestClient
from main import app
from test_solution_library import accounts


@pytest.mark.parametrize('resource,payload', [
    ('animation_scripts', {'note':'动画测试', 'code':'from manim import *\nclass GenScene(Scene):\n    def construct(self):\n        self.wait(1)'}),
    ('agent_templates', {'name':'解题模板','prompt':'解方程 x^2=1','steps':[{'section':'calculate','formula':'x^2=1','trigger':'generate'}]}),
])
def test_assistant_outputs_require_session_and_isolate_accounts(accounts, resource, payload):
    users, sessions = accounts
    base = '/api/' + resource
    with TestClient(app) as client:
        assert client.post(base+'/save', json={**payload,'username':users[0]}).status_code == 401
        client.cookies.set('auth_session', sessions[0])
        saved = client.post(base+'/save', json={**payload,'username':users[0]})
        assert saved.status_code == 200, saved.text
        ident = saved.json()['id']
        assert client.get(base+'/get',params={'id':ident,'username':users[0]}).json()['data']
        if resource=='animation_scripts':
            # MySQL may report zero changed rows when saving an unchanged script.
            for _ in range(2):
                assert client.put(base+'/update',json={**payload,'username':users[0],'id':ident}).status_code==200
        client.cookies.set('auth_session', sessions[1])
        assert client.get(base+'/list',params={'username':users[0]}).status_code == 403
        assert client.get(base+'/get',params={'id':ident,'username':users[0]}).status_code == 403
        assert client.get(base+'/get',params={'id':ident,'username':users[1]}).status_code == 404
        if resource=='animation_scripts':
            assert client.put(base+'/update',json={**payload,'username':users[1],'id':ident}).status_code==404
        assert client.delete(base+'/delete',params={'id':ident,'username':users[0]}).status_code == 403
        client.cookies.set('auth_session',sessions[0])
        assert client.delete(base+'/delete',params={'id':ident,'username':users[0]}).status_code == 200
        assert client.get(base+'/get',params={'id':ident,'username':users[0]}).status_code == 404
