import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright,expect

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local web servers')


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=','http://127.0.0.1:5173/'])
def test_entitlements_application_owner_entry_and_shared_help(base):
    state={'role':'member','owner':False}
    def access(route):
        role=state['role'];unlimited=role in ['vip','admin']
        quotas={'all':{'limit':None if unlimited else 40,'remaining':None if unlimited else 12,'used':28}}
        if role=='guest':quotas={key:{'limit':n,'remaining':n,'used':0} for key,n in [('calculate',3),('recognize',2),('assistant',2),('code',2),('render',3)]}
        route.fulfill(json={'role':role,'can_manage':state['owner'],'username':None if role=='guest' else 'rainbow_yu' if state['owner'] else '学习者','quotas':quotas})
    def me(route):
        route.fulfill(status=401 if state['role']=='guest' else 200,json={'status':'success','username':'rainbow_yu' if state['owner'] else '学习者'})
    def admin(route):
        route.fulfill(json={'items':[],'page':1,'total':0,'settings':{'daily_limit':40,'contact_email':'author@example.com'}})
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write'],reduced_motion='reduce')
        page=context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/api/account/access',access);page.route('**/api/user/me',me);page.route('**/api/admin/**',admin)
        page.goto(base+'home' if '?' in base else base,wait_until='domcontentloaded')
        page.locator('.desktop-auth [data-access-details]').click()
        dialog=page.locator('.account-details-dialog[open]')
        expect(dialog).to_contain_text('12 / 40');expect(dialog).to_contain_text('如何申请 VIP')
        assert dialog.locator('.access-application-actions a').get_attribute('href')=='https://github.com/rainbowyuyu'
        dialog.locator('[data-copy]').click();expect(dialog.locator('[data-copy-status]')).to_contain_text('申请说明已复制')
        assert '智算视界用户名：学习者' in page.evaluate('navigator.clipboard.readText()')
        label='vue' if '5173' in base else 'static'
        Path('tests/artifacts').mkdir(exist_ok=True)
        for width,theme in [(1440,'light'),(390,'dark')]:
            page.set_viewport_size({'width':width,'height':1000});page.evaluate('(v)=>document.documentElement.dataset.theme=v',theme);page.wait_for_timeout(350)
            assert dialog.evaluate('e=>e.scrollWidth<=e.clientWidth+2')
            page.screenshot(path=f'tests/artifacts/entitlements-{label}-{width}.png')
        dialog.locator('[data-help]').click()
        page.locator('#help-search-input').fill('VIP')
        expect(page.locator('[data-faq=vip]')).to_be_visible()
        page.locator('#help-search-input').fill('zzzzzz-no-match')
        expect(page.locator('.help-empty')).to_be_visible()
        page.locator('#help-search-input').fill('')
        expect(page.locator('[data-faq]')).to_have_count(13)
        page.locator('[data-help-action=guide]').click();expect(page.locator('#docs-title')).to_have_text('分步解题指南')
        page.locator('#docs-modal .close-modal').click()
        state.update(role='admin',owner=False)
        page.evaluate("window.dispatchEvent(new CustomEvent('auth-state-change'))")
        expect(page.locator('[data-help-action=admin]')).to_be_hidden()
        page.locator('[data-help-action=access]').click()
        expect(dialog).to_contain_text('管理员身份');expect(dialog.locator('[data-admin]')).to_have_count(0)
        expect(dialog).to_contain_text('不会开放管理后台')
        # Auth changes dismiss the previous account's entitlement panel.
        state.update(role='guest');page.evaluate("window.dispatchEvent(new CustomEvent('auth-state-change'))")
        expect(dialog).to_have_count(0)
        page.locator('[data-help-action=access]').click()
        expect(dialog).to_contain_text('3 / 3');expect(dialog.locator('[data-copy]')).to_be_disabled()
        page.keyboard.press('Escape');expect(dialog).to_have_count(0)
        state.update(role='admin',owner=True)
        page.goto(base+'home' if '?' in base else base,wait_until='domcontentloaded')
        for width,theme in [(1440,'light'),(390,'dark'),(320,'light')]:
            page.set_viewport_size({'width':width,'height':1000});page.evaluate('(v)=>document.documentElement.dataset.theme=v',theme)
            scope='.desktop-auth' if width>900 else '.mobile-account-access'
            expect(page.locator(scope+' [data-access-admin]')).to_have_text('管理中心')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
            page.wait_for_timeout(350);page.screenshot(path=f'tests/artifacts/owner-entry-{label}-{width}.png')
        page.locator('.mobile-account-access [data-access-admin]').click()
        expect(page.locator('.account-admin-page h1')).to_have_text('用户管理')
        page.evaluate("window.showSection('help')")
        expect(page.locator('[data-help-action=admin]')).to_be_visible()
        page.locator('#help-search-input').fill('请求记录')
        expect(page.locator('[data-faq=requests]')).to_be_visible()
        page.screenshot(path=f'tests/artifacts/help-latest-{label}.png',full_page=True)
        assert not errors,errors
        browser.close()
