"""Both shipped UIs preserve complete statements and block unsafe OCR handoffs."""
import io
import os
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from PIL import Image
from playwright.sync_api import sync_playwright, expect

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires local UI servers')


@pytest.fixture(params=['http://127.0.0.1:8000/?section=detect','http://127.0.0.1:5173/detect'])
def ui(request):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1280,'height':1000})
        calls=[];result={'status':'success','latex':'x^2=1','problem_text':'已知 x>0，解方程 x^2=1，并说明理由。','vision_prompt':'A 点的横坐标为 1','needs_review':False}
        def api(route):
            path=urlsplit(route.request.url).path
            if path=='/api/detect':calls.append(path);return route.fulfill(json=result)
            if path=='/api/user/me':return route.fulfill(status=401,json={'status':'error'})
            if path=='/api/solve/capabilities':return route.fulfill(json={'manim':True})
            return route.fulfill(json={'status':'success','data':[],'items':[]})
        page.route('**/api/**',api)
        page.goto(request.param,wait_until='domcontentloaded')
        page.wait_for_selector('#detect-problem')
        page.wait_for_function('!!window.MathfieldElement')
        page.locator('#detect .tab-btn').filter(has_text='上传').click()
        image=io.BytesIO();Image.new('RGB',(240,140),'white').save(image,'PNG')
        page.locator('#image-upload').set_input_files({'name':'one.png','mimeType':'image/png','buffer':image.getvalue()})
        yield page,result,calls
        browser.close()


def recognize(page):
    page.locator('.btn-detect-primary').click()
    expect(page.locator('.btn-detect-primary')).to_be_enabled()


def test_complete_statement_and_edits_reach_calculation(ui):
    page,result,calls=ui
    recognize(page)
    expect(page.locator('#detect-problem')).to_have_value(result['problem_text'])
    page.locator('#latex-code-detect').evaluate("e=>{e.value='x^2=4';e.dispatchEvent(new Event('input',{bubbles:true}));}")
    expect(page.locator('#detect-problem')).to_have_value('已知 x>0，解方程 x^2=4，并说明理由。')
    page.locator('#btn-copy-calc').click()
    expect(page.locator('#tutor-problem')).to_have_value('已知 x>0，解方程 x^2=4，并说明理由。')
    assert calls==['/api/detect']


def test_failed_recognition_keeps_image_and_errors_outside_formula(ui):
    page,result,calls=ui
    result.clear();result.update(status='error',message='请裁剪到一道题后再试。')
    recognize(page)
    expect(page.locator('#detect-feedback')).to_contain_text('裁剪')
    expect(page.locator('#btn-copy-calc')).to_be_disabled()
    assert '裁剪' not in page.locator('#latex-output').evaluate('e=>e.value')
    assert page.locator('#image-upload').evaluate('e=>e.files.length')==1
    page.locator('#detect-problem').fill('已知 x>0，解方程 x^2=4。')
    page.locator('#detect-confirm').check()
    page.locator('#btn-copy-calc').click()
    expect(page.locator('#tutor-problem')).to_have_value('已知 x>0，解方程 x^2=4。')


def test_uncertain_recognition_requires_review_and_replaced_image_clears_result(ui):
    page,result,calls=ui
    result.update(needs_review=True,message='请核对指数。')
    recognize(page)
    expect(page.locator('#btn-copy-calc')).to_be_disabled()
    page.locator('#detect-confirm').check()
    expect(page.locator('#btn-copy-calc')).to_be_enabled()
    page.locator('#image-upload').set_input_files([])
    expect(page.locator('#btn-copy-calc')).to_be_disabled()
    expect(page.locator('#detect-problem')).to_have_value('')


def test_mobile_manual_entry_has_no_horizontal_overflow(ui):
    page,result,calls=ui
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#detect-problem').fill('求导 x^2')
    expect(page.locator('#btn-copy-calc')).to_be_enabled()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    Path('tmp/recognition-review').mkdir(parents=True,exist_ok=True)
    page.screenshot(path='tmp/recognition-review/'+('vue' if '5173' in page.url else 'static')+'.png',full_page=True)


def test_multiple_problems_blocked_but_subquestions_allowed(ui):
    page,_,_=ui
    page.locator('#detect-problem').fill('第一题 求导 x^2；第二题 求导 x^3')
    expect(page.locator('#btn-copy-calc')).to_be_disabled()
    page.locator('#detect-problem').fill('已知 f(x)=x^3，(1) 求导；(2) 求极值')
    expect(page.locator('#btn-copy-calc')).to_be_enabled()


def test_late_response_and_duplicate_click_cannot_replace_manual_edit(ui):
    page,_,_=ui
    result=page.evaluate('''async()=>{
        const {createRecognitionFlow}=await import('/static/js/recognition-flow.js');
        const original=window.fetch;let respond,calls=0;
        window.fetch=()=>{calls++;return new Promise(resolve=>respond=resolve);};
        try{
            const flow=createRecognitionFlow(()=>{});
            const first=flow.run(async()=>new Blob(['picture']));
            await Promise.resolve();
            await flow.run(async()=>new Blob(['duplicate']));
            flow.editProblem('人工补充：解 x+1=2');
            respond({ok:true,json:async()=>({status:'success',problem_text:'旧识别结果',latex:'x=999'})});
            await first;
            return {calls,problem:flow.payload().problem,busy:flow.state.busy};
        }finally{window.fetch=original;}
    }''')
    assert result=={'calls':1,'problem':'人工补充：解 x+1=2','busy':False}


def test_handwriting_exports_visible_ink(ui):
    page,result,_=ui
    images=[]
    def upload(route):
        body=route.request.post_data_buffer
        start=body.find(b'\x89PNG')
        if start<0:start=body.find(b'\xff\xd8')
        assert start>=0
        image=Image.open(io.BytesIO(body[start:])).convert('RGB')
        images.append(image)
        route.fulfill(json=result)
    page.route('**/api/detect',upload)
    page.locator('#detect .tab-btn').filter(has_text='手写').click()
    canvas=page.locator('#drawing-board');canvas.scroll_into_view_if_needed()
    box=canvas.bounding_box()
    page.mouse.move(box['x']+50,box['y']+50);page.mouse.down()
    page.mouse.move(box['x']+180,box['y']+130,steps=15);page.mouse.up()
    recognize(page)
    assert len(images)==1
    low,high=images[0].convert('L').getextrema()
    assert low<100 and high>240
