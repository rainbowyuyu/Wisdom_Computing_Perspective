"""Brand, discover links and account round-trip UX in isolated browser data."""
from pathlib import Path
from playwright.sync_api import expect
from test_browser import browser, local_server, workbench

ARTIFACTS=Path(__file__).resolve().parents[1]/'tmp'/'wiscomper-qa'


def test_brand_responsive_navigation_and_account_unconfigured(workbench):
    page,_=workbench
    expect(page).to_have_title('Wiscomper 智算视界 · Wisdom Computer Perspective')
    expect(page.locator('.brand')).to_contain_text('智算视界')
    expect(page.locator('.account-trigger')).to_contain_text('GitHub')
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(ARTIFACTS/'desktop.png'))
    page.locator('.account-trigger').click()
    expect(page.locator('.account-panel')).to_be_visible()
    expect(page.locator('.account-primary')).to_be_disabled()
    page.locator('.account-close').click()
    for width in (390,320,711,1080):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        if width<951:
            page.locator('[data-workspace-jump="create"]').click()
            expect(page.locator('#prompt')).to_be_focused()
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.app-header').scroll_into_view_if_needed()
    page.screenshot(path=str(ARTIFACTS/'mobile.png'))


def test_public_discover_links_choose_sample_once_and_restore_draft(workbench):
    page,_=workbench
    base=page.url.split('?')[0]
    page.goto(base+'?sample=fan')
    expect(page.locator('#scene-mode')).to_have_text('3D',timeout=20000)
    expect(page).not_to_have_url(__import__('re').compile('sample='))
    count=page.locator('#project-count').inner_text()
    page.reload()
    expect(page.locator('#scene-mode')).to_have_text('3D',timeout=20000)
    expect(page.locator('#project-count')).to_have_text(count)
    page.evaluate("""sessionStorage.setItem('wiscomper.auth-draft',JSON.stringify({prompt:'解释振幅与频率',mode:'formula',provider:'qwen',duration:'20',targetId:null,saved:Date.now()}))""")
    page.reload()
    expect(page.locator('#prompt')).to_have_value('解释振幅与频率',timeout=20000)
    expect(page.locator('#provider')).to_have_value('qwen')
    expect(page.locator('#iterate')).not_to_be_checked()
    assert page.evaluate("sessionStorage.getItem('wiscomper.auth-draft')") is None
    page.goto(base+'about')
    expect(page.get_by_role('heading',level=1)).to_be_visible()
    assert '智算视界' in page.title()


def test_late_oauth_image_restore_cannot_overwrite_new_exploration(workbench):
    import base64
    page,_=workbench
    ident='a'*32
    pending=[]
    page.route('**/api/assets/'+ident,lambda route:pending.append(route))
    page.evaluate("""id=>sessionStorage.setItem('wiscomper.auth-draft',JSON.stringify({prompt:'old image draft',mode:'image',provider:'chatgpt',duration:'12',assetId:id,saved:Date.now()}))""",ident)
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('#prompt')).to_have_value('old image draft')
    expect(page.locator('#generate')).to_be_disabled()
    page.locator('#new-project').click()
    page.locator('#prompt').fill('my new idea')
    assert pending
    pending[0].fulfill(status=200,content_type='image/png',body=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1cAAAAASUVORK5CYII='))
    expect(page.locator('#generate')).to_be_enabled()
    expect(page.locator('#asset-preview')).to_be_hidden()
    expect(page.locator('#prompt')).to_have_value('my new idea')
