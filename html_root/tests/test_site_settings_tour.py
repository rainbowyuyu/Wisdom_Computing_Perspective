"""The shared settings and guide work in both shells, without submitting work."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires UI servers')


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=home','http://127.0.0.1:5173/home'])
def test_settings_persistence_and_complete_tour(base):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':390,'height':950},reduced_motion='reduce')
        errors=[];paid=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:paid.append(r.url) if r.method=='POST' and any(x in r.url for x in ['/api/solve','/api/agent','/api/detect','/api/devtools']) else None)
        page.goto(base,wait_until='domcontentloaded');page.locator('#home').wait_for()
        page.wait_for_function('!!(window.openSettings && window.startTutorial)')
        page.evaluate("Promise.all([window.openSettings('agent'),window.openSettings('agent')])")
        expect(page.locator('#settings-modal')).to_have_count(1)
        page.locator('.settings-toggle:has(#agent-enter-send)').click()
        assert page.evaluate("localStorage.getItem('agent_enter_send')")=='false'
        page.evaluate('window.closeSettings()')
        page.evaluate("window.openSettings('agent')")
        expect(page.locator('#agent-enter-send')).not_to_be_checked()
        page.evaluate("window.openSettings('appearance')")
        page.locator('#theme-toggle-btn').click()
        expect(page.locator('html')).to_have_attribute('data-theme','dark')
        page.evaluate("window.openSettings('profile')")
        expect(page.locator('#settings-profile-guest')).to_be_visible()
        Path('tests/artifacts').mkdir(exist_ok=True)
        label='vue' if '5173' in base else 'static'
        page.screenshot(path=f'tests/artifacts/settings-{label}-mobile.png')
        page.evaluate('window.closeSettings()')
        page.locator('#settings-modal').wait_for(state='hidden')
        page.evaluate('window.startTutorial()')
        titles=['先了解你的学习账户','从一道典型例题开始','输入题目，探索每一步','复杂题交给后台任务','把理解积累成学习资料','随时从星云继续探索']
        for title in titles:
            expect(page.locator('.driver-popover-title')).to_have_text(title)
            page.locator('.driver-popover-next-btn').click()
        expect(page.locator('.driver-popover')).to_have_count(0)
        expect(page.locator('#knowledge-panel-bubble-inner')).to_be_attached()
        assert not paid,paid
        assert not errors,errors
        browser.close()
