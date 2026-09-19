"""Timeout recovery on the actual static and Vue tutor, using an unresponsive transport."""
import os
import pytest
from playwright.sync_api import sync_playwright
from logic.solution_engine import local_solution

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires UI servers')


@pytest.mark.parametrize('url', ['http://127.0.0.1:8000/?section=calculate', 'http://127.0.0.1:5173/calculate'])
def test_timeout_retry_completion_and_cancel(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page()
        page.goto(url, wait_until='domcontentloaded')
        page.wait_for_selector('.step-tutor textarea')
        page.clock.install()
        page.evaluate('''() => {
            const original = window.fetch;
            window.tutorRequests = [];
            window.fetch = (url, options) => {
                if (url !== '/api/solve/stream') return original(url, options);
                const record = {cancelled:false};
                window.tutorRequests.push(record);
                return Promise.resolve(new Response(new ReadableStream({
                    start(controller){record.controller=controller;},
                    cancel(){record.cancelled=true;}
                })));
            };
            window.sendTutor = event => window.tutorRequests.at(-1).controller.enqueue(
                new TextEncoder().encode('data: '+JSON.stringify(event)+'\\n\\n'));
        }''')
        solution = local_solution('x^2=1').model_dump()
        page.locator('[name=autoRender]').uncheck()
        page.locator('#tutor-problem').fill('x^2=1')
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_function('window.tutorRequests.length===1')
        page.evaluate('(step)=>window.sendTutor({type:"step",index:0,step})', solution['steps'][0])
        page.clock.fast_forward(31000)
        page.wait_for_function("window.StepTutor.getState().status.includes('自动修复')")
        assert not page.locator('[data-action=retry]').is_visible()
        assert page.locator('#tutor-problem').input_value() == 'x^2=1'
        assert page.evaluate('window.StepTutor.getState().steps.length') == 1
        assert page.evaluate('window.tutorRequests[0].cancelled')
        assert page.evaluate('window.StepTutor.getState().busy')
        page.clock.run_for(1100)
        page.wait_for_function('window.tutorRequests.length===2')
        page.evaluate('(solution)=>window.sendTutor({type:"complete",solution})', solution)
        page.wait_for_function('!window.StepTutor.getState().busy')
        assert page.locator('.tutor-result').is_visible()
        assert page.locator('.tutor-job-track').get_attribute('aria-valuenow') == '100'
        assert page.evaluate('window.tutorRequests[1].cancelled')
        # Old watchdogs must not change a completed task back to failure.
        page.clock.fast_forward(200000)
        assert page.locator('.tutor-job').get_attribute('data-phase') == 'done'
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_function('window.tutorRequests.length===3')
        page.locator('[data-action=cancel]').click()
        page.wait_for_function('window.tutorRequests[2].cancelled')
        assert page.locator('.tutor-job').get_attribute('data-phase') == 'cancelled'
        assert not page.evaluate('window.StepTutor.getState().busy')
        browser.close()
