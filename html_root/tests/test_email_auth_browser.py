"""Exercise both shipped auth UIs with deterministic API responses; no mail is sent."""
import os
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from playwright.sync_api import sync_playwright, expect

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires local UI servers')
BASES = ['http://127.0.0.1:8000/?section=home', 'http://127.0.0.1:5173/']


def mock_api(page, state):
    requests = []
    def handle(route):
        path = urlsplit(route.request.url).path
        if path == '/api/captcha':
            return route.fulfill(content_type='image/svg+xml', headers={'X-Captcha-ID':'test-picture'},
                body='<svg xmlns="http://www.w3.org/2000/svg" width="125" height="44"><rect width="125" height="44" fill="#eef2ff"/><text x="20" y="30" font-size="24">ABCD</text></svg>')
        if path == '/api/user/me':
            return route.fulfill(status=200 if state['signed'] else 401,
                json={'status':'success','username':'student','email_verified':state['verified'], 'email_address':state.get('email_address',''), 'email':state.get('email','')} if state['signed'] else {'status':'error'})
        if path == '/api/account/access':
            return route.fulfill(json={'role':'member' if state['signed'] else 'guest', 'username':'student' if state['signed'] else None,
                'email_verified':state['verified'],'can_manage':False,'quotas':{n:{'limit':3,'remaining':3,'used':0} for n in ['all','calculate','recognize','assistant']}})
        if path == '/api/user/check-username':
            return route.fulfill(json={'available':True})
        if path in ['/api/email/send-code','/api/password/forgot/request','/api/email/verify','/api/email/change','/api/password/forgot/reset','/api/register','/api/login']:
            body = route.request.post_data_json
            requests.append((path, body))
            if path.endswith('send-code') or path.endswith('/request'):
                if state.get('mail_down'):
                    return route.fulfill(status=503,json={'status':'error','message':'邮箱服务尚未配置，请联系作者。'})
                return route.fulfill(json={'status':'success','message':'验证码已发送，请查收邮箱。'})
            if path == '/api/login':
                state['signed'] = True
                return route.fulfill(json={'status':'success','username':'student','email_verified':state['verified'], 'email_address':state.get('email_address',''), 'email':state.get('email','')})
            if path == '/api/email/verify':
                state['verified'] = True
            if path == '/api/email/change':
                state.update(verified=True,email=body['email'],email_address=body['email'])
            if path == '/api/password/forgot/reset':
                state['signed'] = False
            return route.fulfill(json={'status':'success','message':'操作成功。'})
        return route.fulfill(json={'status':'success','data':[],'items':[],'settings':{},'profile':{}})
    page.route('**/api/**', handle)
    return requests


@pytest.mark.parametrize('base', BASES)
def test_settings_email_change_updates_profile(base):
    state = {'signed':True,'verified':True,'email':'old@example.test','email_address':'old@example.test'}
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':390,'height':844})
        requests=mock_api(page,state)
        page.goto(base,wait_until='domcontentloaded')
        page.wait_for_function("typeof window.openSettings==='function'")
        page.evaluate("window.openSettings('profile')")
        expect(page.locator('#profile-email-display')).to_have_text('old@example.test')
        page.locator('.profile-email-change-btn').click()
        expect(page.locator('#change-email-modal')).to_be_visible()
        page.locator('#change-email-new').fill('new@example.test')
        page.locator('#btn-change-email-code').click()
        expect(page.locator('#change-email-hint')).to_contain_text('已发送')
        expect(page.locator('#btn-change-email-code')).to_be_disabled()
        assert ('/api/email/send-code',{'email':'new@example.test','purpose':'change_email'}) in requests
        page.locator('#change-email-code').fill('123456')
        page.locator('#btn-change-email-submit').click()
        expect(page.locator('#change-email-modal')).not_to_be_visible()
        expect(page.locator('#profile-email-display')).to_have_text('new@example.test')
        expect(page.locator('#profile-email-status')).to_have_text('已验证')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        assert ('/api/email/change',{'email':'new@example.test','code':'123456'}) in requests
        browser.close()


@pytest.mark.parametrize('base', BASES)
def test_registration_reset_and_mobile_layout(base):
    vue = ':5173' in base
    state = {'signed':False,'verified':True}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        requests = mock_api(page, state)
        page.goto(base, wait_until='domcontentloaded')
        page.wait_for_function("typeof window.toggleAuthModal==='function'")
        page.evaluate('window.toggleAuthModal(true)')
        if vue:
            modal = page.locator('.auth-account-dialog')
            modal.get_by_role('button',name='创建账户',exact=True).click()
            modal.get_by_label('用户名',exact=True).fill('student')
            modal.get_by_label('设置密码（至少 6 位）').fill('new-password')
            modal.get_by_label('确认密码',exact=True).fill('new-password')
            modal.get_by_label('邮箱',exact=True).fill('student@example.test')
            modal.get_by_label('图片验证码',exact=True).fill('ABCD')
            modal.get_by_role('button',name='获取验证码').click()
            expect(modal.get_by_role('button',name='秒后重发')).to_be_disabled()
            modal.get_by_label('邮箱验证码',exact=True).fill('123456')
            modal.get_by_role('button',name='验证并注册').click()
            expect(modal.locator('[role=status]')).to_contain_text('注册成功')
            modal.get_by_role('button',name='忘记密码？').click()
            modal.get_by_label('邮箱',exact=True).fill('student@example.test')
            modal.get_by_label('邮箱验证码',exact=True).fill('123456')
            modal.get_by_label('设置密码（至少 6 位）').fill('another-password')
            modal.get_by_label('确认密码',exact=True).fill('another-password')
        else:
            modal = page.locator('#auth-modal')
            modal.locator('.auth-tab').nth(1).click()
            for ident, value in [('reg-user','student'),('reg-pass','new-password'),('reg-pass-confirm','new-password'),
                                  ('reg-email','student@example.test'),('reg-captcha','ABCD')]:
                page.locator('#'+ident).fill(value)
            page.locator('#btn-reg-email-code').click()
            expect(page.locator('#btn-reg-email-code')).to_contain_text('秒后重发')
            page.locator('#reg-email-code').fill('123456')
            page.locator('#reg-agree').check()
            page.locator('#btn-reg-submit').click()
            expect(page.locator('#login-form')).to_be_visible()
            modal.get_by_role('button',name='忘记密码？').click()
            for ident, value in [('forgot-email','student@example.test'),('forgot-email-code','123456'),
                                  ('forgot-new-pass','another-password'),('forgot-new-pass-confirm','another-password')]:
                page.locator('#'+ident).fill(value)
        assert any(path=='/api/register' and body['email_code']=='123456' for path,body in requests)
        page.set_viewport_size({'width':390,'height':844})
        assert modal.evaluate('(el)=>el.scrollWidth<=el.clientWidth+2')
        Path('tests/artifacts').mkdir(exist_ok=True)
        page.screenshot(path='tests/artifacts/email-forgot-'+('vue' if vue else 'static')+'.png')
        modal.get_by_role('button',name='重置密码',exact=True).click()
        page.wait_for_function("document.body.innerText.includes('密码已重置')")
        assert any(path=='/api/password/forgot/reset' and body['new_password']=='another-password' for path,body in requests)
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize('base', BASES)
def test_existing_user_prompt_retry_and_verification(base):
    vue = ':5173' in base
    state = {'signed':True,'verified':False,'mail_down':True}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        requests = mock_api(page, state)
        page.goto(base, wait_until='domcontentloaded')
        modal = page.locator('.auth-account-dialog' if vue else '#auth-modal')
        expect(modal).to_be_visible()
        expect(modal).to_contain_text('你的学习资料会保留')
        email = modal.get_by_label('邮箱',exact=True) if vue else page.locator('#verify-email')
        email.fill('student@example.test')
        button = modal.get_by_role('button',name='获取验证码',exact=True) if vue else page.locator('#btn-verify-code')
        button.click()
        status = modal.locator('[role=status]') if vue else page.locator('#email-verify-form [role=status]')
        expect(status).to_contain_text('尚未配置')
        expect(button).to_be_enabled()
        state['mail_down'] = False
        button.click()
        expect(status).to_contain_text('已发送')
        page.set_viewport_size({'width':390,'height':844})
        assert modal.evaluate('(el)=>el.scrollWidth<=el.clientWidth+2')
        Path('tests/artifacts').mkdir(exist_ok=True)
        page.screenshot(path='tests/artifacts/email-verify-'+('vue' if vue else 'static')+'.png')
        if vue:
            modal.get_by_label('邮箱验证码',exact=True).fill('123456')
        else:
            page.locator('#verify-email-code').fill('123456')
        with page.expect_navigation():
            modal.get_by_role('button',name='验证并继续',exact=True).click()
        assert state['verified']
        expect(modal).not_to_be_visible()
        assert any(path=='/api/email/verify' for path,_ in requests)
        browser.close()


@pytest.mark.parametrize('bound_email', ['', 'student@example.test', 's***@example.test'])
def test_verification_does_not_request_gated_profile(bound_email):
    state = {'signed': True, 'verified': False, 'email': bound_email,
             'email_address': bound_email if '*' not in bound_email else ''}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        requests = mock_api(page, state)
        profile_requests = []
        def forbidden_profile(route):
            if state['verified']:
                return route.fallback()
            profile_requests.append(route.request.url)
            # Cap the pre-fix recursion so a regression cannot flood the test browser.
            route.fulfill(status=403, json={'message': '请先验证邮箱'},
                headers={'X-Wisdom-Access': 'email_verification_required'} if len(profile_requests) < 20 else {})
        page.route('**/api/user/profile', forbidden_profile)
        page.route('**/api/formulas', lambda route: route.fallback() if state['verified'] else route.fulfill(status=403,
            headers={'X-Wisdom-Access': 'email_verification_required'}, json={'message': '请先验证邮箱'}))
        page.goto(BASES[0], wait_until='domcontentloaded')
        expect(page.locator('#email-verify-form')).to_be_visible()
        page.wait_for_timeout(400)
        assert not profile_requests
        email = page.locator('#verify-email')
        expect(email).to_have_value(bound_email if '*' not in bound_email else '')
        email.fill('student@example.test')
        page.locator('#btn-verify-code').click()
        expect(page.locator('#btn-verify-code')).to_contain_text('秒后重发')
        page.locator('#verify-email-code').fill('123456')
        # Concurrent denied tool requests must not restart the form or its cooldown.
        page.evaluate("async () => { await Promise.all(Array.from({length:5},()=>fetch('/api/formulas'))); window.openEmailVerification(); }")
        expect(email).to_have_value('student@example.test')
        expect(page.locator('#verify-email-code')).to_have_value('123456')
        expect(page.locator('#btn-verify-code')).to_be_disabled()
        expect(page.locator('#btn-verify-code')).to_contain_text('秒后重发')
        # Settings uses /user/me for the unverified account instead of gated /profile.
        page.evaluate("async () => { const p=await import('/static/js/profile.js'); await p.loadProfile(); }")
        assert not profile_requests
        with page.expect_navigation():
            page.locator('#btn-verify-submit').click()
        assert state['verified']
        expect(page.locator('#auth-modal')).not_to_be_visible()
        sends = [body for path, body in requests if path == '/api/email/send-code']
        assert sends == [{'email':'student@example.test','purpose':'verify','captcha_id':''}]
        assert any(path == '/api/email/verify' and body == {'email':'student@example.test','code':'123456'} for path, body in requests)
        browser.close()


def test_unverified_background_requests_pause_and_resume():
    state = {'signed': True, 'verified': False}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width':1280,'height':900})
        mock_api(page, state)
        protected = []
        task_denied = False
        def handle(route):
            path = urlsplit(route.request.url).path
            protected.append(path)
            if not state['verified'] or (task_denied and path == '/api/agent/tasks'):
                return route.fulfill(status=403,headers={'X-Wisdom-Access':'email_verification_required'},
                    json={'message':'verification required'})
            return route.fulfill(json={'status':'success','data':{},'items':[],'owner':'student'})
        for path in ['/api/examples','/api/user/stats','/api/user/settings','/api/agent/tasks','/api/achievements/list*']:
            page.route('**'+path, handle)
        page.goto(BASES[0],wait_until='domcontentloaded')
        expect(page.locator('#email-verify-form')).to_be_visible()
        page.wait_for_function("typeof window.openSettings==='function' && typeof window.Examples==='object'")
        page.evaluate("async()=>{window.openEmailVerification();const tasks=await import('/static/js/agent-task-board.js?v=20260919-tasks-1');await tasks.refreshTasks();await window.loadExamples();}")
        page.evaluate("async()=>{const settings=await import('/static/js/settings.js');await settings.loadUserSettings();}")
        page.wait_for_timeout(11000)
        assert protected == []
        state['verified'] = True
        page.evaluate("window.dispatchEvent(new CustomEvent('auth-state-change',{detail:{username:'student',email_verified:true}}))")
        page.evaluate("async()=>{const tasks=await import('/static/js/agent-task-board.js?v=20260919-tasks-1');await tasks.refreshTasks();}")
        page.wait_for_function("true")
        assert '/api/agent/tasks' in protected
        task_denied = True
        page.evaluate("async()=>{const tasks=await import('/static/js/agent-task-board.js?v=20260919-tasks-1');await tasks.refreshTasks();}")
        before = protected.count('/api/agent/tasks')
        page.wait_for_timeout(11000)
        assert protected.count('/api/agent/tasks') == before
        browser.close()
