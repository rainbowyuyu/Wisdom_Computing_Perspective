"""Email UI contract tests with intercepted requests. No email is ever sent."""
from pathlib import Path

from playwright.sync_api import expect
from test_account_browser import account_page,mount,session,quota  # noqa: F401
from test_browser import browser  # noqa: F401

ROOT=Path(__file__).resolve().parents[1]


def email_session(*,authenticated=False,configured=True,verified=True,role='member',email='reader@example.test',unlimited=False):
    return {**session(authenticated=authenticated,user={'login':'reader','name':'小读者','email':email,'email_verified':verified,'role':role} if authenticated else None),
            'email':{'login_available':True,'configured':configured,'message':'' if configured else '邮箱验证码服务尚未配置。'},
            'public_mode':True,'model_access':{'allowed':['qwen','chatgpt','claude'] if role in ['vip','admin','owner'] else ['qwen']},
            'usage':quota(scope='account',total=None if unlimited else 3,used=1,remaining=None if unlimited else 2,available=2,site_remaining=7,unlimited=unlimited)}


def open_login(page):
    page.locator('.account-trigger').click()
    page.locator('.account-email-login').click()
    expect(page.locator('.email-auth-dialog')).to_be_visible()


def fill_login(page):
    page.get_by_label('邮箱或用户名',exact=True).fill('reader@example.test')
    page.get_by_label('密码',exact=True).fill('synthetic-password')


def test_email_login_flushes_before_mutation_and_rotates_csrf(account_page):
    page=account_page;mount(page,email_session())
    sent=[]
    def login(route):
        sent.append(route.request.post_data_json)
        route.fulfill(json={**email_session(authenticated=True),'csrf':'csrf_email_rotated'})
    page.route('**/api/auth/email/login',login)
    open_login(page);fill_login(page)
    page.evaluate("window.beforeMode='hold'")
    page.locator('.email-auth-submit').click()
    expect(page.locator('.email-auth-submit')).to_be_disabled()
    page.keyboard.press('Escape');expect(page.locator('.email-auth-dialog')).to_be_visible()
    assert sent==[] and page.evaluate('window.accountBusy')==['login']
    page.evaluate('window.releaseSave()')
    expect(page.locator('.email-auth-dialog')).not_to_be_visible()
    assert sent==[{'identifier':'reader@example.test','password':'synthetic-password'}]
    assert page.evaluate('window.accountCsrf')=='csrf_email_rotated'
    assert page.evaluate('window.accountEvents.slice(-3)')==[
        {'type':'before','reason':'login'},{'type':'saved','reason':'login'},{'type':'session','authenticated':True,'reason':'login'}]
    assert page.locator('.email-auth-password input').input_value()==''
    assert page.evaluate('window.accountBusy')==['login',None]
    page.locator('.account-trigger').click()


def test_save_failure_blocks_email_login_and_close_clears_secrets(account_page):
    page=account_page;mount(page,email_session());open_login(page);fill_login(page)
    page.evaluate("window.beforeMode='reject'")
    page.locator('.email-auth-submit').click()
    expect(page.locator('.email-auth-message')).to_have_text('当前修改尚未保存，请重试。')
    assert not page.evaluate("window.accountRequests.some(x=>x.path.endsWith('/email/login'))")
    page.keyboard.press('Escape')
    expect(page.locator('.account-trigger')).to_be_focused()
    assert page.locator('.email-auth-password input').input_value()==''
    assert page.evaluate('localStorage.length')==0


def test_email_login_preserves_editing_lock_until_host_navigation(account_page):
    page=account_page;mount(page,email_session())
    page.route('**/api/auth/email/login',lambda route:route.fulfill(json=email_session(authenticated=True)))
    open_login(page);fill_login(page);page.evaluate('window.returnNavigation=true')
    page.locator('.email-auth-submit').click()
    expect(page.locator('.email-auth-dialog')).not_to_be_visible()
    assert page.evaluate('window.account.session.authenticated') is True
    assert page.evaluate('window.accountBusy')==['login']
    assert page.evaluate("window.account.openEmail('login')") is False
    page.evaluate('window.account.dispose()')
    assert page.evaluate('window.accountBusy')==['login',None]


def test_registration_code_cooldown_matching_password_and_session(account_page):
    page=account_page;mount(page,email_session());sent=[]
    page.route('**/api/auth/email/send-code',lambda route:(sent.append(route.request.post_data_json),route.fulfill(json={'message':'验证码已发送，请查收邮箱。','retry_after':60})))
    page.route('**/api/auth/email/register',lambda route:(sent.append(route.request.post_data_json),route.fulfill(json=email_session(authenticated=True))))
    open_login(page);page.get_by_role('tab',name='注册',exact=True).click()
    page.get_by_label('用户名',exact=True).fill('reader')
    page.get_by_label('邮箱',exact=True).fill('reader@example.test')
    page.get_by_role('button',name='获取验证码',exact=True).click()
    expect(page.locator('.email-auth-send-code')).to_be_disabled()
    expect(page.locator('.email-auth-send-code')).to_contain_text('秒后重发')
    page.get_by_label('邮箱验证码',exact=True).fill('123456')
    page.get_by_label('设置密码',exact=True).fill('synthetic-password')
    page.get_by_label('确认密码',exact=True).fill('different-password')
    page.locator('.email-auth-submit').click()
    expect(page.locator('.email-auth-message')).to_have_text('两次密码不一致，请检查后重试。')
    assert len(sent)==1
    page.get_by_label('确认密码',exact=True).fill('synthetic-password')
    page.locator('.email-auth-submit').click()
    expect(page.locator('.email-auth-dialog')).not_to_be_visible()
    assert sent==[{'email':'reader@example.test','purpose':'register'},{'username':'reader','email':'reader@example.test','password':'synthetic-password','code':'123456'}]
    assert page.evaluate('window.accountEvents.at(-1).reason')=='register'


def test_reset_returns_to_login_without_claiming_authenticated(account_page):
    page=account_page;mount(page,email_session());sent=[]
    page.route('**/api/auth/email/send-code',lambda route:(sent.append(route.request.post_data_json),route.fulfill(json={'retry_after':60})))
    page.route('**/api/auth/email/reset',lambda route:(sent.append(route.request.post_data_json),route.fulfill(json={'ok':True})))
    open_login(page);page.get_by_label('邮箱或用户名').fill('reader@example.test')
    page.get_by_role('button',name='忘记密码？').click()
    expect(page.get_by_label('邮箱',exact=True)).to_have_value('reader@example.test')
    page.get_by_role('button',name='获取验证码',exact=True).click()
    page.get_by_label('邮箱验证码',exact=True).fill('123456');page.get_by_label('新密码').fill('new-password');page.get_by_label('确认密码').fill('new-password')
    page.locator('.email-auth-submit').click()
    expect(page.locator('.email-auth-dialog')).to_have_attribute('data-mode','login')
    expect(page.locator('.email-auth-message')).to_have_text('密码已重设，请使用新密码登录。')
    assert sent==[{'email':'reader@example.test','purpose':'reset'},{'email':'reader@example.test','new_password':'new-password','code':'123456'}]
    assert page.evaluate('window.account.session.authenticated') is False
    expect(page.get_by_label('密码',exact=True)).to_have_value('')


def test_existing_unverified_account_binds_email_and_keeps_identity(account_page):
    page=account_page;mount(page,email_session(authenticated=True,verified=False,email=''));sent=[]
    page.route('**/api/auth/email/send-code',lambda route:(sent.append(route.request.post_data_json),route.fulfill(json={'retry_after':60})))
    page.route('**/api/auth/email/verify',lambda route:(sent.append(route.request.post_data_json),route.fulfill(json={**email_session(authenticated=True),'csrf':'verify_csrf'})))
    page.locator('.account-trigger').click();page.locator('.account-verify').click()
    expect(page.locator('.email-auth-title')).to_have_text('绑定常用邮箱')
    expect(page.get_by_label('邮箱',exact=True)).to_have_value('')
    page.get_by_label('邮箱',exact=True).fill('reader@example.test');page.get_by_role('button',name='获取验证码',exact=True).click()
    page.get_by_label('邮箱验证码',exact=True).fill('123456');page.locator('.email-auth-submit').click()
    expect(page.locator('.email-auth-dialog')).not_to_be_visible()
    assert sent==[{'email':'reader@example.test','purpose':'verify'},{'email':'reader@example.test','code':'123456'}]
    assert page.evaluate('window.accountEvents.at(-1).reason')=='verify'
    assert page.evaluate('window.account.session.user.email_verified') is True
    assert page.evaluate('window.accountCsrf')=='verify_csrf'


def test_smtp_missing_keeps_password_login_and_explains_code_unavailable(account_page):
    page=account_page;mount(page,email_session(configured=False));open_login(page)
    expect(page.locator('.email-auth-submit')).to_be_enabled()
    page.get_by_role('tab',name='注册',exact=True).click()
    expect(page.locator('.email-auth-submit')).to_be_disabled()
    expect(page.locator('.email-auth-send-code')).to_be_disabled()
    expect(page.locator('.email-auth-availability')).to_have_text('邮箱验证码服务尚未配置。')
    page.get_by_role('tab',name='登录',exact=True).click();expect(page.locator('.email-auth-submit')).to_be_enabled()


def test_vip_unlimited_usage_and_model_access_are_server_driven(account_page):
    page=account_page;mount(page,email_session(authenticated=True,role='vip',unlimited=True))
    page.locator('.account-trigger').click()
    expect(page.locator('.account-role')).to_have_text('VIP')
    expect(page.locator('.account-usage-balance')).to_have_text('账号不限次数')
    expect(page.locator('.account-usage-detail')).to_contain_text('全站当前可提交 2 次')
    expect(page.locator('.account-usage-meter')).to_be_hidden()
    expect(page.locator('.account-model-access')).to_have_text('可用模型：Qwen · ChatGPT · Claude')


def test_email_ui_mobile_keyboard_and_disposal(account_page):
    page=account_page;mount(page,email_session());page.set_viewport_size({'width':320,'height':568})
    page.emulate_media(reduced_motion='reduce');open_login(page)
    page.get_by_role('tab',name='登录',exact=True).focus();page.keyboard.press('ArrowRight')
    expect(page.get_by_role('tab',name='注册',exact=True)).to_be_focused()
    expect(page.locator('.email-auth-dialog')).to_have_attribute('data-mode','register')
    bounds=page.locator('.email-auth-dialog').bounding_box()
    assert bounds['x']>=13 and bounds['x']+bounds['width']<=307 and bounds['y']+bounds['height']<=555
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    output=ROOT/'tmp/email-auth-qa';output.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(output/'register-mobile.png'))
    page.set_viewport_size({'width':1000,'height':900});page.get_by_role('tab',name='登录',exact=True).click()
    page.screenshot(path=str(output/'login-desktop.png'))
    page.get_by_label('密码',exact=True).fill('sensitive-only-in-memory');page.evaluate('window.account.dispose();window.account.dispose()')
    expect(page.locator('.email-auth-dialog')).to_have_count(0)
