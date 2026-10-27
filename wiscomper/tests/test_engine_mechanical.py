"""Real Three.js checks. Opt in with RUN_REAL_EXPORT=1; use an isolated server."""
from contextlib import contextmanager
import math
import os

import pytest

from server.exporter import _chromium_path
from server.mechanical import build_fan
from server.schema import Proposal, Scene
from test_export_browser import render_server


pytestmark=pytest.mark.skipif(os.getenv('RUN_REAL_EXPORT')!='1',reason='Requires a real headless browser.')


@contextmanager
def open_scene(scene):
    from playwright.sync_api import sync_playwright
    with render_server(scene) as (url,_), sync_playwright() as p:
        options={'headless':True}
        if _chromium_path():options['executable_path']=_chromium_path()
        browser=p.chromium.launch(**options)
        try:
            context=browser.new_context(viewport={'width':1280,'height':720},device_scale_factor=1)
            context.add_cookies([{'name':'test_session','value':'private-export-session','url':url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url+'/render.html?job=test-job');page.wait_for_function('window.renderReady || window.renderError')
            assert page.evaluate('window.renderError') is None
            yield page,errors
        finally:browser.close()


def test_real_fan_geometry_hierarchy_frames_and_cleanup(tmp_path):
    scene=build_fan(Proposal(title='风机如何推动空气',recipe='fan')).model_dump()
    with open_scene(scene) as (page,errors):
        properties=page.evaluate('''() => {
          const p=window.scenePlayer, blade=p.meshes.get('blade-0'), rim=p.meshes.get('front-rim');
          blade.geometry.computeBoundingBox();
          return {type:blade.geometry.type,depth:blade.geometry.boundingBox.max.z-blade.geometry.boundingBox.min.z,
            parent:blade.parent.userData.objectId,grandparent:blade.parent.parent.userData.objectId,
            pitch:blade.rotation.x,wireframe:blade.material.wireframe,rim:rim.geometry.type,nose:p.meshes.get('hub-nose').geometry.type};
        }''')
        assert properties['type']=='ExtrudeGeometry' and properties['depth']==pytest.approx(.105,abs=1e-7)
        assert properties['parent']=='blade-root-0' and properties['grandparent']=='rotor'
        assert properties['pitch']==pytest.approx(math.radians(20))
        assert not properties['wireframe'] and properties['rim']=='TorusGeometry' and properties['nose']=='ConeGeometry'
        page.evaluate('window.renderFrame(4.1)')
        first=page.screenshot(path=str(tmp_path/'fan-rotation.png'))
        before=page.evaluate('''() => {const p=window.scenePlayer;return {blade:p.meshes.get('blade-0').localToWorld(new p.T.Vector3(1.5,0,0)).toArray(),stand:p.meshes.get('stand-base').matrixWorld.elements.slice(),rim:p.meshes.get('front-rim').matrixWorld.elements.slice()}}''')
        page.evaluate('window.renderFrame(4.35)')
        after=page.evaluate('''() => {const p=window.scenePlayer;return {blade:p.meshes.get('blade-0').localToWorld(new p.T.Vector3(1.5,0,0)).toArray(),stand:p.meshes.get('stand-base').matrixWorld.elements.slice(),rim:p.meshes.get('front-rim').matrixWorld.elements.slice()}}''')
        assert before['blade']!=after['blade']
        assert before['stand']==after['stand'] and before['rim']==after['rim']
        page.evaluate('window.renderFrame(9.6)');page.screenshot(path=str(tmp_path/'fan-airflow.png'))
        page.evaluate('window.renderFrame(4.1)');assert page.screenshot()==first
        page.evaluate('window.scenePlayer.setVisible("rotor",false)')
        assert page.evaluate('window.scenePlayer.meshes.get("blade-0").userData.effectiveVisible') is False
        assert page.evaluate('window.scenePlayer.meshes.get("front-rim").userData.effectiveVisible') is True
        assert page.screenshot()!=first
        page.evaluate('window.scenePlayer.setVisible("rotor",true)');assert page.screenshot()==first
        counts=page.evaluate('''async () => {
          const p=window.scenePlayer,geometry=new Set(),material=new Set();p.world.traverse(n=>{if(n.geometry)geometry.add(n.geometry);if(n.material)material.add(n.material)});
          const stats={g:0,m:0,totalG:geometry.size,totalM:material.size};for(const g of geometry)g.addEventListener('dispose',()=>stats.g++);for(const m of material)m.addEventListener('dispose',()=>stats.m++);
          await p.load({title:'2d',duration:6,background:'#0c1420',mode:'2d',objects:[{id:'c',kind:'circle',radius:1,color:'#ffffff',stroke:'#ffffff',filled:true,line_width:.035,font_size:.3,frames:[],points:[]}]});
          return stats;
        }''')
        assert counts['g']==counts['totalG'] and counts['m']==counts['totalM']
        assert not errors


def test_group_world_anchor_label_visibility_and_picking(tmp_path):
    scene=Scene.model_validate({'title':'Hierarchy','mode':'3d','duration':6,'camera':{'azimuth':0,'elevation':0,'distance':12,'orbit':0},'objects':[
        {'id':'child','parent_id':'assembly','kind':'box','x':1,'width':.8,'height':.8,'depth':.8,'opacity':.8},
        {'id':'label','parent_id':'assembly','kind':'text','x':1,'y':1,'text':'跟随父对象'},
        {'id':'assembly','kind':'group','x':1,'y':-.5,'opacity':.5,'frames':[{'t':0,'rotation':0},{'t':6,'rotation':math.pi}]},
    ]}).model_dump()
    with open_scene(scene) as (page,errors):
        page.evaluate('window.renderFrame(3)')
        state=page.evaluate('''() => {
          const p=window.scenePlayer,c=p.meshes.get('child'),l=p.meshes.get('label');
          const a=l.getWorldPosition(new p.T.Vector3()).project(p.camera), dom=p.nodes.get('label');
          const target=c.getWorldPosition(new p.T.Vector3()).project(p.camera);
          return {position:c.getWorldPosition(new p.T.Vector3()).toArray(),opacity:c.material.opacity,label:[parseFloat(dom.style.left),parseFloat(dom.style.top)],expected:[(a.x+1)*640,(1-a.y)*360],click:[(target.x+1)*640,(1-target.y)*360]};
        }''')
        assert state['position']==pytest.approx([1,.5,0],abs=1e-10)
        assert state['opacity']==pytest.approx(.4)
        assert state['label']==pytest.approx(state['expected'],abs=.001)
        page.mouse.click(*state['click']);assert page.evaluate('window.scenePlayer.selected')=='child'
        page.evaluate('window.scenePlayer.setVisible("assembly",false)')
        assert page.locator('[data-object-id="label"]').evaluate('(n)=>n.style.visibility')=='hidden'
        page.mouse.click(*state['click']);assert page.evaluate('window.scenePlayer.selected') is None
        assert not errors


def test_transparent_context_shell_does_not_capture_solid_part_clicks():
    scene=Scene.model_validate({'title':'Transparent shell','mode':'3d','duration':6,'camera':{'azimuth':0,'elevation':0,'distance':12,'orbit':0},'objects':[
        {'id':'blade','kind':'prism','points':[[-.8,-.4],[.8,-.4],[.8,.4],[-.8,.4]],'depth':.12},
        {'id':'shell','kind':'cylinder','radius':2,'height':1,'rotation_x':math.pi/2,'opacity':.055},
    ]}).model_dump()
    with open_scene(scene) as (page,errors):
        page.mouse.click(640,360)
        assert page.evaluate('window.scenePlayer.selected')=='blade'
        page.evaluate('window.scenePlayer.setVisible("blade",false)')
        page.mouse.click(640,360)
        assert page.evaluate('window.scenePlayer.selected')=='shell'
        assert not errors
