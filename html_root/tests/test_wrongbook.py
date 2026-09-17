import json
import os
from pathlib import Path
from datetime import datetime,timezone
import pytest
from fastapi.testclient import TestClient
from main import app
from app.database import transaction,backfill_legacy,apply_migrations
from test_solution_library import accounts,payload
from test_teaching import teaching_page,live_library_server

BASE='/api/wrongbook'


def body():return {'title':'二次方程订正','problem':r'解方程 $x^2-5x+6=0$','answer':r'$x=2$ 或 $x=3$','note':'忘记检验根','tags':['方程','代数'],'difficulty':2}


def test_wrongbook_crud_review_revision_isolation_and_cascade(accounts):
    users,sessions=accounts
    with TestClient(app) as c:
        assert c.get(BASE+'/list',params={'username':users[0]}).status_code==401
        assert c.post(BASE+'/add',json={**body(),'username':users[0]}).status_code==401
        c.cookies.set('auth_session',sessions[0])
        assert c.post(BASE+'/add',json={**body(),'username':users[1]}).status_code==403
        saved=c.post(BASE+'/add',json=body());assert saved.status_code==200,saved.text
        ident=saved.json()['id'];path=BASE+'/'+str(ident)
        assert c.post(BASE+'/add',json=body()).json()['id']==ident
        listing=c.get(BASE+'/list').json();assert listing['total']==1 and listing['stats']['due']==1
        assert c.get(BASE+'/list',params={'q':'x^2','tag':'代数'}).json()['total']==1
        assert c.get(BASE+'/list',params={'q':'%'}).json()['total']==0
        record=c.get(path).json()['data'];assert record['problem']==body()['problem']
        record['note']='已完成验根'
        assert c.put(path,json=record).json()['revision']==2
        assert c.put(path,json=record).status_code==409
        for revision,grade in [(2,'good'),(3,'mastered'),(4,'again')]:
            r=c.post(path+'/review',json={'revision':revision,'grade':grade,'note':'复习心得'});assert r.status_code==200,r.text
            assert c.post(path+'/review',json={'revision':revision,'grade':grade}).status_code==409
        result=c.get(path).json()['data'];assert result['review_count']==3 and len(result['reviews'])==3
        assert result['interval_days']==1 and result['status']=='reviewing'
        assert datetime.fromisoformat(result['next_review_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)
        assert c.get(BASE+'/list?status=due').json()['total']==0
        assert len(c.get(BASE+'/export').json()['reviews'])==3
        c.cookies.set('auth_session',sessions[1])
        assert c.get(BASE+'/list').json()['total']==0
        assert c.get(BASE+'/list',params={'username':users[0]}).status_code==403
        assert c.get(path).status_code==404
        assert c.put(path,json=record).status_code==404
        assert c.post(path+'/review',json={'revision':5,'grade':'good'}).status_code==404
        assert c.delete(path).status_code==404
        c.cookies.set('auth_session',sessions[0]);assert c.delete(path).status_code==200
        with transaction() as (_,q):
            q.execute('SELECT COUNT(*) AS n FROM learning_wrongbook_reviews WHERE entry_id=%s',(ident,));assert q.fetchone()['n']==0
            q.execute('SELECT COUNT(*) AS n FROM learning_wrongbook_tags WHERE entry_id=%s',(ident,));assert q.fetchone()['n']==0


def test_legacy_update_and_agent_wrongbook_route(accounts):
    with TestClient(app) as c:
        c.cookies.set('auth_session',accounts[1][0]);ident=c.post(BASE+'/add',json=body()).json()['id']
        assert c.put(BASE+'/update',json={'id':ident,'username':accounts[0][1],'note':'越权'}).status_code==403
        assert c.put(BASE+'/update',json={'id':ident,'note':'兼容旧入口'}).status_code==200
        assert c.get(BASE+'/'+str(ident)).json()['data']['note']=='兼容旧入口'
        step=c.post('/api/agent/execute',json={'prompt':'打开错题本'}).json()['steps'][0]
        assert step['section']=='examples' and step['examples_filter']=='wrongbook'


def test_wrongbook_snapshot_survives_original_deletion_and_legacy_backfill(accounts):
    users,sessions=accounts
    with TestClient(app) as c:
        c.cookies.set('auth_session',sessions[0]);source=payload()
        fid=c.post('/api/formulas/solutions',json=source).json()['id']
        persisted=c.get('/api/formulas/solutions/'+str(fid)).json()['data']['solution']
        record={**body(),'source_type':'solution','snapshot':source,'formula_id':fid}
        ident=c.post(BASE+'/add',json=record).json()['id']
        assert c.delete('/api/formulas/solutions/'+str(fid)).status_code==200
        entry=c.get(BASE+'/'+str(ident)).json()['data']
        assert entry['formula_id'] is None
        for actual,expected in zip(entry['snapshot']['solution']['steps'],persisted['steps']):
            assert actual['formula']==expected['formula'] and actual['explanation']==expected['explanation']
            for a,b in zip(actual['visual']['curves'],expected['visual']['curves']):
                for point,original in zip(a['points'],b['points']):assert point==pytest.approx(original,abs=1e-12)
        with transaction() as (_,q):
            q.execute('INSERT INTO user_wrongbook(user_id,video_id,title,time_sec,note) VALUES(%s,%s,%s,%s,%s)',(users[0],'legacy-video','旧错题',12,r'订正 $x^2$'))
            legacy=q.lastrowid;backfill_legacy(q);backfill_legacy(q)
            q.execute('SELECT COUNT(*) AS n FROM learning_wrongbook WHERE legacy_id=%s',(legacy,));assert q.fetchone()['n']==1
            q.execute('DELETE FROM user_wrongbook WHERE id=%s',(legacy,))
        assert c.get(BASE+'/list').json()['total']==2
        apply_migrations();apply_migrations()
        assert c.get(BASE+'/list').json()['total']==2


def test_username_change_keeps_learning_records(accounts):
    users,sessions=accounts;newname=users[0]+'_new'
    with TestClient(app) as c:
        c.cookies.set('auth_session',sessions[0]);ident=c.post(BASE+'/add',json=body()).json()['id']
        formula=c.post('/api/formulas/solutions',json=payload()).json()['id']
        pack=c.post('/api/examples/course-packs',json={'name':'改名后仍可阅读','video_ids':[]}).json()['id']
        changed=False
        try:
            response=c.put('/api/user/username',json={'new_username':newname,'password':'Library-QA-test-password'})
            assert response.status_code==200,response.text;changed=True
            assert c.get(BASE+'/'+str(ident)).status_code==200
            assert c.get('/api/formulas/solutions/'+str(formula)).status_code==200
            assert c.get('/api/examples/course-packs/'+str(pack)).status_code==200
        finally:
            if changed:assert c.put('/api/user/username',json={'new_username':users[0],'password':'Library-QA-test-password'}).status_code==200


def test_wrongbook_browser_create_review_edit_search_and_delete(teaching_page):
    page,origin,kind=teaching_page
    page.locator('[data-filter=wrongbook]').click();page.wait_for_selector('[data-wb-new]')
    page.locator('[data-wb-new]').click();page.wait_for_selector('.wrongbook-editor')
    form=page.locator('.wrongbook-editor');form.locator('[name=title]').fill('方程错题测试')
    form.locator('[name=problem]').fill(r'解方程 $x^2-5x+6=0$');form.locator('[name=answer]').fill(r'$x=2,3$')
    form.locator('[name=note]').fill('需要验根');form.locator('[name=tags]').fill('方程,代数')
    form.locator('[data-wb-preview]').click();page.wait_for_selector('.wrongbook-preview .katex')
    form.locator('[type=submit]').click();page.wait_for_selector('.wrongbook-reader')
    assert page.locator('[data-math=problem] .katex').count()==1
    page.locator('[data-wb-close]').click();page.locator('[data-wb-review]').click()
    page.wait_for_selector('.wrongbook-reader');assert not page.locator('.wrongbook-answer').evaluate('e=>e.open')
    page.locator('.wrongbook-answer summary').click();page.locator('.wrongbook-review textarea').fill('已理解因式分解')
    page.locator('[data-grade=good]').click();page.wait_for_function("document.querySelector('.course-status')?.textContent.includes('复习已记录')")
    page.locator('.wrongbook-history summary').click()
    assert '基本掌握' in page.locator('.wrongbook-history').inner_text()
    page.locator('[data-wb-close]').click();page.locator('[data-wb-open]').click();page.locator('[data-wb-edit]').click()
    page.wait_for_selector('.wrongbook-editor');page.locator('[name=note]').fill('修改后：验根并比较两种解法')
    page.locator('.wrongbook-editor [type=submit]').click();page.wait_for_selector('.wrongbook-reader')
    assert '修改后' in page.locator('[data-math=note]').inner_text()
    page.locator('[data-wb-close]').click()
    with page.expect_download() as download:page.locator('[data-wb-export]').click()
    content=json.loads(Path(download.value.path()).read_text(encoding='utf-8'));assert len(content['data'])==1 and len(content['reviews'])==1
    page.reload();page.wait_for_selector('[data-filter=wrongbook]');page.locator('[data-filter=wrongbook]').click();page.wait_for_selector('.wrongbook-card')
    page.locator('.wrongbook-search input').fill('不存在的题');page.locator('.wrongbook-search [type=submit]').click();page.wait_for_selector('.wrongbook-cards .course-empty')
    page.locator('.wrongbook-search input').fill('方程');page.locator('.wrongbook-search [type=submit]').click();page.wait_for_selector('.wrongbook-card')
    page.screenshot(path=f'tests/artifacts/wrongbook-{kind}.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    tab=page.locator('[data-filter=wrongbook]').bounding_box();assert tab['x']>=0 and tab['x']+tab['width']<=390
    page.screenshot(path=f'tests/artifacts/wrongbook-mobile-{kind}.png',full_page=True)
    page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
    page.locator('.wrongbook-host').screenshot(path=f'tests/artifacts/wrongbook-dark-{kind}.png')
    page.locator('[data-wb-open]').click();page.on('dialog',lambda d:d.accept());page.locator('[data-wb-delete]').click()
    page.wait_for_selector('.wrongbook-dialog',state='detached');page.wait_for_selector('.wrongbook-cards .course-empty')


def test_wrongbook_video_and_graph_connection(teaching_page):
    page,origin,kind=teaching_page
    page.locator('.video-card').first.click();page.wait_for_function("document.querySelector('#example-video-player').readyState>=2",timeout=45000)
    page.evaluate("document.querySelector('#example-video-player').pause();document.querySelector('#example-video-player').currentTime=2")
    page.locator('#video-mark-wrong-btn').click();page.wait_for_selector('.wrongbook-editor')
    page.locator('.wrongbook-editor [name=note]').fill('理解这一步变换')
    page.locator('.wrongbook-editor [type=submit]').click();page.wait_for_selector('[data-wb-video]')
    page.locator('[data-wb-close]').click();page.locator('#video-open-wrongbook-btn').click();page.wait_for_selector('.wrongbook-card')
    page.locator('[data-wb-open]').click();page.locator('[data-wb-video]').click();page.wait_for_selector('#video-modal.show')
    page.wait_for_function("document.querySelector('#example-video-player').currentTime>=1.9",timeout=45000)
    page.keyboard.press('Escape');page.wait_for_selector('#video-modal',state='hidden')
    page.evaluate("window.showSection('home')");page.wait_for_selector('.graph-explorer input')
    page.locator('.graph-explorer input').fill('错题本');page.locator('[data-graph-node=errorbook]').click();page.locator('[data-node-open=errorbook]').click()
    page.wait_for_selector('.wrongbook-card')


def test_solution_and_local_records_join_same_notebook(teaching_page):
    page,origin,kind=teaching_page
    page.evaluate("window.showSection('calculate')");page.wait_for_selector('.step-tutor textarea')
    page.locator('[name=autoRender]').uncheck();page.locator('.step-tutor textarea').fill('x^2-5*x+6=0')
    page.locator('.step-tutor button[type=submit]').click();page.wait_for_function('window.StepTutor.getState().solution && !window.StepTutor.getState().busy')
    page.locator('.tutor-more summary').click();page.locator('[data-action=wrongbook]').click();page.wait_for_selector('.wrongbook-editor')
    page.locator('.wrongbook-editor [name=note]').fill('对照因式分解复习');page.locator('.wrongbook-editor [type=submit]').click()
    page.wait_for_selector('.wrongbook-snapshot .katex');assert page.locator('.wrongbook-snapshot section').count()>=2
    page.locator('[data-wb-close]').click()
    page.evaluate("localStorage.setItem('wcp_examples_wrongbook_v1',JSON.stringify([{video_id:'legacy-test',time_sec:4,title:'本地旧错题',note:'旧错因'}]));window.openWrongbook()")
    page.wait_for_selector('[data-wb-import]');page.locator('[data-wb-import]').click();page.wait_for_function("document.querySelectorAll('.wrongbook-card').length===2")
    page.locator('[data-wb-import]').click();page.wait_for_timeout(300)
    assert page.locator('.wrongbook-card').count()==2
    page.evaluate("window.showSection('agent')");page.wait_for_selector('#agent-prompt')
    page.locator('#agent-prompt').fill('打开错题本');page.locator('#agent-submit-btn').click();page.wait_for_selector('.wrongbook-card')
    page.wait_for_function('!window.AgentWorkspace.getState().busy');assert page.evaluate('window.AgentWorkspace.getState().error')==''
