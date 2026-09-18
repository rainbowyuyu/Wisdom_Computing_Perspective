"""Release announcement, stable version anchors and real cross-page destinations."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local web servers')

@pytest.mark.parametrize('origin,path,kind',[
 ('http://127.0.0.1:8000','/?section=calculate','static'),
 ('http://127.0.0.1:5173','/calculate','vue')])
@pytest.mark.parametrize('width',[1280,390])
def test_release_notes_navigation(origin,path,kind,width):
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='chrome',headless=True)
  page=browser.new_page(viewport={'width':width,'height':950})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(origin+path,wait_until='domcontentloaded')
  page.wait_for_function('!!window.openDoc')
  layout=page.locator('.agent-update-detail').evaluate('''el => {
    const a=el.getBoundingClientRect(), close=document.querySelector('.agent-update-close').getBoundingClientRect();
    const range=document.createRange();range.selectNodeContents(el);const text=range.getBoundingClientRect();
    return {fits: text.left>=a.left && text.right<=a.right && text.top>=a.top && text.bottom<=a.bottom,
      separate: a.right<=close.left || a.top>=close.bottom, nowrap: getComputedStyle(el).whiteSpace==='nowrap'};
  }''')
  assert all(layout.values()),layout
  page.locator('.agent-update-detail').click()
  page.wait_for_selector('.docs-release-latest')
  assert page.locator('#docs-version-select').input_value()=='update-v-0.4.5'
  page.wait_for_function("document.querySelector('[id=\"update-v-0.4.5\"]').getBoundingClientRect().top>document.querySelector('.docs-update-jump').getBoundingClientRect().bottom")
  assert page.locator('.docs-release-latest').get_by_text('首页全屏渐变、解题进度与部署体验优化').count()==1
  headings=page.locator('.docs-release h2').all_text_contents()
  assert len(headings)==29
  assert headings[0].strip()=='v 0.4.5' and headings[-1].strip()=='初始版'
  versions=[tuple(map(int,h.lower().replace('v','').strip().split('.'))) for h in headings[:-1]]
  assert versions==sorted(versions,reverse=True)
  page.wait_for_function("document.querySelector('#docs-content').scrollTop===0")
  # Sample the whole document, including the old bottom, to catch empty scroll extents.
  for fraction in (0,.25,.5,.75,1):
   page.locator('#docs-content').evaluate('(el,f)=>el.scrollTo({top:(el.scrollHeight-el.clientHeight)*f,behavior:"instant"})',fraction)
   page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
   visible=page.locator('#docs-content').evaluate('''el=>{
     const box=el.getBoundingClientRect(), walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
     let count=0;
     while(walker.nextNode()){
       const node=walker.currentNode;if(!node.textContent.trim())continue;
       const range=document.createRange();range.selectNodeContents(node);
       if([...range.getClientRects()].some(r=>r.width>0&&r.bottom>box.top&&r.top<box.bottom))count++;
     }
     return count;
   }''')
   assert visible>0,('blank document viewport',fraction)
  assert page.locator('#docs-version-select').input_value().startswith('update-initial-')
  assert page.locator('#docs-modal .modal-content').evaluate('el=>el.scrollTop===0')
  Path('tests/artifacts').mkdir(exist_ok=True)
  page.locator('#docs-modal .modal-content').screenshot(path=f'tests/artifacts/release-notes-bottom-{kind}-{width}.png')
  # Wheel overscroll stays inside the document, and a jump returns to the newest card.
  scroll_before=page.evaluate('window.scrollY')
  page.locator('#docs-content').hover()
  page.mouse.wheel(0,1200)
  page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(resolve))')
  assert page.evaluate('window.scrollY')==scroll_before
  page.locator('.docs-update-jump-btn').click()
  page.wait_for_function("document.querySelector('#docs-version-select').value==='update-v-0.4.5'")
  Path('tests/artifacts').mkdir(exist_ok=True)
  page.locator('#docs-modal .modal-content').screenshot(path=f'tests/artifacts/release-notes-{kind}-{width}.png')
  page.locator('#docs-version-select').select_option('update-v-0.3.9')
  page.wait_for_function("Math.abs(document.querySelector('[id=\"update-v-0.3.9\"]').getBoundingClientRect().top-document.querySelector('.docs-update-jump').getBoundingClientRect().bottom-24)<3")
  page.locator('.docs-update-jump-btn').click()
  page.wait_for_function("document.querySelector('#docs-version-select').value==='update-v-0.4.5'")
  page.locator('.docs-release-latest a[href="#section-calculate-input"]').first.click()
  page.wait_for_function("document.activeElement.id==='tutor-problem'")
  assert not page.locator('#docs-modal').evaluate("el=>el.classList.contains('show')")
  async_open="() => window.openDoc('update.md','更新日志','update-v-0.4.4')"
  page.evaluate(async_open)
  page.locator('.docs-release:has([id="update-v-0.4.4"]) a[href="#section-examples-create-course"]').click()
  page.wait_for_selector('.course-editor')
  assert page.locator('.course-editor [name=name]').is_visible()
  page.locator('.course-dialog [data-close]').click()
  page.evaluate(async_open)
  page.locator('.docs-release:has([id="update-v-0.4.4"]) a[href="#section-my-formulas"]').click()
  page.wait_for_function("document.getElementById('my-formulas')?.checkVisibility()")
  page.evaluate("() => window.openDoc('update.md','更新日志','update-v-0.4.1')")
  page.locator('a[href="#section-formulas"]').first.click()
  page.wait_for_function("document.getElementById('my-formulas')?.checkVisibility()")
  page.evaluate(async_open)
  page.locator('.docs-release:has([id="update-v-0.4.4"]) a[href="#section-search"]').click()
  page.wait_for_function("document.activeElement.id==='nav-search-input'")
  page.evaluate(async_open)
  page.locator('.docs-release:has([id="update-v-0.4.4"]) a[href="#section-nebula"]').first.click()
  page.wait_for_function("!document.querySelector('#knowledge-panel').classList.contains('collapsed')")
  page.reload(wait_until='domcontentloaded')
  page.locator('.agent-update-close').click()
  page.reload(wait_until='domcontentloaded')
  page.wait_for_function('!!window.openDoc')
  assert not page.locator('#agent-update-banner').is_visible()
  assert not errors,errors
  browser.close()


@pytest.mark.parametrize('width',[320,1280])
def test_banner_with_cached_legacy_home_styles(width):
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='chrome',headless=True)
  page=browser.new_page(viewport={'width':width,'height':950})
  page.route('**/pages/home.css',lambda route:route.fulfill(content_type='text/css',body='''
    .agent-update-banner{display:flex;gap:.5rem;padding:.5rem 1rem}
    .agent-update-detail{display:inline-flex;width:1.25rem;height:1.25rem;border-radius:50%;line-height:1;flex-shrink:0}
    .agent-update-detail:hover{transform:scale(1.1)}
  '''))
  page.goto('http://127.0.0.1:8000/?section=detect',wait_until='domcontentloaded')
  page.wait_for_function('!!window.openDoc')
  link=page.locator('.agent-update-detail')
  assert link.evaluate("e=>getComputedStyle(e).whiteSpace==='nowrap' && e.offsetWidth>90 && e.offsetHeight>=32")
  page.locator('#agent-update-banner').screenshot(path=f'tests/artifacts/release-banner-cached-{width}.png')
  link.click()
  page.wait_for_selector('.docs-release-latest')
  browser.close()
