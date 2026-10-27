"""Opt-in real browser/FFmpeg checks use an isolated ephemeral local server."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import threading
from urllib.parse import urlsplit

import pytest

from server.exporter import ExportCancelled, ExportError, _chromium_path, _safe_worker_env, export_video, renderer_capabilities
from server.schema import Scene

ROOT = Path(__file__).resolve().parents[1]
REAL = os.environ.get('RUN_REAL_EXPORT') == '1'


def sample_scene(mode='2d'):
    return Scene.model_validate({
        'title': '确定性运动验证', 'duration': 6, 'mode': mode,
        'objects': [
            {'id':'ball','kind':'sphere' if mode == '3d' else 'circle','radius':.65,'x':-3,'frames':[{'t':0,'x':-3},{'t':6,'x':3}]},
            {'id':'trail','kind':'path','points':[[-3,-1.5],[0,1.5],[3,-1.5]],'stroke':'#829cf5','frames':[{'t':0,'draw':0},{'t':6,'draw':1}]},
            {'id':'eq','kind':'formula','y':3,'font_size':.5,'latex':'x(t)=v_0t','latex_next':'v(t)=v_0'},
            {'id':'title','kind':'text','y':-3,'text':'运动与时间同步','font_size':.4},
        ]}).model_dump()


@contextmanager
def render_server(scene):
    state = {'scene':scene}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/api/export-scene/test-job':
                if self.headers.get('Cookie') != 'test_session=private-export-session':
                    self.send_error(403); return
                payload = json.dumps(state['scene']).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(payload); return
            roots = {'/vendor/three/': ROOT / 'node_modules/three/build', '/vendor/katex/':ROOT / 'node_modules/katex/dist'}
            file_root = ROOT / 'web'; suffix = path.removeprefix('/web/').lstrip('/')
            for prefix, candidate in roots.items():
                if path.startswith(prefix): file_root = candidate; suffix = path[len(prefix):]; break
            target = (file_root / suffix).resolve()
            if not target.is_relative_to(file_root.resolve()) or not target.is_file():
                self.send_error(404); return
            payload = target.read_bytes(); self.send_response(200); self.send_header('Content-Type', 'text/javascript' if target.suffix in ('.js','.mjs') else mimetypes.guess_type(str(target))[0] or 'application/octet-stream'); self.end_headers(); self.wfile.write(payload)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_worker_environment_excludes_credentials(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'do-not-copy')
    monkeypatch.setenv('OPENAI_API_KEY', 'do-not-copy')
    monkeypatch.setenv('PYTHONPATH', 'untrusted')
    env = _safe_worker_env()
    assert 'ANTHROPIC_API_KEY' not in env and 'OPENAI_API_KEY' not in env and 'PYTHONPATH' not in env


def test_cancelled_export_never_publishes(tmp_path, monkeypatch):
    monkeypatch.setattr('server.exporter.renderer_capabilities', lambda: {'browser':True, 'manim':True})
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(ExportCancelled):
        export_video(sample_scene(), tmp_path / 'cancelled.mp4', cancelled=cancelled)
    assert not list(tmp_path.glob('*.mp4'))


def test_export_rejects_nonlocal_server(tmp_path, monkeypatch):
    pytest.importorskip('playwright')
    monkeypatch.setattr('server.exporter.renderer_capabilities', lambda: {'browser':True, 'manim':True})
    with pytest.raises(ExportError, match='本地'):
        export_video(sample_scene(), tmp_path / 'rejected.mp4', base_url='https://example.com', job_id='test-job', cookie_name='a', cookie_value='b')
    assert not list(tmp_path.glob('*.mp4'))


@pytest.mark.skipif(not REAL, reason='Set RUN_REAL_EXPORT=1 for actual browser capture and ffmpeg.')
@pytest.mark.parametrize('mode', ['2d','3d'])
def test_real_six_second_mp4(tmp_path,mode):
    assert renderer_capabilities()['browser']
    events = []
    with render_server(sample_scene(mode)) as (base_url, _):
        output = export_video(sample_scene(mode), tmp_path / 'real-six-seconds.mp4', fps=15, base_url=base_url, job_id='test-job', cookie_name='test_session', cookie_value='private-export-session', on_event=events.append, timeout=180)
    data = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
    stream = data['streams'][0]
    assert (stream['width'],stream['height']) == (1280,720)
    assert stream['r_frame_rate'] == '15/1' and stream['pix_fmt'] == 'yuv420p'
    assert abs(float(data['format']['duration']) - 6) < .05
    assert int(stream['nb_frames']) == 90
    assert events[-1]['progress'] == 100
    assert output.read_bytes().find(b'moov') < output.read_bytes().find(b'mdat')


@pytest.mark.skipif(not REAL, reason='Set RUN_REAL_EXPORT=1 for browser rendering.')
@pytest.mark.parametrize('mode', ['2d','3d'])
def test_seek_hide_and_formula_are_rendered(tmp_path, mode):
    from playwright.sync_api import sync_playwright
    with render_server(sample_scene(mode)) as (base_url, _), sync_playwright() as p:
        options = {'headless':True}
        if _chromium_path(): options['executable_path'] = _chromium_path()
        browser = p.chromium.launch(**options)
        try:
            context = browser.new_context(viewport={'width':1280,'height':720}, device_scale_factor=1)
            context.add_cookies([{'name':'test_session','value':'private-export-session','url':base_url}])
            page = context.new_page(); errors=[]; page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(base_url + '/render.html?job=test-job')
            page.wait_for_function('window.renderReady || window.renderError', timeout=30000)
            assert page.evaluate('window.renderError') is None
            page.evaluate('window.renderFrame(1.5)')
            first = page.screenshot(path=str(tmp_path / f'{mode}-first.png'))
            page.evaluate('window.renderFrame(5)')
            assert page.screenshot() != first
            assert page.locator('[data-phase="next"]').evaluate('(el)=>getComputedStyle(el).opacity') == '1'
            page.evaluate('window.renderFrame(1.5)')
            assert page.screenshot() == first
            page.evaluate('window.scenePlayer.setVisible("ball",false)')
            assert page.screenshot() != first
            assert page.locator('.katex').count() == 2
            assert not errors
        finally:
            browser.close()
