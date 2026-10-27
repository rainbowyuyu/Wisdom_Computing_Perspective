"""Floating assistant acceptance. Model and export jobs are explicitly mocked."""
from __future__ import annotations

import time

from playwright.sync_api import expect

from test_browser import browser, local_server, workbench, enable_mock_provider  # noqa: F401


def test_keyboard_focus_and_formula_navigation(workbench):
    page, _ = workbench
    orb = page.locator(".hub-orb")
    panel = page.locator(".hub-panel")
    orb.focus()
    orb.press("Enter")
    expect(panel).to_be_visible()
    expect(orb).to_have_attribute("aria-expanded", "true")
    expect(panel.get_by_role("button", name="收起创作助手")).to_be_focused()
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    expect(orb).to_be_focused()
    initial = orb.bounding_box()
    orb.press("ArrowLeft")
    assert abs(orb.bounding_box()["x"] - initial["x"] + 16) < 1
    orb.press("Space")
    expect(panel).to_be_visible()
    panel.get_by_role("button", name="公式库", exact=True).click()
    expect(panel).to_be_hidden()
    expect(page.locator("#knowledge-workspace")).to_be_visible()
    expect(page.locator('#knowledge-workspace [data-view="library"]')).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Escape")
    expect(page.locator("#knowledge-workspace")).to_be_hidden()
    expect(orb).to_be_focused()


def test_drag_does_not_click_and_mobile_resize_preserves_access(workbench):
    page, _ = workbench
    orb = page.locator(".hub-orb")
    panel = page.locator(".hub-panel")
    before = orb.bounding_box()
    page.mouse.move(before["x"] + before["width"] / 2, before["y"] + before["height"] / 2)
    page.mouse.down()
    page.mouse.move(before["x"] - 100, before["y"] - 80, steps=8)
    page.mouse.up()
    expect(panel).to_be_hidden()
    after = orb.bounding_box()
    assert after["x"] < before["x"] - 100 and after["y"] < before["y"] - 80
    saved = page.evaluate("JSON.parse(localStorage.getItem('visualize-dsh.floating-hub.v1'))")
    assert saved["v"] == 2
    assert abs(saved["x"] * (1440-after["width"]-24) + 12 - after["x"]) < 1
    assert abs(saved["y"] * (960-after["height"]-24) + 12 - after["y"]) < 1
    page.reload()
    expect(page.locator("#canvas-empty")).to_be_hidden(timeout=15000)
    assert abs(orb.bounding_box()["x"] - after["x"]) < 1
    page.set_viewport_size({"width": 390, "height": 330})
    expect(orb).to_be_in_viewport()
    orb.focus()
    orb.press("Enter")
    expect(panel).to_be_visible()
    bounds = panel.bounding_box()
    assert bounds["x"] >= 11 and bounds["y"] >= 11
    assert bounds["x"] + bounds["width"] <= 379
    assert bounds["y"] + bounds["height"] <= 319
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    expect(panel.get_by_role("button", name="收起创作助手")).to_be_in_viewport()
    panel.get_by_role("button", name="知识图谱", exact=True).click()
    expect(page.locator("#knowledge-workspace")).to_be_visible()
    page.keyboard.press("Escape")
    page.emulate_media(reduced_motion="reduce")
    assert orb.locator(".hub-drift").evaluate("node => getComputedStyle(node).animationName") == "none"


def test_actual_task_progress_unknown_and_pending_cancel(workbench):
    page, _ = workbench
    enable_mock_provider(page)
    submissions, cancellations = [], []
    job = {
        "id": "hub_export_job", "kind": "export", "status": "rendering", "stage": "rendering",
        "message": "正在逐帧渲染", "events": [], "created": time.time() + 100,
        "updated": time.time(), "progress": 0,
    }

    def submit(route):
        submissions.append(route.request.post_data_json)
        job["project_id"] = route.request.url.split("/projects/")[1].split("/")[0]
        route.fulfill(status=202, json={"job": job})

    page.route("**/api/projects/*/export", submit)
    page.route("**/api/jobs/hub_export_job", lambda route: route.fulfill(json={"job": job}))
    page.route("**/api/jobs/hub_export_job/cancel", lambda route: cancellations.append(route))
    page.locator("#export-toggle").click()
    page.locator("#export-video").click()
    expect(page.locator("#export-dialog")).not_to_be_visible()
    orb, panel = page.locator(".hub-orb"), page.locator(".hub-panel")
    expect(orb).to_have_attribute("data-progress", "known")
    expect(orb.locator(".hub-orb-value")).to_have_text("0%")
    orb.click()
    task = panel.locator('[data-hub-job-id="hub_export_job"]')
    progress = task.get_by_role("progressbar")
    expect(progress).to_have_attribute("aria-valuenow", "0")
    job["progress"] = 42.5
    expect(progress).to_have_attribute("aria-valuenow", "42.5", timeout=6000)
    assert orb.evaluate("node => node.style.getPropertyValue('--hub-level')") == "42.5%"
    expect(orb.locator(".hub-orb-value")).to_have_text("43%")
    job["progress"] = None
    expect(orb).to_have_attribute("data-progress", "unknown", timeout=6000)
    assert progress.get_attribute("aria-valuenow") is None
    assert "%" not in orb.get_attribute("aria-label")
    expect(task.locator(".hub-task-value")).to_have_text("进度待更新")
    cancel = task.get_by_role("button", name="取消任务", exact=True)
    cancel.click()
    expect(task.get_by_role("button", name="正在取消…")).to_be_disabled()
    assert len(cancellations) == 1
    job.update(status="cancelled", stage="cancelled", message="已取消导出")
    cancellations[0].fulfill(json={"job": job})
    expect(task).to_have_attribute("data-state", "cancelled")
    expect(task.locator(".hub-cancel-button")).to_be_hidden()
    expect(task.get_by_role("button", name="查看任务")).to_be_focused()
    assert submissions == [{"engine": "browser", "fps": 24}]


def test_component_lifecycle_multitask_and_export_result(workbench):
    page, _ = workbench
    page.evaluate("""async () => {
      const {mountFloatingHub} = await import(new URL('floating-hub.js', document.querySelector('script[type="module"]').src));
      window.hubActions = [];
      window.hubPositions=[];
      window.testHub = mountFloatingHub({onAction: (action, payload) => window.hubActions.push({action, payload}),onPositionChange: value=>window.hubPositions.push(value)});
      document.body.lastElementChild.id = 'hub-test-root';
      window.hubJobs = [
        {id:'hub_a',kind:'create',status:'building',stage:'building',progress:15,created:3},
        {id:'hub_b',kind:'export',status:'rendering',stage:'rendering',progress:null,created:2},
        {id:'hub_done',kind:'export',status:'completed',progress:100,project_id:'p_existing',created:1},
        {id:'hub_fail',kind:'create',status:'failed',message:'<img src=x onerror=alert(1)>',created:0},
      ];
      window.testHub.update({jobs:window.hubJobs});
    }""")
    root = page.locator("#hub-test-root")
    expect(root.locator(".hub-count")).to_have_text("2")
    expect(root.locator(".hub-orb-value")).to_have_text("15%")
    root.locator(".hub-orb").focus()
    root.locator(".hub-orb").press("Enter")
    expect(root.locator(".hub-task")).to_have_count(3)
    root.locator('[data-hub-job-id="hub_done"]').get_by_role("button", name="查看视频").click()
    assert page.evaluate("window.hubActions") == [{"action": "jobs", "payload": {"jobId": "hub_done"}}]
    root.locator(".hub-orb").press("Enter")
    target = root.locator('[data-hub-job-id="hub_a"] .hub-result-button')
    target.focus()
    page.evaluate("window.hubJobs[1].created = 4; window.testHub.update({jobs:window.hubJobs})")
    expect(target).to_be_focused()
    page.evaluate("window.testHub.setPreferences({floating_size:80,floating_opacity:.5,floating_x:.5,floating_y:.25,reduced_motion:true})")
    assert root.locator('.hub-orb').bounding_box()['width']==80
    assert root.locator('.hub-orb').evaluate('node=>getComputedStyle(node).opacity')=='0.5'
    assert root.locator('.hub-drift').evaluate('node=>getComputedStyle(node).animationName')=='none'
    page.keyboard.press('Escape')
    root.locator('.hub-orb').focus();root.locator('.hub-orb').press('ArrowLeft')
    positions=page.evaluate('window.hubPositions')
    assert len(positions)==1 and 0<=positions[0]['floating_x']<.5 and positions[0]['floating_y']==.25
    page.evaluate("window.testHub.setPreferences({floating_visible:false})")
    expect(root).to_be_hidden()
    page.evaluate("window.testHub.setPreferences({floating_visible:true,floating_x:null,floating_y:null})")
    expect(root).to_be_visible()
    root.locator('.hub-orb').focus();root.locator('.hub-orb').press('Enter')
    root.get_by_role('button',name='设置',exact=True).click()
    assert page.evaluate('window.hubActions.at(-1).action')=='settings'
    page.evaluate("window.testHub.dispose(); window.testHub.update({jobs:[]}); window.testHub.dispose()")
    expect(root).to_have_count(0)
    expect(page.locator(".hub-root")).to_have_count(1)
    page.set_viewport_size({"width": 900, "height": 700})
    expect(page.locator(".hub-orb")).to_be_in_viewport()
