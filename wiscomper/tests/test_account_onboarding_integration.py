"""Real workbench integration; all custom generation remains blocked by fixture."""
from pathlib import Path

from playwright.sync_api import expect
from test_browser import browser,local_server,workbench  # noqa: F401

OUTPUT=Path(__file__).resolve().parents[1]/'tmp'/'browser-qa'


def open_help(page):
    page.locator('.workspace-more > summary').click()
    page.locator('#open-help').click()
    expect(page.locator('#kw-help')).to_be_visible()


def test_help_shortcuts_reach_workspace_and_tutorial(workbench):
    page,_=workbench
    for action,title in [('learning','学习资料'),('course-packs','教案与课包'),('settings','偏好设置'),('achievements','探索足迹'),('releases','版本动态')]:
        open_help(page)
        page.locator(f'[data-help-action="{action}"]').click()
        expect(page.locator('#knowledge-workspace')).not_to_be_visible()
        expect(page.locator('#workspace-center')).to_be_visible()
        expect(page.locator('#wc-title')).to_have_text(title)
        expect(page.locator('.wc-loading')).to_have_count(0)
        page.locator('#wc-close').click()
    open_help(page)
    expect(page.locator('#kw-help')).to_contain_text('区分作品版本与站点动态')
    page.locator('[data-help-action="tutorial"]').click()
    expect(page.locator('.onboarding-overlay')).to_be_visible()
    expect(page.locator('#knowledge-workspace')).not_to_be_visible()
    expect(page.locator('.onboarding-next')).to_be_focused()
    OUTPUT.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(OUTPUT/'app-onboarding-desktop.png'))
    page.locator('.onboarding-skip').click()
    expect(page.locator('#welcome-hint')).to_be_hidden()
    page.reload();expect(page.locator('#play')).to_be_enabled(timeout=20000)
    expect(page.locator('#welcome-hint')).to_be_hidden()


def test_account_usage_and_preferences_match_server(workbench):
    page,_=workbench
    page.locator('.account-trigger').click()
    expect(page.locator('.account-loading')).to_be_hidden()
    data=page.request.get(page.url.rstrip('/')+'/api/auth/session').json()
    expect(page.locator('.account-usage-balance')).to_have_text(f"还可提交 {data['usage']['available']} 次")
    expect(page.locator('.account-panel input')).to_have_count(0)
    assert page.request.get(page.url.rstrip('/')+'/web/github-setup.html').status==200
    page.keyboard.press('Escape')
    open_help(page);page.locator('[data-help-action="settings"]').click()
    speed=page.get_by_role('combobox',name='默认播放速度',exact=True)
    speed.select_option('0.75')
    expect(page.locator('.wc-status')).to_have_text('设置已保存')
    page.locator('#wc-close').click()
    expect(page.locator('#speed')).to_have_value('0.75')
    page.reload();expect(page.locator('#play')).to_be_enabled(timeout=20000)
    expect(page.locator('#speed')).to_have_value('0.75')
    page.set_viewport_size({'width':360,'height':740})
    page.locator('.workspace-more > summary').click()
    page.locator('.workspace-more [data-ecosystem-action="tutorial"]').click()
    expect(page.locator('.onboarding-overlay')).to_be_visible()
    OUTPUT.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(OUTPUT/'app-onboarding-mobile.png'))
    bounds=page.locator('.onboarding-card').bounding_box()
    assert bounds['x']>=13 and bounds['x']+bounds['width']<=347 and bounds['y']+bounds['height']<=727
    page.keyboard.press('Escape')


def test_sketch_png_upload_preserves_prompt_without_generating(workbench):
    page,_=workbench
    sizes=page.locator('.input-tabs button').evaluate_all('(buttons)=>buttons.map(button=>button.getBoundingClientRect().height)')
    assert max(sizes)-min(sizes)<2
    assert max(sizes)<45
    page.locator('#prompt').fill('请解释我画出的运动关系，保留这段说明。')
    requests=[]
    page.on('request',lambda request:requests.append(request.url) if request.method=='POST' and request.url.endswith('/api/jobs') else None)
    page.locator('[data-ecosystem-action="sketch"]').click()
    expect(page.locator('.sketch-dialog')).to_be_visible()
    canvas=page.locator('.sketch-canvas');bounds=canvas.bounding_box()
    page.mouse.move(bounds['x']+bounds['width']*.2,bounds['y']+bounds['height']*.4);page.mouse.down()
    page.mouse.move(bounds['x']+bounds['width']*.7,bounds['y']+bounds['height']*.6,steps=12);page.mouse.up()
    with page.expect_response(lambda response:response.url.endswith('/api/assets') and response.request.method=='POST') as uploaded:
        page.locator('.sketch-submit').click()
    assert uploaded.value.status==200
    expect(page.locator('.sketch-dialog')).not_to_be_visible()
    expect(page.locator('#asset-preview')).to_be_visible()
    expect(page.locator('#prompt')).to_have_value('请解释我画出的运动关系，保留这段说明。')
    expect(page.locator('[data-mode="image"]')).to_have_attribute('aria-selected','true')
    assert page.locator('#asset-image').evaluate('img=>img.naturalWidth')==1200
    assert requests==[]
    page.set_viewport_size({'width':320,'height':700})
    toolbar=page.locator('.input-tabs').bounding_box()
    for button in page.locator('.input-tabs button').all():
        button_box=button.bounding_box();assert button_box['x']>=toolbar['x'] and button_box['x']+button_box['width']<=toolbar['x']+toolbar['width']+1
    page.locator('[data-ecosystem-action="sketch"]').click()
    expect(page.locator('.sketch-submit')).to_be_enabled()
    page.keyboard.press('Escape')
