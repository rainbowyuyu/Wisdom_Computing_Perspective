"""Deterministic local exports. Scene data never becomes executable code."""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


class ExportError(RuntimeError):
    pass


class ExportCancelled(ExportError):
    pass


class ExportUnavailable(ExportError):
    pass


def _chromium_path() -> str | None:
    """Use a separate headless profile, never the user's browsing session."""
    candidates = [
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Microsoft/Edge/Application/msedge.exe',
    ]
    return next((str(p) for p in candidates if p.is_file()), None)


def _has_browser() -> bool:
    if not importlib.util.find_spec('playwright'):
        return False
    if _chromium_path():
        return True
    browser_root = Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or Path(os.environ.get('LOCALAPPDATA', Path.home() / '.cache')) / 'ms-playwright')
    return browser_root.exists() and any(browser_root.glob('chromium*'))


def renderer_capabilities() -> dict[str, bool]:
    ffmpeg = bool(shutil.which('ffmpeg'))
    return {
        'browser': ffmpeg and _has_browser(),
        'manim': ffmpeg and bool(importlib.util.find_spec('manim')) and bool(shutil.which('latex')) and bool(shutil.which('dvisvgm')),
    }


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        import signal
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _popen_options() -> dict:
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def _safe_worker_env() -> dict[str, str]:
    # Explicit allowlist: no inherited API keys, provider auth, proxy or Python hooks.
    names = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP', 'TMPDIR', 'LOCALAPPDATA', 'APPDATA', 'PROGRAMDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'USERPROFILE', 'HOME', 'LANG', 'LC_ALL', 'NUMBER_OF_PROCESSORS', 'PLAYWRIGHT_BROWSERS_PATH'}
    result = {key: value for key, value in os.environ.items() if key.upper() in names}
    result.update({'PYTHONNOUSERSITE': '1', 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
    return result


def export_video(scene: dict, output_path: str | Path, *, engine: str = 'browser', fps: int = 24,
                 base_url: str = '', job_id: str = '', cookie_name: str = '', cookie_value: str = '',
                 asset_root: str | Path | None = None, cancelled: threading.Event | None = None,
                 on_event=None, timeout: float = 600) -> Path:
    """Run in a job worker thread; on_event receives stage/progress/message dicts.

    The server owns job_id and its private scene endpoint. Cookie credentials remain
    in memory and are never put in argv, logs or output files. A failed export never
    publishes a partial MP4. The caller must serialize export jobs for resource use.
    """
    from server.schema import Scene
    try:
        scene = Scene.model_validate(scene).model_dump()
    except Exception as error:
        raise ExportError('场景校验失败，未开始导出。') from error
    if fps not in (15, 24):
        raise ExportError('仅支持 15 或 24 fps。')
    if engine not in ('browser', 'manim'):
        raise ExportError('未知导出引擎。')
    if not renderer_capabilities()[engine]:
        raise ExportUnavailable('浏览器导出依赖不可用。' if engine == 'browser' else 'Manim / LaTeX / dvisvgm / FFmpeg 未完整安装，无法使用该后端。')
    if engine == 'manim':
        if scene['mode'] != '2d':
            raise ExportUnavailable('三维场景请使用浏览器视频导出；Manim 后端用于二维几何与公式变形。')
        from server.tex_safety import validate_tex
        try:
            for obj in scene['objects']:
                if obj['kind'] == 'formula':
                    validate_tex(obj['latex'])
                    if obj['latex_next']: validate_tex(obj['latex_next'])
        except ValueError as error:
            raise ExportError(str(error)) from error
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ExportError('导出目标已存在，请创建新任务。')
    partial = output.with_name(output.stem + '.partial.mp4')
    if partial.exists():
        raise ExportError('导出任务临时文件已存在。')
    deadline = time.monotonic() + max(1, min(float(timeout), 1800))
    cancel = cancelled or threading.Event()

    def check():
        if cancel.is_set():
            raise ExportCancelled('导出已取消。')
        if time.monotonic() >= deadline:
            raise ExportError('导出超时，已停止本次任务。')

    def event(stage, progress, message):
        check()
        if on_event:
            on_event({'stage': stage, 'progress': progress, 'message': message})

    try:
        event('rendering', 2, '正在准备本地渲染器。')
        if engine == 'browser':
            _export_browser(scene, partial, fps, base_url, job_id, cookie_name, cookie_value, check, event, deadline)
        else:
            _export_manim(scene, partial, fps, asset_root, check, event, deadline)
        check()
        if not partial.is_file() or partial.stat().st_size < 1024:
            raise ExportError('导出未产生有效视频。')
        partial.replace(output)
        if on_event:
            on_event({'stage': 'completed', 'progress': 100, 'message': 'MP4 视频已生成。'})
        return output
    except (ExportError, ExportCancelled):
        raise
    except Exception as error:
        raise ExportError('本地渲染失败，请检查渲染依赖后重试。') from error
    finally:
        partial.unlink(missing_ok=True)


def _export_browser(scene, output, fps, base_url, job_id, cookie_name, cookie_value, check, event, deadline):
    from playwright.sync_api import sync_playwright
    parsed = urlparse(base_url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
        raise ExportError('导出只能连接当前本地服务。')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', job_id) or not cookie_name or not cookie_value:
        raise ExportError('导出任务会话无效。')
    base_url = base_url.rstrip('/')
    total = math.ceil(scene['duration'] * fps)
    process = None
    log_path = output.with_suffix('.ffmpeg.log')
    guard_stop = threading.Event()
    process_box: list[subprocess.Popen] = []
    def guard():
        while not guard_stop.wait(.1):
            try:
                check()
            except ExportError:
                if process_box:
                    _stop_process(process_box[0])
                return
    watcher = threading.Thread(target=guard, daemon=True)
    try:
        with sync_playwright() as playwright:
            launch = {'headless': True, 'args': ['--disable-dev-shm-usage'], 'timeout': min(30000, max(1000, int((deadline - time.monotonic()) * 1000)))}
            executable = _chromium_path()
            if executable:
                launch['executable_path'] = executable
            browser = playwright.chromium.launch(**launch)
            try:
                context = browser.new_context(viewport={'width': 1280, 'height': 720}, device_scale_factor=1, locale='zh-CN', color_scheme='dark')
                context.add_cookies([{'name': cookie_name, 'value': cookie_value, 'url': base_url, 'httpOnly': True, 'sameSite': 'Strict'}])
                # Block all off-origin requests, including an unexpected asset URL.
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base_url + '/') else route.abort())
                page = context.new_page()
                page.set_default_timeout(10000)
                page.goto(f'{base_url}/render.html?job={job_id}', wait_until='domcontentloaded', timeout=30000)
                start = time.monotonic()
                while not page.evaluate('Boolean(window.renderReady || window.renderError)'):
                    check()
                    if time.monotonic() - start > 45:
                        raise ExportError('场景加载超时。')
                    page.wait_for_timeout(50)
                if page.evaluate('window.renderError'):
                    raise ExportError('场景或本地渲染资源未能加载。')
                check()
                with log_path.open('wb') as log:
                    command = [shutil.which('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-vcodec', 'png', '-r', str(fps), '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-threads', '2', '-f', 'mp4', str(output)]
                    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log, env=_safe_worker_env(), **_popen_options())
                    process_box.append(process); watcher.start()
                    for frame in range(total):
                        check()
                        page.evaluate('(t) => window.renderFrame(t)', frame / fps)
                        png = page.screenshot(type='png', animations='disabled', timeout=10000)
                        try:
                            process.stdin.write(png)
                        except (BrokenPipeError, OSError) as error:
                            check()
                            raise ExportError('视频编码进程提前退出。') from error
                        if frame == 0 or frame % max(1, fps) == 0 or frame == total - 1:
                            event('rendering', 5 + round(88 * (frame + 1) / total, 1), f'正在渲染 {frame + 1} / {total} 帧。')
                    process.stdin.close()
                    event('encoding', 96, '正在完成 MP4 编码。')
                    while process.poll() is None:
                        check(); time.sleep(.05)
                    if process.returncode:
                        raise ExportError('FFmpeg 编码失败。')
            finally:
                browser.close()
    finally:
        guard_stop.set()
        if watcher.is_alive(): watcher.join(timeout=2)
        _stop_process(process)
        log_path.unlink(missing_ok=True)


def _export_manim(scene, output, fps, asset_root, check, event, deadline):
    scratch = output.parent / (output.stem + '-manim')
    scratch.mkdir(exist_ok=False)
    scene_path = scratch / 'scene.json'
    scene_path.write_text(json.dumps(scene, ensure_ascii=False), encoding='utf-8')
    env = _safe_worker_env()
    env.update({'DSH_SCENE_PATH': str(scene_path), 'DSH_ASSET_ROOT': str(Path(asset_root).resolve()) if asset_root else str(scratch / 'assets')})
    log_path = scratch / 'render.log'
    command = [sys.executable, '-m', 'manim', '--disable_caching', '--format', 'mp4', '--fps', str(fps), '-r', '1280,720', '--media_dir', str(scratch / 'media'), '-o', 'scene.mp4', str(ROOT / 'server/manim_scene.py'), 'DSHScene']
    process = None
    try:
        with log_path.open('wb') as log:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log, env=env, **_popen_options())
            event('rendering', 8, 'Manim 正在生成几何与数学动画。')
            while process.poll() is None:
                check(); time.sleep(.1)
            check()
            if process.returncode:
                raise ExportError('Manim 渲染失败；请检查公式和本地 LaTeX 依赖。')
        candidates = list((scratch / 'media').rglob('scene.mp4'))
        if len(candidates) != 1:
            raise ExportError('Manim 未返回唯一的视频文件。')
        event('encoding', 96, '正在整理 MP4 文件。')
        with log_path.open('ab') as log:
            process = subprocess.Popen([shutil.which('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(candidates[0]), '-c', 'copy', '-movflags', '+faststart', str(output)], stdout=log, stderr=log, env=env, **_popen_options())
            while process.poll() is None:
                check(); time.sleep(.05)
            if process.returncode:
                raise ExportError('MP4 文件封装失败。')
    finally:
        _stop_process(process)
        # Scratch is generated here under the caller's output directory only.
        if scratch.parent == output.parent and scratch.name == output.stem + '-manim':
            shutil.rmtree(scratch, ignore_errors=True)
