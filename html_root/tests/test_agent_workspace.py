import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from test_solution_library import accounts, live_library_server

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires Chrome and servers')
CODE='from manim import *\n\nclass GenScene(Scene):\n    def construct(self):\n        shape = Circle(color=PURPLE, fill_opacity=0.5)\n        self.play(Create(shape), run_time=0.3)\n        self.wait(0.3)\n'


@pytest.fixture(params=['static','vue'])
def workspace(live_library_server,request):
    from playwright.sync_api import sync_playwright
    origin,(users,sessions)=live_library_server
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_cookies([{'name':'auth_session','value':sessions[0],'url':origin}])
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_locator_handler(page.locator('#achievement-unlock-modal.show'),lambda overlay:overlay.locator('#achievement-unlock-close-x').click())
        if request.param=='vue':
            page.route('**/api/**',lambda route:route.fulfill(response=route.fetch(url=origin+urlsplit(route.request.url).path+('?' + urlsplit(route.request.url).query if urlsplit(route.request.url).query else ''))))
        page.goto(origin+'/?section=agent' if request.param=='static' else 'http://127.0.0.1:5173/agent',wait_until='domcontentloaded')
        page.wait_for_selector('.assistant-shell')
        yield page,origin,request.param
        assert not errors,errors
        browser.close()


def test_agent_solves_renders_saves_and_reads_real_record(workspace):
    page,origin,kind=workspace
    plan={'status':'success','steps':[
        {'section':'calculate','trigger':'generate','formula':'x^2-5*x+6=0','reply':'求解并保存这道方程。','save_to_formulas':True}]}
    page.route('**/api/agent/execute',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(plan)))
    page.locator('#agent-prompt').fill('解方程并保存到我的算式')
    page.locator('#agent-submit-btn').click()
    page.wait_for_function('window.AgentWorkspace.getState().result?.id && !window.AgentWorkspace.getState().busy',timeout=180000)
    assert page.locator('.assistant-plan li.done').count()==1
    ident=page.evaluate('window.AgentWorkspace.getState().result.id')
    record=page.request.get(origin+f'/api/formulas/solutions/{ident}').json()['data']
    assert record['video']['url'].endswith('.mp4')
    page.locator('[data-agent=result]').click();page.wait_for_selector('.solution-reader[open]')
    assert page.locator('.reader-video').get_attribute('src')==record['video']['url']
    page.locator('[data-reader=close]').click()
    page.screenshot(path=f'tests/artifacts/agent-complete-{kind}.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.screenshot(path=f'tests/artifacts/agent-mobile-{kind}.png',full_page=True)


def test_code_assistant_preview_conflict_apply_undo_and_render(workspace, accounts, monkeypatch):
    monkeypatch.setenv('WISDOM_CODE_RUNNERS', accounts[0][0])
    page,origin,kind=workspace
    page.evaluate("window.showSection('devtools')")
    page.wait_for_function("document.querySelector('#devtools')?.dataset.devInitialized")
    page.evaluate("window.switchDevTool('manim')")
    page.wait_for_function('!!window.monacoEditor',timeout=45000)
    original=page.evaluate('window.monacoEditor.getValue()')
    page.route('**/api/devtools/edit_code',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps({'status':'success','code':CODE,'summary':'绘制紫色圆','validation':'syntax_checked','keyframe_lines':[6]})))
    page.locator('#manim-ai-edit-input').fill('绘制紫色圆')
    page.locator('#manim-ai-edit-btn').click()
    page.wait_for_selector('.code-assistant-proposal')
    assert page.evaluate('window.monacoEditor.getValue()')==original
    page.locator('[data-code=preview]').click()
    page.wait_for_selector('.code-assistant-preview img',timeout=120000)
    assert '渲染成功' in page.locator('.code-assistant-status').inner_text()
    page.evaluate("window.monacoEditor.setValue(window.monacoEditor.getValue()+'\\n# manual edit')")
    page.locator('[data-code=apply]').click()
    assert '已发生变化' in page.locator('.code-assistant-status').inner_text()
    assert page.evaluate('window.monacoEditor.getValue()').endswith('# manual edit')
    page.evaluate('(code)=>window.monacoEditor.setValue(code)',original)
    page.locator('[data-code=apply]').click()
    assert page.evaluate('window.monacoEditor.getValue()')==CODE
    page.locator('[data-code=undo]').click()
    assert page.evaluate('window.monacoEditor.getValue()')==original
    page.locator('#manim-ai-edit-btn').click();page.wait_for_selector('.code-assistant-proposal')
    page.locator('[data-code=apply-run]').click()
    page.wait_for_function("document.querySelector('#dev-manim-video').getAttribute('src')",timeout=120000)
    page.wait_for_function("document.querySelector('.code-assistant-status').textContent.includes('视频已生成')")
    page.screenshot(path=f'tests/artifacts/code-assistant-complete-{kind}.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.screenshot(path=f'tests/artifacts/code-assistant-mobile-{kind}.png',full_page=True)


def test_agent_failure_stops_dependent_actions(workspace):
    page,_,_=workspace;calls=[]
    plan={'status':'success','steps':[{'section':'calculate','trigger':'generate','formula':'x^2=1'},{'section':'my-formulas','save_to_formulas':True}]}
    page.route('**/api/agent/execute',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(plan)))
    page.route('**/api/solve/stream',lambda route:route.fulfill(status=200,content_type='text/event-stream',body='data: {"type":"status","message":"interrupted"}\n\n'))
    page.on('request',lambda req:calls.append(req.url) if '/api/formulas/solutions' in req.url else None)
    page.locator('#agent-prompt').fill('失败后不要继续保存');page.locator('#agent-submit-btn').click()
    page.wait_for_function('window.AgentWorkspace.getState().error && !window.AgentWorkspace.getState().busy')
    assert page.locator('.assistant-plan li.error').count()==1
    assert page.locator('.assistant-plan li.pending').count()==1
    assert not calls
    assert page.locator('[data-agent=retry]').is_visible()


def test_agent_creates_runs_and_saves_script_across_navigation(workspace, accounts, monkeypatch):
    monkeypatch.setenv('WISDOM_CODE_RUNNERS', accounts[0][0])
    page,origin,kind=workspace
    # Different scene names occur in actual model replies. The browser must run them.
    code=CODE.replace('GenScene','SquareToCircle')
    plan={'status':'success','steps':[{'section':'devtools','devtool':'manim','devtool_action':'run','fill_manim_code':code}]}
    page.route('**/api/agent/execute',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(plan)))
    page.locator('#agent-prompt').fill('编写并运行动画');page.locator('#agent-submit-btn').click()
    page.wait_for_function('!window.AgentWorkspace.getState().busy',timeout=120000)
    assert not page.evaluate('window.AgentWorkspace.getState().error')
    assert page.locator('#dev-manim-video').get_attribute('src').endswith('.mp4')
    assert page.evaluate('window.monacoEditor.getValue()')==code
    page.locator('.ide-btn-save').click()
    page.locator('.studio-save-dialog input').fill('智能体动画')
    with page.expect_response('**/api/animation_scripts/save') as saved:
        page.locator('.studio-save-dialog button[type=submit]').click()
    ident=saved.value.json()['id']
    page.wait_for_selector('.studio-save-dialog',state='detached')
    username=page.request.get(origin+'/api/user/me').json()['username']
    assert page.request.get(origin+f'/api/animation_scripts/get?id={ident}&username={username}').json()['data']['code']==code
    page.evaluate("window.showSection('agent')")
    page.wait_for_selector('[data-agent=template]:visible')
    page.locator('[data-agent=template]').click()
    page.wait_for_function("document.querySelector('[data-agent=template]').textContent==='已存为模板'")
    assert len(page.request.get(origin+f'/api/agent_templates/list?username={username}').json()['data'])==1
    page.evaluate("document.documentElement.dataset.theme='dark'")
    page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    page.screenshot(path=f'tests/artifacts/agent-dark-{kind}.png',full_page=True)
    page.evaluate("window.showSection('devtools')")
    page.wait_for_function("document.querySelector('#devtools')?.dataset.devInitialized")
    page.evaluate("window.switchDevTool('manim')")
    page.wait_for_function('!!window.monacoEditor')
    assert page.evaluate('window.monacoEditor.getValue()')==code
    page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    page.screenshot(path=f'tests/artifacts/studio-dark-{kind}.png',full_page=True)


def test_agent_stop_retry_and_enter_preference(workspace):
    page,_,_=workspace
    # Keep a planner pending without using a timer in the application.
    page.route('**/api/agent/execute',lambda route:None)
    page.evaluate("localStorage.setItem('agent_enter_send','false');window.unrelatedCancelled=false;window.StepTutor={getState:()=>({busy:true}),cancel:()=>window.unrelatedCancelled=true}")
    page.locator('#agent-prompt').fill('打开我的算式')
    page.locator('#agent-prompt').press('Enter')
    assert not page.evaluate('window.AgentWorkspace.getState().busy')
    page.locator('#agent-prompt').press('Control+Enter')
    page.wait_for_function('window.AgentWorkspace.getState().busy')
    page.locator('[data-agent=stop]').click()
    assert not page.evaluate('window.AgentWorkspace.getState().busy')
    assert not page.evaluate('window.unrelatedCancelled')
    page.unroute('**/api/agent/execute')
    page.route('**/api/agent/execute',lambda route:route.fulfill(status=502,content_type='application/json',body='{"message":"暂时不可用"}'))
    page.locator('#agent-prompt').fill('再试一次');page.locator('#agent-submit-btn').click()
    page.wait_for_selector('[data-agent=retry]:visible')
    page.unroute('**/api/agent/execute')
    plan={'status':'success','steps':[{'section':'chat','reply':'服务已恢复'}]}
    page.route('**/api/agent/execute',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(plan)))
    page.locator('[data-agent=retry]').click()
    page.wait_for_function("window.AgentWorkspace.getState().status==='已回复'")
    assert '服务已恢复' in page.locator('.assistant-messages').inner_text()


def test_code_cancellation_and_latex_import_keep_user_content(workspace):
    page,_,kind=workspace
    page.evaluate("window.showSection('devtools')")
    page.wait_for_function("document.querySelector('#devtools')?.dataset.devInitialized")
    latex=r'\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}'
    page.evaluate('(latex)=>window.DevTools.fillLatexInDevtools(latex)',latex)
    assert page.locator('#dev-latex-source').input_value()==latex
    page.evaluate("window.DevTools.fillLatexInDevtools('<img src=x onerror=alert(1)>')")
    assert page.locator('#dev-latex-preview img').count()==0
    page.evaluate("window.switchDevTool('manim')")
    page.wait_for_function('!!window.monacoEditor')
    original=page.evaluate('window.monacoEditor.getValue()')
    page.route('**/api/devtools/edit_code',lambda route:None)
    page.locator('#manim-ai-edit-input').fill('修改圆的颜色')
    page.locator('#manim-ai-edit-btn').click()
    page.wait_for_selector('[data-code=stop]:visible')
    page.locator('[data-code=stop]').click()
    assert page.evaluate('window.monacoEditor.getValue()')==original
    assert page.locator('#manim-ai-edit-btn').is_enabled()
    page.route('**/api/devtools/render_keyframe',lambda route:None)
    page.locator('#btn-manim-keyframe').click()
    assert page.locator('#btn-manim-keyframe').inner_text()=='停止预览'
    page.locator('#btn-manim-keyframe').click()
    page.wait_for_function("document.querySelector('#dev-manim-log').textContent.includes('已停止预览')")
    assert not page.locator('#dev-manim-loading').is_visible()
    page.evaluate("document.documentElement.dataset.theme='dark'")
    page.set_viewport_size({'width':390,'height':844})
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.screenshot(path=f'tests/artifacts/studio-dark-mobile-{kind}.png',full_page=True)
