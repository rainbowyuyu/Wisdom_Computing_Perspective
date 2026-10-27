"""Real browser integration of the migrated library, graph and floating hub.

Isolated session/data; providers are never called.
"""
import json
import time
from pathlib import Path

from playwright.sync_api import expect
from test_browser import browser, local_server, workbench

ARTIFACTS = Path(__file__).resolve().parents[1] / 'tmp' / 'ecosystem-qa'


def test_formula_library_edit_search_archive_restore_and_roundtrip(workbench):
    page, _ = workbench
    page.locator('#open-library').click()
    expect(page.locator('.kw-formula-card')).to_have_count(16)
    expect(page.locator('#kw-library-list .katex').first).to_be_visible()
    page.locator('#kw-new').click()
    page.locator('#kw-form-title').fill('能量与质量')
    page.locator('#kw-form-latex').fill(r'E=mc^2')
    page.locator('#kw-form-note').fill('测试笔记：解释变量与适用条件')
    page.locator('#kw-form-tags').fill('物理，能量')
    page.locator('#kw-form-link').check()
    expect(page.locator('#kw-form-preview .katex')).to_be_visible()
    page.locator('#kw-save').click()
    card=page.locator('.kw-formula-card').filter(has_text='能量与质量')
    expect(card).to_be_visible()
    formula_id=card.get_attribute('data-formula-id')
    card.get_by_role('button',name='☆ 收藏',exact=True).click()
    expect(card.get_by_role('button',name='★ 已收藏',exact=True)).to_be_visible()
    card.get_by_role('button',name='编辑',exact=True).click()
    page.locator('#kw-form-note').fill('增加了新的说明')
    page.locator('#kw-save').click()
    expect(card).to_contain_text('增加了新的说明')
    card.get_by_role('button',name='归档',exact=True).click()
    expect(card).not_to_be_visible()
    page.locator('#kw-scope').select_option('archived')
    expect(card).to_be_visible()
    card.get_by_role('button',name='恢复',exact=True).click()
    expect(card).not_to_be_visible()
    page.locator('#kw-scope').select_option('saved')
    expect(card).to_be_visible()
    with page.expect_download() as download:
        page.locator('#kw-export').click()
    exported=json.loads(Path(download.value.path()).read_text('utf-8'))
    assert any(item['latex']=='E=mc^2' for item in exported['items'])
    page.locator('#kw-import-file').set_input_files({'name':'formulas.json','mimeType':'application/json','buffer':json.dumps(exported).encode()})
    expect(page.locator('#kw-message')).to_contain_text('重复')
    expect(page.locator('.kw-formula-card')).to_have_count(1)
    page.locator('#kw-close').click()
    page.locator('#prompt').fill('保留这段草稿')
    page.locator('#open-library').click()
    card.get_by_role('button',name='带入创作',exact=True).click()
    assert '保留这段草稿' in page.locator('#prompt').input_value()
    assert 'E=mc^2' in page.locator('#prompt').input_value()
    expect(page.locator('#iterate')).not_to_be_checked()
    page.reload()
    expect(page.locator('#canvas-empty')).to_be_hidden(timeout=20000)
    page.locator('#open-library').click()
    page.locator('#kw-search').fill('增加了新的说明')
    expect(page.locator(f'[data-formula-id="{formula_id}"]')).to_be_visible()


def test_graph_formula_relations_navigation_and_mobile_layout(workbench):
    page,_=workbench
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    page.locator('#open-knowledge').click()
    page.locator('#kw-graph-2d').click()
    expect(page.locator('.kw-graph-node')).not_to_have_count(0)
    page.locator('#kw-graph-search').fill('斯涅尔')
    page.locator('#kw-graph-results').get_by_role('button',name='斯涅尔折射定律',exact=True).click()
    expect(page.locator('#kw-node-detail h3')).to_have_text('斯涅尔折射定律')
    expect(page.locator('.kw-graph-node.selected .katex')).to_be_visible()
    expect(page.locator('#kw-graph svg line')).not_to_have_count(0)
    page.screenshot(path=str(ARTIFACTS/'graph-desktop.png'),full_page=True)
    page.locator('#kw-node-detail').get_by_role('button',name='查看公式',exact=True).click()
    expect(page.locator('.kw-formula-card')).to_have_count(1)
    expect(page.locator('.kw-formula-card')).to_contain_text('斯涅尔')
    page.locator('.kw-formula-card').get_by_role('button',name='探索示例',exact=True).click()
    expect(page.locator('#scene-title')).to_have_text('光为什么会拐弯',timeout=15000)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#open-knowledge').click()
    expect(page.locator('#kw-node-detail h3')).to_have_text('斯涅尔折射定律')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#knowledge-workspace').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
    page.screenshot(path=str(ARTIFACTS/'graph-mobile.png'))
    page.locator('[data-view="library"]').click()
    page.locator('#kw-search').fill('')
    expect(page.locator('.kw-formula-card')).to_have_count(16)
    assert page.locator('#knowledge-workspace').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
    page.screenshot(path=str(ARTIFACTS/'library-mobile.png'))
    page.locator('#kw-close').click()
    page.locator('#provider').select_option('qwen')
    expect(page.locator('#provider-status')).to_contain_text('Qwen')


def test_library_untrusted_text_is_inert_and_capture_links_project(workbench):
    page,_=workbench
    page.locator('[data-sample="formula"]').click()
    expect(page.locator('#scene-title')).to_have_text('公式里的对应关系',timeout=15000)
    page.locator('#open-library').click()
    page.locator('#kw-capture').click()
    expect(page.locator('#kw-editor')).to_be_visible()
    expect(page.locator('#kw-form-link')).to_be_checked()
    page.locator('#kw-form-title').fill('<img src=x onerror=alert(1)>')
    page.locator('#kw-save').click()
    card=page.locator('.kw-formula-card')
    expect(card).to_have_count(1)
    expect(card).to_contain_text('<img src=x onerror=alert(1)>')
    expect(card.locator('img')).to_have_count(0)
    card.get_by_role('button',name='关联作品',exact=True).click()
    expect(page.locator('#knowledge-workspace')).not_to_be_visible()
    expect(page.locator('#scene-title')).to_have_text('公式里的对应关系')


def test_library_save_locks_form_and_closed_dialog_errors_remain_visible(workbench):
    page,_=workbench
    page.locator('#open-library').click()
    page.locator('#kw-new').click()
    page.locator('#kw-form-title').fill('等待保存的公式')
    page.locator('#kw-form-latex').fill('a+b=c')
    held={}
    def hold(route):
        if route.request.method=='POST': held.update(route=route,response=route.fetch())
        else: route.continue_()
    page.route('**/api/library',hold)
    page.locator('#kw-save').click()
    deadline=time.monotonic()+5
    while not held and time.monotonic()<deadline: page.wait_for_timeout(20)
    assert held
    expect(page.locator('#kw-form-latex')).to_be_disabled()
    expect(page.locator('#kw-editor-cancel')).to_be_disabled()
    page.locator('#kw-new').click()
    expect(page.locator('#kw-message')).to_contain_text('正在保存')
    held['route'].fulfill(response=held['response'])
    expect(page.locator('#kw-editor')).not_to_be_visible()
    expect(page.locator('.kw-formula-card').filter(has_text='等待保存的公式')).to_be_visible()
    page.locator('#kw-close').click()
    page.locator('#prompt').fill('已有内容'*1500)
    page.locator('#open-library').click()
    page.locator('.kw-formula-card').get_by_role('button',name='带入创作',exact=True).click()
    expect(page.locator('#knowledge-workspace')).not_to_be_visible()
    expect(page.locator('#toast')).to_contain_text('请先精简内容')
    assert page.locator('#prompt').input_value()=='已有内容'*1500
