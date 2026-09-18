"""Documentation must distinguish literal syntax examples from actual equations."""
import os
import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires local web servers')


@pytest.mark.parametrize('url', ['http://127.0.0.1:8000/?section=my-formulas', 'http://127.0.0.1:5173/my-formulas'])
def test_changelog_math_and_delayed_renderer(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_function('!!window.openDoc && !!window.renderMathInElement')
        page.evaluate('''() => {
            window.documentMathErrors=[];
            const original=window.renderMathInElement;
            window.renderMathInElement=(el,options)=>original(el,{...options,errorCallback:(message,error)=>{
                window.documentMathErrors.push(message);options.errorCallback?.(message,error);
            }});
        }''')
        page.evaluate("()=>window.openDoc('update.md','更新日志')")
        page.wait_for_selector('.docs-release-latest')
        assert page.evaluate('window.documentMathErrors') == []
        content = page.locator('#docs-content')
        assert not content.get_attribute('title')
        assert content.locator('.katex').count() >= 5
        assert content.locator('.katex-error,.math-render-error').count() == 0
        codes = content.locator('code').all_text_contents()
        assert {'EXAMPLES_USE_CDN=1', 'manim_extend_rainbow', 'setting_key', 'setting_value', '```latex'} <= set(codes)
        page.locator('#docs-version-select').select_option('update-v-0.4.2')
        assert not content.evaluate("el=>el.classList.contains('math-render-error')")
        assert content.locator('article').filter(has=page.locator('[id="update-v-0.4.2"]')).locator('.katex').count() >= 4
        # Keep document mode when KaTeX arrives late; keep bare detection in solution mode.
        result = page.evaluate(r'''async () => {
            const {renderMathIn}=await import('/static/js/math-text.js?v=20260918-doc-math-1');
            const el=document.createElement('div');document.body.append(el);
            el.textContent='EXAMPLES_USE_CDN=1 / manim_extend_rainbow；$x^2$';
            const renderer=window.renderMathInElement;
            window.renderMathInElement=undefined;
            renderMathIn(el,{detectBareMath:false});
            window.renderMathInElement=renderer;
            window.dispatchEvent(new Event('math-renderer-ready'));
            const documentMode=!el.classList.contains('math-render-error') && el.querySelectorAll('.katex').length===1 && el.textContent.includes('EXAMPLES_USE_CDN=1 / manim_extend_rainbow');
            el.textContent=String.raw`结果为 \frac{1}{2}`;
            renderMathIn(el);
            const solutionMode=el.querySelectorAll('.katex').length===1;
            el.textContent=String.raw`$\notARealCommand{x}$`;
            renderMathIn(el,{detectBareMath:false});
            const invalidFormula=el.classList.contains('math-render-error');
            el.remove();return {documentMode,solutionMode,invalidFormula};
        }''')
        assert all(result.values()), result
        browser.close()
