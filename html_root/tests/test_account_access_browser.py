"""Account UI and access prompts on both frontend entries; no paid model calls."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright,expect

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local UI servers')


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=','http://127.0.0.1:5173/'])
def test_home_roles_admin_editor_and_guest_login_prompt(base):
    role=['guest'];updates=[]
    user={'id':99,'username':'演示用户','role':'member','disabled':False,'daily_limit':None,'used':2}
    def route_access(route):
        quotas={name:{'remaining':limit,'limit':limit,'used':0} for name,limit in [('calculate',3),('recognize',2),('assistant',2),('code',2),('render',3)]}
        if role[0]!='guest':quotas={'all':{'remaining':None,'limit':None,'used':0}}
        route.fulfill(json={'can_manage':role[0]=='admin','role':role[0],'username':'rainbow_yu' if role[0]=='admin' else None,'quotas':quotas,'contact_email':'rainbowyu619@gmail.com'})
    def route_admin(route):
        if '/admin/requests' in route.request.url:
            route.fulfill(json={'items':[],'total':0,'page':1});return
        if route.request.method=='PATCH':
            data=route.request.post_data_json;updates.append(data);user.update(data);route.fulfill(json={'status':'success'})
        elif route.request.url.endswith('/access-audit'):route.fulfill(json={'items':[]})
        else:route.fulfill(json={'items':[user,{'id':1,'username':'rainbow_yu','role':'admin','disabled':False,'daily_limit':None,'used':0}],'total':2,'page':1,'settings':{'daily_limit':40,'contact_email':'rainbowyu619@gmail.com'}})
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/account/access',route_access);page.route('**/api/admin/**',route_admin)
        page.goto(base+'home' if '?' in base else base,wait_until='domcontentloaded')
        page.wait_for_selector('.account-access-card .account-type.guest')
        expect(page.locator('.account-access-card')).to_contain_text('计算试用剩余 3 / 3')
        assert page.locator('.vip-contact').get_attribute('href')=='https://github.com/rainbowyuyu'
        expect(page.locator('.desktop-auth [data-account-header]')).to_contain_text('试用剩余 3 / 3')
        role[0]='admin'
        page.evaluate("window.dispatchEvent(new CustomEvent('auth-state-change',{detail:{username:'rainbow_yu'}}))")
        page.wait_for_selector('.desktop-auth [data-access-admin]');page.locator('.desktop-auth [data-access-admin]').click()
        page.wait_for_selector('.account-admin-page .access-user')
        form=page.locator('.access-user[data-id="99"]')
        form.locator('[name=role]').select_option('vip');form.locator('button').click()
        expect(page.locator('.account-admin-page [data-status]')).to_contain_text('已保存')
        assert updates[-1]['role']=='vip'
        form.locator('[name=role]').select_option('member');form.locator('[name=daily_limit]').fill('12');form.locator('[name=reset_today]').check();form.locator('button').click()
        expect(page.locator('.account-admin-page [data-status]')).to_contain_text('已保存')
        assert updates[-1]['daily_limit']==12 and updates[-1]['reset_today']
        Path('tests/artifacts').mkdir(exist_ok=True)
        label='vue' if '5173' in base else 'static'
        page.screenshot(path=f'tests/artifacts/account-admin-{label}.png')
        page.set_viewport_size({'width':390,'height':844})
        assert page.locator('.account-admin-page').evaluate('(el)=>el.scrollWidth<=el.clientWidth+2')
        page.screenshot(path=f'tests/artifacts/account-admin-{label}-mobile.png')
        page.locator('.account-admin-page [data-home]').click()
        role[0]='guest';page.evaluate("window.dispatchEvent(new CustomEvent('auth-state-change',{detail:{username:null}}))")
        page.wait_for_selector('.account-access-card .account-type.guest')
        page.route('**/api/solve/stream',lambda r:r.fulfill(status=401,headers={'X-Wisdom-Access':'trial_exhausted'},json={'message':'游客计算试用已用完（共 3 次）。请登录后使用完整功能。','code':'trial_exhausted'}))
        page.evaluate("window.showSection('calculate')")
        page.locator('#tutor-problem').fill('x^2=1');page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_selector('.access-limit-dialog[open]')
        expect(page.locator('.access-limit-dialog')).to_contain_text('请登录后使用完整功能')
        page.locator('.access-limit-dialog [data-login]').click()
        expect(page.locator('.access-limit-dialog')).to_have_count(0)
        assert not errors
        browser.close()


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=','http://127.0.0.1:5173/'])
def test_header_quotas_roles_errors_and_stale_auth_response(base):
    state={'role':'member','remaining':7,'limit':40,'fail':False,'hold':False}
    pending=[];admin_requests=[]
    def access_data():
        role=state['role']
        return {'can_manage':role=='admin','role':role,'username':'rainbow_yu' if role=='admin' else '学习者',
                'quotas':{'all':{'remaining':state['remaining'],'limit':state['limit'],'used':33}}}
    def route_access(route):
        if state['hold']:
            state['hold']=False;pending.append(route);return
        if state['fail']:route.fulfill(status=503,json={'message':'暂时无法读取'});return
        route.fulfill(json=access_data())
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/api/user/me',lambda r:r.fulfill(json={'username':'学习者','status':'success'}))
        page.route('**/api/account/access',route_access)
        page.route('**/api/admin/**',lambda r:(admin_requests.append(r.request.url),r.fulfill(status=403,json={'message':'无权限'})))
        page.goto(base+'home' if '?' in base else base,wait_until='domcontentloaded')
        header=page.locator('.desktop-auth [data-account-header]')
        expect(header).to_contain_text('普通用户');expect(header).to_contain_text('今日剩余 7 / 40')
        expect(page.locator('#username-span')).to_have_text('学习者')
        def refresh():
            page.evaluate("async()=>{const A=await import('/static/js/account-access.js?v=20260919-access-1');await A.refreshAccess();}")
        for remaining,limit in [(0,40),(0,0),(9,12)]:
            state.update(remaining=remaining,limit=limit);refresh()
            expect(header).to_contain_text(f'今日剩余 {remaining} / {limit}')
        for role,label in [('vip','VIP 用户'),('admin','管理员')]:
            state.update(role=role,remaining=None,limit=None);refresh()
            expect(header).to_contain_text(label);expect(header).to_contain_text('额度不限')
        # A malformed/missing bucket must never claim unlimited permission.
        state.update(role='member',remaining=None,limit=None);refresh()
        expect(header).to_contain_text('额度待更新')
        state['fail']=True;refresh()
        expect(header).to_contain_text('额度读取失败')
        expect(header.locator('[data-access-admin]')).to_have_count(0)
        state.update(fail=False,remaining=5,limit=12)
        header.locator('[data-access-retry]').click();expect(header).to_contain_text('今日剩余 5 / 12')
        # Pending admin response arriving after an account switch must be ignored.
        state['hold']=True
        page.evaluate("void import('/static/js/account-access.js?v=20260919-access-1').then(A=>A.refreshAccess())")
        for _ in range(40):
            if pending:break
            page.wait_for_timeout(25)
        assert pending
        page.evaluate("window.dispatchEvent(new CustomEvent('auth-state-change'))")
        expect(header).to_contain_text('今日剩余 5 / 12')
        pending.pop().fulfill(json={'role':'admin','username':'旧管理员','quotas':{'all':{'limit':None,'remaining':None,'used':0}}})
        page.wait_for_timeout(150)
        expect(header).to_contain_text('普通用户');expect(header.locator('[data-access-admin]')).to_have_count(0)
        label='vue' if '5173' in base else 'static'
        for width,theme in [(1440,'light'),(1024,'light'),(390,'dark'),(320,'light')]:
            page.set_viewport_size({'width':width,'height':1000})
            page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
            visible=header if width>900 else page.locator('.mobile-account-access')
            expect(visible).to_be_visible();expect(visible).to_contain_text('今日剩余 5 / 12')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
            page.wait_for_timeout(350)
            page.screenshot(path=f'tests/artifacts/account-header-{label}-{width}.png')
        page.goto(base+'admin',wait_until='domcontentloaded')
        expect(page.locator('.admin-gate')).to_contain_text('仅限主账号 rainbow_yu')
        assert not admin_requests
        assert not errors,errors
        browser.close()


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=','http://127.0.0.1:5173/'])
def test_admin_page_settings_search_pagination_retry_and_revocation(base):
    state={'role':'admin','failure':True,'denied':False,'limit':40}
    writes=[];reads=[]
    def route_access(route):
        route.fulfill(json={'can_manage':state['role']=='admin','role':state['role'],'username':'rainbow_yu','quotas':{'all':{'limit':None,'remaining':None,'used':0}}})
    def route_admin(route):
        from urllib.parse import urlparse,parse_qs
        request=route.request;reads.append(request.url)
        if '/admin/requests' in request.url:
            route.fulfill(json={'items':[],'total':0,'page':1});return
        if state['denied']:route.fulfill(status=403,json={'message':'管理权限已取消'});return
        if request.method=='PUT':
            data=request.post_data_json;writes.append(data);state['limit']=data['daily_limit']
            route.fulfill(json={'status':'success'});return
        if '/access-audit' in request.url:
            route.fulfill(json={'items':[{'actor_id':1,'target_id':99,'action':'update_user','details':{'role':'vip'},'created_at':'2026-09-19 12:00:00'}]});return
        if state['failure']:route.fulfill(status=503,json={'message':'列表暂时不可用'});return
        params=parse_qs(urlparse(request.url).query);number=int(params.get('page',['1'])[0]);query=params.get('q',[''])[0]
        item={'id':number,'username':f'第{number}页用户','role':'member','disabled':False,'daily_limit':None,'used':3}
        route.fulfill(json={'items':[] if query else [item],'total':0 if query else 21,'page':number,'settings':{'daily_limit':state['limit'],'contact_email':'author@example.com'}})
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1050},reduced_motion='reduce')
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/api/user/me',lambda r:r.fulfill(json={'username':'rainbow_yu','status':'success'}))
        page.route('**/api/account/access',route_access);page.route('**/api/admin/**',route_admin)
        page.goto(base+'admin',wait_until='domcontentloaded')
        expect(page.locator('[data-admin-host] [data-status]')).to_contain_text('列表暂时不可用')
        state['failure']=False;page.locator('[data-admin-host] [data-retry]').click()
        expect(page.locator('.access-user')).to_contain_text('第1页用户')
        # The shared knowledge graph opens the dedicated page for an admin.
        page.evaluate("window.showSection('home')")
        expect(page.locator('#home')).to_be_visible()
        assert page.evaluate("async()=>{const G=await import('/static/js/site-graph.js?v=20260917-ecosystem-6');return G.executeNodeAction(G.getNodeById('home-admin'));}")
        expect(page.locator('.access-user')).to_contain_text('第1页用户')
        page.locator('[data-next]').click();expect(page.locator('.access-user')).to_contain_text('第2页用户')
        expect(page.locator('[data-next]')).to_be_disabled()
        page.locator('.access-search input').fill('不存在的用户');page.locator('.access-search button[type=submit]').click()
        expect(page.locator('.access-user-list')).to_contain_text('没有找到匹配的用户')
        expect(page.locator('[data-page]')).to_have_text('第 1 / 1 页 · 共 0 人')
        page.locator('.access-search input').fill('');page.locator('.access-search button[type=submit]').click()
        expect(page.locator('.access-user')).to_contain_text('第1页用户')
        page.locator('.admin-settings-panel summary').click()
        page.locator('.access-settings [name=daily_limit]').fill('60');page.locator('.access-settings button').click()
        expect(page.locator('[data-admin-host] [data-status]')).to_contain_text('已保存')
        assert writes[-1]['daily_limit']==60
        expect(page.locator('[data-default]')).to_have_text('60')
        expect(page.locator('.access-user')).to_contain_text('今日剩余 57 / 60 次')
        page.locator('[data-audit]').click();expect(page.locator('[data-audit-list]')).to_contain_text('调整用户权限')
        label='vue' if '5173' in base else 'static'
        for width,theme in [(1440,'light'),(1024,'dark'),(390,'dark')]:
            page.set_viewport_size({'width':width,'height':1050})
            page.evaluate('(t)=>{document.documentElement.dataset.theme=t;window.scrollTo(0,0)}',theme)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
            page.wait_for_timeout(350)
            page.screenshot(path=f'tests/artifacts/account-management-{label}-{width}.png',full_page=True)
        # Backend rejection removes private rows AND audit data, rather than
        # leaving the previous administrator's data visible behind an error.
        state.update(denied=True,role='member');page.locator('[data-refresh]').click()
        expect(page.locator('.admin-gate')).to_contain_text('没有管理权限')
        expect(page.locator('.access-user')).to_have_count(0);expect(page.locator('[data-audit-list]')).to_have_count(0)
        page.locator('.admin-gate [data-home]').click();expect(page.locator('#home')).to_be_visible()
        assert not errors,errors
        browser.close()
