import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from main import app
from app.config import STORAGE_DIR
from test_solution_library import accounts, live_library_server

BASE='/api/examples/course-packs'
VIDEO=next(Path(STORAGE_DIR).glob('*.mp4')).stem
VIDEOS=[p.stem for p in Path(STORAGE_DIR).glob('*.mp4')][:2]


def test_course_pack_roundtrip_revision_order_and_isolation(accounts):
    users,sessions=accounts
    body={'name':'二次函数课包','description':'课堂探究','lesson':{'objectives':r'理解 $y=x^2$','procedure':'观察—推导—验证','duration':45},'video_ids':VIDEOS}
    with TestClient(app) as c:
        assert c.get(BASE).status_code==401
        c.cookies.set('auth_session',sessions[0])
        saved=c.post(BASE,json=body);assert saved.status_code==200,saved.text
        ident=saved.json()['id']
        pack=c.get(f'{BASE}/{ident}').json()['data']
        assert pack['lesson']['objectives']==body['lesson']['objectives']
        assert pack['video_ids']==VIDEOS
        assert c.get(BASE).json()['data'][0]['video_count']==len(VIDEOS)
        pack['video_ids']=list(reversed(VIDEOS));pack['name']='新版教案'
        assert c.put(f'{BASE}/{ident}',json=pack).json()['revision']==2
        assert c.put(f'{BASE}/{ident}',json=pack).status_code==409
        assert c.get(f'{BASE}/{ident}').json()['data']['video_ids']==list(reversed(VIDEOS))
        assert c.post(BASE,json={**body,'video_ids':['../outside']}).status_code==422
        c.cookies.set('auth_session',sessions[1])
        assert c.get(BASE).json()['data']==[]
        assert c.get(f'{BASE}/{ident}').status_code==404
        assert c.put(f'{BASE}/{ident}',json=pack).status_code==404
        assert c.delete(f'{BASE}/{ident}').status_code==404
        c.cookies.set('auth_session',sessions[0])
        assert c.delete(f'{BASE}/{ident}').status_code==200
        assert c.get(f'{BASE}/{ident}').status_code==404


def test_danmaku_broadcast_persistence_and_resume(accounts):
    with TestClient(app) as c:
        payload={'video_id':VIDEO,'text':'观察这个变换','time':2.5,'color':0x7c3aed,'mode':5}
        assert c.post('/api/v1/danmaku/send',json=payload).status_code==401
        c.cookies.set('auth_session',accounts[1][0])
        with c.websocket_connect('/api/examples/ws/'+VIDEO) as ws:
            assert ws.receive_json()['type']=='viewer_count'
            r=c.post('/api/v1/danmaku/send',json=payload);assert r.status_code==200,r.text
            event=ws.receive_json();assert event['data']['id']==r.json()['data']['id']
            assert event['data']['color']==payload['color'] and event['data']['mode']==5
        rows=c.get('/api/v1/danmaku/list',params={'video_id':VIDEO}).json()['data']
        assert any(row[0:3]==[2.5,5,0x7c3aed] and row[4]=='观察这个变换' for row in rows)
        assert c.post('/api/v1/danmaku/send',json={**payload,'time':-1}).status_code==422
        assert c.post('/api/v1/danmaku/send',json={**payload,'video_id':'nonexistent-video'}).status_code==404
        assert c.post('/api/v1/player/heartbeat',json={'video_id':VIDEO,'progress':12.5}).json()['code']==0
        assert c.get('/api/v1/player/config/'+VIDEO).json()['data']['last_play_time']==12.5
        note=c.post('/api/examples/notes',json={'video_id':VIDEO,'content':r'$x^2$ 的变化','time_sec':5}).json()['data']
        c.cookies.set('auth_session',accounts[1][1])
        assert c.get('/api/examples/notes',params={'video_id':VIDEO}).json()['data']==[]
        assert c.get('/api/v1/player/config/'+VIDEO).json()['data']['last_play_time']==0
        ident=r.json()['data']['id']
        assert c.delete('/api/v1/danmaku/'+str(ident)).status_code==404
        c.cookies.set('auth_session',accounts[1][0])
        with c.websocket_connect('/api/examples/ws/'+VIDEO) as ws:
            ws.receive_json()
            assert c.delete('/api/v1/danmaku/'+str(ident)).status_code==200
            assert ws.receive_json()=={'type':'delete_danmaku','id':ident}
        assert all(row[5]!=ident for row in c.get('/api/v1/danmaku/list',params={'video_id':VIDEO}).json()['data'])
        assert c.delete('/api/examples/notes/'+str(note['id'])).json()['status']=='success'


@pytest.mark.parametrize('prompt,expected',[('打开教案',{'examples_action':'lesson'}),('创建课包',{'examples_action':'create_pack'}),('打开我的课件',{'examples_filter':'courseware'}),('打开播放器弹幕',{'examples_action':'danmaku'})])
def test_agent_teaching_routes_without_model(prompt,expected,accounts):
    with TestClient(app) as c:
        c.cookies.set('auth_session',accounts[1][0])
        response=c.post('/api/agent/execute',json={'prompt':prompt})
        assert response.status_code==200,response.text
        step=response.json()['steps'][0]
        assert step['section']=='examples'
        for key,value in expected.items():assert step[key]==value


@pytest.fixture(params=['static','vue'])
def teaching_page(live_library_server,request):
    if os.getenv('WISDOM_BROWSER_TESTS')!='1':pytest.skip('Requires local Chrome and Vite')
    from playwright.sync_api import sync_playwright
    from urllib.parse import urlsplit
    origin,(users,sessions)=live_library_server
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_cookies([{'name':'auth_session','value':sessions[0],'url':origin}])
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_locator_handler(page.locator('#achievement-unlock-modal.show'),lambda overlay:overlay.locator('#achievement-unlock-close-x').click())
        if request.param=='vue':page.route('**/api/**',lambda route:route.fulfill(response=route.fetch(url=origin+urlsplit(route.request.url).path+('?' + urlsplit(route.request.url).query if urlsplit(route.request.url).query else ''))))
        page.goto(origin+'/?section=examples' if request.param=='static' else 'http://127.0.0.1:5173/examples',wait_until='domcontentloaded')
        page.wait_for_selector('.video-card')
        yield page,origin,request.param
        assert not errors,errors
        browser.close()


def test_teaching_pack_editor_and_player_workflow(teaching_page):
    page,origin,kind=teaching_page
    page.locator('#examples-create-course-btn').click()
    editor=page.locator('.course-editor')
    editor.locator('[name=name]').fill('二次函数探究课')
    editor.locator('[name=objectives]').fill(r'掌握 $y=x^2$ 的图像性质')
    editor.locator('[data-outline]').click()
    editor.locator('[data-add]').nth(0).click()
    editor.locator('[data-add]:not([disabled])').nth(0).click()
    editor.locator('[data-move="1"][data-offset="-1"]').click()
    selected=editor.locator('[data-selected-videos]').inner_text()
    with page.expect_response(lambda r:r.url.endswith('/course-packs') and r.request.method=='POST') as response:
        editor.locator('[type=submit]').click()
    ident=response.value.json()['id']
    page.wait_for_selector('.lesson-reader .katex')
    assert page.locator('.course-playlist [data-play]').count()==2
    with page.expect_download() as downloaded:page.locator('[data-json]').click()
    exported=Path(downloaded.value.path()).read_text(encoding='utf-8')
    assert json.loads(exported)['name']=='二次函数探究课'
    with page.expect_download() as downloaded:page.locator('[data-md]').click()
    assert '$y=x^2$' in Path(downloaded.value.path()).read_text(encoding='utf-8')
    page.screenshot(path=f'tests/artifacts/teaching-lesson-{kind}.png',full_page=True)
    box=page.locator('.course-dialog').bounding_box()
    assert abs(box['x']+(box['width']/2)-720)<2
    page.locator('.course-dialog [data-close]').click()
    page.locator('[data-filter=courseware]').click();page.wait_for_selector('.course-card')
    page.locator('.course-card button').click();page.wait_for_selector('.course-playlist')
    videoid=page.locator('.course-playlist [data-play]').first.get_attribute('data-play')
    page.locator('.course-playlist [data-play]').first.click()
    page.wait_for_function("document.querySelector('#example-video-player').readyState>=2",timeout=45000)
    assert page.locator('.course-player-nav [data-previous]').is_disabled()
    page.locator('.course-player-nav [data-next]').click()
    page.wait_for_function("document.querySelector('.course-player-nav span').textContent.includes('2 / 2')")
    assert page.locator('.course-player-nav [data-next]').is_disabled()
    page.locator('.course-player-nav [data-previous]').click()
    page.wait_for_function("document.querySelector('.course-player-nav span').textContent.includes('1 / 2')")
    page.wait_for_function("document.querySelector('#example-video-player').readyState>=2",timeout=45000)
    page.evaluate("document.querySelector('#example-video-player').pause();document.querySelector('#example-video-player').currentTime=2")
    page.evaluate("""() => {const ctx=document.querySelector('#video-danmaku-canvas').getContext('2d');window.bulletDraws=[];const fill=ctx.fillText.bind(ctx),clear=ctx.clearRect.bind(ctx);ctx.clearRect=(...args)=>{window.bulletDraws=[];clear(...args)};ctx.fillText=(text,x,y)=>{window.bulletDraws.push({text,x,y});fill(text,x,y)};}""")
    page.wait_for_selector('#video-danmaku-input-wrap:visible')
    page.locator('#video-danmaku-mode').select_option('5')
    page.locator('#video-danmaku-color').fill('#7c3aed')
    page.locator('#video-danmaku-input').fill('课堂弹幕测试')
    with page.expect_response('**/api/v1/danmaku/send') as sent:page.locator('#video-danmaku-send').click()
    assert sent.value.json()['data']['mode']==5
    page.locator('[data-player-tab=danmaku]').click()
    page.wait_for_selector('[data-delete-bullet]')
    assert '课堂弹幕测试' in page.locator('.danmaku-archive-list').inner_text()
    page.wait_for_function("window.bulletDraws.some(d=>d.text==='课堂弹幕测试')")
    paused=page.evaluate("window.bulletDraws.find(d=>d.text==='课堂弹幕测试')")
    page.wait_for_timeout(150)
    assert page.evaluate("window.bulletDraws.find(d=>d.text==='课堂弹幕测试')")==paused
    page.evaluate("document.querySelector('#example-video-player').currentTime=0")
    page.wait_for_function("!window.bulletDraws.some(d=>d.text==='课堂弹幕测试')")
    page.locator('[data-bullet-time]').filter(has_text='0:02').first.click()
    page.wait_for_function("window.bulletDraws.some(d=>d.text==='课堂弹幕测试')")
    page.locator('[data-player-tab=notes]').click()
    page.locator('#video-note-input').fill(r'观察 $x^2$ 的顶点与对称轴')
    page.locator('#video-note-send').click()
    page.wait_for_selector('.video-note-item')
    page.wait_for_selector('.video-note-content .katex')
    page.locator('[data-player-tab=lesson]').click()
    page.locator('#video-add-course-pack-btn').click()
    page.wait_for_selector('[data-choose]');page.locator('[data-choose]').first.click()
    page.wait_for_function("document.querySelector('.course-status').textContent.includes('已加入')")
    page.locator('.course-dialog [data-close]').click()
    page.locator('[data-player-tab=comments]').click()
    page.locator('#video-comment-input').fill('课堂讨论测试')
    page.locator('#video-comment-send').click()
    page.wait_for_selector('.video-comment-content')
    page.locator('[data-player-tab=notes]').click()
    page.screenshot(path=f'tests/artifacts/teaching-player-{kind}.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(200)
    page.screenshot(path=f'tests/artifacts/teaching-player-mobile-{kind}.png',full_page=True)
    assert page.locator('#video-modal').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
    assert page.locator('.video-modal-panel').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
    page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
    page.screenshot(path=f'tests/artifacts/teaching-player-dark-{kind}.png')
    page.evaluate("document.documentElement.setAttribute('data-theme','light')")
    page.evaluate("document.querySelector('#example-video-player').pause();document.querySelector('#example-video-player').currentTime=3")
    page.wait_for_function("Math.abs(document.querySelector('#example-video-player').currentTime-3)<.1")
    with page.expect_response(lambda r:'/api/v1/player/heartbeat' in r.url and r.request.method=='POST'):
        page.keyboard.press('Escape')
    page.wait_for_selector('#video-modal',state='hidden')
    assert page.locator('#example-video-player').evaluate('e=>e.paused')
    page.evaluate('(id)=>window.Examples.playExampleByVideoId(id)',videoid)
    page.wait_for_function("document.querySelector('#example-video-player').readyState>=2&&document.querySelector('#example-video-player').currentTime>=2.9",timeout=45000)
    page.wait_for_selector('.video-note-item')
    page.locator('[data-player-tab=danmaku]').click()
    page.wait_for_selector('[data-delete-bullet]')
    page.locator('[data-delete-bullet]').click()
    page.wait_for_selector('[data-delete-bullet]',state='detached')
    page.locator('[data-player-tab=notes]').click()
    page.locator('.video-note-delete').click()
    page.wait_for_selector('.video-note-item',state='detached')
    page.keyboard.press('Escape');page.wait_for_selector('#video-modal',state='hidden')
    page.evaluate("window.showSection('home')")
    page.wait_for_selector('.graph-explorer input')
    page.locator('.graph-explorer input').fill('教案')
    page.locator('[data-graph-node=examples-lesson]').click()
    page.wait_for_selector('.graph-node-detail:not([hidden])')
    assert page.locator('[data-related=examples-create-course]').count()==1
    page.locator('[data-node-open=examples-lesson]').click()
    page.wait_for_selector('.course-editor')
    assert page.locator('.course-editor [name=name]').input_value()==''
    page.locator('.course-dialog [data-close]').click()
    page.locator('[data-filter=courseware]').click();page.wait_for_selector('.course-card')
    page.reload();page.wait_for_selector('.video-card')
    page.locator('[data-filter=courseware]').click();page.wait_for_selector('.course-card')
    assert '二次函数探究课' in page.locator('.course-card').inner_text()
    page.evaluate("async data=>{const m=await import('/static/js/course-packs.js');await m.importCoursePack(new File([data],'course.json',{type:'application/json'}));}",exported)
    page.wait_for_selector('.lesson-reader .katex')
    assert page.locator('.course-playlist [data-play]').count()==2
    page.locator('[data-edit]').click();page.wait_for_selector('.course-editor')
    page.locator('.course-editor [name=name]').fill('调整后的课堂教案')
    page.locator('[data-move="1"][data-offset="-1"]').click()
    page.locator('.course-editor [type=submit]').click()
    page.wait_for_selector('.lesson-reader')
    assert page.locator('.lesson-reader h2').inner_text()=='调整后的课堂教案'


def test_agent_opens_real_teaching_editor(teaching_page):
    page,origin,kind=teaching_page
    page.evaluate("window.showSection('agent')")
    page.wait_for_selector('#agent-prompt')
    page.locator('#agent-prompt').fill('打开教案')
    page.locator('#agent-submit-btn').click()
    page.wait_for_selector('.course-editor')
    page.wait_for_function('!window.AgentWorkspace.getState().busy')
    assert page.evaluate('window.AgentWorkspace.getState().error')==''


def test_player_websocket_transport(teaching_page):
    page,origin,kind=teaching_page
    event=page.evaluate("""id=>new Promise((resolve,reject)=>{const ws=new WebSocket(location.origin.replace('http','ws')+'/api/examples/ws/'+encodeURIComponent(id));const timeout=setTimeout(()=>{ws.close();reject(new Error('websocket timed out'))},8000);ws.onmessage=e=>{clearTimeout(timeout);ws.close();resolve(JSON.parse(e.data))};ws.onerror=()=>{clearTimeout(timeout);reject(new Error('websocket failed'))};})""",VIDEO)
    assert event['type']=='viewer_count'
