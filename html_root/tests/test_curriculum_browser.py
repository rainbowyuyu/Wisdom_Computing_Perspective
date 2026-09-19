import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright
from test_solution_library import accounts, live_library_server

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires UI servers')


@pytest.mark.parametrize('url', ['http://127.0.0.1:8000/?section=calculate','http://127.0.0.1:5173/calculate'])
def test_catalog_read_filter_variant_and_split(url,live_library_server):
    origin,(_,sessions)=live_library_server
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1100})
        page.context.add_cookies([{'name':'auth_session','value':sessions[0],'url':origin}])
        if '5173' in url:
            page.route('**/api/**',lambda route:route.fulfill(response=route.fetch(
                url=origin+urlsplit(route.request.url).path+('?' + urlsplit(route.request.url).query if urlsplit(route.request.url).query else ''))))
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(url.replace('http://127.0.0.1:8000',origin).replace('calculate','examples'),wait_until='domcontentloaded')
        page.locator('.examples-filter-tab[data-filter=curriculum]').click()
        page.wait_for_selector('.curriculum-card')
        assert page.locator('.curriculum-card').count()==20
        page.locator('[data-filter=level]').select_option('大学')
        assert page.locator('.curriculum-card').count()==10
        page.locator('.curriculum-search input').fill('贝叶斯')
        assert page.locator('.curriculum-card').count()==1
        page.locator('[data-read=uni-bayes]').click()
        page.wait_for_selector('.solution-reader[open]')
        assert page.locator('.solution-reader [data-reader-step]').count()==3
        assert page.locator('#examples .tutor-curriculum').count()==1
        assert page.locator('#calculate .tutor-curriculum').count()==0
        page.locator('[data-reader-step="1"]').click()
        assert page.locator('.reader-step .reader-kicker').inner_text()=='步骤 2 / 3'
        assert page.locator('.reader-step .katex-error').count()==0
        page.locator('[data-reader-step="2"]').click()
        assert '4' in page.locator('.reader-step .tutor-formula').inner_text()
        page.locator('[data-reader=open]').click()
        page.wait_for_selector('.tutor-result:not([hidden])')
        assert page.evaluate("window.StepTutor.getState().solution.source")=='curriculum'
        assert page.locator('#calculate .tutor-curriculum').count()==0
        Path('tests/artifacts').mkdir(exist_ok=True)
        page.screenshot(path='tests/artifacts/curriculum-'+('vue' if '5173' in url else 'static')+'.png')
        page.evaluate("window.showSection('examples')")
        page.locator('.examples-filter-tab[data-filter=curriculum]').click()
        page.locator('[data-filter=level]').select_option('大学')
        page.locator('.curriculum-search input').fill('贝叶斯')
        page.locator('[data-fill=uni-bayes]').click()
        page.wait_for_selector('.step-tutor textarea:visible')
        assert '甲厂供货' in page.locator('#tutor-problem').input_value()
        page.locator('[name=autoRender]').uncheck()
        page.locator('#tutor-problem').fill('如图，求AB的长度。')
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_selector('.tutor-advice:not([hidden])')
        page.wait_for_function('!window.StepTutor.getState().busy')
        assert '图形信息' in page.locator('.tutor-advice strong').inner_text()
        assert '补充' in page.locator('.tutor-advice').inner_text()
        # Complex input moves intact to the agent; login is required before billing.
        page.context.clear_cookies()
        page.evaluate("window.dispatchEvent(new CustomEvent('auth-state-change',{detail:{username:null}}))")
        page.locator('#tutor-problem').fill('已知函数f(x)=x^2。（1）求定义域（2）求值域（3）求最小值')
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_selector('.math-task-pending:not([hidden])')
        page.wait_for_function("document.querySelector('.math-task-feedback').textContent.includes('登录')")
        assert '（3）求最小值' in page.locator('.math-task-pending').inner_text()
        assert not page.evaluate('window.StepTutor.getState().busy')
        page.evaluate('window.toggleAuthModal?.(false)')
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path='tests/artifacts/curriculum-mobile-'+('vue' if '5173' in url else 'static')+'.png')
        assert page.locator('.math-task-board').evaluate('(el)=>el.scrollWidth<=el.clientWidth+2')
        assert not errors
        browser.close()
