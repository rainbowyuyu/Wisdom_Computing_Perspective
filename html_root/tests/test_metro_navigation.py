"""The actual floating rail locates the selected math tool without losing input."""
import os
from pathlib import Path

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
        # Sibling tools are reached through the parent, not an invented sibling edge.
        assert page.locator('.knowledge-metro-station[data-node-id=calc-formula]').count()==0
        assert page.locator('.knowledge-metro-station[data-node-id=calc-math-input]').count()==1
        page.locator('.knowledge-metro-station[data-node-id=calculate]').click()
        page.wait_for_function("document.querySelector('.knowledge-metro-station[aria-current=step]')?.dataset.nodeId==='calculate'")
        # Missing results return to the input station, rather than claiming to open hidden content.
        page.locator('.knowledge-metro-station[data-node-id=calc-formula]').click()
        page.wait_for_function("document.activeElement.id==='tutor-problem'")
        assert '输入题目' in page.locator('.knowledge-metro-current-pill').inner_text()
        solution=local_solution('x^2-5*x+6=0').model_dump(mode='json')
        page.evaluate('(solution)=>window.StepTutor.restore({problem:"x^2-5*x+6=0",solution})',solution)
        page.locator('.knowledge-metro-station[data-node-id=calculate]').click()
        page.wait_for_function("document.querySelector('.knowledge-metro-station[aria-current=step]')?.dataset.nodeId==='calculate'")
        page.locator('.knowledge-metro-station[data-node-id=calc-formula]').click()
        page.wait_for_function("document.activeElement.classList.contains('tutor-workspace')")
        page.wait_for_function("Math.abs(document.querySelector('.tutor-workspace').getBoundingClientRect().top-document.querySelector('.navbar').getBoundingClientRect().bottom-20)<2")
        assert page.locator('.knowledge-metro-station[aria-current=step]').get_attribute('data-node-id')=='calc-formula'
        # Repeated use returns to the input without adding history or clearing the solution.
        page.locator('.knowledge-metro-station[data-node-id=calculate]').click()
        page.wait_for_function("document.querySelector('.knowledge-metro-station[aria-current=step]')?.dataset.nodeId==='calculate'")
        page.locator('.knowledge-metro-station[data-node-id=calc-normal]').click()
        page.wait_for_function("document.activeElement.id==='tutor-problem'")
        assert page.evaluate('!!window.StepTutor.getState().solution')
        assert not errors,errors
        browser.close()


@pytest.mark.parametrize('origin,path',[
    ('http://127.0.0.1:8000','/?section=home'),
    ('http://127.0.0.1:5173','/home'),
])
def test_graph_connections_refresh_and_rail_recenters(origin,path):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1280,'height':900},reduced_motion='reduce')
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(origin+path,wait_until='domcontentloaded')
        page.wait_for_function("document.querySelector('#knowledge-panel')?.dataset.floatingReady")
        page.locator('#knowledge-panel-bubble').press('Enter')
        page.wait_for_selector('.knowledge-metro-station.current')
        assert page.locator('.knowledge-metro-station.current').get_attribute('data-node-id')=='home'
        # All siblings remain available, including branches beyond the previous cap of three.
        assert page.locator('.knowledge-metro-station[data-relation=outgoing]').count()>3
        page.locator('.knowledge-metro-station[data-node-id=examples]').click()
        page.wait_for_function("document.querySelector('.knowledge-metro-station.current')?.dataset.nodeId==='examples'")
        # Selecting a nested filter refreshes the graph around that station.
        page.locator('.knowledge-metro-station[data-node-id=examples-courseware]').click()
        # Guest-only course collections keep their existing login gate.
        login_close=page.locator('#auth-modal.show .close-modal, .auth-account-dialog[open] [aria-label="关闭"]')
        login_close.wait_for();login_close.click()
        assert page.locator('.knowledge-metro-station.current').get_attribute('data-node-id')=='examples'
        page.locator('.knowledge-metro-station[data-node-id=examples-curriculum]').click()
        page.wait_for_function("document.querySelector('.knowledge-metro-station.current')?.dataset.nodeId==='examples-curriculum'")
        assert page.locator('.knowledge-metro-station[data-node-id=curriculum-highschool]').count()==1
        assert page.locator('.knowledge-metro-station[data-node-id=curriculum-university]').count()==1
        page.locator('.knowledge-metro-station[data-node-id=examples]').click()
        page.wait_for_function("document.querySelector('.knowledge-metro-station.current')?.dataset.nodeId==='examples'")
        # Graph updates alone drive the rail; detached, duplicate, self and missing edges are harmless.
        page.evaluate("""async () => {
          const G=await import('/static/js/site-graph.js?v=20260917-ecosystem-6');
          G.EDGES.push({source:'examples',target:'calc-normal'}, {source:'examples',target:'calc-normal'},
            {source:'examples',target:'examples'}, {source:'examples',target:'missing'});
          const graph=G.getGraphDataFor3D();
          graph.links.forEach(e=>{e.source={id:e.source};e.target={id:e.target}});
          window.dispatchEvent(new CustomEvent('graph-station-selected',{detail:{nodeId:'examples'}}));
          window.dispatchEvent(new CustomEvent('graph-station-selected'));
          window.dispatchEvent(new CustomEvent('graph-station-selected',{detail:{nodeId:'missing'}}));
          window.dispatchEvent(new CustomEvent('graph-station-selected',{detail:{nodeId:'home'}}));
        }""")
        assert page.locator('.knowledge-metro-station[data-node-id=calc-normal]').count()==1
        assert page.locator('.knowledge-metro-station.current').get_attribute('data-node-id')=='examples'
        page.locator('.knowledge-metro-station[data-node-id=calc-normal]').click()
        page.wait_for_function("document.querySelector('.knowledge-metro-station.current')?.dataset.nodeId==='calc-normal'")
        page.wait_for_function("document.activeElement.id==='tutor-problem'")
        page.locator('#knowledge-panel-close-btn').click()
        page.evaluate("window.showSection('home')")
        page.set_viewport_size({'width':390,'height':844})
        page.evaluate("document.documentElement.dataset.theme='dark'")
        page.locator('#knowledge-panel-bubble').press('Enter')
        page.wait_for_function("""() => {
          const line=document.querySelector('.knowledge-metro-line'), current=line?.querySelector('.current');
          if(!current || current.dataset.nodeId!=='home')return false;
          const a=line.getBoundingClientRect(),b=current.getBoundingClientRect();
          return Math.abs(a.left+a.width/2-b.left-b.width/2)<3;
        }""")
        line=page.locator('.knowledge-metro-line')
        before=line.evaluate('el=>el.scrollLeft')
        line.hover();page.mouse.wheel(0,160)
        page.wait_for_function('(before)=>document.querySelector(".knowledge-metro-line").scrollLeft>before',arg=before)
        # Collapsing/reopening returns to the current station after manual scrolling.
        page.locator('#knowledge-panel-close-btn').click()
        page.locator('#knowledge-panel-bubble').press('Enter')
        page.wait_for_function("""() => {
          const a=document.querySelector('.knowledge-metro-line').getBoundingClientRect();
          const b=document.querySelector('.knowledge-metro-station.current').getBoundingClientRect();
          return Math.abs(a.left+a.width/2-b.left-b.width/2)<3;
        }""")
        Path('tests/artifacts').mkdir(exist_ok=True)
        page.locator('#knowledge-panel').screenshot(path=f"tests/artifacts/metro-graph-{'vue' if '5173' in origin else 'static'}.png")
        page.evaluate("window.showSection('devtools')")
        page.wait_for_function("document.querySelector('#devtools')?.dataset.devInitialized")
        # Vue uses data-tool rather than inline onclick; both must resolve the same station.
        page.evaluate("window.switchDevTool('latex')")
        page.wait_for_function("document.querySelector('.knowledge-metro-station.current')?.dataset.nodeId==='devtools-latex'")
        assert page.locator('.knowledge-metro-station[data-node-id=devtools-latex-copy]').count()==1
        page.evaluate("window.switchDevTool('rainbow')")
        page.wait_for_function("document.querySelector('.knowledge-metro-station.current')?.dataset.nodeId==='devtools-rainbow'")
        assert not errors,errors
        browser.close()
