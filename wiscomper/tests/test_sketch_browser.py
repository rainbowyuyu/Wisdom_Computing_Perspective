"""Canvas input stays local until the injected upload callback accepts a PNG."""
from pathlib import Path

import pytest
from playwright.sync_api import expect
from test_browser import browser  # noqa: F401

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def sketch_page(browser):
    context=browser.new_context(viewport={'width':1100,'height':900})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/*',lambda route:route.abort())
    page.route('**/web/sketch-input.js',lambda route:route.fulfill(path=str(ROOT/'web/sketch-input.js'),content_type='text/javascript'))
    page.route('**/web/sketch-input.css',lambda route:route.fulfill(path=str(ROOT/'web/sketch-input.css'),content_type='text/css'))
    page.route('**/sketch-test',lambda route:route.fulfill(content_type='text/html',body='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/web/sketch-input.css"></head><body><button id="open">手写草图</button></body></html>'''))
    page.goto('http://sketch.test/sketch-test')
    page.evaluate('''async()=>{
      const {mountSketchInput}=await import('/web/sketch-input.js');window.images=[];window.notifications=[];window.result=true;
      window.sketch=mountSketchInput({notify:text=>window.notifications.push(text),onImage:async file=>{
        const bitmap=await createImageBitmap(file);window.images.push({name:file.name,type:file.type,size:file.size,width:bitmap.width,height:bitmap.height});bitmap.close();
        if(window.result==='hold')return await new Promise(resolve=>window.resolveImage=resolve);
        if(window.result==='throw')throw new Error('模拟上传失败');return window.result;
      }});
      document.querySelector('#open').onclick=()=>window.sketch.open();
    }''')
    yield page
    context.close();assert not errors


def draw_line(page,start=(.2,.5),end=(.7,.5)):
    bounds=page.locator('.sketch-canvas').bounding_box()
    page.mouse.move(bounds['x']+bounds['width']*start[0],bounds['y']+bounds['height']*start[1]);page.mouse.down()
    page.mouse.move(bounds['x']+bounds['width']*end[0],bounds['y']+bounds['height']*end[1],steps=16);page.mouse.up()


def pixel(page,x=.45,y=.5):
    return page.locator('.sketch-canvas').evaluate('(canvas,p)=>Array.from(canvas.getContext("2d").getImageData(Math.floor(canvas.width*p.x),Math.floor(canvas.height*p.y),1,1).data)',{'x':x,'y':y})


def test_pen_eraser_undo_redo_clear_and_export(sketch_page):
    page=sketch_page;page.locator('#open').click()
    expect(page.locator('.sketch-submit')).to_be_disabled();draw_line(page)
    assert pixel(page)[0]<100
    page.locator('[data-tool="erase"]').click();draw_line(page,start=(.45,.42),end=(.45,.58))
    assert pixel(page)==[255,255,255,255]
    page.locator('.sketch-undo').click();assert pixel(page)[0]<100
    page.keyboard.press('Control+Shift+z');assert pixel(page)==[255,255,255,255]
    page.locator('.sketch-undo').click();page.locator('.sketch-clear').click()
    assert pixel(page)==[255,255,255,255]
    page.locator('.sketch-submit').click();expect(page.locator('.sketch-status')).to_contain_text('画板还是空白')
    assert page.evaluate('window.images')==[]
    page.locator('.sketch-undo').click();assert pixel(page)[0]<100
    page.locator('.sketch-submit').click();expect(page.locator('.sketch-dialog')).not_to_be_visible()
    expect(page.locator('#open')).to_be_focused()
    files=page.evaluate('window.images');assert len(files)==1
    assert files[0]['type']=='image/png' and files[0]['width']==1200 and files[0]['height']==800 and files[0]['size']>100
    assert files[0]['name'].endswith('.png')
    page.locator('#open').click();assert pixel(page)[0]<100


def test_upload_failure_retains_drawing_and_busy_prevents_duplicate(sketch_page):
    page=sketch_page;page.locator('#open').click();draw_line(page)
    page.evaluate("window.result='hold'");page.locator('.sketch-submit').click()
    expect(page.locator('.sketch-submit')).to_be_disabled();expect(page.locator('.sketch-close')).to_be_disabled()
    page.keyboard.press('Escape');expect(page.locator('.sketch-dialog')).to_be_visible()
    page.wait_for_function('typeof window.resolveImage==="function"');page.evaluate('window.resolveImage(false)')
    expect(page.locator('.sketch-status')).to_contain_text('图片尚未添加')
    expect(page.locator('.sketch-submit')).to_be_enabled();assert pixel(page)[0]<100
    page.evaluate("window.result='throw'");page.locator('.sketch-submit').click()
    expect(page.locator('.sketch-status')).to_have_text('模拟上传失败')
    page.keyboard.press('Escape');expect(page.locator('.sketch-dialog')).not_to_be_visible()
    page.locator('#open').click();assert pixel(page)[0]<100
    page.evaluate('window.result=true');page.locator('.sketch-submit').click()
    expect(page.locator('.sketch-dialog')).not_to_be_visible();assert len(page.evaluate('window.images'))==3


def test_mobile_canvas_and_dispose(sketch_page):
    page=sketch_page;page.set_viewport_size({'width':360,'height':740});page.emulate_media(reduced_motion='reduce')
    page.locator('#open').click();draw_line(page)
    bounds=page.locator('.sketch-dialog').bounding_box()
    assert bounds['x']>=13 and bounds['x']+bounds['width']<=347 and bounds['y']+bounds['height']<=727
    output=ROOT/'tmp/browser-qa';output.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(output/'sketch-mobile.png'))
    assert page.locator('.sketch-canvas').evaluate('canvas=>getComputedStyle(canvas).touchAction')=='none'
    page.evaluate('window.sketch.dispose();window.sketch.dispose()')
    expect(page.locator('.sketch-dialog')).to_have_count(0);assert page.evaluate('window.sketch.open()') is False
