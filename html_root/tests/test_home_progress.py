"""Hero alignment and feedback during genuinely pending streamed work."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from logic.solution_engine import local_solution

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires UI servers')


@pytest.mark.parametrize('origin,home,calculate', [
    ('http://127.0.0.1:8000', '/?section=home', '/?section=calculate'),
    ('http://127.0.0.1:5173', '/', '/calculate'),
])
@pytest.mark.parametrize('width,theme', [(2048, 'light'), (390, 'dark')])
def test_home_background_and_task_feedback(origin, home, calculate, width, theme):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': width, 'height': 1050}, reduced_motion='reduce')
        page.goto(origin + home, wait_until='domcontentloaded')
        page.wait_for_selector('.hero h1')
        page.evaluate("theme=>document.documentElement.dataset.theme=theme", theme)
        page.wait_for_timeout(700)
        geometry = page.locator('.hero').evaluate("""el=>({
            glow:getComputedStyle(el,'::before').content,
            background:getComputedStyle(document.querySelector('.home-page-background')).backgroundImage,
            overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth
        })""")
        assert geometry['glow'] == 'none' and 'radial-gradient' in geometry['background']
        assert geometry['overflow'] <= 2, geometry
        Path('tests/artifacts').mkdir(exist_ok=True)
        kind = 'static' if ':8000' in origin else 'vue'
        page.screenshot(path=f'tests/artifacts/home-centered-{kind}-{width}.png')
        page.goto(origin + calculate, wait_until='domcontentloaded')
        page.wait_for_selector('.step-tutor textarea')
        page.evaluate("theme=>document.documentElement.dataset.theme=theme", theme)
        # Hold fetch streams open so each intermediate state can be observed deterministically.
        page.evaluate('''()=>{
            const fetchOriginal=window.fetch;
            window.progressStreams={};
            window.fetch=(url,options)=>{
                if(!['/api/solve/stream','/api/solve/render'].includes(url))return fetchOriginal(url,options);
                const stream=new ReadableStream({start(c){window.progressStreams[url]=c;}});
                return Promise.resolve(new Response(stream,{headers:{'Content-Type':'text/event-stream'}}));
            };
            window.progressSend=(url,event)=>window.progressStreams[url].enqueue(new TextEncoder().encode('data: '+JSON.stringify(event)+'\\n\\n'));
        }''')
        def send(event, url='/api/solve/stream'):
            page.evaluate('([url,event])=>window.progressSend(url,event)', [url,event])
        def end(url='/api/solve/stream'):
            page.evaluate('(url)=>window.progressStreams[url].close()', url)
        page.locator('[name=autoRender]').uncheck()
        page.locator('#tutor-problem').fill('解方程 x^2-5*x+6=0')
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_selector('.tutor-job.is-indeterminate')
        assert page.locator('.tutor-job-track').get_attribute('aria-valuenow') is None
        page.locator('.tutor-job').screenshot(path=f'tests/artifacts/solve-progress-{kind}-{width}.png')
        solution=local_solution('解方程 x^2-5*x+6=0').model_dump()
        count=len(solution['steps'])
        send({'type':'plan','title':'逐步推导','total':count,'source':'sympy'})
        send({'type':'step','index':0,'step':solution['steps'][0]})
        page.wait_for_function("document.querySelector('.tutor-job-track').getAttribute('aria-valuenow')==='25'")
        send({'type':'complete','solution':solution})
        end()
        page.wait_for_function('!window.StepTutor.getState().busy')
        assert page.locator('.tutor-job-track').get_attribute('aria-valuenow') == '100'
        page.locator('[data-action=render]').click()
        page.wait_for_selector('.tutor-job[data-phase=render].is-indeterminate')
        send({'type':'progress','chapter':0,'total':count}, '/api/solve/render')
        page.wait_for_function("document.querySelector('.tutor-job-track').getAttribute('aria-valuenow')==='0'")
        send({'type':'progress','chapter':2,'total':count}, '/api/solve/render')
        page.wait_for_function("document.querySelector('.tutor-job-track').getAttribute('aria-valuenow')==='50'")
        page.locator('.tutor-job').screenshot(path=f'tests/artifacts/render-progress-{kind}-{width}.png')
        send({'type':'error','message':'测试渲染错误'}, '/api/solve/render')
        page.wait_for_selector('.tutor-job[data-phase=error]')
        assert not page.locator('.tutor-job').evaluate("el=>el.classList.contains('is-active')")
        assert page.locator('.tutor-result').is_visible()
        page.locator('[data-action=render]').click()
        page.wait_for_selector('.tutor-job.is-indeterminate')
        page.locator('[data-action=cancel]').click()
        page.wait_for_selector('.tutor-job[data-phase=cancelled]')
        assert page.locator('.tutor-job').get_attribute('aria-busy') == 'false'
        page.locator('[data-action=render]').click()
        page.wait_for_selector('.tutor-job[data-phase=render]')
        send({'type':'complete','video_url':'/videos/solution_'+'a'*32+'.mp4',
              'chapters':[{'title':step['title'],'start':i*5,'end':(i+1)*5} for i,step in enumerate(solution['steps'])]}, '/api/solve/render')
        end('/api/solve/render')
        page.wait_for_function('!window.StepTutor.getState().rendering')
        assert page.locator('.tutor-job').get_attribute('data-phase') == 'done'
        assert page.locator('.tutor-job-track').get_attribute('aria-valuenow') == '100'
        assert page.locator('.tutor-video').is_visible()
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_selector('.tutor-job[data-phase=solve]')
        end()
        page.wait_for_selector('.tutor-job[data-phase=error]')
        assert page.locator('[data-action=retry]').is_visible()
        browser.close()
