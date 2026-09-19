"""Real MySQL persistence tests; opt in with WISDOM_DATABASE_TESTS=1."""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from main import app
from app.config import get_db_connection
from app.store import SESSION_STORE
from app.store import CAPTCHA_STORE
from logic.solution_engine import local_solution


@pytest.fixture
def accounts():
    if os.getenv('WISDOM_DATABASE_TESTS') != '1':
        pytest.skip('Requires configured MySQL')
    users=['qa_library_'+uuid.uuid4().hex[:14] for _ in range(2)]
    sessions=[uuid.uuid4().hex for _ in users]
    conn=get_db_connection();cursor=conn.cursor()
    try:
        import bcrypt
        hashed=bcrypt.hashpw(b'Library-QA-test-password',bcrypt.gensalt()).decode()
        cursor.executemany('INSERT INTO users (username,hashed_password,email_verified) VALUES (%s,%s,1)',[(u,hashed) for u in users]);conn.commit()
        for session,user in zip(sessions,users): SESSION_STORE[session]=user
        yield users,sessions
    finally:
        for session,user in list(SESSION_STORE.items()):
            if user in users: SESSION_STORE.pop(session,None)
        for user in users:
            cursor.execute("SHOW TABLES LIKE 'course_packs'")
            if cursor.fetchone():
                cursor.execute('SELECT id FROM course_packs WHERE user_id=%s',(user,))
                for (ident,) in cursor.fetchall():
                    cursor.execute('DELETE FROM course_pack_videos WHERE pack_id=%s',(ident,))
                    cursor.execute("SHOW TABLES LIKE 'course_pack_documents'")
                    if cursor.fetchone(): cursor.execute('DELETE FROM course_pack_documents WHERE pack_id=%s',(ident,))
                cursor.execute('DELETE FROM course_packs WHERE user_id=%s',(user,))
            for table in ('animation_scripts', 'agent_templates','example_video_danmaku','example_video_notes','user_wrongbook','example_play_history','example_video_comments','example_video_likes','user_favorites','watch_later'):
                cursor.execute('SHOW TABLES LIKE %s', (table,))
                if cursor.fetchone():
                    cursor.execute(f'DELETE FROM {table} WHERE user_id=%s', (user,))
            cursor.execute('DELETE FROM formula_topics WHERE user_id=%s',(user,))
            cursor.execute('DELETE FROM formulas WHERE user_id=%s',(user,))
            cursor.execute('DELETE FROM users WHERE username=%s',(user,))
        conn.commit();cursor.close();conn.close()


def payload():
    return {'problem':'解方程 x^2-5*x+6=0','context':'','solution':local_solution('x^2-5*x+6=0').model_dump(mode='json'),'video':None}


def test_curriculum_solution_in_formula_wrongbook_and_course_pack(accounts):
    from logic.curriculum import EXAMPLES, worked_solution
    item = next(e for e in EXAMPLES if e['id']=='uni-bayes')
    snapshot = {'problem':item['problem'], 'solution':worked_solution(item).model_dump(mode='json')}
    with TestClient(app) as client:
        client.cookies.set('auth_session', accounts[1][0])
        saved = client.post('/api/formulas/solutions', json=snapshot)
        assert saved.status_code==200, saved.text
        fid=saved.json()['id']
        restored=client.get(f'/api/formulas/solutions/{fid}').json()['data']
        assert restored['solution']==snapshot['solution']
        wrong=client.post('/api/wrongbook/add',json={'title':'贝叶斯例题复习','problem':item['problem'],
            'answer':snapshot['solution']['summary'],'formula_id':fid,'source_type':'solution','snapshot':snapshot})
        assert wrong.status_code==200,wrong.text
        pack=client.post('/api/examples/course-packs',json={'name':'典型例题课包','resources':[{'kind':'solution','source_id':fid}]})
        assert pack.status_code==200,pack.text
        data=client.get('/api/examples/course-packs/'+str(pack.json()['id'])).json()['data']
        assert data['resources'][0]['snapshot']['solution']['solution']['source']=='curriculum'


def test_solution_library_requires_session():
    with TestClient(app) as client:
        assert client.post('/api/formulas/solutions',json=payload()).status_code==401
        assert client.get('/api/formulas/solutions/1').status_code==401
        assert client.delete('/api/formulas/solutions/1').status_code==401
        assert client.get('/api/formulas/list/me').status_code==401


def test_saved_solution_roundtrip_update_isolation_and_delete(accounts):
    users,sessions=accounts
    with TestClient(app) as client:
        client.cookies.set('auth_session',sessions[0])
        original=payload()
        original['solution']['task_goal']='仅求原题方程的根，其他子目标另存题解。'
        response=client.post('/api/formulas/solutions',json=original)
        assert response.status_code==200,response.text
        ident=response.json()['id']
        restored=client.get(f'/api/formulas/solutions/{ident}').json()['data']
        assert restored['solution']==original['solution']
        assert restored['problem']==original['problem']
        listed=client.get('/api/formulas/list/me').json()['data']
        assert listed[0]['id']==ident and listed[0]['step_count']==4
        assert 'payload' not in listed[0]
        video={'url':'/videos/solution_123abc.mp4','chapters':[{'title':s['title'],'start':i*5,'end':(i+1)*5} for i,s in enumerate(original['solution']['steps'])]}
        assert client.post('/api/formulas/solutions',json={**original,'id':ident,'video':video}).json()['id']==ident
        assert len(client.get('/api/formulas/list/me').json()['data'])==1
        assert client.get(f'/api/formulas/solutions/{ident}').json()['data']['video']==video
        assert client.put('/api/formulas/update',json={'id':ident,'username':users[0],'latex':'new problem','note':'bad'}).status_code==409
        client.cookies.set('auth_session',sessions[1])
        assert client.get(f'/api/formulas/solutions/{ident}').status_code==404
        assert client.post('/api/formulas/solutions',json={**original,'id':ident}).status_code==404
        assert client.delete(f'/api/formulas/solutions/{ident}').status_code==404
        assert client.get('/api/formulas/list',params={'username':users[0]}).json()['data']==[]
        assert client.delete('/api/formulas/delete',params={'username':users[0],'id':ident}).status_code==403
        client.cookies.set('auth_session',sessions[0])
        assert client.delete(f'/api/formulas/solutions/{ident}').status_code==200
        assert client.get(f'/api/formulas/solutions/{ident}').status_code==404
        conn=get_db_connection();cursor=conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM formula_solutions WHERE formula_id=%s',(ident,));assert cursor.fetchone()[0]==0
        cursor.execute('SELECT COUNT(*) FROM formula_topics WHERE formula_id=%s',(ident,));assert cursor.fetchone()[0]==0
        cursor.close();conn.close()


def test_invalid_video_cannot_be_saved(accounts):
    with TestClient(app) as client:
        client.cookies.set('auth_session',accounts[1][0])
        assert client.post('/api/formulas/solutions',json={**payload(),'video':{'url':'https://outside.invalid/x.mp4','chapters':[]}}).status_code==422
        assert client.get('/api/formulas/list/me').json()['data']==[]


@pytest.fixture
def live_library_server(accounts, tmp_path, monkeypatch):
    import socket
    import threading
    import time
    import uvicorn
    from app import math_jobs
    from app.routers import math_tasks
    # Each in-process server owns its scheduler and event loop, as a real
    # main.py process does. Never carry a driver into the next test's loop.
    scheduler=math_jobs.MathJobManager(math_jobs.JobStore(tmp_path/'tasks.sqlite3'))
    monkeypatch.setattr(math_jobs,'manager',scheduler)
    monkeypatch.setattr(math_tasks,'manager',scheduler)
    sock=socket.socket();sock.bind(('127.0.0.1',0))
    origin=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,timeout_graceful_shutdown=2))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    deadline=time.monotonic()+10
    while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.05)
    assert server.started
    try: yield origin,accounts
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()
        assert not thread.is_alive(), 'Test server must release its event loop before the next test'


def test_browser_saves_renders_and_reads_across_frontends(live_library_server):
    if os.getenv('WISDOM_BROWSER_TESTS')!='1': pytest.skip('Requires local Chrome and Vite')
    from pathlib import Path
    from urllib.parse import urlsplit
    from playwright.sync_api import sync_playwright
    origin,(users,sessions)=live_library_server
    folder=Path('tests/artifacts');folder.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write'])
        context.add_cookies([{'name':'auth_session','value':sessions[0],'url':origin}])
        page=context.new_page();errors=[];page.on('pageerror',lambda error: errors.append(str(error)))
        page.goto(origin+'/?section=calculate',wait_until='domcontentloaded')
        page.locator('.step-tutor textarea').wait_for()
        assert page.locator('#calculate .calc-layout').count()==0
        assert page.get_by_text('公式编辑器与自由动画工作台',exact=False).count()==0
        page.locator('.step-tutor').screenshot(path=str(folder/'refined-calculate-empty.png'))
        page.locator('[name=autoRender]').uncheck()
        page.locator('.step-tutor textarea').fill('解方程 x^2-5*x+6=0')
        page.locator('.step-tutor button[type=submit]').click()
        page.wait_for_function('window.StepTutor.getState().solution && !window.StepTutor.getState().busy')
        page.locator('[data-action=save]').click()
        page.wait_for_function('window.StepTutor.getState().libraryId && !window.StepTutor.getState().saving')
        ident=page.evaluate('window.StepTutor.getState().libraryId')
        page.locator('[data-action=render]').click()
        page.wait_for_function('window.StepTutor.getState().video && !window.StepTutor.getState().rendering && !window.StepTutor.getState().saving',timeout=180000)
        saved=page.request.get(origin+f'/api/formulas/solutions/{ident}').json()['data']
        assert saved['video']['url']==page.evaluate('window.StepTutor.getState().video.url')
        page.locator('.tutor-workspace').screenshot(path=str(folder/'refined-calculate-result.png'))
        page.locator('[data-action=library]').click()
        page.locator(f'[data-solution-read="{ident}"]').click()
        page.locator('.solution-reader[open]').wait_for()
        page.locator('[data-reader-step="2"]').click()
        page.locator('.solution-reader[open]').screenshot(path=str(folder/'refined-library-reader.png'))
        with page.expect_download() as event:page.locator('[data-reader=export]').click()
        assert event.value.suggested_filename.endswith('.md')
        page.locator('[data-reader=copy]').click()
        assert 'x^2' in page.evaluate('navigator.clipboard.readText()')
        page.keyboard.press('Escape')
        page.locator('#my-formulas').screenshot(path=str(folder/'refined-library.png'))
        # New browser storage, same authenticated database account: cross-page persistence is real.
        page.close();context.close()
        context=browser.new_context(viewport={'width':1440,'height':1000})
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/api/**',lambda route:route.fulfill(response=route.fetch(url=origin+urlsplit(route.request.url).path+('?' + urlsplit(route.request.url).query if urlsplit(route.request.url).query else ''))))
        page.goto('http://127.0.0.1:5173/my-formulas',wait_until='domcontentloaded')
        with page.expect_response(lambda response:'/api/captcha' in response.url) as captcha_response:
            page.locator('.desktop-auth .login-btn').click()
        captcha_id=captcha_response.value.headers['x-captcha-id']
        auth=page.locator('.auth-account-dialog[open]')
        auth.get_by_label('用户名').fill(users[0])
        auth.get_by_label('密码',exact=True).fill('Library-QA-test-password')
        auth.locator('input[autocomplete=off]').fill(CAPTCHA_STORE[captcha_id])
        auth.locator('button[type=submit]').click()
        auth.wait_for(state='hidden')
        page.locator('.solution-card-open').first.click()
        page.locator('.solution-reader[open]').wait_for()
        assert page.locator('.reader-video').get_attribute('src')==saved['video']['url']
        page.locator('[data-reader=open]').click()
        page.wait_for_url('**/calculate')
        page.wait_for_function('window.StepTutor.getState().libraryId === '+str(ident))
        page.locator('.tutor-workspace').wait_for()
        assert page.locator('#calculate .calc-layout').count()==0
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        page.locator('.tutor-workspace').screenshot(path=str(folder/'refined-calculate-dark.png'))
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.locator('.tutor-stage').screenshot(path=str(folder/'refined-calculate-mobile.png'))
        page.locator('[data-action=read]').click()
        page.locator('.solution-reader[open]').screenshot(path=str(folder/'refined-reader-mobile.png'))
        assert page.locator('.solution-reader[open]').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
        assert not errors,errors
        browser.close()
