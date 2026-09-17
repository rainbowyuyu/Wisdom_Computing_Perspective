"""Browser regressions for unavailable editor assets and expired teaching sessions."""
import json
import os

import pytest

from app.store import CAPTCHA_STORE
from test_solution_library import accounts, live_library_server
from test_teaching import teaching_page
from test_agent_workspace import workspace, CODE

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires Chrome and servers')


@pytest.mark.parametrize('failed_asset', ['loader.js', 'editor/editor.main.js'])
def test_creator_recovers_from_editor_load_failure(workspace, failed_asset):
    page, _, _ = workspace
    page.route('https://cdnjs.cloudflare.com/**/monaco-editor/**', lambda r: r.abort())
    pattern = '**/static/vendor/monaco-editor/**/' + failed_asset
    page.route(pattern, lambda r: r.abort())
    page.evaluate("window.showSection('devtools')")
    page.wait_for_function("document.querySelector('#devtools')?.dataset.devInitialized")
    page.evaluate("window.switchDevTool('manim')")
    page.get_by_role('button', name='重新加载编辑器').wait_for()
    assert not page.evaluate('!!window.monacoEditor')
    page.unroute(pattern)
    # Generating a suggestion must itself retry and await the editor.
    page.route('**/api/devtools/edit_code', lambda r: r.fulfill(content_type='application/json', body=json.dumps({'status':'success','code':CODE,'summary':'绘制紫色圆'})))
    page.locator('#manim-ai-edit-input').fill('绘制紫色圆')
    page.locator('#manim-ai-edit-btn').click()
    page.wait_for_selector('.code-assistant-proposal:visible')
    page.locator('[data-code=apply]').click()
    assert page.evaluate('window.monacoEditor.getValue()') == CODE


@pytest.mark.parametrize('expire_after_open', [False, True])
def test_course_draft_survives_login_and_saves_to_database(teaching_page, live_library_server, expire_after_open):
    page, origin, kind = teaching_page
    _, (users, _) = live_library_server
    if not expire_after_open:
        page.context.clear_cookies()
    page.locator('#examples-create-course-btn').click()
    form = page.locator('.course-editor')
    form.locator('[name=name]').fill('登录后保留的教案')
    form.locator('[name=objectives]').fill(r'理解 $y=x^2$')
    page.wait_for_selector('.course-video-options [data-add]')
    form.locator('[data-add]').first.click()
    selected = form.locator('[data-selected-videos]').inner_text()
    if expire_after_open:
        page.context.clear_cookies()
    form.locator('[type=submit]').click()
    auth = page.locator('#auth-modal.show' if kind == 'static' else '.auth-account-dialog[open]')
    auth.wait_for()
    assert not form.is_visible()
    # Cancelling sign-in also restores the draft, without saving anything.
    if kind == 'static':
        page.evaluate('window.toggleAuthModal(false)')
    else:
        auth.get_by_role('button', name='关闭', exact=True).click()
    form.wait_for(state='visible')
    assert form.locator('[name=name]').input_value() == '登录后保留的教案'
    form.locator('[type=submit]').click()
    auth.wait_for()
    # Submit the real login form with a server-generated test captcha.
    if kind == 'static':
        with page.expect_response(lambda r: '/api/captcha' in r.url) as captcha:
            auth.locator('#captcha-img-login').click()
        auth.locator('#login-user').fill(users[0])
        auth.locator('#login-pass').fill('Library-QA-test-password')
        auth.locator('#login-captcha').fill(CAPTCHA_STORE[captcha.value.headers['x-captcha-id']])
        auth.locator('#login-agree').check()
        with page.expect_response('**/api/login') as logged_in:
            auth.locator('#btn-login-submit').click()
    else:
        auth.locator('.auth-captcha-row img').wait_for()
        with page.expect_response(lambda r: '/api/captcha' in r.url) as captcha:
            auth.get_by_role('button', name='刷新验证码').click()
        auth.get_by_label('用户名').fill(users[0])
        auth.get_by_label('密码', exact=True).fill('Library-QA-test-password')
        auth.locator('input[autocomplete=off]').fill(CAPTCHA_STORE[captcha.value.headers['x-captcha-id']])
        with page.expect_response('**/api/login') as logged_in:
            auth.locator('[type=submit]').click()
    assert logged_in.value.status == 200, logged_in.value.text()
    form.wait_for(state='visible')
    assert form.locator('[data-selected-videos]').inner_text() == selected
    with page.expect_response(lambda r: r.url.endswith('/course-packs') and r.request.method == 'POST') as saved:
        form.locator('[type=submit]').click()
    ident = saved.value.json()['id']
    page.wait_for_selector('.lesson-reader .katex')
    restored = page.request.get(origin + f'/api/examples/course-packs/{ident}').json()['data']
    assert restored['name'] == '登录后保留的教案'
    assert restored['lesson']['objectives'] == r'理解 $y=x^2$'
    assert len(restored['video_ids']) == 1


def test_course_catalog_failure_does_not_block_lesson(teaching_page):
    page, origin, _ = teaching_page
    page.route('**/api/examples', lambda r: r.fulfill(status=503, content_type='application/json', body='{"status":"error"}'))
    page.locator('#examples-create-course-btn').click()
    form = page.locator('.course-editor')
    form.locator('[name=name]').fill('无需视频的教案')
    page.get_by_role('button', name='重新加载视频').wait_for()
    page.unroute('**/api/examples')
    page.get_by_role('button', name='重新加载视频').click()
    form.locator('[data-add]').first.wait_for()
    assert form.locator('[name=name]').input_value() == '无需视频的教案'
    page.route('**/api/examples', lambda r: r.abort())
    with page.expect_response(lambda r: r.url.endswith('/course-packs') and r.request.method == 'POST') as saved:
        form.locator('[type=submit]').click()
    page.wait_for_selector('.lesson-reader')
    ident = saved.value.json()['id']
    assert page.request.get(origin + f'/api/examples/course-packs/{ident}').json()['data']['video_ids'] == []
