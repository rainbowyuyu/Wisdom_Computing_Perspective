"""Nebula renders the original complete problem on both frontends."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local web servers')

@pytest.mark.parametrize('origin,path,kind',[
    ('http://127.0.0.1:8000','/?section=calculate','static'),
    ('http://127.0.0.1:5173','/calculate','vue')])
@pytest.mark.parametrize('width',[1280,390])
def test_nebula_complete_latex(origin,path,kind,width):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':width,'height':900})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(origin+path,wait_until='domcontentloaded')
        page.wait_for_function("document.querySelector('#knowledge-panel')?.dataset.floatingReady && !!window.renderMathInElement")
        page.locator('#knowledge-panel-bubble').click()
        def publish(problem):
            page.evaluate("problem=>window.dispatchEvent(new CustomEvent('tutor-state',{detail:{problem,status:'解答已完成',busy:false}}))",problem)
        formula=r'\int_0^1 x^{2}+3x\,dx'
        publish(formula)
        page.locator('.tutor-task-problem .katex').wait_for()
        assert page.locator('.tutor-task-problem annotation').text_content()==formula
        Path('tests/artifacts').mkdir(exist_ok=True)
        page.locator('#knowledge-panel').screenshot(path=f'tests/artifacts/nebula-latex-{kind}-{width}.png')
        long_formula=r'\frac{'+ '+'.join(f'x^{{{i}}}' for i in range(1,50))+r'}{1+x^2}'
        publish('请计算：$'+long_formula+'$，并说明过程。')
        assert page.locator('.tutor-task-problem annotation').text_content()==long_formula
        assert '并说明过程' in page.locator('.tutor-task-problem').inner_text()
        assert page.locator('.tutor-task-problem .katex-error').count()==0
        assert page.evaluate("document.querySelector('#knowledge-panel').getBoundingClientRect().right<=innerWidth")
        assert page.evaluate("document.querySelector('.tutor-task-card').scrollWidth<=document.querySelector('.tutor-task-card').clientWidth+2")
        assert page.evaluate("getComputedStyle(document.querySelector('.tutor-task-problem')).overflowX==='auto'")
        publish('<img src=x onerror=alert(1)> '+formula)
        assert page.locator('.tutor-task-problem img').count()==0
        page.evaluate("window.nebulaRenderer=window.renderMathInElement;window.renderMathInElement=undefined")
        publish(r'\sqrt{x+1}')
        page.evaluate("window.renderMathInElement=window.nebulaRenderer;window.dispatchEvent(new Event('math-renderer-ready'))")
        page.locator('.tutor-task-problem .katex').wait_for()
        assert not errors,errors
        browser.close()
