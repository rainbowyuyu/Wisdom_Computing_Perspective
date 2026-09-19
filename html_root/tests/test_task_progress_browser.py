import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright,expect

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local UI servers')

MOCK='''() => {
 const original=window.fetch;
 window.taskStreams={};
 window.fetch=(input,options={})=>{
   const url=typeof input==='string'?input:input.url;
   if(!['/api/solve/render','/api/devtools/edit_code'].includes(url))return original(input,options);
   return Promise.resolve(new Response(new ReadableStream({start(controller){
     window.taskStreams[url]=controller;
     options.signal?.addEventListener('abort',()=>{try{controller.error(new DOMException('Aborted','AbortError'));}catch{}},{once:true});
   }}),{headers:{'Content-Type':url.includes('edit_code')?'application/json':'text/event-stream'}}));
 };
 window.sendTask=(url,event)=>window.taskStreams[url].enqueue(new TextEncoder().encode('data: '+JSON.stringify(event)+'\\n\\n'));
}'''

@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=calculate','http://127.0.0.1:5173/calculate'])
def test_water_progress_concurrency_cancel_and_navigation(base):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.add_init_script('('+MOCK+')()');page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base,wait_until='domcontentloaded');page.wait_for_selector('#knowledge-panel[data-progress-ready=true]')
        page.wait_for_timeout(300)
        page.evaluate("()=>{window.firstTask=fetch('/api/solve/render',{method:'POST',body:'{}'}).then(r=>r.text()).catch(()=>{});}")
        expect(page.locator('#knowledge-bubble-render-wrap')).to_be_visible()
        expect(page.locator('#knowledge-bubble-render-pct')).to_have_text('…')
        page.evaluate("sendTask('/api/solve/render',{type:'progress',chapter:2,total:4,message:'正在绘制第3步'})")
        expect(page.locator('#knowledge-bubble-render-pct')).to_have_text('50%')
        Path('tests/artifacts').mkdir(exist_ok=True)
        label='vue' if '5173' in base else 'static'
        page.locator('#knowledge-panel').screenshot(path=f'tests/artifacts/task-wave-{label}.png')
        page.set_viewport_size({'width':390,'height':844})
        page.evaluate("document.documentElement.dataset.theme='dark'")
        page.emulate_media(reduced_motion='reduce')
        assert page.locator('.knowledge-bubble-wave').evaluate("el=>getComputedStyle(el).animationName")=='none'
        page.locator('#knowledge-panel').screenshot(path=f'tests/artifacts/task-wave-{label}-mobile-dark.png')
        page.emulate_media(reduced_motion='no-preference');page.set_viewport_size({'width':1440,'height':1000})
        page.evaluate("document.documentElement.dataset.theme='light'")
        page.evaluate("()=>{window.secondTask=fetch('/api/devtools/edit_code',{method:'POST',body:'{}'}).then(r=>r.json()).catch(()=>{});}")
        expect(page.locator('#knowledge-bubble-render-pct')).to_have_text('2项')
        page.evaluate("sendTask('/api/solve/render',{type:'complete'})")
        page.wait_for_function("window.__wisdomActivities.all().filter(t=>t.status==='running').length===1")
        expect(page.locator('#knowledge-panel')).to_have_attribute('data-task-state','running')
        page.evaluate("window.showSection('examples')")
        page.locator('#knowledge-panel-bubble').press('Enter')
        expect(page.locator('.task-progress-items')).to_contain_text('创作助手')
        page.locator('#knowledge-panel').screenshot(path=f'tests/artifacts/task-panel-{label}.png')
        page.get_by_role('button',name='停止创作助手',exact=True).click()
        page.wait_for_function("window.__wisdomActivities.all().every(t=>t.status!=='running')")
        page.wait_for_timeout(1800)
        expect(page.locator('.task-progress-panel')).to_be_hidden()
        assert not errors,errors
        browser.close()


def test_graph_assets_load_only_when_graph_becomes_visible():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page();requests=[]
        page.on('request',lambda r:requests.append(r.url))
        page.goto('http://127.0.0.1:8000/?section=calculate',wait_until='domcontentloaded');page.wait_for_selector('.step-tutor textarea')
        assert not any('three@' in u or '3d-force-graph@' in u for u in requests)
        page.evaluate("window.showSection('home')")
        page.locator('#role-graph-3d').scroll_into_view_if_needed()
        page.wait_for_selector('#role-graph-3d canvas',timeout=40000)
        assert len([u for u in requests if 'three@' in u or '3d-force-graph@' in u])==2
        page.evaluate("window.showSection('calculate')")
        page.wait_for_function("document.getElementById('role-graph-3d').dataset.graphState==='paused'")
        browser.close()


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=calculate','http://127.0.0.1:5173/calculate'])
def test_slow_mathlive_does_not_block_input(base):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page();held=[]
        page.route('https://unpkg.com/mathlive',lambda route:held.append(route))
        page.goto(base,wait_until='domcontentloaded',timeout=15000)
        page.locator('#tutor-problem').fill(r'求解 x^2=1')
        assert page.locator('#tutor-problem').input_value()==r'求解 x^2=1'
        assert held and not page.evaluate("!!customElements.get('math-field')")
        held[0].abort();browser.close()
