"""Independent guide tests use real module files, no generation/auth calls."""
from pathlib import Path

import pytest
from playwright.sync_api import expect
from test_browser import browser  # noqa: F401

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def tour_page(browser):
    context=browser.new_context(viewport={"width":1100,"height":800})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/*',lambda route:route.abort())
    for name,mime in [('onboarding.js','text/javascript'),('onboarding.css','text/css')]:
        page.route('**/web/'+name,lambda route,request,name=name,mime=mime:route.fulfill(path=str(ROOT/'web'/name),content_type=mime))
    page.route('**/tour-test',lambda route:route.fulfill(content_type='text/html',body='''<!doctype html>
    <html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/web/onboarding.css"></head>
    <body style="margin:0;font-family:Arial,sans-serif;background:#f8fafc"><header style="display:flex;padding:12px;justify-content:space-between"><nav class="ecosystem-nav"><button id="open-help">帮助</button><button id="open-library">公式库</button></nav><div id="account-menu"><button>GitHub登录</button></div></header>
    <main style="display:flex;flex-wrap:wrap;gap:20px;padding:20px"><aside style="width:280px"><button id="creation-tab">创作</button><button id="history-tab">项目</button><div id="composer" style="margin:15px 0;padding:16px;background:white"><textarea id="prompt">保留草稿</textarea></div><select id="sample-filter"><option>全部方案</option></select></aside>
    <section style="width:340px;max-width:100%"><div class="stage-actions"><button>版本</button><button>导出</button></div><div id="scene-host" style="height:200px;background:#e6edfb">预览</div><div class="timeline" style="padding:20px;background:white"><button id="play">播放</button><input type="range"></div></section>
    <aside><button id="detail-tab">场景</button><div id="interaction-section" style="padding:20px;background:white">交互探索</div></aside></main></body></html>'''))
    page.goto('http://tour.test/tour-test')
    page.evaluate('''async()=>{
      const {mountOnboarding}=await import('/web/onboarding.js');
      window.results=[];window.notifications=[];window.workspaceKeys=[];
      document.addEventListener('keydown',event=>window.workspaceKeys.push(event.key));
      window.tour=mountOnboarding({onComplete:result=>window.results.push(result),notify:text=>window.notifications.push(text)});
    }''')
    yield page
    context.close();assert not errors


def test_full_guide_navigation_skip_replay_and_focus(tour_page):
    page=tour_page
    page.locator('#open-help').focus()
    assert page.evaluate('window.tour.start()')
    expect(page.locator('.onboarding-overlay')).to_be_visible()
    expect(page.locator('.onboarding-title')).to_have_text('写下你想看懂的内容')
    expect(page.locator('.onboarding-previous')).to_be_disabled()
    expect(page.locator('.onboarding-next')).to_be_focused()
    output=ROOT/'tmp'/'browser-qa';output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'onboarding-desktop.png'))
    page.keyboard.press('Tab');expect(page.locator('.onboarding-skip')).to_be_focused()
    page.keyboard.press('Shift+Tab');expect(page.locator('.onboarding-next')).to_be_focused()
    page.keyboard.press('ArrowRight');expect(page.locator('.onboarding-progress')).to_have_text('2 / 7')
    page.locator('.onboarding-previous').click();expect(page.locator('.onboarding-progress')).to_have_text('1 / 7')
    for _ in range(6):page.locator('.onboarding-next').click()
    expect(page.locator('.onboarding-next')).to_have_text('开始探索')
    expect(page.locator('.onboarding-replay')).to_be_visible()
    page.locator('.onboarding-replay').click();expect(page.locator('.onboarding-progress')).to_have_text('1 / 7')
    assert page.evaluate('window.results')==[]
    for _ in range(7):page.locator('.onboarding-next').click()
    expect(page.locator('.onboarding-overlay')).to_be_hidden()
    expect(page.locator('#open-help')).to_be_focused()
    expect(page.locator('#prompt')).to_have_value('保留草稿')
    assert page.evaluate('window.results')==[{"completed":True,"skipped":False}]
    assert page.evaluate('window.workspaceKeys')==[]
    page.evaluate('window.tour.start()');page.keyboard.press('Escape')
    assert page.evaluate('window.results')[-1]=={"completed":False,"skipped":True}
    page.evaluate('window.tour.start()');page.locator('.onboarding-skip').click()
    assert len(page.evaluate('window.results'))==3


def test_small_viewport_reduced_motion_scroll_restore_and_cleanup(tour_page):
    page=tour_page
    page.set_viewport_size({"width":320,"height":568});page.emulate_media(reduced_motion='reduce')
    page.evaluate('scrollTo(0,100)');original=page.evaluate('scrollY')
    page.evaluate('window.tour.start()')
    output=ROOT/'tmp'/'browser-qa';output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'onboarding-mobile.png'))
    for _ in range(7):
        card=page.locator('.onboarding-card').bounding_box()
        assert card['x']>=13 and card['y']>=13 and card['x']+card['width']<=307 and card['y']+card['height']<=555
        assert page.evaluate("getComputedStyle(document.querySelector('.onboarding-card')).transitionDuration")=='0s'
        page.locator('.onboarding-next').click()
    assert page.evaluate('scrollY')==original
    page.evaluate('window.tour.start();window.tour.dispose();window.tour.dispose()')
    expect(page.locator('.onboarding-overlay')).to_have_count(0)
    assert page.evaluate('window.tour.start()') is False
    assert len(page.evaluate('window.results'))==1


def test_missing_targets_and_other_dialog_are_safe(tour_page):
    page=tour_page
    page.evaluate("document.querySelector('#composer').remove();document.querySelector('#creation-tab').remove()")
    assert page.evaluate('window.tour.start()')
    expect(page.locator('.onboarding-title')).to_have_text('先试一个本地示例')
    expect(page.locator('.onboarding-progress')).to_have_text('1 / 6')
    page.evaluate("document.querySelector('#sample-filter').remove();dispatchEvent(new Event('resize'))")
    expect(page.locator('.onboarding-missing')).to_be_visible()
    page.keyboard.press('Escape')
    page.evaluate("window.other=document.createElement('dialog');document.body.append(window.other);window.other.showModal()")
    assert page.evaluate('window.tour.start()') is False
    page.evaluate("window.other.close();document.querySelector('header').remove();document.querySelector('main').remove()")
    assert page.evaluate('window.tour.start()') is False
    assert len(page.evaluate('window.notifications'))==2
