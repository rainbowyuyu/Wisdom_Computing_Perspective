"""Real browser regressions for layered artwork, themes and course playback."""
import io
from pathlib import Path
import pytest
from PIL import Image, ImageChops, ImageStat
from test_teaching import teaching_page
from test_solution_library import accounts, live_library_server


def test_create_pack_from_player_and_continuous_playback(teaching_page):
    page, origin, kind = teaching_page
    page.locator('.video-card').first.click()
    page.wait_for_function("document.querySelector('#example-video-player').readyState>=2")
    page.locator('[data-watch-create]').click()
    editor=page.locator('.course-editor')
    assert editor.locator('[name=name]').input_value().endswith('课堂教案')
    assert editor.locator('[data-selected-videos] li').count()==1
    editor.locator('[name=name]').fill('从播放器创建的课包')
    editor.locator('[name=procedure]').fill(r'观察变换，解释 $x^2$ 的含义。')
    editor.locator('[data-add]:not([disabled])').first.click()
    with page.expect_response(lambda r:r.url.endswith('/course-packs') and r.request.method=='POST') as saved:
        editor.locator('[type=submit]').click()
    ident=saved.value.json()['id']
    page.wait_for_selector('.lesson-reader .katex')
    page.locator('[data-play-all]').click()
    page.wait_for_function("document.querySelector('#example-video-player').readyState>=2")
    page.locator('[data-auto-next]').check()
    page.wait_for_function("const v=document.querySelector('#example-video-player');v.readyState>=2&&Number.isFinite(v.duration)&&v.duration>0")
    # Complete the actual media to exercise the ended event, not an invented event.
    page.evaluate("const v=document.querySelector('#example-video-player');v.currentTime=v.duration-.2;v.play()")
    page.wait_for_function("document.querySelector('.course-player-nav span').textContent.includes('2 / 2')")
    assert page.locator('.teaching-episode-list [aria-current]').get_attribute('data-episode')=='1'
    assert page.locator('[data-auto-next]').is_checked()
    page.wait_for_function("document.querySelector('#example-video-player').readyState>=2")
    page.evaluate("document.querySelector('#example-video-player').pause()")
    page.locator('#custom-player-theater').click()
    assert page.locator('#custom-player-theater').get_attribute('aria-pressed')=='true'
    main,side=page.locator('.teaching-watch-main').bounding_box(),page.locator('.teaching-watch-sidebar').bounding_box()
    assert side['y']>main['y']+main['height']-1
    page.locator('#custom-player-theater').click()
    progress=page.get_by_role('slider',name='播放进度')
    progress.press('Home');progress.press('ArrowRight')
    assert page.locator('#example-video-player').evaluate('v=>Math.abs(v.currentTime-5)<.2')
    page.locator('[data-episode="0"]').click()
    page.wait_for_function("document.querySelector('.course-player-nav span').textContent.includes('1 / 2')")
    page.keyboard.press('Escape')
    page.reload();page.wait_for_selector('.video-card')
    page.locator('[data-filter=courseware]').click()
    page.locator(f'[data-pack="{ident}"]').click()
    page.wait_for_selector('.lesson-reader .katex')
    assert page.locator('.lesson-reader h2').inner_text()=='从播放器创建的课包'
    assert page.locator('.course-playlist [data-play]').count()==2


@pytest.mark.parametrize('motion',['no-preference','reduce'])
def test_achievement_artwork_is_visible_and_recovers(teaching_page,motion):
    page,_,kind=teaching_page
    page.emulate_media(reduced_motion=motion)
    count=page.evaluate("""async()=>{
        const m=await import('/static/js/achievement-cards.js?v=20260917-artwork-3');const cards=await m.loadAchievementCardManifest();
        const host=document.createElement('dialog');host.id='qa-cards';host.style='margin:auto;padding:30px;background:var(--bg-surface);border:0;width:95vw;max-height:90vh;overflow:auto';document.body.append(host);host.showModal();
        host.innerHTML='<div class="achievement-holo-grid">'+cards.map(meta=>m.renderHoloCardHtml(meta,{locked:false})).join('')+'</div>';
        m.bindHoloCardTilt(host);await Promise.all([...host.querySelectorAll('img')].map(img=>{img.loading='eager';return img.decode()}));return cards.length;
    }""")
    assert count==13
    # Pixel differences prove the subject contributes to the visible card; negative
    # z depths behind an opaque plane would produce identical screenshots.
    for card in page.locator('#qa-cards .ach-holo-stage').all():
        rendered=Image.open(io.BytesIO(card.screenshot())).convert('RGB')
        ident=card.locator('..').get_attribute('data-achievement-id')
        reference=Image.open(Path('static/assets/achievement-cards')/ident/'preview.png').convert('RGB').resize(rendered.size,Image.Resampling.LANCZOS)
        # Compare the actual colors, not merely successful image downloads. The
        # reported failure leaves only dark outlines despite all PNGs loading.
        w,h=rendered.size;center=(int(w*.15),int(h*.2),int(w*.85),int(h*.8))
        error=sum(ImageStat.Stat(ImageChops.difference(rendered.crop(center),reference.crop(center))).mean)/3
        assert error<25,(ident,error)
        card.locator('.ach-holo-subject').evaluate("e=>e.style.visibility='hidden'")
        without=Image.open(io.BytesIO(card.screenshot())).convert('RGB')
        assert sum(ImageStat.Stat(ImageChops.difference(rendered,without)).mean)>8
        card.locator('.ach-holo-subject').evaluate("e=>e.style.visibility='visible'")
    page.screenshot(path=f'tests/artifacts/achievement-gallery-{kind}-{motion}.png')
    card=page.locator('#qa-cards .ach-holo-stage').first
    card.scroll_into_view_if_needed()
    box=card.bounding_box();page.mouse.move(box['x']+box['width']*.8,box['y']+box['height']*.3)
    page.wait_for_timeout(350)
    transform=card.locator('.ach-holo-flipper').evaluate("e=>getComputedStyle(e).transform")
    assert (transform=='none') == (motion=='reduce')
    if motion!='reduce':
        rendered=Image.open(io.BytesIO(card.screenshot())).convert('RGB')
        card.locator('.ach-holo-subject').evaluate("e=>e.style.visibility='hidden'")
        without=Image.open(io.BytesIO(card.screenshot())).convert('RGB')
        assert sum(ImageStat.Stat(ImageChops.difference(rendered,without)).mean)>8
        card.locator('.ach-holo-subject').evaluate("e=>e.style.visibility='visible'")
    card.locator('.ach-holo-subject img').evaluate("e=>e.src='/assets/achievement-cards/missing.png'")
    page.wait_for_selector('#qa-cards .use-fallback .ach-holo-fallback',state='visible')


def test_code_assistant_theme_and_remount(teaching_page):
    page,_,kind=teaching_page
    page.evaluate("window.showSection('devtools')")
    page.wait_for_function("document.querySelector('#devtools')?.dataset.devInitialized")
    page.evaluate("window.switchDevTool('manim')")
    page.wait_for_function('!!window.monacoEditor',timeout=45000)
    assert page.locator('.manim-ai-edit-float-header').count()==0
    for theme in ['light','dark']:
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        page.wait_for_timeout(400)
        colors=page.locator('#manim-ai-edit-float').evaluate("""e=>{
            const probe=document.createElement('span');probe.style='color:var(--text-main);background:var(--bg-surface)';e.append(probe);
            const expected=getComputedStyle(probe),actual=getComputedStyle(e);const ok=expected.color===actual.color&&expected.backgroundColor===actual.backgroundColor;probe.remove();return ok;
        }""")
        assert colors
        page.screenshot(path=f'tests/artifacts/assistant-theme-{theme}-{kind}.png',full_page=True)
    page.evaluate("window.showSection('examples')")
    page.wait_for_selector('.video-card')
    page.evaluate("window.showSection('devtools')")
    page.wait_for_function("document.querySelector('#devtools')?.dataset.devInitialized")
    page.evaluate("window.switchDevTool('manim')")
    page.wait_for_selector('.code-assistant-form')
    assert page.locator('.code-assistant-form').count()==1
