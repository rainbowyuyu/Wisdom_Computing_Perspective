"""Actual KaTeX and task controls; no provider calls or user data writes."""
import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from logic.solution_engine import local_solution

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local UI servers')
SYSTEM=r'\begin{aligned}&(3)\left\{\begin{array}{l}x_{1}-5x_{3}=1\\-x_{1}+x_{2}+6x_{3}=3\\2x_{1}+3x_{2}-7x_{3}=15\end{array}\right.\\&(5)\left\{\begin{array}{l}x_{1}+x_{2}+x_{3}+x_{4}=1\\2x_{1}+3x_{2}+4x_{3}+x_{4}=3\\3x_{1}+x_{2}-x_{3}+5x_{4}=1\end{array}\right.\end{aligned}'


@pytest.fixture(params=['static','vue'])
def ui(request):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/user/me',lambda r:r.fulfill(json={'username':'qa_retry_browser','email_verified':True}))
        page.route('**/api/agent/tasks',lambda r:r.fulfill(json={'items':[],'owner':'qa_retry_browser'}))
        page.route('**/api/solve/capabilities',lambda r:r.fulfill(json={'manim':True,'symbolic':True}))
        page.route('**/api/achievements/**',lambda r:r.fulfill(json={'status':'success','achievements':[]}))
        page.goto('http://127.0.0.1:8000/?section=calculate' if request.param=='static' else 'http://127.0.0.1:5173/calculate',wait_until='domcontentloaded')
        page.wait_for_selector('.step-tutor textarea')
        yield page,request.param
        assert not errors,errors
        browser.close()


def sse(route,event):
    route.fulfill(status=200,content_type='text/event-stream',body='data: '+json.dumps(event,ensure_ascii=False)+'\n\n')


def test_system_preview_results_and_agent_message_use_katex(ui):
    page,kind=ui
    page.wait_for_function('!!window.katex && !!window.renderMathInElement')
    question=SYSTEM+'\n本次子目标：代入验证。'
    page.locator('#tutor-problem').fill(question)
    preview=page.locator('.tutor-input-preview')
    assert preview.locator('.katex-display').count()==1
    assert preview.locator('.katex-error,.math-render-error').count()==0
    assert '本次子目标：代入验证。' in preview.inner_text()
    assert not preview.evaluate("e=>e.classList.contains('math-render-error')")
    # The same text passes through the actual result and agent readers.
    solution=local_solution('x^2=1').model_dump()
    solution['summary']=question;solution['steps'][0]['explanation']=question
    page.evaluate('(record)=>window.StepTutor.restore(record)',{'problem':question,'solution':solution})
    assert page.locator('.tutor-answer .katex-display').count()==1
    assert page.locator('.tutor-explanation .katex-display').count()==1
    page.set_viewport_size({'width':390,'height':844})
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    Path('tests/artifacts').mkdir(exist_ok=True)
    preview.screenshot(path=f'tests/artifacts/system-preview-{kind}.png')
    page.evaluate("window.showSection('agent')")
    page.wait_for_selector('#agent-prompt')
    page.route('**/api/agent/execute',lambda r:r.fulfill(json={'status':'success','steps':[{'section':'chat','reply':question}]}))
    page.locator('#agent-prompt').fill(question);page.locator('#agent-submit-btn').click()
    page.wait_for_function("window.AgentWorkspace.getState().status==='已回复'")
    assert page.locator('.assistant-message .katex-display').count()==2
    assert page.locator('.assistant-message .math-render-error').count()==0
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')


def test_agent_resumes_animation_without_replanning_or_resolving(ui):
    page,_=ui;plans=[];solves=[];renders=[];saves=[]
    solution=local_solution('x^2=1').model_dump()
    plan={'status':'success','steps':[{'section':'detect','formula':'x^2=1'}, {'section':'calculate','formula':'x^2=1','trigger':'generate','save_to_formulas':True}]}
    def planner(r):plans.append(r.request.post_data);r.fulfill(json=plan)
    def solve(r):solves.append(r.request.post_data);sse(r,{'type':'complete','solution':solution})
    def render(r):
        renders.append((r.request.post_data,r.request.headers))
        sse(r,{'type':'error','message':'模拟渲染失败'} if len(renders)==1 else {'type':'complete','video_url':'/videos/solution_aabbcc.mp4','chapters':[]})
    def save(r):
        saves.append(r.request.post_data)
        r.fulfill(status=503,json={'message':'模拟保存失败'}) if len(saves)==1 else r.fulfill(json={'status':'success','id':123})
    page.route('**/api/formulas/solutions',save)
    page.route('**/api/agent/execute',planner);page.route('**/api/solve/stream',solve);page.route('**/api/solve/render',render)
    page.evaluate("window.showSection('agent')");page.wait_for_selector('#agent-prompt')
    page.locator('#agent-prompt').fill('解题并生成动画');page.locator('#agent-submit-btn').click()
    page.wait_for_function("window.AgentWorkspace.getState().error==='模拟保存失败' && !window.AgentWorkspace.getState().busy")
    assert page.locator('.assistant-plan li.done').count()==1
    page.locator('[data-agent=retry]').click()
    page.wait_for_function("window.AgentWorkspace.getState().status==='任务已完成'")
    assert len(plans)==1 and len(solves)==1 and len(renders)==2
    assert renders[0][0]==renders[1][0]
    assert renders[1][1].get('x-wisdom-retry')=='1'
    assert page.locator('.assistant-plan li.done').count()==2
    assert page.locator('.assistant-message').filter(has_text='识别结果：').count()==1
    assert len(saves)==2 and saves[0]==saves[1]


def test_planner_retry_preserves_original_history(ui):
    page,_=ui;requests=[]
    def planner(r):
        requests.append((r.request.post_data_json,r.request.headers))
        r.fulfill(json={'status':'error','message':'模拟计划失败'} if len(requests)==1 else {'status':'success','steps':[{'section':'chat','reply':'已修复'}]})
    page.route('**/api/agent/execute',planner)
    page.evaluate("window.showSection('agent')");page.wait_for_selector('#agent-prompt')
    page.locator('#agent-prompt').fill('解释这个公式');page.locator('#agent-submit-btn').click()
    page.wait_for_function("window.AgentWorkspace.getState().status==='已回复'")
    assert len(requests)==2 and requests[0][0]==requests[1][0]
    assert requests[1][1].get('x-wisdom-retry')=='1'
    assert page.locator('.assistant-message.user').count()==1


def test_tutor_retry_uses_original_problem_even_if_draft_changes(ui):
    page,_=ui;requests=[]
    solution=local_solution('x^2=1').model_dump()
    def solve(r):
        requests.append((r.request.post_data_json,r.request.headers))
        sse(r,{'type':'error','message':'模拟推导失败'} if len(requests)==1 else {'type':'complete','solution':solution})
    page.route('**/api/solve/stream',solve)
    page.locator('[name=autoRender]').uncheck();page.locator('#tutor-problem').fill('x^2=1')
    page.locator('.step-tutor button[type=submit]').click();page.wait_for_function("window.StepTutor.getState().status.includes('自动修复')")
    assert not page.locator('[data-action=retry]').is_visible()
    page.locator('#tutor-problem').fill('x^2=4')
    page.wait_for_function('!!window.StepTutor.getState().solution')
    assert len(requests)==2 and requests[0][0]==requests[1][0]=={'problem':'x^2=1','context':''}
    assert requests[1][1].get('x-wisdom-retry')=='1'


def test_automatic_recovery_is_bounded_and_stoppable(ui):
    page,_=ui;calls=[]
    def fail(r):calls.append(r.request.headers);sse(r,{'type':'error','message':'临时故障'})
    page.route('**/api/solve/stream',fail)
    page.locator('[name=autoRender]').uncheck();page.locator('#tutor-problem').fill('x^2=1')
    page.locator('.step-tutor button[type=submit]').click()
    page.wait_for_function('window.StepTutor.getState().error && !window.StepTutor.getState().busy')
    assert len(calls)==3 and 'x-wisdom-retry' not in calls[0]
    assert all(c.get('x-wisdom-retry')=='1' for c in calls[1:])
    assert '自动修复后仍未完成' in page.locator('.tutor-status').inner_text()
    page.locator('.step-tutor button[type=submit]').click()
    page.wait_for_function("window.StepTutor.getState().status.includes('正在自动修复')")
    page.locator('[data-action=cancel]').click()
    page.wait_for_timeout(1200)
    assert len(calls)==4 and page.locator('.tutor-job').get_attribute('data-phase')=='cancelled'


def test_permission_rejection_does_not_trigger_automatic_requests(ui):
    page,_=ui;calls=[]
    def deny(r):calls.append(True);r.fulfill(status=403,json={'message':'请先完成邮箱验证','code':'email_verification_required'})
    page.route('**/api/solve/stream',deny)
    page.locator('[name=autoRender]').uncheck();page.locator('#tutor-problem').fill('x^2=1')
    page.locator('.step-tutor button[type=submit]').click()
    page.wait_for_function('window.StepTutor.getState().error && !window.StepTutor.getState().busy')
    assert len(calls)==1
