"""The actual floating rail locates the selected math tool without losing input."""
import os

import pytest
from playwright.sync_api import sync_playwright
from logic.solution_engine import local_solution

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local Chrome and web servers')


@pytest.mark.parametrize('origin,path',[
    ('http://127.0.0.1:8000','/?section=calculate'),
    ('http://127.0.0.1:5173','/calculate'),
])
@pytest.mark.parametrize('width',[1280,390])
def test_metro_input_and_step_targets(origin,path,width):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':width,'height':900})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(origin+path,wait_until='domcontentloaded')
        page.locator('.tutor-composer').wait_for()
        page.wait_for_function("document.querySelector('#knowledge-panel')?.dataset.floatingReady")
        page.locator('#tutor-problem').fill('保留正在输入的题目')
        page.evaluate("window.scrollTo({top:600,behavior:'instant'})")
        page.locator('#knowledge-panel-bubble').click()
        original_history=page.evaluate('history.length')
        page.locator('.knowledge-metro-station[data-node-id=calc-normal]').click()
        page.wait_for_function("document.activeElement.id==='tutor-problem'")
        page.wait_for_function("Math.abs(document.querySelector('.tutor-composer').getBoundingClientRect().top-document.querySelector('.navbar').getBoundingClientRect().bottom-20)<2")
        assert page.locator('#tutor-problem').input_value()=='保留正在输入的题目'
        assert page.evaluate('history.length')==original_history
        assert page.locator('.knowledge-metro-station[aria-current=step]').get_attribute('data-node-id')=='calc-normal'
        # Missing results return to the input station, rather than claiming to open hidden content.
        page.locator('.knowledge-metro-station[data-node-id=calc-formula]').click()
        page.wait_for_function("document.activeElement.id==='tutor-problem'")
        assert '输入题目' in page.locator('.knowledge-metro-current-pill').inner_text()
        solution=local_solution('x^2-5*x+6=0').model_dump(mode='json')
        page.evaluate('(solution)=>window.StepTutor.restore({problem:"x^2-5*x+6=0",solution})',solution)
        page.locator('.knowledge-metro-station[data-node-id=calc-formula]').click()
        page.wait_for_function("document.activeElement.classList.contains('tutor-workspace')")
        page.wait_for_function("Math.abs(document.querySelector('.tutor-workspace').getBoundingClientRect().top-document.querySelector('.navbar').getBoundingClientRect().bottom-20)<2")
        assert page.locator('.knowledge-metro-station[aria-current=step]').get_attribute('data-node-id')=='calc-formula'
        # Repeated use returns to the input without adding history or clearing the solution.
        page.locator('.knowledge-metro-station[data-node-id=calc-normal]').click()
        page.wait_for_function("document.activeElement.id==='tutor-problem'")
        assert page.evaluate('!!window.StepTutor.getState().solution')
        assert not errors,errors
        browser.close()
