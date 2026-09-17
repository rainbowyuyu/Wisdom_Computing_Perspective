"""Verify real page boot, including a browser with cached pre-assistant scripts."""
import json
import os

import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires local web servers and Chrome')


@pytest.mark.parametrize('origin,path', [
    ('http://127.0.0.1:8000', '/?section=devtools'),
    ('http://127.0.0.1:5173', '/devtools'),
])
def test_creator_boots_despite_old_cached_scripts_and_recovers_partial_mount(origin, path):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        # Old cached scripts used to silently skip the new assistant placeholder.
        stale = []
        def cached_old_script(route):
            stale.append(route.request.url)
            route.fulfill(content_type='text/javascript', body='/* cached old release */')
        page.route('**/js/main.js', cached_old_script)
        page.route('**/js/devtools.js', cached_old_script)
        page.route('**/js/code-assistant.js', cached_old_script)
        page.goto(origin + path, wait_until='domcontentloaded')
        # No explicit window.initDevTools call: the page must initialize itself.
        page.locator('#devtools .tab-btn').filter(has_text='Manim').click()
        page.locator('.code-assistant-form').wait_for(state='visible')
        assert not stale, stale
        assert '正在准备创作助手' not in page.locator('#manim-ai-edit-float').inner_text()
        page.wait_for_function('!!window.monacoEditor')
        # A partially restored shell must not be skipped due to stale dataset flags.
        page.evaluate("""() => {
            const panel=document.querySelector('#manim-ai-edit-float');
            panel.innerHTML='<p class="code-assistant-status">正在准备创作助手…</p>';
            panel.dataset.assistantMounted='true';
            document.querySelector('#devtools').dataset.devInitialized='true';
        }""")
        page.locator('#devtools .tab-btn').filter(has_text='Manim').click()
        page.locator('.code-assistant-form').wait_for(state='visible')
        code = 'from manim import *\nclass GenScene(Scene):\n    def construct(self):\n        self.add(Circle())\n'
        requests = []
        def generated(route):
            requests.append(route.request.post_data_json)
            route.fulfill(content_type='application/json', body=json.dumps({'status':'success','code':code,'summary':'绘制圆'}))
        page.route('**/api/devtools/edit_code', generated)
        page.locator('#manim-ai-edit-input').fill('绘制圆')
        page.locator('#manim-ai-edit-btn').click()
        page.locator('.code-assistant-proposal').wait_for(state='visible')
        original = page.evaluate('window.monacoEditor.getValue()')
        page.locator('[data-code=apply]').click()
        assert page.evaluate('window.monacoEditor.getValue()') == code
        page.locator('[data-code=undo]').click()
        assert page.evaluate('window.monacoEditor.getValue()') == original
        assert len(requests) == 1
        assert not errors, errors
        browser.close()
