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
  page.locator('.agent-update-detail').click()
  page.wait_for_selector('.docs-release-latest')
  assert page.locator('#docs-version-select').input_value()=='update-v-0.4.4'
  page.wait_for_function("document.querySelector('[id=\"update-v-0.4.4\"]').getBoundingClientRect().top>document.querySelector('.docs-update-jump').getBoundingClientRect().bottom")
  assert page.locator('.docs-release-latest').get_by_text('分步可视化解题、教学课包与学习生态联动').count()==1
  Path('tests/artifacts').mkdir(exist_ok=True)
  page.locator('#docs-modal .modal-content').screenshot(path=f'tests/artifacts/release-notes-{kind}-{width}.png')
  page.locator('#docs-version-select').select_option('update-v-0.3.9')
  page.wait_for_function("Math.abs(document.querySelector('[id=\"update-v-0.3.9\"]').getBoundingClientRect().top-document.querySelector('.docs-update-jump').getBoundingClientRect().bottom-24)<3")
  page.locator('.docs-update-jump-btn').click()
  page.wait_for_function("document.querySelector('#docs-version-select').value==='update-v-0.4.4'")
  page.locator('.docs-release-latest a[href="#section-calculate-input"]').first.click()
  page.wait_for_function("document.activeElement.id==='tutor-problem'")
  assert not page.locator('#docs-modal').evaluate("el=>el.classList.contains('show')")
  async_open="() => window.openDoc('update.md','更新日志','update-v-0.4.4')"
  page.evaluate(async_open)
  page.locator('.docs-release-latest a[href="#section-examples-create-course"]').click()
  page.wait_for_selector('.course-editor')
  assert page.locator('.course-editor [name=name]').is_visible()
  page.locator('.course-dialog [data-close]').click()
  page.evaluate(async_open)
  page.locator('.docs-release-latest a[href="#section-my-formulas"]').click()
  page.wait_for_function("document.getElementById('my-formulas')?.checkVisibility()")
  page.evaluate("() => window.openDoc('update.md','更新日志','update-v-0.4.1')")
  page.locator('a[href="#section-formulas"]').first.click()
  page.wait_for_function("document.getElementById('my-formulas')?.checkVisibility()")
  page.evaluate(async_open)
  page.locator('.docs-release-latest a[href="#section-search"]').click()
  page.wait_for_function("document.activeElement.id==='nav-search-input'")
  page.evaluate(async_open)
  page.locator('.docs-release-latest a[href="#section-nebula"]').first.click()
  page.wait_for_function("!document.querySelector('#knowledge-panel').classList.contains('collapsed')")
  page.reload(wait_until='domcontentloaded')
  page.locator('.agent-update-close').click()
  page.reload(wait_until='domcontentloaded')
  page.wait_for_function('!!window.openDoc')
  assert not page.locator('#agent-update-banner').is_visible()
  assert not errors,errors
  browser.close()
