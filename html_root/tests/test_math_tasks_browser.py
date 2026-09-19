"""Real static/Vue UI with deterministic task API, without model charges."""
import copy
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect
from logic.solution_engine import local_solution

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires UI servers')


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=','http://127.0.0.1:5173/'])
def test_handoff_parallel_jobs_result_and_navigation(base):
    solution=local_solution('x^2=1').model_dump()
    solution['task_goal']='求方程的实数解'
    jobs=[];submissions=[];saved=[]
    def route_api(route):
        method=route.request.method;path=route.request.url.split('/api/agent/tasks',1)[1]
        if method=='GET' and not path:
            route.fulfill(json={'items':jobs,'owner':'browser-student'});return
        if method=='POST' and not path:
            data=route.request.post_data_json;submissions.append(data)
            job={'id':str(len(jobs)+1),'title':'分步求解 $x^2=1$','problem':data['problem'],'context':data['context'],
                 'status':'running','message':'独立子任务并行，等待前置结果后继续。','completed':1,
                 'nodes':[{'title':'求实数解','goal':solution['task_goal'],'depends_on':[], 'status':'done','message':'解答已完成',
                     'render_status':'skipped','solution':copy.deepcopy(solution),'video':None},
                    {'title':'检验结论','goal':'代回检验','depends_on':[0],'status':'running','message':'正在生成分步解答',
                     'render_status':'pending'}]}
            jobs.insert(0,job);route.fulfill(status=202,json=job);return
        ident=path.strip('/').split('/')[0];job=next(j for j in jobs if j['id']==ident)
        if path.endswith('/cancel'):
            job['status']='cancelled';job['nodes'][1]['status']='cancelled'
        route.fulfill(json=job)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1050})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/agent/tasks**',route_api)
        def save(route):
            saved.append(route.request.post_data_json)
            route.fulfill(json={'status':'success','id':42,'username':'browser-student'})
        page.route('**/api/formulas/solutions',save)
        page.goto(base+'calculate',wait_until='domcontentloaded')
        page.locator('#tutor-problem').fill('已知f(x)=x^2。（1）定义域（2）值域（3）最小值')
        page.locator('[name=autoRender]').uncheck()
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_selector('.math-task-card')
        assert submissions[0]['problem'].endswith('（3）最小值')
        assert submissions[0]['auto_render'] is False
        assert not page.evaluate('window.StepTutor.getState().busy')
        first=page.locator('[data-job="1"]')
        first.locator('summary').click()
        # Poll refresh must not collapse the original question while reading it.
        page.evaluate("async()=>{const m=await import('/static/js/agent-task-board.js?v=20260919-tasks-1');await m.refreshTasks()}")
        assert first.locator('details').get_attribute('open') is not None
        page.locator('[data-task-new]').click()
        assert page.locator('[name=mathTaskMode]').is_checked()
        page.locator('#agent-prompt').fill('解方程 x^2-4=0')
        page.locator('#agent-submit-btn').click()
        expect(page.locator('.math-task-card')).to_have_count(2)
        first.locator('[data-task-cancel]').click()
        expect(first.locator('.math-task-badge')).to_have_text('已停止')
        assert page.locator('[data-job="2"] .math-task-badge').inner_text()=='处理中'
        page.locator('[data-job="2"] [data-task-read="0"]').click()
        page.wait_for_selector('.solution-reader[open]')
        assert '本次子目标' in page.locator('.reader-problem').inner_text()
        assert page.locator('[data-reader=save]').is_visible()
        page.locator('[data-reader=save]').click()
        expect(page.locator('[data-reader=save]')).to_have_text('已保存')
        assert len(saved)==1 and saved[0]['solution']['task_goal']=='求方程的实数解'
        assert page.locator('.solution-reader .katex-error').count()==0
        page.locator('[data-reader=open]').click()
        page.wait_for_selector('.tutor-result:not([hidden])')
        assert page.evaluate('window.StepTutor.getState().solution.task_goal')=='求方程的实数解'
        page.evaluate("window.showSection('agent')")
        page.wait_for_selector('.math-task-card')
        assert page.locator('.math-task-card').count()==2
        Path('tests/artifacts').mkdir(exist_ok=True)
        label='vue' if '5173' in base else 'static'
        page.locator('.assistant-thread').evaluate('(el)=>el.scrollTop=0')
        page.screenshot(path=f'tests/artifacts/math-tasks-{label}.png')
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#agent-prompt').scroll_into_view_if_needed()
        assert page.locator('#agent-submit-btn').bounding_box()['y']+page.locator('#agent-submit-btn').bounding_box()['height']<=844
        assert page.locator('.assistant-shell').evaluate('(el)=>el.scrollWidth<=el.clientWidth+2')
        assert page.locator('.math-task-board').evaluate('(el)=>el.scrollWidth<=el.clientWidth+2')
        page.screenshot(path=f'tests/artifacts/math-tasks-{label}-mobile.png')
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.screenshot(path=f'tests/artifacts/math-tasks-{label}-dark.png')
        page.reload(wait_until='domcontentloaded')
        expect(page.locator('.math-task-card')).to_have_count(2)
        assert not errors
        browser.close()


def test_partial_answer_routes_once_with_forced_decomposition():
    partial=local_solution('x^2=1').model_dump()
    partial.update(completion='partial',next_tasks=['拆解剩余目标'])
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page()
        calls=[]
        page.route('**/api/solve/stream',lambda r:r.fulfill(content_type='text/event-stream',body='data: '+__import__('json').dumps({'type':'complete','solution':partial})+'\n\n'))
        def tasks(route):
            if route.request.method=='POST':
                calls.append(route.request.post_data_json)
                route.fulfill(status=401,json={'detail':'请先登录'})
            else:route.fulfill(status=401,json={'detail':'请先登录'})
        page.route('**/api/agent/tasks**',tasks)
        page.goto('http://127.0.0.1:8000/?section=calculate',wait_until='domcontentloaded')
        page.locator('#tutor-problem').fill('复杂但较短的题目')
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_selector('.math-task-pending:not([hidden])')
        page.wait_for_function("document.querySelector('.math-task-feedback').textContent.includes('登录')")
        assert len(calls)==1 and calls[0]['force_decompose'] is True
        assert calls[0]['problem']=='复杂但较短的题目'
        browser.close()
