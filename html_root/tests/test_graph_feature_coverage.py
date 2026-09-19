"""Graph entry points navigate to real controls without submitting paid work."""
import os
import re
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires UI servers')


@pytest.mark.parametrize('base',['http://127.0.0.1:8000/?section=','http://127.0.0.1:5173/'])
@pytest.mark.parametrize('width',[1440,390])
def test_new_graph_features_navigate_without_billing(base,width):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':width,'height':950},reduced_motion='reduce')
        errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append((r.method,r.url)))
        page.goto(base+'home',wait_until='domcontentloaded')
        page.locator('#home').wait_for()
        page.wait_for_function('window.showSection && window.StepTutor')
        def open_node(node):
            return page.evaluate("""async id=>{const G=await import('/static/js/site-graph.js?v=20260917-ecosystem-6');return G.executeNodeAction(G.getNodeById(id));}""",node)
        # Search and open a new node through the actual graph UI.
        search=page.locator('.graph-explorer input')
        search.fill('大学例题')
        page.locator('[data-graph-node=curriculum-university]').click()
        page.locator('[data-node-open=curriculum-university]').click()
        expect(page.locator('.curriculum-card')).to_have_count(10)
        expect(page.locator('.curriculum-filters [data-filter=level]')).to_have_value('大学')
        assert all('大学' in s for s in page.locator('.curriculum-card>small').all_text_contents())
        assert open_node('curriculum-highschool')
        expect(page.locator('.curriculum-filters [data-filter=level]')).to_have_value('高中')
        expect(page.locator('.curriculum-card')).to_have_count(10)
        # Reading an existing worked example requires no model request.
        page.locator('.curriculum-card [data-read]').first.click()
        page.locator('.solution-reader[open] [data-reader=open]').click()
        page.locator('.tutor-result:not([hidden])').wait_for()
        for node,action in [('calc-export','export'),('calc-copy','copy'),('calc-course','pack'),('calc-wrongbook','wrongbook'),('calc-generate','render')]:
            assert open_node(node)
            expect(page.locator(f'.tutor-result [data-action={action}]')).to_be_visible()
            assert page.evaluate('document.activeElement.dataset.action')==action
        assert page.locator('.tutor-more').get_attribute('open') is not None
        assert open_node('calc-math-input')
        expect(page.locator('[data-input-mode=math]')).to_be_visible()
        # Switching to decomposition preserves the current draft and does not submit it.
        assert open_node('agent-tasks')
        page.locator('#agent-prompt').fill('保留我正在输入的题目')
        assert open_node('agent-decompose')
        expect(page.locator('[name=mathTaskMode]')).to_be_checked()
        expect(page.locator('#agent-prompt')).to_have_value('保留我正在输入的题目')
        assert open_node('detect-eraser')
        expect(page.locator('[data-shortcut=toolEraser]')).to_have_class(re.compile('active'))
        assert open_node('detect-recognize')
        assert page.evaluate('document.activeElement.classList.contains("btn-detect-primary")')
        assert open_node('home-account')
        expect(page.locator('.account-access-card')).to_be_visible()
        assert open_node('home-vip')
        assert page.evaluate('document.activeElement.classList.contains("vip-contact")')
        assert not open_node('home-admin')
        assert page.locator('.account-admin-dialog').count()==0
        assert not any('/api/admin/' in url for _,url in requests)
        assert open_node('home-nebula')
        expect(page.locator('#knowledge-panel')).not_to_have_class(re.compile(r'\bcollapsed\b'))
        page.locator('#knowledge-panel-close-btn').click()
        assert open_node('help-update')
        expect(page.locator('#docs-content')).to_have_class(re.compile('docs-changelog'))
        page.locator('#docs-modal .close-modal').click()
        assert open_node('help-solving')
        expect(page.locator('#docs-title')).to_have_text('分步解题指南')
        page.locator('#docs-modal .close-modal').click()
        assert open_node('examples-curriculum')
        page.evaluate("document.documentElement.dataset.theme='dark'")
        expect(page.locator('.course-import')).to_have_css('background-color','rgb(15, 23, 42)')
        # Native keyboard activation opens the import chooser.
        with page.expect_file_chooser():
            page.locator('.course-import').focus();page.keyboard.press('Enter')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        Path('tests/artifacts').mkdir(exist_ok=True)
        page.screenshot(path=f"tests/artifacts/graph-features-{'vue' if '5173' in base else 'static'}-{width}.png")
        paid=[url for method,url in requests if method=='POST' and any(s in url for s in ['/api/solve/','/api/agent/tasks','/api/agent/chat','/api/devtools/'])]
        assert not paid,paid
        assert not errors,errors
        browser.close()
