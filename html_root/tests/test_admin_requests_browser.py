import os
import re
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright,expect

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local web servers')


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=','http://127.0.0.1:5173/'])
def test_request_management_and_exclusive_owner_gate(base):
    state={'owner':True,'fail':False};writes=[];queries=[]
    user={'id':99,'username':'教学助理','role':'admin','disabled':False,'daily_limit':None,'used':2}
    row={'id':'b'*32,'owner_id':99,'username':'教学助理','feature':'calculate','status':'failed','http_status':200,
         'duration_ms':2100,'device':'Windows / Chrome','has_image':False,'created_at':'2026-09-19T01:02:03',
         'preview':'求导 $x^2$','problem':'求导 $x^2$\n<img src=x onerror="window.requestXss=1">','endpoint':'/api/solve/stream'}
    def access(route):route.fulfill(json={'role':'admin','can_manage':state['owner'],'username':'rainbow_yu' if state['owner'] else '教学助理','quotas':{'all':{'limit':None,'remaining':None,'used':0}}})
    def api(route):
        url=route.request.url
        if '/admin/requests' in url:
            queries.append(url)
            if state['fail']:route.fulfill(status=503,json={'message':'读取失败'});return
            if url.endswith(row['id']):route.fulfill(json={'item':row});return
            route.fulfill(json={'items':[row],'total':1,'page':1,'recording':{'pending':0,'failed':0,'dropped':0}});return
        if route.request.method=='PATCH':
            data=route.request.post_data_json;writes.append(data);user.update(data)
            route.fulfill(json={'status':'success'});return
        route.fulfill(json={'items':[user,{'id':1,'username':'rainbow_yu','role':'admin','used':0,'daily_limit':None}],
            'total':2,'page':1,'settings':{'daily_limit':40,'contact_email':'author@example.com'}})
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/account/access',access);page.route('**/api/admin/**',api)
        page.route('**/api/user/me',lambda r:r.fulfill(json={'status':'success','username':'rainbow_yu'}))
        page.goto(base+'admin',wait_until='domcontentloaded')
        expect(page.locator('.request-record')).to_contain_text('分步计算')
        expect(page.locator('.request-record')).to_contain_text('失败')
        expect(page.locator('.request-record time')).to_contain_text('09:02:03')
        form=page.locator('.access-user[data-id="99"]')
        for role in ['vip','admin','member']:
            form.locator('[name=role]').select_option(role);form.locator('button').click()
            expect(page.locator('[data-admin-host] [data-status]')).to_contain_text('已保存')
            assert writes[-1]['role']==role
        expect(page.locator('.access-user[data-id="1"] select')).to_have_count(0)
        page.locator('.request-filters [name=q]').fill('题目')
        page.locator('.request-filters [name=status]').select_option('failed')
        page.locator('.request-filters [name=days]').select_option('30')
        page.locator('.request-filters button').click()
        expect(page.locator('[data-requests-list]')).to_have_attribute('aria-busy','false')
        assert 'status=failed' in queries[-1] and 'days=30' in queries[-1]
        page.locator('[data-request-id]').click()
        expect(page.locator('.request-problem')).to_contain_text('<img')
        expect(page.locator('.request-problem img')).to_have_count(0)
        assert page.evaluate('window.requestXss||0')==0
        page.wait_for_function("!!document.querySelector('.request-problem .katex')")
        Path('tests/artifacts').mkdir(exist_ok=True)
        for width,theme in [(1440,'light'),(390,'dark')]:
            page.set_viewport_size({'width':width,'height':1000});page.evaluate('(v)=>document.documentElement.dataset.theme=v',theme)
            page.locator('.admin-requests-panel').scroll_into_view_if_needed();page.wait_for_timeout(350)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
            page.screenshot(path=f"tests/artifacts/request-records-{'vue' if '5173' in base else 'static'}-{width}.png")
        state['fail']=True;page.locator('[data-requests-refresh]').click()
        expect(page.locator('[data-requests-status]')).to_contain_text('读取失败')
        state['fail']=False;page.locator('[data-requests-refresh]').click()
        expect(page.locator('.request-record')).to_be_visible()
        # A delegated admin cannot enter management or retain old private data.
        state['owner']=False;page.evaluate("window.dispatchEvent(new CustomEvent('auth-state-change'))")
        expect(page.locator('.admin-gate')).to_contain_text('仅限主账号 rainbow_yu')
        expect(page.locator('.request-record')).to_have_count(0)
        expect(page.locator('[data-account-header] [data-access-admin]')).to_have_count(0)
        assert not errors,errors
        browser.close()
