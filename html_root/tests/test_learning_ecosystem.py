"""Integration contracts for reusable course materials and private search."""
import json
import pytest
from fastapi.testclient import TestClient
from main import app
from test_solution_library import accounts, payload
from test_teaching import teaching_page, live_library_server

BASE='/api/examples/course-packs'

def test_resources_ownership_snapshots_revision_and_search(accounts):
    with TestClient(app) as c:
        c.cookies.set('auth_session',accounts[1][0])
        solution=payload()
        fid=c.post('/api/formulas/solutions',json=solution).json()['id']
        wid=c.post('/api/wrongbook/add',json={'title':'生态联动错题','problem':'求 x+1=2','answer':'x=1','note':'检查移项'}).json()['id']
        pack={'name':'生态联动课包','resources':[{'kind':'solution','source_id':fid},{'kind':'wrongbook','source_id':wid}]}
        result=c.post(BASE,json=pack);assert result.status_code==200,result.text
        pid=result.json()['id'];path=f'{BASE}/{pid}'
        record=c.get(path).json()['data']
        assert len(record['resources'])==2
        assert record['resources'][0]['snapshot']['solution']['id'] is None
        assert c.get(BASE).json()['data'][0]['resource_count']==2
        search=c.get('/api/search',params={'q':'生态联动'}).json()
        assert c.get('/api/search',params={'q':'%'}).json()['course_packs']==[]
        assert search['course_packs'][0]['id']==pid and search['wrongbook'][0]['id']==wid
        assert any(r['is_solution'] for r in c.get('/api/search',params={'q':'x^2'}).json()['formulas'])
        c.cookies.set('auth_session',accounts[1][1])
        assert c.get(path).status_code==404
        assert c.post(BASE,json=pack).status_code==404
        search=c.get('/api/search',params={'q':'生态联动'}).json()
        assert search['course_packs']==[] and search['wrongbook']==[]
        c.cookies.set('auth_session',accounts[1][0])
        assert c.post(BASE,json={**pack,'resources':[pack['resources'][0]]*2}).status_code==422
        # Old editors preserve materials when the optional field is absent.
        assert c.put(path,json={'name':pack['name'],'revision':1}).status_code==200
        assert len(c.get(path).json()['data']['resources'])==2
        assert c.put(path,json=record).status_code==409
        assert c.delete(f'/api/formulas/solutions/{fid}').status_code==200
        assert c.delete(f'/api/wrongbook/{wid}').status_code==200
        after=c.get(path).json()['data']
        assert all(r['source_id'] is None for r in after['resources'])
        assert after['resources'][0]['snapshot']==record['resources'][0]['snapshot']
        assert after['resources'][1]['snapshot']['note']=='检查移项'
        after['resources'].reverse()
        assert c.put(path,json=after).status_code==200
        assert c.get(path).json()['data']['resources'][0]['kind']=='wrongbook'
        # Snapshot-only transfer to another account cannot overwrite source formulas.
        c.cookies.set('auth_session',accounts[1][1])
        imported=c.post(BASE,json={**after,'name':'导入副本'});assert imported.status_code==200,imported.text
        resources=c.get(BASE+'/'+str(imported.json()['id'])).json()['data']['resources']
        assert all(r['source_id'] is None for r in resources)
        c.cookies.clear()
        search=c.get('/api/search',params={'q':'生态联动'}).json()
        assert search['course_packs']==[] and search['wrongbook']==[]


def test_review_agent_route(accounts):
    with TestClient(app) as c:
        c.cookies.set('auth_session',accounts[1][0])
        result=c.post('/api/agent/execute',json={'prompt':'复习错题'})
        assert result.status_code==200
        assert result.json()['steps'][0]['examples_action']=='review'


def test_course_wrongbook_search_and_resume_browser(teaching_page):
    page,origin,kind=teaching_page
    page.evaluate("""async () => {
      const post=async(url,data)=>(await fetch('/api'+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})).json();
      window.ecoPack=(await post('/examples/course-packs',{name:'生态联动课堂'})).id;
      window.ecoWrong=(await post('/wrongbook/add',{title:'生态联动练习',problem:'解方程 $x+1=2$',answer:'$x=1$',note:'移项改变符号'})).id;
      const W=await import('/static/js/wrongbook.js');await W.openWrongbookEntry(window.ecoWrong);
    }""")
    page.locator('[data-wb-pack]').click()
    page.locator('[data-material-pack]').click()
    page.wait_for_function("document.querySelector('[data-material-pack]')?.textContent==='已加入'")
    page.locator('.course-dialog:not(.wrongbook-dialog) [data-close]').click()
    search=page.locator('#nav-search-input');search.fill('生态联动')
    page.wait_for_selector('[data-search-result]')
    page.locator('#nav-search-dropdown button',has_text='生态联动课堂').click()
    page.wait_for_selector('.course-material .katex')
    assert page.locator('.course-material').count()==1
    page.locator('[data-material-source]').click()
    page.wait_for_selector('.wrongbook-answer:not([open])')
    page.locator('[data-grade=good]').click()
    page.wait_for_function("document.querySelector('.wrongbook-meta')?.textContent.includes('复习 1 次')")
    page.locator('[data-wb-solve]').click()
    page.wait_for_selector('.step-tutor')
    page.wait_for_function("window.StepTutor?.getState().draftProblem.includes('x+1=2')")
    assert page.locator('dialog[open]').count()==0
    page.screenshot(path=f'tests/artifacts/ecosystem-{kind}.png',full_page=True)


def test_solution_material_snapshot_and_import_browser(teaching_page):
    page,origin,kind=teaching_page
    source=payload()
    page.evaluate("""async record => {
      const response=await fetch('/api/formulas/solutions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(record)});
      window.ecoSolution=(await response.json()).id;
      const S=await import('/static/js/solution-library.js');await S.openSavedSolution(window.ecoSolution);
    }""",source)
    page.locator('[data-reader=pack]').click()
    page.locator('[data-material-new]').click()
    page.locator('.course-editor [name=name]').fill('题解快照课包')
    page.locator('.course-editor [type=submit]').click()
    page.wait_for_selector('.course-material')
    page.locator('.course-dialog').screenshot(path=f'tests/artifacts/ecosystem-materials-{kind}.png')
    with page.expect_download() as download:page.locator('[data-json]').click()
    exported=json.loads(__import__('pathlib').Path(download.value.path()).read_text(encoding='utf-8'))
    assert exported['resources'][0]['snapshot']['solution']['solution']['summary']==source['solution']['summary']
    assert len(exported['resources'][0]['snapshot']['solution']['solution']['steps'])==len(source['solution']['steps'])
    page.locator('[data-material-read]').click()
    page.wait_for_selector('.solution-reader .katex')
    page.locator('[data-reader=open]').click()
    page.wait_for_function("window.StepTutor?.getState().solution?.steps.length>0")
    assert page.locator('.course-dialog[open]').count()==0
    page.evaluate("""async pack => {
      const C=await import('/static/js/course-packs.js');await C.importCoursePack(new File([JSON.stringify(pack)],'pack.json',{type:'application/json'}));
    }""",exported)
    page.wait_for_selector('.course-material')
    assert page.locator('[data-material-source]').count()==0


def test_search_opens_saved_script_and_graph_starts_review(teaching_page):
    page,origin,kind=teaching_page
    script='from manim import *\n\nclass LinkedScene(Scene):\n    def construct(self):\n        self.play(Create(Circle()))\n'
    page.evaluate("""async code => {
      const me=await (await fetch('/api/user/me')).json();
      await fetch('/api/animation_scripts/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:me.username,note:'生态脚本搜索',code})});
    }""",script)
    page.locator('#nav-search-input').fill('生态脚本搜索')
    page.locator('#nav-search-dropdown button',has_text='生态脚本搜索').click()
    page.wait_for_function("window.monacoEditor?.getValue().includes('LinkedScene')",timeout=45000)
    page.evaluate("""async () => {
      await fetch('/api/wrongbook/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'图谱复习入口',problem:'x+2=3'})});
      const G=await import('/static/js/site-graph.js?v=20260917-ecosystem-6');
      await G.executeNodeAction(G.getNodeById('wrongbook-review'));
    }""")
    page.wait_for_selector('.wrongbook-answer:not([open])')
    assert '图谱复习入口' in page.locator('.wrongbook-reader').inner_text()
