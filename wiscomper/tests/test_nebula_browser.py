"""Real WebGL graph acceptance against the isolated application and knowledge API."""
from pathlib import Path

from playwright.sync_api import expect
from test_browser import browser, local_server, workbench  # noqa: F401

ARTIFACTS=Path(__file__).resolve().parents[1]/'tmp'/'nebula-qa'


def open_graph(page):
    page.locator('#open-knowledge').click()
    expect(page.locator('#kw-graph')).to_have_attribute('data-renderer','webgl',timeout=20000)
    expect(page.locator('#kw-graph canvas')).to_be_visible()
    page.wait_for_function("Number(document.querySelector('#kw-graph').dataset.frameCount)>0")


def test_real_webgl_search_math_and_true_station_links(workbench):
    page,_=workbench
    open_graph(page)
    graph=page.request.get(page.url.split('?')[0]+'api/knowledge').json()
    host=page.locator('#kw-graph')
    assert int(host.get_attribute('data-node-count'))==len(graph['nodes'])
    assert int(host.get_attribute('data-link-count'))==len(graph['links'])
    assert host.locator('canvas').evaluate("canvas=>!!canvas.getContext('webgl2')")
    assert host.locator('canvas').evaluate("canvas=>canvas.width/canvas.clientWidth")<=1.51
    page.locator('#kw-graph-search').fill('斯涅尔')
    page.locator('#kw-graph-results').get_by_role('button',name='斯涅尔折射定律',exact=True).click()
    expect(page.locator('#kw-node-detail h3')).to_have_text('斯涅尔折射定律')
    expect(host.locator('.nebula-selected .katex')).to_be_visible()
    route=page.locator('#kw-stations [data-station-id]').evaluate_all('nodes=>nodes.map(n=>n.dataset.stationId)')
    assert len(route)>1
    edges={frozenset((link['source'],link['target'])) for link in graph['links']}
    assert all(frozenset((a,b)) in edges for a,b in zip(route,route[1:]))
    page.locator('#kw-stations [data-station-id]').first.click()
    page.locator('#kw-stations').get_by_role('button',name='下一站 →').click()
    expected=next(n['label'] for n in graph['nodes'] if n['id']==route[1])
    expect(page.locator('#kw-node-detail h3')).to_have_text(expected)
    page.locator('#kw-graph-search').fill('斯涅尔')
    page.locator('#kw-graph-results').get_by_role('button',name='斯涅尔折射定律',exact=True).click()
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(ARTIFACTS/'graph-3d-desktop.png'))
    page.locator('#kw-node-detail').get_by_role('button',name='查看公式',exact=True).click()
    expect(page.locator('#kw-library-list .kw-formula-card')).to_have_count(1)
    expect(page.locator('#kw-graph canvas')).to_have_count(0)
    expect(page.locator('#kw-library-list .katex')).to_be_visible()


def test_orbit_zoom_2d_close_and_reopen_release_context(workbench):
    page,_=workbench
    open_graph(page)
    host=page.locator('#kw-graph'); canvas=host.locator('canvas')
    page.locator('#kw-graph-motion').click()
    expect(host).to_have_attribute('data-graph-state','still')
    page.wait_for_timeout(700)
    node=host.locator('.nebula-label[aria-pressed="false"]:visible').first
    label=node.get_attribute('title');node.click()
    expect(page.locator('#kw-node-detail h3')).to_have_text(label)
    box=canvas.bounding_box()
    before=host.get_attribute('data-camera')
    page.mouse.move(box['x']+20,box['y']+box['height']-50)
    page.mouse.down();page.mouse.move(box['x']+115,box['y']+box['height']-85,steps=8);page.mouse.up()
    page.wait_for_function("previous=>document.querySelector('#kw-graph').dataset.camera!==previous",arg=before)
    distance=float(host.get_attribute('data-camera').split(',')[2])
    page.locator('#kw-graph-zoom-in').click()
    page.wait_for_function("previous=>Number(document.querySelector('#kw-graph').dataset.camera.split(',')[2])<previous",arg=distance)
    page.evaluate("window.oldGraphCanvas=document.querySelector('#kw-graph canvas')")
    page.locator('#kw-graph-2d').click()
    expect(host).to_have_attribute('data-renderer','2d')
    expect(host.locator('.kw-graph-node')).not_to_have_count(0)
    assert page.evaluate("window.oldGraphCanvas.getContext('webgl2').isContextLost()")
    page.locator('#kw-graph-3d').click()
    expect(host).to_have_attribute('data-renderer','webgl')
    expect(canvas).to_have_count(1)
    page.locator('#kw-close').click()
    expect(canvas).to_have_count(0)
    open_graph(page)
    expect(canvas).to_have_count(1)


def test_mobile_reduced_motion_and_context_loss_fallback(workbench):
    page,_=workbench
    page.set_viewport_size({'width':390,'height':844})
    page.emulate_media(reduced_motion='reduce')
    open_graph(page)
    host=page.locator('#kw-graph')
    expect(page.locator('#kw-graph-motion')).to_be_disabled()
    expect(host).to_have_attribute('data-graph-state','still')
    before=host.get_attribute('data-frame-count')
    page.wait_for_timeout(150)
    assert host.get_attribute('data-frame-count')==before
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('#knowledge-workspace').evaluate('node=>node.scrollWidth<=node.clientWidth+1')
    box=host.bounding_box();cx=box['x']+box['width']/2;cy=box['y']+box['height']/2
    distance=float(host.get_attribute('data-camera').split(',')[2])
    cdp=page.context.new_cdp_session(page)
    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':cx-30,'y':cy},{'x':cx+30,'y':cy}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':cx-65,'y':cy},{'x':cx+65,'y':cy}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    page.wait_for_function("previous=>Number(document.querySelector('#kw-graph').dataset.camera.split(',')[2])<previous",arg=distance)
    cdp.detach()
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(ARTIFACTS/'graph-3d-mobile.png'))
    page.evaluate("document.querySelector('#kw-graph canvas').getContext('webgl2').getExtension('WEBGL_lose_context').loseContext()")
    expect(host).to_have_attribute('data-renderer','2d')
    expect(page.locator('#kw-graph-status')).to_contain_text('二维')
    expect(host.locator('.kw-graph-node')).not_to_have_count(0)


def test_webgl_unavailable_preserves_2d_navigation(workbench):
    page,_=workbench
    page.add_init_script("""const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){if(type==='webgl2')return null;return original.call(this,type,...args)}""")
    page.reload();expect(page.locator('#canvas-empty')).to_be_hidden(timeout=20000)
    page.locator('#open-knowledge').click()
    expect(page.locator('#kw-graph')).to_have_attribute('data-renderer','2d',timeout=15000)
    expect(page.locator('#kw-graph-status')).to_contain_text('WebGL')
    page.locator('#kw-graph-search').fill('斯涅尔')
    page.locator('#kw-graph-results').get_by_role('button',name='斯涅尔折射定律',exact=True).click()
    expect(page.locator('#kw-node-detail h3')).to_have_text('斯涅尔折射定律')
    expect(page.locator('#kw-graph .katex')).not_to_have_count(0)
