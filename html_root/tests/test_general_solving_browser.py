"""Use the actual shared UI and API for parameter answers, steps, and exports."""
import os
from pathlib import Path

import pytest

from test_browser import browser, page, solve
from test_solution_library import accounts, live_library_server

pytestmark = pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS') != '1', reason='Requires browser and UI servers')


def test_parameter_circle_steps_export_and_changed_coefficients(page):
    problem = '已知抛物线y=x^2+2x+m与x轴交于A、B两点，求以线段AB为直径的圆的方程。'
    solve(page, problem)
    summary = page.evaluate('window.StepTutor.getState().solution.summary')
    assert '1 - m' in summary and 'm < 1' in summary
    assert page.locator('[data-step]').count() == 6
    for index in range(6):
        page.locator(f'[data-step="{index}"]').click()
        assert page.locator('.tutor-step-count').inner_text() == f'步骤 {index+1} / 6'
        assert page.locator('.tutor-formula .katex').count() == 1
        assert page.locator('.katex-error').count() == 0
    page.locator('.tutor-more summary').click()
    with page.expect_download() as download:
        page.locator('[data-action=export]').click()
    content = Path(download.value.path()).read_text(encoding='utf-8')
    assert '1 - m' in content and 'm < 1' in content
    solve(page, problem.replace('x^2+2x+m', '2x^2-4x-6'))
    page.locator('[data-step="5"]').click()
    visual = page.evaluate('window.StepTutor.getState().solution.steps[5].visual')
    assert visual['points'] == [[-1,0],[3,0],[1,0]]
    assert any(c['label'] == '直径圆' for c in visual['curves'])
    assert page.locator('.tutor-visual svg').count() >= 1
    assert page.locator('.katex-error').count() == 0
