"""Run with WISDOM_BROWSER_TESTS=1 and the backend/Vite servers running."""
import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires running UI servers')


@pytest.fixture(scope='module')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.getenv('WISDOM_BROWSER_CHANNEL', 'chrome'), headless=True)
        yield b
        b.close()


@pytest.fixture(params=['http://127.0.0.1:8000/?section=calculate', 'http://127.0.0.1:5173/calculate'])
def page(browser, request):
    page = browser.new_page(viewport={'width':1440,'height':1000}, device_scale_factor=1)
    page.errors=[]
    page.on('pageerror', lambda error: page.errors.append(str(error)))
    page.goto(request.param, wait_until='domcontentloaded')
    page.wait_for_selector('.step-tutor textarea')
    yield page
    errors = page.errors
    page.close()
    assert not errors, errors


def solve(page, problem):
    page.locator('[name=autoRender]').uncheck()
    page.locator('.step-tutor textarea').fill(problem)
    page.locator('.step-tutor button[type=submit]').click()
    page.wait_for_function('window.StepTutor.getState().solution && !window.StepTutor.getState().busy')


def test_steps_slider_playback_export_history(page):
    solve(page, '解方程 x^2-5*x+6=0')
    assert '2, 3' in page.locator('.tutor-answer').inner_text()
    assert page.locator('.tutor-step-count').inner_text() == '步骤 1 / 4'
    page.locator('[data-step="3"]').click()
    assert page.locator('.tutor-step-count').inner_text() == '步骤 4 / 4'
    slider=page.locator('.tutor-slider-label input')
    before=page.locator('.tutor-visual').inner_html()
    slider.fill('300');slider.dispatch_event('input')
    assert before != page.locator('.tutor-visual').inner_html()
    page.locator('[data-action=play]').click()
    page.wait_for_function('window.StepTutor.getState().progress < 0.9')
    page.locator('[data-action=play]').click()
    page.locator('.tutor-more summary').click()
    with page.expect_download() as event: page.locator('[data-action=export]').click()
    assert event.value.suggested_filename.endswith('.md')
    page.reload(wait_until='domcontentloaded')
    page.locator('.tutor-history summary').click()
    page.locator('[data-history="0"]').click()
    assert '2, 3' in page.locator('.tutor-answer').inner_text()


def test_inline_math_is_rendered_without_interpreting_html(page):
    page.wait_for_function('typeof window.renderMathInElement === "function"')
    text = '条件 $x > 2$，<img src=x onerror=alert(1)>'
    solution = {'title':'条件筛选', 'summary':'答案 $x = 3$', 'source':'ai', 'verification':'测试数据', 'steps':[
        {'title':'条件', 'explanation':text, 'formula':'x>2', 'hint':'保留 $x=3$', 'visual':{'kind':'reasoning','caption':'检查 $x > 2$'}},
        {'title':'结果', 'explanation':'答案 $x=3$', 'formula':'x=3', 'visual':{'kind':'reasoning'}}]}
    events = [{'type':'step','index':i,'step':step} for i,step in enumerate(solution['steps'])] + [{'type':'complete','solution':solution}]
    page.route('**/api/solve/stream',lambda route: route.fulfill(status=200,content_type='text/event-stream',body=''.join('data: '+json.dumps(event)+'\n\n' for event in events)))
    solve(page, '测试内联公式')
    assert page.locator('.tutor-explanation .katex').count() == 1
    assert page.locator('.tutor-answer .katex').count() == 1
    assert page.locator('.tutor-explanation img').count() == 0
    assert '<img' in page.locator('.tutor-explanation').inner_text()


def test_floating_keyboard_drag_and_resize(page):
    page.wait_for_selector('#knowledge-panel[data-floating-ready]')
    bubble=page.locator('#knowledge-panel-bubble')
    assert page.locator('#knowledge-panel').evaluate('el=>el.classList.contains("collapsed")')
    bubble.focus();page.keyboard.press('Enter')
    assert page.locator('#knowledge-panel-close-btn').is_visible()
    box=page.locator('#knowledge-panel-header').bounding_box()
    page.mouse.move(box['x']+40,box['y']+15);page.mouse.down();page.mouse.move(500,220,steps=12);page.mouse.up()
    rect=page.locator('#knowledge-panel').bounding_box()
    assert rect['x']<700
    page.locator('#knowledge-panel-header').focus();page.keyboard.press('ArrowLeft')
    assert page.locator('#knowledge-panel').bounding_box()['x']<rect['x']
    page.keyboard.press('Escape')
    assert bubble.is_visible()
    page.set_viewport_size({'width':390,'height':844})
    bubble.focus();page.keyboard.press('Enter')
    page.wait_for_timeout(250)
    box=page.locator('#knowledge-panel').bounding_box()
    assert box['x']>=0 and box['x']+box['width']<=391
    assert box['y']>=0 and box['y']+box['height']<=845
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')


def test_disconnected_stream_and_retry(page):
    def truncated(route): route.fulfill(status=200, content_type='text/event-stream', body='data: {"type":"status","message":"分析中"}\n\n')
    page.route('**/api/solve/stream',truncated)
    page.locator('.step-tutor textarea').fill('x^2=1')
    page.locator('.step-tutor button[type=submit]').click()
    page.wait_for_function('window.StepTutor.getState().error')
    assert '连接提前结束' in page.locator('.tutor-status').inner_text()
    assert page.locator('.step-tutor button[type=submit]').is_enabled()
    page.unroute('**/api/solve/stream',truncated)
    solve(page, '矩阵 [[1,2],[0,1]]')
    slider=page.locator('.tutor-slider-label input')
    slider.fill('0');slider.dispatch_event('input')
    before=page.locator('.tutor-visual').inner_html()
    slider.fill('1000');slider.dispatch_event('input')
    assert before!=page.locator('.tutor-visual').inner_html()


def test_prefilled_context_is_bound_to_the_draft_not_an_old_solution(page):
    solve(page, 'x^2=1')
    captured=[]
    def receive(route):
        captured.append(route.request.post_data_json)
        route.fulfill(status=200,content_type='text/event-stream',body='data: {"type":"error","message":"测试已收到题目"}\n\n')
    page.route('**/api/solve/stream', receive)
    page.evaluate("window.StepTutor.prefill('完整题面：已知三角形 ABC，求面积。','AB=3, BC=4，B 为直角')")
    assert page.evaluate('window.StepTutor.getState().problem') == 'x^2=1'
    page.locator('.step-tutor button[type=submit]').click()
    page.wait_for_function('window.StepTutor.getState().error')
    assert captured[-1]['context'].startswith('AB=3')
    page.locator('.step-tutor textarea').fill('另一个独立问题')
    page.locator('.step-tutor button[type=submit]').click()
    page.wait_for_function('!window.StepTutor.getState().busy')
    assert captured[-1]['context'] == ''


def test_graph_navigation_pause_and_remount(page):
    # Exercise arriving from a non-home page, rather than relying on initial visibility.
    page.evaluate("window.showSection('home')")
    page.wait_for_selector('.graph-explorer input')
    page.locator('#role-graph-3d').scroll_into_view_if_needed()
    page.wait_for_selector('#role-graph-3d canvas')
    page.wait_for_function("document.querySelector('#role-graph-3d').dataset.graphState === 'active'")
    page.locator('.graph-explorer input').fill('Manim')
    assert page.locator('.graph-search-results button').count() >= 1
    page.evaluate("window.showSection('calculate')")
    page.wait_for_selector('.step-tutor textarea')
    if ':8000' in page.url:
        page.wait_for_function("document.querySelector('#role-graph-3d').dataset.graphState === 'paused'")
    page.evaluate("window.showSection('home')")
    page.wait_for_selector('.graph-explorer input')
    page.locator('#role-graph-3d').scroll_into_view_if_needed()
    page.wait_for_selector('#role-graph-3d canvas')
    assert page.locator('#role-graph-3d canvas').count()==1
    page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
    page.wait_for_timeout(100)
    folder=Path('tests/artifacts');folder.mkdir(exist_ok=True)
    name='vue' if ':5173' in page.url else 'static'
    page.locator('.role-graph-wrap').screenshot(path=str(folder/f'{name}-graph-verified.png'))


def test_video_chapter_contract(page):
    result_path=Path('tests/render-result.json')
    if not result_path.exists(): pytest.skip('Run the real render verification first')
    # Replay a completed real render to test player controls without rerendering it.
    rendered=json.loads(result_path.read_text())
    page.route('**/api/solve/render', lambda route: route.fulfill(status=200,content_type='text/event-stream',body='data: '+json.dumps(rendered)+'\n\n'))
    solve(page, 'x^2-5*x+6=0')
    page.locator('[data-action=render]').click()
    page.wait_for_selector('.tutor-video video')
    page.wait_for_function("document.querySelector('.tutor-video video').readyState >= 1")
    page.locator('[data-chapter="2"]').click()
    assert page.locator('.tutor-video video').evaluate('v=>v.currentTime') >= 10
    assert page.locator('.tutor-step-count').inner_text() == '步骤 3 / 4'
    page.locator('.tutor-video video').evaluate('v=>{v.pause();v.currentTime=16;}')
    page.wait_for_function('window.StepTutor.getState().index===3')


def test_agent_skips_chat_and_serializes_two_calculation_steps(browser):
    result_path = Path('tests/render-result.json')
    if not result_path.exists(): pytest.skip('Run live render verification first')
    page = browser.new_page()
    calls = []
    rendered = json.loads(result_path.read_text())
    page.route('**/api/solve/render', lambda route: route.fulfill(status=200, content_type='text/event-stream', body='data: '+json.dumps(rendered)+'\n\n'))
    page.on('request', lambda request: calls.append(request.url) if request.url.endswith('/api/solve/stream') else None)
    page.goto('http://127.0.0.1:5173/calculate', wait_until='domcontentloaded')
    page.wait_for_selector('.step-tutor textarea')
    page.evaluate('''async () => {
      const loaded=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/stores/agentRunner.ts');
      const {useAgentRunnerStore}=await import(loaded?.name||'/src/stores/agentRunner.ts');
      window.testRunner=useAgentRunnerStore();
      window.testRunner.start([
        {section:'chat',reply:'开始'},
        {section:'calculate',formula:'x^2=1',trigger:'generate'},
        {section:'calculate',formula:'求导 x^2',trigger:'generate'}
      ]);
    }''')
    page.wait_for_function("window.testRunner.state.status === 'finished'")
    assert len(calls) == 2
    assert page.evaluate("window.StepTutor.getState().problem") == '求导 x^2'
    page.close()


def test_visual_latex_composer_roundtrip_and_exact_integral(page):
    page.wait_for_function("typeof document.querySelector('.tutor-math-input').setValue === 'function'")
    source = r'\int_0^1 x^{2}+3x\,dx'
    page.locator('.step-tutor textarea').fill(source)
    assert page.locator('.tutor-input-preview .katex').count() == 1
    page.locator('[data-input-mode=math]').click()
    field = page.locator('.tutor-math-input')
    assert field.is_visible()
    assert not page.locator('.step-tutor textarea').is_visible()
    # The recognition-result editor uses the same MathLive input event contract.
    field.evaluate("(el,value)=>{el.setValue(value);el.dispatchEvent(new InputEvent('input',{bubbles:true}));}", source)
    serialized = field.evaluate('el=>el.value')
    page.locator('[data-input-mode=text]').click()
    assert page.locator('.step-tutor textarea').input_value() == serialized
    page.locator('[data-input-mode=math]').click()
    page.locator('[name=autoRender]').uncheck()
    page.locator('.step-tutor button[type=submit]').click()
    page.wait_for_function('window.StepTutor.getState().solution && !window.StepTutor.getState().busy')
    assert page.evaluate('window.StepTutor.getState().solution.source') == 'sympy'
    assert page.locator('.tutor-answer .katex').count() == 1
    assert page.locator('.tutor-answer annotation').text_content() == r'\frac{11}{6}'
    page.locator('[data-step="3"]').click()
    assert r'\frac{11}{6}' in page.locator('.tutor-formula annotation').text_content()
    page.set_viewport_size({'width':390,'height':844})
    field.scroll_into_view_if_needed()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    name='vue' if ':5173' in page.url else 'static'
    page.locator('.tutor-composer').screenshot(path=f'tests/artifacts/{name}-latex-composer-mobile.png')
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('.step-tutor').screenshot(path=f'tests/artifacts/{name}-latex-integral-result.png')


def test_saved_reader_renders_legacy_bare_latex_safely(page):
    page.wait_for_function('typeof window.openSavedSolution === "function" && typeof window.renderMathInElement === "function"')
    record={'id':999,'problem':r'\int_0^1 x^2+3x\,dx', 'solution':{
        'title':'积分题解', 'summary':r'结果为 \frac{11}{6}。', 'verification':'读取已保存数据', 'steps':[
            {'title':r'计算 \frac{11}{6}', 'explanation':r'原函数 F(x)=\frac{x^3}{3}+\frac{3x^2}{2}，代入上下限。<img src=x onerror=alert(1)>',
             'formula':r'F(1)-F(0)=\frac{11}{6}', 'hint':r'核对 \frac{1}{3}+\frac{3}{2}', 'visual':{'kind':'reasoning','caption':r'答案 \frac{11}{6}'}}]}}
    page.route('**/api/formulas/solutions/999',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps({'status':'success','data':record})))
    page.evaluate('window.openSavedSolution(999)')
    page.wait_for_selector('.solution-reader[open]')
    assert page.locator('.reader-conclusion .katex').count()==1
    assert page.locator('.reader-problem .katex').count()==1
    assert page.locator('.reader-step h4 .katex').count()==1
    assert page.locator('.reader-step>p .katex').count()==2
    assert page.locator('.reader-step img').count()==0
    assert '<img' in page.locator('.reader-step').inner_text()
    assert page.locator('.reader-step .katex-error').count()==0
    page.locator('[data-reader=close]').click()
