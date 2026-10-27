"""Browser acceptance: real local samples; model/export orchestration uses explicit mocks.

Run with .venv/Scripts/python.exe -m pytest tests/test_browser.py -q.
No test makes a real model request.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "tmp" / "browser-qa"


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["VISUALIZE_PORT"] = str(port)
    env["VISUALIZE_DATA"] = str(tmp_path_factory.mktemp("visualize-browser-data"))
    # Never load legacy users or send real verification emails from local .env.
    env["LEGACY_ACCOUNT_BACKEND"] = "sqlite"
    env["SMTP_HOST"] = ""
    env["EMAIL_CODE_SECRET"] = ""
    base = f"http://127.0.0.1:{port}"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("The isolated local server exited before becoming ready.")
            try:
                with urllib.request.urlopen(f"{base}/healthz", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.15)
        else:
            pytest.fail("The isolated local server did not become ready.")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        launch = {"headless": True}
        if not Path(playwright.chromium.executable_path).exists():
            launch["channel"] = "chrome"
        instance = playwright.chromium.launch(**launch)
        yield instance
        instance.close()


@pytest.fixture
def workbench(browser, local_server):
    context = browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.on("console", lambda item: failures.append(f"Console: {item.text}") if item.type == "error" else None)
    page.on("response", lambda response: failures.append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)
    # A safety boundary makes accidental non-sample requests fail in all tests.
    def guard_model_calls(route):
        if route.request.method == "POST" and not route.request.post_data_json.get("sample"):
            route.fulfill(status=503, json={"detail": "Browser test forbids real model calls."})
        else:
            route.continue_()
    page.route("**/api/jobs", guard_model_calls)
    page.goto(local_server)
    expect(page.locator("#canvas-empty")).to_be_hidden(timeout=20000)
    expect(page.locator("#play")).to_be_enabled()
    yield page, failures
    context.close()
    assert not failures, f"Unexpected browser errors: {failures}"


def test_local_sample_playback_parameters_layers_and_persistence(workbench):
    page, _ = workbench
    expect(page.locator("#scene-title")).not_to_have_text("准备探索")
    expect(page.locator("#scene-host canvas")).to_have_count(1)
    page.locator("#play").click()
    expect(page.locator("#play")).to_have_attribute("aria-label", "播放动画")
    page.locator("#seek").fill("4.5")
    expect(page.locator("#current-time")).to_have_text("00:04.5")
    page.locator("#speed").select_option("1.5")
    page.locator(".layer-select").first.click()
    expect(page.locator(".layer.selected")).to_have_count(1)
    page.locator(".layer-visibility").first.click()
    expect(page.locator(".layer.hidden-layer")).to_have_count(1)
    page.locator(".layer-visibility").first.click()
    page.locator(".step-card").nth(1).click()
    expect(page.locator(".step-card").nth(1)).to_have_class("step-card active")

    slider = page.locator(".control-slider").first
    value = float(slider.get_attribute("min")) + float(slider.get_attribute("step")) * 2
    with page.expect_response(lambda response: "/recompute" in response.url and response.request.method == "POST") as result:
        slider.fill(f"{value:g}")
    assert result.value.ok
    expect(page.locator("#save-status")).to_contain_text("v2")
    title = page.locator("#scene-title").inner_text()
    page.reload()
    expect(page.locator("#canvas-empty")).to_be_hidden(timeout=15000)
    expect(page.locator("#scene-title")).to_have_text(title)
    expect(page.locator("#save-status")).to_contain_text("v2")
    page.locator("#history-tab").click()
    expect(page.locator(".project-card")).to_have_count(1)
    page.locator(".project-card").click()
    expect(page.locator("#canvas-empty")).to_be_hidden()


def test_responsive_workbench_and_3d_sample(workbench):
    page, _ = workbench
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": 1080, "height": 820})
    page.locator("#play").click()
    page.locator("#seek").fill("5")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator("#scene-host").bounding_box()["width"] > 400
    page.screenshot(path=str(ARTIFACTS / "desktop-1080.png"), full_page=True)
    bootstrap = page.request.get(f"{page.url.rstrip('/')}/api/bootstrap").json()
    sample3d = next(sample for sample in bootstrap["samples"] if sample["id"] == "model3d")
    page.locator(f'[data-sample="{sample3d["id"]}"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    assert page.locator("#scene-host canvas").count() == 1
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#play").click()
    page.locator("#seek").fill("4")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator("#scene-host").bounding_box()["width"] >= 350
    page.screenshot(path=str(ARTIFACTS / "mobile-390.png"), full_page=True)
    expect(page.locator("#generate")).to_be_enabled()


def test_image_upload_and_json_download(workbench):
    page, _ = workbench
    # Browser-owned PNG fixture; upload travels through the actual protected API.
    png = page.locator("#scene-host canvas").screenshot()
    page.locator('[data-mode="image"]').click()
    page.locator("#image-file").set_input_files({"name": "reference.png", "mimeType": "image/png", "buffer": png})
    expect(page.locator("#asset-preview")).to_be_visible()
    assert page.locator("#asset-image").evaluate(r"""image => {
        const url = new URL(image.src, location.href);
        return url.origin === location.origin && /^\/api\/assets\/[a-zA-Z0-9_-]+$/.test(url.pathname)
            && !url.search && !url.hash;
    }""")
    assert page.locator("#asset-image").evaluate("image => image.complete && image.naturalWidth > 0")
    page.locator("#remove-image").click()
    expect(page.locator("#asset-preview")).to_be_hidden()
    page.locator("#export-toggle").click()
    with page.expect_download() as downloaded:
        page.locator("#export-json").click()
    document = json.loads(Path(downloaded.value.path()).read_text(encoding="utf-8"))
    assert document["scene"]["version"] == 1 and document["scene"]["objects"]
    assert document["format"] == "visualize-project" and document["version"] == 1
    assert "values" in document["exploration"]
    expect(page.locator("#export-dialog")).not_to_be_visible()


def enable_mock_provider(page, *, manim=False, browser_renderer=True):
    def bootstrap(route):
        response = route.fetch()
        data = response.json()
        data["providers"] = [
            {"id": "qwen", "name": "Qwen", "available": True, "message": "Test provider"},
            {"id": "chatgpt", "name": "ChatGPT", "available": True, "message": "Test provider"},
            {"id": "claude", "name": "Claude", "available": True, "message": "Test provider"},
        ]
        data["renderers"] = {"browser": browser_renderer, "manim": manim}
        route.fulfill(response=response, json=data)
    page.route("**/api/bootstrap", bootstrap)
    page.reload()
    expect(page.locator("#canvas-empty")).to_be_hidden(timeout=15000)


def test_iteration_needs_input_and_cancel_without_model_call(workbench):
    page, _ = workbench
    enable_mock_provider(page)
    requests = []
    job = {"id": "test_create_job", "kind": "create", "status": "needs_input", "stage": "needs_input", "message": "请补充需要解释的边界条件。", "events": [{"stage": "planning", "message": "<img src=x onerror=alert(1)>"}], "created": time.time(), "updated": time.time(), "progress": None}
    def submit(route):
        requests.append(route.request.post_data_json)
        route.fulfill(status=202, json={"job": job})
    page.route("**/api/jobs", lambda route: submit(route) if route.request.method == "POST" else route.continue_())
    page.locator("#prompt").fill("解释初始条件对运动的影响")
    page.locator("#provider").select_option("claude")
    page.locator('input[name="duration"][value="20"]').check()
    page.locator("#generate").click()
    expect(page.locator('[data-job-id="test_create_job"]')).to_have_attribute("data-status", "needs_input")
    assert requests[0]["parent_id"] and requests[0]["provider"] == "claude" and requests[0]["duration"] == 20
    assert "<img src=x" in page.locator('[data-job-id="test_create_job"] .job-events').inner_text()
    assert page.locator('[data-job-id="test_create_job"] img').count() == 0
    expect(page.locator("#form-message")).to_contain_text("边界条件")
    job.update(id="test_cancel_job", status="planning", message="正在理解输入")
    page.route("**/api/jobs/test_cancel_job", lambda route: route.fulfill(json={"job": job}))
    def cancel(route):
        job.update(status="cancelled", message="任务已取消")
        route.fulfill(json={"job": job})
    page.route("**/api/jobs/test_cancel_job/cancel", cancel)
    page.locator("#new-project").click()
    page.locator("#prompt").fill("一个全新的探索")
    page.locator("#generate").click()
    expect(page.locator('[data-job-id="test_cancel_job"]')).to_have_attribute("data-status", "planning")
    assert "parent_id" not in requests[1]
    page.locator('[data-job-id="test_cancel_job"]').get_by_role("button", name="取消任务").click()
    expect(page.locator('[data-job-id="test_cancel_job"]')).to_have_attribute("data-status", "cancelled")
    expect(page.locator("#generate")).to_be_enabled()


def test_export_runs_without_blocking_existing_scene(workbench):
    page, _ = workbench
    enable_mock_provider(page)
    export_requests = []
    job = {"id": "test_export_job", "kind": "export", "status": "rendering", "stage": "rendering", "message": "正在逐帧渲染", "events": [], "created": time.time(), "updated": time.time(), "progress": 10}
    def submit(route):
        export_requests.append(route.request.post_data_json)
        route.fulfill(status=202, json={"job": job})
    page.route("**/api/projects/*/export", submit)
    page.route("**/api/jobs/test_export_job", lambda route: route.fulfill(json={"job": job}))
    title = page.locator("#scene-title").inner_text()
    page.locator("#export-toggle").click()
    expect(page.locator("#manim-engine")).to_be_disabled()
    page.locator("#export-video").click()
    expect(page.locator("#export-dialog")).not_to_be_visible()
    expect(page.locator('[data-job-id="test_export_job"]')).to_have_attribute("data-status", "rendering")
    expect(page.locator("#scene-title")).to_have_text(title)
    expect(page.locator("#play")).to_be_enabled()
    page.locator("#seek").fill("3")
    expect(page.locator("#current-time")).to_have_text("00:03.0")
    assert export_requests == [{"engine": "browser", "fps": 24}]
    job.update(status="completed", progress=100, video_url="/api/media/test_export_job", message="视频已完成")
    expect(page.locator('[data-job-id="test_export_job"]').get_by_role("link", name="下载 MP4")).to_have_attribute("href", "/api/media/test_export_job?download=true", timeout=5000)


def test_manim_is_selectable_only_for_supported_2d_scenes(workbench):
    page, _ = workbench
    enable_mock_provider(page, manim=True)
    page.locator("#export-toggle").click()
    expect(page.locator("#manim-engine")).to_be_enabled()
    page.locator("#manim-engine").check()
    expect(page.locator("#manim-engine")).to_be_checked()
    page.get_by_role("button", name="关闭导出窗口").click()
    page.locator('[data-sample="model3d"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    page.locator("#export-toggle").click()
    expect(page.locator("#manim-engine")).to_be_disabled()
    expect(page.locator("#manim-engine")).not_to_be_checked()
    expect(page.locator("#manim-status")).to_contain_text("仅支持二维场景")
    expect(page.locator('input[name="export-engine"][value="browser"]')).to_be_checked()
    page.get_by_role("button", name="关闭导出窗口").click()
    enable_mock_provider(page, manim=True, browser_renderer=False)
    expect(page.locator("#scene-mode")).to_have_text("3D")
    page.locator("#export-toggle").click()
    expect(page.locator("#export-video")).to_be_disabled()
    expect(page.locator("#export-message")).to_contain_text("当前三维场景需要浏览器渲染")
    expect(page.locator("#export-json")).to_be_enabled()


def test_scene_selection_recommends_manim_and_preserves_legacy_truth(workbench):
    page, _ = workbench
    enable_mock_provider(page, manim=True)
    def recommended_project(route):
        response = route.fetch()
        data = response.json()
        data["project"]["scene"]["selection"] = {"engine": "manim", "category": "formula", "reason": "公式适合逐步推导。<img src=x onerror=alert(1)>"}
        route.fulfill(response=response, json=data)
    page.route("**/api/projects/*", recommended_project)
    page.reload()
    expect(page.locator("#canvas-empty")).to_be_hidden(timeout=15000)
    expect(page.locator("#selection-title")).to_have_text("Manim · 数学动画")
    expect(page.locator("#selection-reason")).to_contain_text("<img src=x onerror=alert(1)>")
    expect(page.locator("#scene-selection img")).to_have_count(0)
    expect(page.locator("#selection-renderer")).to_contain_text("画布预览 Canvas 2D")
    page.locator("#export-toggle").click()
    expect(page.locator("#manim-engine")).to_be_checked()
    expect(page.locator("#browser-engine-title")).to_have_text("浏览器渲染 · Canvas 2D")
    page.get_by_role("button", name="关闭导出窗口").click()
    enable_mock_provider(page, manim=False)
    page.locator("#export-toggle").click()
    expect(page.locator("#manim-engine")).to_be_disabled()
    expect(page.locator('input[name="export-engine"][value="browser"]')).to_be_checked()
    page.get_by_role("button", name="关闭导出窗口").click()
    page.unroute("**/api/projects/*", recommended_project)
    def legacy_project(route):
        response = route.fetch()
        data = response.json()
        data["project"]["scene"].pop("selection", None)
        data["project"]["proposal"].pop("selection", None)
        route.fulfill(response=response, json=data)
    page.route("**/api/projects/*", legacy_project)
    page.reload()
    expect(page.locator("#canvas-empty")).to_be_hidden(timeout=15000)
    expect(page.locator("#selection-title")).to_have_text("Canvas 2D · 二维可视化")
    expect(page.locator("#selection-renderer")).to_contain_text("按现有场景识别")
    assert "模型" not in page.locator("#scene-selection").inner_text()


def test_real_fan_sample_uses_threejs_and_switches_back_to_2d(workbench):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    expect(page.locator("#scene-selection")).to_have_attribute("data-engine", "threejs")
    expect(page.locator("#selection-title")).to_have_text("Three.js · 三维建模")
    expect(page.locator("#selection-renderer")).to_have_text("浏览器引擎 Three.js")
    assert page.locator("#scene-host canvas").evaluate("canvas => !!(canvas.getContext('webgl2') || canvas.getContext('webgl'))")
    page.locator("#seek").fill("4")
    page.set_viewport_size({"width": 1080, "height": 820})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.locator("#creation-content").evaluate("panel => { panel.scrollTop = 0; }")
    expect(page.locator("#toast")).to_be_hidden(timeout=5000)
    page.screenshot(path=str(ARTIFACTS / "fan-threejs-1080.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(ARTIFACTS / "fan-threejs-390.png"))
    page.set_viewport_size({"width": 1080, "height": 820})
    page.locator("#export-toggle").click()
    expect(page.locator("#browser-engine-title")).to_have_text("浏览器渲染 · Three.js")
    expect(page.locator("#manim-engine")).to_be_disabled()
    expect(page.locator('input[name="export-engine"][value="browser"]')).to_be_checked()
    page.get_by_role("button", name="关闭导出窗口").click()
    page.locator('[data-sample="wave"]').click()
    expect(page.locator("#scene-mode")).to_have_text("2D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    expect(page.locator("#selection-title")).to_have_text("Canvas 2D · 二维可视化")
    assert page.locator("#scene-host canvas").evaluate("canvas => !!canvas.getContext('2d')")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_medium_711_viewport_gives_preview_full_width_without_letterbox_gap(workbench):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    page.locator("#seek").fill("4")
    page.set_viewport_size({"width": 711, "height": 960})
    page.locator("#creation-content").evaluate("panel => { panel.scrollTop = 0; }")
    expect(page.locator("#toast")).to_be_hidden(timeout=5000)
    host = page.locator("#scene-host").bounding_box()
    canvas = page.locator("#scene-host canvas").bounding_box()
    stage = page.locator(".stage-panel").bounding_box()
    creation = page.locator(".creation-panel").bounding_box()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "fan-threejs-711.png"))
    (ARTIFACTS / "fan-711-layout.json").write_text(json.dumps({"host": host, "canvas": canvas, "stage": stage, "creation": creation}, indent=2), encoding="utf-8")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert host["width"] > 650
    assert abs(host["height"] - host["width"] * 9 / 16) < 2
    assert abs(canvas["height"] - host["height"]) < 2
    # Narrow screens now put creation first; the sticky jump bar reaches preview.
    assert stage["y"] >= creation["y"] + creation["height"]
    page.locator('[data-workspace-jump="preview"]').click()
    expect(page.locator('#scene-host')).to_be_in_viewport()
    page.locator("#seek").fill("6")
    expect(page.locator("#current-time")).to_have_text("00:06.0")


def test_interaction_values_and_camera_save_restore_reset_without_reloading_canvas(workbench):
    page, _ = workbench
    expect(page.locator("#interaction-hint")).to_contain_text("没有构件自由度")
    expect(page.locator("#camera-toolbar")).to_be_hidden()
    page.locator('[data-sample="fan"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    page.locator("#seek").fill("4")
    expect(page.locator("#camera-toolbar")).to_be_visible()
    slider = page.locator(".interaction-slider").first
    control_id = slider.get_attribute("data-interaction-id")
    value = float(slider.get_attribute("min")) + float(slider.get_attribute("step")) * 15
    before = page.locator("#scene-host canvas").evaluate("canvas => { canvas.dataset.keep = 'same'; return canvas.toDataURL(); }")
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST") as saved:
        slider.fill(f"{value:g}")
    assert saved.value.ok
    stored = saved.value.json()["project"]
    assert stored["exploration"]["values"][control_id] == value
    expect(page.locator("#interaction-save-state")).to_have_text("已保存")
    expect(page.locator("#scene-host canvas")).to_have_attribute("data-keep", "same")
    expect(page.locator("#play")).to_have_attribute("aria-label", "播放动画")
    assert before != page.locator("#scene-host canvas").evaluate("canvas => canvas.toDataURL()")
    page.reload()
    expect(page.locator("#canvas-empty")).to_be_hidden(timeout=15000)
    expect(page.locator(f'.interaction-slider[data-interaction-id="{control_id}"]')).to_have_value(f"{value:g}")
    page.locator("#seek").fill("4")
    canvas = page.locator("#scene-host canvas").bounding_box()
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST") as camera_saved:
        page.mouse.move(canvas["x"] + canvas["width"] * .45, canvas["y"] + canvas["height"] * .45)
        page.mouse.down()
        page.mouse.move(canvas["x"] + canvas["width"] * .6, canvas["y"] + canvas["height"] * .52, steps=8)
        page.mouse.up()
    assert camera_saved.value.json()["project"]["exploration"]["camera"]["orbit"] == 0
    expect(page.locator("#camera-state")).to_contain_text("观察视角")
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST") as reset_saved:
        page.locator("#interaction-reset").click()
    restored = reset_saved.value.json()["project"]
    assert restored["exploration"]["camera"] is None
    assert restored["exploration"]["values"] == {item["id"]: item["value"] for item in restored["scene"]["interactions"]}
    expect(page.locator("#camera-state")).to_have_text("默认镜头 · 跟随场景")
    # A declared child hit moves the semantic rotor freedom, not the timeline.
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST"):
        page.locator('.interaction-toggle[data-interaction-id="guards-visible"]').uncheck()
    page.locator("#camera-interact").click()
    expect(page.locator("#camera-interact")).to_have_attribute("aria-pressed", "true")
    canvas = page.locator("#scene-host canvas").bounding_box()
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST") as dragged:
        page.mouse.move(canvas["x"] + canvas["width"] * .5, canvas["y"] + canvas["height"] * .47)
        page.mouse.down()
        page.mouse.move(canvas["x"] + canvas["width"] * .5 + 40, canvas["y"] + canvas["height"] * .47, steps=8)
        page.mouse.up()
    assert dragged.value.json()["project"]["exploration"]["values"][control_id] != 0
    expect(page.locator("#current-time")).to_have_text("00:04.0")
    current_value = page.locator(f'.interaction-slider[data-interaction-id="{control_id}"]').input_value()
    with page.expect_response(lambda response: "/recompute" in response.url and response.request.method == "POST"):
        page.locator('.control-slider[data-control-id="pitch"]').fill("25")
    expect(page.locator("#parameter-state")).to_have_text("参数已更新")
    expect(page.locator(f'.interaction-slider[data-interaction-id="{control_id}"]')).to_have_value(current_value)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.locator("#interaction-section").scroll_into_view_if_needed()
    page.screenshot(path=str(ARTIFACTS / "fan-interaction-1440.png"))


def test_mobile_touch_observation_and_export_wait_for_latest_interaction(workbench):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    enable_mock_provider(page)
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#seek").fill("4")
    expect(page.locator("#camera-free")).to_have_attribute("aria-pressed", "true")
    canvas = page.locator("#scene-host canvas").bounding_box()
    touch = page.context.new_cdp_session(page)
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST") as camera_saved:
        touch.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": canvas["x"] + 80, "y": canvas["y"] + 65}]})
        touch.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": canvas["x"] + 125, "y": canvas["y"] + 85}]})
        touch.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    assert camera_saved.value.json()["project"]["exploration"]["camera"] is not None
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / "fan-touch-390.png"))
    calls = []
    page.on("request", lambda request: calls.append(request.url.rsplit("/", 1)[-1]) if request.method == "POST" and ("/interaction-state" in request.url or request.url.endswith("/export")) else None)
    job = {"id": "interaction_export", "kind": "export", "status": "completed", "stage": "completed", "message": "完成", "events": [], "created": time.time(), "updated": time.time(), "progress": 100}
    page.route("**/api/projects/*/export", lambda route: route.fulfill(status=202, json={"job": job}))
    toggle = page.locator(".interaction-toggle").first
    toggle.set_checked(not toggle.is_checked())
    page.locator("#export-toggle").click()
    expect(page.locator(".export-note")).to_contain_text("当前构件交互与观察视角")
    page.locator("#export-video").click()
    expect(page.locator("#export-dialog")).not_to_be_visible()
    assert "interaction-state" in calls and "export" in calls
    assert calls.index("interaction-state") < calls.index("export")
    touch.detach()


def test_same_project_delayed_read_preserves_newer_interaction_and_numeric_commit(workbench):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    page.locator("#seek").fill("4")
    angle = page.get_by_role("spinbutton", name="手动转动叶轮数值", exact=True)
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST") as numeric_saved:
        angle.fill("60")
        angle.press("Tab")
        page.locator('.interaction-toggle[data-interaction-id="guards-visible"]').uncheck()
    expect(page.locator("#interaction-save-state")).to_have_text("已保存")
    project = numeric_saved.value.json()["project"]
    assert project["exploration"]["values"]["rotor-angle"] == 60
    assert project["exploration"]["values"]["guards-visible"] == 0

    delayed = {}
    endpoint = f'**/api/projects/{project["id"]}'
    def hold_current_project(route):
        response = route.fetch()
        delayed.update(route=route, response=response)
    page.route(endpoint, hold_current_project)
    page.locator("#history-tab").click()
    with page.expect_request(lambda request: request.url.endswith(f'/api/projects/{project["id"]}')):
        page.locator(f'.project-card[data-project-id="{project["id"]}"]').click()
    # The route has already read the old snapshot, but its delivery stays pending.
    deadline = time.monotonic() + 5
    while "route" not in delayed and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert "route" in delayed
    assert delayed["response"].json()["project"]["exploration"]["values"]["rotor-angle"] == 60
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST"):
        angle.fill("95")
        angle.press("Tab")
    expect(page.locator("#interaction-save-state")).to_have_text("已保存")
    delayed["route"].fulfill(response=delayed["response"])
    page.unroute(endpoint, hold_current_project)
    expect(page.locator("#play")).to_be_enabled()
    expect(page.locator('.interaction-slider[data-interaction-id="rotor-angle"]')).to_have_value("95")
    expect(page.get_by_role("spinbutton", name="手动转动叶轮数值", exact=True)).to_have_value("95")
    saved_project = page.request.get(f'{page.url.rstrip("/")}/api/projects/{project["id"]}').json()["project"]
    assert saved_project["exploration"]["values"]["rotor-angle"] == 95


def test_numeric_keyboard_tab_then_toggle_commits_angle_at_animation_end(workbench):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    page.locator("#seek").fill("12")
    angle = page.get_by_role("spinbutton", name="手动转动叶轮数值", exact=True)
    angle.evaluate("input => { window.angleChanges = []; input.addEventListener('change', () => window.angleChanges.push(input.value)); }")
    with page.expect_response(lambda response: "/interaction-state" in response.url and response.request.method == "POST") as saved:
        angle.click()
        angle.press("ControlOrMeta+A")
        angle.press_sequentially("60")
        angle.press("Tab")
        page.locator('.interaction-toggle[data-interaction-id="guards-visible"]').uncheck()
    expect(page.locator("#interaction-save-state")).to_have_text("已保存")
    values = saved.value.json()["project"]["exploration"]["values"]
    assert values["rotor-angle"] == 60 and values["guards-visible"] == 0
    assert page.evaluate("window.angleChanges") == ["60"]
    expect(angle).to_have_value("60")


@pytest.mark.parametrize("output_kind", ["video", "json"])
def test_immediate_export_drains_trusted_parameter_recompute_and_exploration(workbench, output_kind):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    enable_mock_provider(page)
    exported = []
    def export(route):
        project_url = route.request.url.removesuffix("/export")
        exported.append(page.request.get(project_url).json()["project"])
        job = {"id": "latest_parameter_export", "kind": "export", "status": "completed", "stage": "completed", "message": "完成", "events": [], "created": time.time(), "updated": time.time(), "progress": 100}
        route.fulfill(status=202, json={"job": job})
    page.route("**/api/projects/*/export", export)
    # Queue both kinds of change, then start export before their normal debounce.
    page.locator('.interaction-slider[data-interaction-id="rotor-angle"]').fill("33")
    page.locator('.control-slider[data-control-id="pitch"]').fill("27")
    page.locator("#export-toggle").click()
    if output_kind == "video":
        page.locator("#export-video").click()
        expect(page.locator("#export-dialog")).not_to_be_visible(timeout=10000)
        assert len(exported) == 1
        result = exported[0]
        assert result["proposal"]["parameters"]["pitch"] == 27
    else:
        with page.expect_download() as download:
            page.locator("#export-json").click()
        result = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    assert next(control["value"] for control in result["scene"]["controls"] if control["id"] == "pitch") == 27
    assert result["exploration"]["values"]["rotor-angle"] == 33
    expect(page.locator("#parameter-state")).to_have_text("参数已更新")


def test_video_export_waits_for_already_running_recompute(workbench):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator("#scene-mode")).to_have_text("3D", timeout=15000)
    expect(page.locator("#play")).to_be_enabled()
    enable_mock_provider(page)
    held = {}
    def hold_recompute(route):
        response = route.fetch()
        held.update(route=route, response=response)
    page.route("**/api/projects/*/recompute", hold_recompute)
    with page.expect_request(lambda request: request.url.endswith("/recompute")):
        page.locator('.control-slider[data-control-id="pitch"]').fill("31")
    deadline = time.monotonic() + 5
    while "route" not in held and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert "route" in held
    calls = []
    def export(route):
        calls.append(route.request.url)
        job = {"id": "running_parameter_export", "kind": "export", "status": "completed", "stage": "completed", "message": "完成", "events": [], "created": time.time(), "updated": time.time(), "progress": 100}
        route.fulfill(status=202, json={"job": job})
    page.route("**/api/projects/*/export", export)
    page.locator('.interaction-slider[data-interaction-id="rotor-angle"]').fill("45")
    page.locator("#export-toggle").click()
    page.locator("#export-video").click()
    expect(page.locator("#export-video")).to_be_disabled()
    page.wait_for_timeout(100)
    assert calls == []
    held["route"].fulfill(response=held["response"])
    expect(page.locator("#export-dialog")).not_to_be_visible(timeout=10000)
    assert len(calls) == 1
    project = page.request.get(calls[0].removesuffix("/export")).json()["project"]
    assert project["proposal"]["parameters"]["pitch"] == 31
    assert project["exploration"]["values"]["rotor-angle"] == 45


def test_project_revision_preview_restore_and_reopen(workbench):
    page, _ = workbench
    before = page.request.get(page.url.rstrip('/') + '/api/projects').json()['projects'][0]
    original = page.request.get(page.url.rstrip('/') + '/api/projects/' + before['id']).json()['project']
    slider = page.locator('.control-slider[data-control-id="speed"]')
    slider.fill('20')
    expect(page.locator('#scene-meta')).to_contain_text('v2')
    page.locator('#versions-toggle').click()
    expect(page.locator('.revision-card')).to_have_count(2)
    page.locator('.revision-card[data-revision="1"]').get_by_role('button', name='回看此版本').click()
    expect(page.locator('#revision-preview')).to_be_visible()
    expect(page.locator('#scene-meta')).to_contain_text('v1')
    expect(slider).to_be_disabled()
    expect(page.locator('#generate')).to_be_disabled()
    expect(page.locator('#export-toggle')).to_be_disabled()
    page.locator('#seek').fill('8')
    expect(page.locator('#current-time')).to_have_text('00:08.0')
    current = page.request.get(page.url.rstrip('/') + '/api/projects/' + before['id']).json()['project']
    assert current['revision'] == 2 and current['proposal']['parameters']['speed'] == 20
    page.locator('#revision-restore').click()
    expect(page.locator('#revision-preview')).not_to_be_visible()
    expect(page.locator('#scene-meta')).to_contain_text('v3')
    expect(slider).to_be_enabled()
    restored = page.request.get(page.url.rstrip('/') + '/api/projects/' + before['id']).json()['project']
    assert restored['scene'] == original['scene']
    assert restored['restored_from'] == 1
    assert len(page.request.get(page.url.rstrip('/') + '/api/projects').json()['projects']) == 1
    page.reload()
    expect(page.locator('#scene-meta')).to_contain_text('v3')
    page.locator('#versions-toggle').click()
    expect(page.locator('.revision-card')).to_have_count(3)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / 'revisions-desktop.png'))
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(ARTIFACTS / 'revisions-mobile.png'))
    assert page.locator('#versions-dialog').evaluate('node => node.scrollWidth <= node.clientWidth + 1')


def test_iteration_flushes_pending_parameters_and_sends_revision(workbench):
    page, _ = workbench
    enable_mock_provider(page)
    submitted = []
    def submit(route):
        submitted.append(route.request.post_data_json)
        route.fulfill(status=202, json={'job': {'id': 'iteration_revision_test', 'kind': 'create', 'status': 'needs_input', 'message': '请明确需要增加的内容。', 'events': [], 'created': time.time()}})
    page.route('**/api/jobs', lambda route: submit(route) if route.request.method == 'POST' else route.continue_())
    page.locator('.control-slider[data-control-id="speed"]').fill('19')
    page.locator('#prompt').fill('保留已有轨迹，增加说明初速度的标注')
    page.locator('#generate').click()
    expect(page.locator('[data-job-id="iteration_revision_test"]')).to_be_visible()
    assert len(submitted) == 1 and submitted[0]['expected_revision'] == 2
    saved = page.request.get(page.url.rstrip('/') + '/api/projects/' + submitted[0]['parent_id']).json()['project']
    assert saved['proposal']['parameters']['speed'] == 19
    assert saved['revision'] == 2


def test_visualization_library_filters_and_new_schemes(workbench):
    page, _ = workbench
    for category, sample, control, value in [
        ('math', 'riemann', 'count', '20'),
        ('physics', 'refraction', 'angle', '70'),
        ('process', 'queue', 'service', '2'),
    ]:
        page.locator('#sample-filter').select_option(category)
        expect(page.locator(f'[data-sample="{sample}"]')).to_be_visible()
        page.locator(f'[data-sample="{sample}"]').click()
        expect(page.locator(f'.control-slider[data-control-id="{control}"]')).to_be_visible(timeout=15000)
        page.locator(f'.control-slider[data-control-id="{control}"]').fill(value)
        expect(page.locator('#parameter-state')).to_have_text('参数已更新')
        expect(page.locator('#evidence-label')).to_have_text('计算生成')
        expect(page.locator('#scene-host canvas')).to_have_count(1)


def test_parameter_change_during_post_recompute_autosave_is_not_lost(workbench):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator('#scene-mode')).to_have_text('3D', timeout=15000)
    expect(page.locator('#play')).to_be_enabled()
    pitch = page.locator('.control-slider[data-control-id="pitch"]')
    angle = page.locator('.interaction-slider[data-interaction-id="rotor-angle"]')
    held_recompute, held_exploration, recomputes = {}, {}, []

    def hold_first_recompute(route):
        recomputes.append(route.request.post_data_json)
        if len(recomputes) == 1:
            held_recompute.update(route=route, response=route.fetch())
        else:
            route.continue_()

    def hold_exploration(route):
        held_exploration.update(route=route, response=route.fetch())

    page.route('**/api/projects/*/recompute', hold_first_recompute)
    page.route('**/api/projects/*/interaction-state', hold_exploration)
    pitch.fill('25')
    deadline = time.monotonic() + 5
    while 'route' not in held_recompute and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert 'route' in held_recompute
    first_project = held_recompute['response'].json()['project']
    assert first_project['revision'] == 2
    # This gesture is queued behind the in-flight parameter response. After
    # that response arrives, the recompute routine waits for its state save.
    angle.fill('45')
    held_recompute['route'].fulfill(response=held_recompute['response'])
    deadline = time.monotonic() + 5
    while 'route' not in held_exploration and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert 'route' in held_exploration
    assert held_exploration['route'].request.post_data_json['expected_revision'] == 2
    # A newer parameter edit must survive the await before showProject(v2).
    pitch.fill('30')
    expect(page.locator('#parameter-state')).to_have_text('等待重算…')
    held_exploration['route'].fulfill(response=held_exploration['response'])
    page.unroute('**/api/projects/*/interaction-state', hold_exploration)
    expect(page.locator('#scene-meta')).to_contain_text('v3', timeout=10000)
    expect(page.locator('#parameter-state')).to_have_text('参数已更新')
    expect(pitch).to_have_value('30')
    expect(angle).to_have_value('45')
    assert [item['parameters']['pitch'] for item in recomputes] == [25, 30]
    project = page.request.get(page.url.rstrip('/') + '/api/projects/' + first_project['id']).json()['project']
    assert project['revision'] == 3 and project['proposal']['parameters']['pitch'] == 30
    assert project['exploration']['values']['rotor-angle'] == 45


def test_closed_history_request_cannot_enter_preview_after_current_edit(workbench):
    page, _ = workbench
    page.locator('[data-sample="fan"]').click()
    expect(page.locator('#scene-mode')).to_have_text('3D', timeout=15000)
    expect(page.locator('#play')).to_be_enabled()
    pitch = page.locator('.control-slider[data-control-id="pitch"]')
    with page.expect_response(lambda response: response.url.endswith('/recompute')) as updated:
        pitch.fill('25')
    project = updated.value.json()['project']
    expect(page.locator('#scene-meta')).to_contain_text('v2')
    held_history, held_exploration = {}, {}
    history_endpoint = f'**/api/projects/{project["id"]}/revisions/1'

    def hold_history(route):
        held_history.update(route=route, response=route.fetch())

    def hold_exploration(route):
        held_exploration.update(route=route, response=route.fetch())

    page.route(history_endpoint, hold_history)
    page.route('**/api/projects/*/interaction-state', hold_exploration)
    page.locator('#versions-toggle').click()
    trigger = page.locator('.revision-card[data-revision="1"] button')
    trigger.click()
    deadline = time.monotonic() + 5
    while 'route' not in held_history and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert 'route' in held_history
    page.keyboard.press('Escape')
    expect(page.locator('#versions-dialog')).not_to_be_visible()
    # After dismissing the pending history request, editing the current
    # project remains valid. Hold its save until the old history response.
    page.locator('.interaction-slider[data-interaction-id="rotor-angle"]').fill('80')
    deadline = time.monotonic() + 5
    while 'route' not in held_exploration and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert 'route' in held_exploration
    assert held_exploration['route'].request.post_data_json['expected_revision'] == 2
    held_history['route'].fulfill(response=held_history['response'])
    # Re-enabled trigger confirms the awaited click callback has finished.
    expect(trigger).to_be_enabled()
    expect(page.locator('#revision-preview')).not_to_be_visible()
    held_exploration['route'].fulfill(response=held_exploration['response'])
    expect(page.locator('#interaction-save-state')).to_have_text('已保存')
    expect(page.locator('#scene-meta')).to_contain_text('v2')
    expect(pitch).to_be_enabled()
    expect(pitch).to_have_value('25')
    expect(page.locator('.interaction-slider[data-interaction-id="rotor-angle"]')).to_have_value('80')
    current = page.request.get(page.url.rstrip('/') + '/api/projects/' + project['id']).json()['project']
    assert current['revision'] == 2 and current['proposal']['parameters']['pitch'] == 25
    assert current['exploration']['values']['rotor-angle'] == 80
