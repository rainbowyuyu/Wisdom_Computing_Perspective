"""Both tutor frontends retain repair progress and save the repaired solution."""
import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect

from logic.solution_engine import local_solution

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local UI servers')


@pytest.mark.parametrize('url',['http://127.0.0.1:8000/?section=calculate','http://127.0.0.1:5173/calculate'])
def test_repair_progress_success_and_saved_formula(url):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto(url,wait_until='domcontentloaded')
        page.wait_for_selector('.step-tutor textarea')
        page.evaluate('''() => {
            const original=window.fetch;
            window.fetch=(url,options)=>url==='/api/solve/render'?Promise.resolve(new Response(new ReadableStream({start(c){window.renderStream=c;}}))):original(url,options);
            window.sendRender=event=>window.renderStream.enqueue(new TextEncoder().encode('data: '+JSON.stringify(event)+'\\n\\n'));
        }''')
        solution=local_solution('x^2=1').model_dump()
        page.evaluate('(solution)=>window.StepTutor.restore({problem:"x^2=1",solution})',solution)
        page.locator('[data-action=render]').click()
        page.wait_for_function('!!window.renderStream')
        page.evaluate('window.sendRender({type:"status",repairing:true,message:"正在分析渲染错误并尝试修复（最多一次）…"})')
        expect(page.locator('.tutor-status')).to_contain_text('尝试修复')
        expect(page.locator('.tutor-render-feedback')).to_contain_text('尝试修复')
        assert page.evaluate('window.StepTutor.getState().rendering')
        assert not page.evaluate('window.StepTutor.getState().error')
        Path('tests/artifacts').mkdir(exist_ok=True)
        page.screenshot(path='tests/artifacts/render-repair-'+('vue' if '5173' in url else 'static')+'.png')
        solution['steps'][0]['formula']=r'\frac{1}{2}'
        page.evaluate('(solution)=>window.sendRender({type:"complete",repaired:true,solution,video_url:"/videos/solution_a.mp4",chapters:[]})',solution)
        page.wait_for_function('!window.StepTutor.getState().rendering')
        state=page.evaluate('window.StepTutor.getState()')
        assert not state['error'] and state['solution']['steps'][0]['formula']==r'\frac{1}{2}'
        assert state['steps'][0]['formula']==r'\frac{1}{2}'
        expect(page.locator('[data-action=save]')).to_be_enabled()
        browser.close()
