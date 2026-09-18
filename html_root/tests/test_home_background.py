"""Full-page background must survive cached section clipping without visible seams."""
import io
import os
from pathlib import Path
import pytest
from PIL import Image
from playwright.sync_api import sync_playwright

pytestmark=pytest.mark.skipif(os.getenv('WISDOM_BROWSER_TESTS')!='1',reason='Requires UI servers')


@pytest.mark.parametrize('origin,path,kind',[
    ('http://127.0.0.1:8000','/?section=home','static'),
    ('http://127.0.0.1:5173','/','vue')])
@pytest.mark.parametrize('width,theme',[(2048,'light'),(390,'dark')])
def test_background_outside_clipped_home(origin,path,kind,width,theme):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':width,'height':1000},reduced_motion='reduce')
        # Reproduce the obsolete cached rule that cropped the viewport-wide glow.
        def legacy_styles(route):
            response=route.fetch()
            route.fulfill(response=response,body=response.text()+"\n#home{overflow-x:clip!important}.hero::before{content:'';position:absolute;width:100vw;height:100%;left:50%;transform:translateX(-50%);background:#dbeafe}")
        page.route('**/refinements.css*',legacy_styles)
        page.goto(origin+path,wait_until='domcontentloaded')
        page.wait_for_selector('.hero h1')
        page.evaluate("theme=>document.documentElement.dataset.theme=theme",theme)
        page.wait_for_timeout(700)
        info=page.locator('#home').evaluate('''el=>({
            clip:getComputedStyle(el).overflowX,
            pseudo:getComputedStyle(el.querySelector('.hero'),'::before').content,
            background:getComputedStyle(document.querySelector('.home-page-background')).backgroundImage,
            backdrop:document.querySelector('.home-page-background').getBoundingClientRect().toJSON(),
            rect:el.getBoundingClientRect().toJSON(),
            overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth
        })''')
        assert info['clip']=='clip' and info['pseudo']=='none'
        assert info['background'].count('radial-gradient')==2
        assert info['backdrop']['x']==0 and info['backdrop']['y']==0
        assert info['backdrop']['width']==page.evaluate('document.documentElement.clientWidth')
        assert info['backdrop']['height']==1000
        assert info['overflow']<=2
        Path('tests/artifacts').mkdir(exist_ok=True)
        raw=page.screenshot(path=f'tests/artifacts/home-full-page-{kind}-{width}.png')
        if width>1000:
            image=Image.open(io.BytesIO(raw)).convert('RGB')
            # Inspect the exact vertical lines formerly delimiting the home container.
            for edge in ('left','right'):
                x=round(info['rect'][edge])
                for y in (250,350,450,550):
                    left=image.getpixel((x-2,y));right=image.getpixel((x+2,y))
                    assert max(abs(a-b) for a,b in zip(left,right))<=3,(edge,y,left,right)
        page.evaluate("()=>window.showSection('calculate')")
        page.wait_for_selector('.step-tutor textarea')
        assert not page.locator('.home-page-background').is_visible()
        page.evaluate("()=>window.showSection('home')")
        page.wait_for_selector('.hero h1')
        assert page.locator('.home-page-background').is_visible()
        page.set_viewport_size({'width':2560 if width>1000 else 430,'height':1440 if width>1000 else 900})
        page.evaluate('window.scrollTo(0,0)')
        bounds=page.locator('.home-page-background').bounding_box()
        assert bounds['x']==0 and bounds['y']==0
        assert bounds['width']==page.evaluate('document.documentElement.clientWidth')
        assert bounds['height']==min(1000,max(760,page.evaluate('window.innerHeight')))
        raw=page.screenshot(path=f'tests/artifacts/home-fullscreen-{kind}-{width}.png')
        if width>1000:
            image=Image.open(io.BytesIO(raw)).convert('RGB')
            # Both edges share the glow midway down, then return to the page's white below.
            for x in (5,image.width-6):
                middle=image.getpixel((x,450));bottom=image.getpixel((x,1100))
                assert max(abs(a-b) for a,b in zip(middle,bottom))>8,(middle,bottom)
                assert max(abs(a-b) for a,b in zip(bottom,(248,250,252)))<=2,bottom
        page.evaluate('window.scrollTo(0,350)')
        page.wait_for_function('window.scrollY>0')
        bounds=page.locator('.home-page-background').bounding_box()
        assert abs(bounds['y']+page.evaluate('window.scrollY'))<2
        browser.close()
