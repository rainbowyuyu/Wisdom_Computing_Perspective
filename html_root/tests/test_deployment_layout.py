"""An isolated website copy must serve assets without its repository parent."""
import os
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
import httpx
import mysql.connector
import pytest
from websockets.sync.client import connect
from app import config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def uploaded_site(tmp_path):
    site = tmp_path / 'uploaded' / 'html_root'
    site.mkdir(parents=True)
    for folder in ('app', 'logic', 'database'):
        shutil.copytree(ROOT / folder, site / folder, ignore=shutil.ignore_patterns('__pycache__'))
    for file in ('main.py', 'start.py'):
        shutil.copy2(ROOT / file, site / file)
    for folder in ('css', 'js', 'assets', 'docs', 'videos'):
        (site / 'static' / folder).mkdir(parents=True)
    for file in ('index.html', 'css/components/release-banner.css', 'docs/update.md'):
        target = site / 'static' / file
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'static' / file, target)
    return site


def test_standalone_copy_runs_from_unrelated_working_directory(tmp_path, uploaded_site):
    site = uploaded_site
    script = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import main, app.config
from fastapi.testclient import TestClient
assert Path(main.__file__).parent == Path(sys.argv[1])
assert Path(app.config.__file__).parents[1] == Path(sys.argv[1])
client = TestClient(main.app)
for route in ('/', '/static/css/components/release-banner.css', '/update.md'):
    response = client.get(route)
    assert response.status_code == 200, (route, response.status_code)
assert client.get('/.env.local').status_code == 404
assert client.get('/visdom_db.sql').status_code == 404
'''
    env = {**os.environ, 'MYSQL_HOST': '127.0.0.1', 'MYSQL_PORT': '1', 'ALIYUN_KEY': ''}
    result = subprocess.run([sys.executable, '-c', script, str(site)], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.getenv('WISDOM_DATABASE_TESTS') != '1', reason='Requires disposable MySQL database')
@pytest.mark.parametrize('entry', ['main.py', 'start.py'])
def test_real_launcher_serves_http_database_stream_and_websocket(tmp_path, uploaded_site, entry):
    name = 'qa_launcher_' + uuid.uuid4().hex
    conn = mysql.connector.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                                   user=config.MYSQL_USER, password=config.MYSQL_PASSWORD)
    cursor = conn.cursor()
    created = False
    process = None
    output = tmp_path / 'launcher.log'
    try:
        cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
        created = True
        cursor.execute(f'USE `{name}`')
        sql = re.sub(r'^\s*--[^\n]*', '', (ROOT / 'visdom_db.sql').read_text(encoding='utf-8'), flags=re.M)
        for statement in sql.split(';'):
            if statement.strip():
                cursor.execute(statement)
                if cursor.with_rows:
                    cursor.fetchall()
        cursor.execute("INSERT INTO users(username,hashed_password) VALUES('startup_probe','not-a-login')")
        conn.commit()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        env = {**os.environ, 'HOST': '127.0.0.1', 'PORT': str(port),
               'MYSQL_HOST': config.MYSQL_HOST, 'MYSQL_PORT': str(config.MYSQL_PORT),
               'MYSQL_USER': config.MYSQL_USER, 'MYSQL_PASSWORD': config.MYSQL_PASSWORD,
               'MYSQL_DB': name, 'ALIYUN_KEY': ''}
        with output.open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, str(uploaded_site / entry)], cwd=tmp_path,
                                       env=env, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=3, trust_env=False) as client:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                assert process.poll() is None, output.read_text(encoding='utf-8')
                try:
                    if client.get('/').status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            else:
                pytest.fail('Startup timed out: ' + output.read_text(encoding='utf-8'))
            for section in ('home', 'detect', 'calculate', 'agent', 'devtools', 'examples', 'my-formulas'):
                assert client.get('/', params={'section': section}).status_code == 200
            assert client.get('/static/css/components/release-banner.css').status_code == 200
            assert client.get('/update.md').status_code == 200
            captcha = client.get('/api/captcha')
            assert captcha.status_code == 200 and captcha.headers['content-type'] == 'image/png'
            assert client.get('/api/user/check-username', params={'username': 'startup_probe'}).json() == {'available': False}
            assert client.get('/api/agent/tools').status_code == 200
            assert client.get('/api/solve/capabilities').status_code == 200
            for protected in ('/api/wrongbook/list', '/api/examples/course-packs', '/api/user/me'):
                assert client.get(protected).status_code == 401
            routes = client.get('/openapi.json').json()['paths']
            assert {'/api/detect', '/api/devtools/edit_code', '/api/solve/render', '/api/agent/execute'} <= routes.keys()
            solution = client.post('/api/solve/stream', json={'problem': '解方程 x^2-5*x+6=0'})
            events = [json.loads(line[6:]) for line in solution.text.splitlines() if line.startswith('data: ')]
            assert any(e['type'] == 'step' for e in events)
            assert events[-1]['type'] == 'complete', events
        with connect(f'ws://127.0.0.1:{port}/api/examples/ws/startup-probe', open_timeout=5) as ws:
            assert json.loads(ws.recv(timeout=3))['type'] == 'viewer_count'
            ws.send('{"type":"ping"}')
            assert json.loads(ws.recv(timeout=3))['type'] == 'pong'
        conn.commit()
        cursor.execute('SELECT COUNT(*) FROM schema_migrations')
        assert cursor.fetchone()[0] == len(list((uploaded_site / 'database/migrations').glob('*.sql')))
        assert output.read_text(encoding='utf-8').count('MySQL connection pool created successfully') == 1
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        conn.rollback()
        if created:
            assert re.fullmatch(r'qa_launcher_[a-f0-9]{32}', name)
            cursor.execute(f'DROP DATABASE `{name}`')
        cursor.close()
        conn.close()
