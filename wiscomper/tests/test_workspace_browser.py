"""Workspace acceptance against isolated storage, with no real model calls."""
from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect

from test_browser import browser, local_server, workbench  # noqa: F401


def open_workspace(page, view):
    page.locator('.workspace-more summary').click()
    page.locator(f'.more-panel [data-ecosystem-action="{view}"]').click()
    dialog = page.locator('#workspace-center')
    expect(dialog).to_be_visible()
    expect(dialog.locator('.wc-loading')).to_have_count(0)
    return dialog


def api_data(page, path):
    response = page.request.get(page.url.rstrip('/') + path)
    assert response.ok, response.text()
    return response.json()


def test_preferences_survive_reload_and_apply_to_workspace(workbench):
    page, _ = workbench
    dialog = open_workspace(page, 'settings')
    for label, value in [('界面主题', 'dark'), ('默认输入', 'formula'),
                         ('默认播放速度', '1.5'), ('悬浮球大小', '80'),
                         ('悬浮球不透明度', '0.65')]:
        with page.expect_response(lambda response: response.url.endswith('/api/preferences') and response.request.method == 'PUT') as saved:
            dialog.get_by_label(label, exact=True).select_option(value)
        assert saved.value.ok
        expect(dialog.get_by_label(label, exact=True)).to_be_enabled()
    for label in ['减少界面动效', '显示悬浮球']:
        with page.expect_response(lambda response: response.url.endswith('/api/preferences') and response.request.method == 'PUT') as saved:
            dialog.get_by_label(label, exact=True).click()
        assert saved.value.ok
        expect(dialog.get_by_label(label, exact=True)).to_be_enabled()
    prefs = api_data(page, '/api/preferences')['preferences']
    assert prefs['theme'] == 'dark' and prefs['default_input'] == 'formula'
    assert prefs['default_speed'] == 1.5 and prefs['floating_size'] == 80
    assert prefs['floating_opacity'] == .65 and prefs['reduced_motion']
    assert not prefs['floating_visible']
    dialog.get_by_label('关闭我的空间').click()
    page.reload()
    expect(page.locator('#play')).to_be_enabled()
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    expect(page.locator('html')).to_have_attribute('data-reduced-motion', 'true')
    expect(page.locator('#speed')).to_have_value('1.5')
    expect(page.locator('.hub-root')).to_be_hidden()
    dialog = open_workspace(page, 'settings')
    expect(dialog.get_by_label('默认输入', exact=True)).to_have_value('formula')
    expect(dialog.get_by_label('悬浮球大小', exact=True)).to_have_value('80')
    expect(dialog.get_by_label('显示悬浮球', exact=True)).not_to_be_checked()


def test_learning_capture_review_archive_and_portable_export(workbench):
    page, _ = workbench
    page.locator('#seek').fill('4.5')
    page.locator('[data-study-kind="wrongbook"]').click()
    dialog = page.locator('#workspace-center')
    expect(dialog.get_by_label('标题', exact=True)).to_be_visible()
    dialog.get_by_label('标题', exact=True).fill('为什么射程不是无限大？')
    dialog.get_by_label('题目 / 观察对象', exact=True).fill('比较 $\\theta=30^\\circ$ 与 $45^\\circ$ 的射程。')
    dialog.get_by_label('解答 / 结论', exact=True).fill('同高、无阻力时，$R=v_0^2\\sin(2\\theta)/g$。')
    dialog.get_by_label('我的笔记', exact=True).fill('条件必须是同高落地。')
    dialog.get_by_label('标签（逗号分隔，最多 8 个）', exact=True).fill('力学，射程')
    dialog.get_by_role('button', name='保存资料', exact=True).click()
    card = dialog.locator('.wc-card').filter(has=page.get_by_role('heading', name='为什么射程不是无限大？', exact=True))
    expect(card).to_be_visible()
    item = api_data(page, '/api/learning')['items'][0]
    assert item['time_sec'] == 4.5 and item['project_id']
    assert item['tags'] == ['力学', '射程']
    card.get_by_role('button', name='开始复习', exact=True).click()
    expect(dialog.locator('.wc-preview').first).not_to_have_attribute('open', '')
    dialog.get_by_text('查看解答与笔记', exact=True).click()
    expect(dialog.locator('.katex')).not_to_have_count(0)
    dialog.get_by_role('button', name='已掌握', exact=True).click()
    expect(card).to_contain_text('已自评掌握')
    reviewed = api_data(page, f'/api/learning/{item["id"]}')['item']
    assert reviewed['review_count'] == 1 and reviewed['status'] == 'mastered'
    assert reviewed['reviews'][0]['grade'] == 'easy'
    card.get_by_role('button', name='查看与编辑', exact=True).click()
    dialog.get_by_label('我的笔记', exact=True).fill('再次确认：同高落地，忽略空气阻力。')
    dialog.get_by_role('button', name='保存资料', exact=True).click()
    expect(card).to_be_visible()
    card.get_by_role('button', name='归档', exact=True).click()
    expect(card).to_have_count(0)
    dialog.get_by_role('combobox', name='复习状态', exact=True).select_option('archived')
    expect(card).to_be_visible()
    card.get_by_role('button', name='恢复', exact=True).click()
    expect(card).to_have_count(0)
    dialog.get_by_role('combobox', name='复习状态', exact=True).select_option('all')
    expect(card).to_be_visible()
    with page.expect_download() as download:
        dialog.get_by_role('button', name='导出', exact=True).click()
    exported = json.loads(download.value.path().read_text(encoding='utf-8'))
    portable = exported['items'][0]
    assert exported['format'] == 'wiscomper-learning'
    assert portable['note'] == '再次确认：同高落地，忽略空气阻力。'
    assert not portable.get('project_id') and not portable.get('time_sec')
    assert 'reviews' not in portable
    dialog.locator('input[type=file]').set_input_files({'name': 'learning.json', 'mimeType': 'application/json', 'buffer': json.dumps(exported).encode()})
    expect(dialog.locator('.wc-loading')).to_have_count(0)
    expect(card).to_have_count(1)


def test_learning_draft_guard_and_unsafe_text_are_preserved_as_text(workbench):
    page, _ = workbench
    dialog = open_workspace(page, 'learning')
    dialog.get_by_role('button', name='＋ 添加资料', exact=True).click()
    payload = '<img src=x onerror="window.workspaceXss=1">'
    dialog.get_by_label('标题', exact=True).fill('纯文本预览')
    dialog.get_by_label('我的笔记', exact=True).fill(payload + ' $x^2$')
    dialog.get_by_text('公式预览', exact=True).click()
    expect(dialog.locator('.wc-preview .wc-rich')).to_contain_text(payload)
    expect(dialog.locator('.wc-preview img')).to_have_count(0)
    assert page.evaluate('window.workspaceXss === undefined')
    dialog.get_by_label('关闭我的空间').click()
    expect(dialog.locator('.wc-confirm')).to_be_visible()
    dialog.get_by_role('button', name='继续编辑', exact=True).click()
    expect(dialog.get_by_label('我的笔记', exact=True)).to_have_value(payload + ' $x^2$')
    dialog.get_by_role('button', name='保存资料', exact=True).click()
    expect(dialog.locator('.wc-card')).to_contain_text(payload)
    assert page.evaluate('window.workspaceXss === undefined')


def test_course_pack_material_order_lesson_export_and_reimport(workbench):
    page, _ = workbench
    dialog = open_workspace(page, 'course-packs')
    dialog.get_by_role('button', name='＋ 创建课包', exact=True).click()
    expect(dialog.get_by_label('课包名称', exact=True)).to_be_visible()
    dialog.get_by_label('课包名称', exact=True).fill('从公式到抛体实验')
    dialog.get_by_label('课包介绍', exact=True).fill('先观察，再推导，再解释。')
    dialog.get_by_label('适用对象', exact=True).fill('高中物理')
    dialog.get_by_label('预计时长（分钟）', exact=True).fill('35')
    dialog.get_by_label('学习目标', exact=True).fill('说明同高、无阻力假设对射程公式的限制。')
    dialog.get_by_label('教学过程', exact=True).fill('观察作品 → 写出 $R=v_0^2\\sin(2\\theta)/g$ → 对照示例。')
    picker = dialog.get_by_role('combobox', name='添加材料', exact=True)
    options = picker.locator('option').evaluate_all('(nodes)=>nodes.map(n=>({value:n.value,text:n.textContent}))')
    assert all(any(x['text'].startswith(prefix) for x in options) for prefix in ['作品 · ', '公式 · ', '示例 · ']), json.dumps(options, ensure_ascii=True)
    selected = [next(x for x in options if x['text'].startswith(prefix)) for prefix in ['作品 · ', '公式 · ', '示例 · ']]
    for option in selected:
        picker.select_option(option['value'])
        dialog.get_by_role('button', name='加入课包', exact=True).click()
    rows = dialog.locator('.wc-material-row')
    expect(rows).to_have_count(3)
    rows.nth(2).get_by_role('button', name='上移', exact=True).click()
    rows.nth(0).get_by_label('讲解备注', exact=True).fill('停在最高点，引导学生观察速度方向。')
    dialog.get_by_role('button', name='保存课包', exact=True).click()
    card = dialog.locator('.wc-card').filter(has=page.get_by_role('heading', name='从公式到抛体实验', exact=True))
    expect(card).to_be_visible()
    saved = api_data(page, '/api/course-packs')['items'][0]
    pack = api_data(page, f'/api/course-packs/{saved["id"]}')['item']
    assert [x['kind'] for x in pack['items']] == ['project', 'sample', 'formula']
    assert pack['lesson']['duration'] == 35 and pack['lesson']['audience'] == '高中物理'
    assert pack['items'][0]['note'] == '停在最高点，引导学生观察速度方向。'
    with page.expect_download() as download:
        card.get_by_role('button', name='导出', exact=True).click()
    exported = json.loads(download.value.path().read_text(encoding='utf-8'))
    assert exported['format'] == 'wiscomper-course-pack'
    entries = exported['pack']['items']
    assert [x['kind'] for x in entries] == ['project', 'sample', 'formula']
    assert not entries[0].get('id') and entries[0]['snapshot']['title']
    assert entries[1]['id'] and entries[2]['id'].startswith('builtin-')
    dialog.locator('input[type=file]').set_input_files({'name': 'pack.json', 'mimeType': 'application/json', 'buffer': json.dumps(exported).encode()})
    expect(dialog.locator('.wc-loading')).to_have_count(0)
    expect(card).to_have_count(1)
    card.get_by_role('button', name='打开课包', exact=True).click()
    expect(dialog.locator('.wc-pack-materials .wc-card')).to_have_count(3)
    expect(dialog.locator('.wc-main')).to_contain_text('高中物理 · 35 分钟')
    expect(dialog.locator('.katex')).not_to_have_count(0)


def test_favorite_error_is_visible_without_opening_workspace(workbench):
    page, failures = workbench

    def fail_save(route):
        route.fulfill(status=503, json={'detail': '测试：保存服务暂时不可用'})

    page.route('**/api/learning', fail_save)
    page.locator('[data-study-kind="favorite"]').click()
    expect(page.locator('#toast')).to_contain_text('测试：保存服务暂时不可用')
    expect(page.locator('#workspace-center')).not_to_be_visible()
    failures[:] = [failure for failure in failures if '503' not in failure]


def test_preference_conflict_preserves_newer_settings_and_refreshes_controls(workbench):
    page, failures = workbench
    dialog = open_workspace(page, 'settings')
    previous = api_data(page, '/api/preferences')
    csrf = api_data(page, '/api/bootstrap')['csrf']
    response = page.request.put(page.url.rstrip('/') + '/api/preferences',
                                headers={'X-CSRF-Token': csrf},
                                data={'expected_revision': previous['revision'],
                                      'preferences': {'theme': 'dark', 'default_input': 'formula'}})
    assert response.ok
    # This open settings panel still has the earlier revision, just as a
    # second browser tab would after the first tab changes its preferences.
    with page.expect_response(lambda response: response.url.endswith('/api/preferences') and response.request.method == 'PUT') as conflict:
        dialog.get_by_label('界面主题', exact=True).select_option('light')
    assert conflict.value.status == 409
    expect(dialog.locator('.wc-status.error')).to_be_visible()
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    expect(dialog.get_by_label('界面主题', exact=True)).to_have_value('dark')
    expect(dialog.get_by_label('默认输入', exact=True)).to_have_value('formula')
    stored = api_data(page, '/api/preferences')
    assert stored['revision'] == response.json()['revision']
    assert stored['preferences']['theme'] == 'dark'
    failures[:] = [failure for failure in failures if '409' not in failure]


def test_learning_save_does_not_accept_edits_that_it_will_discard(workbench):
    page, _ = workbench
    dialog = open_workspace(page, 'learning')
    dialog.get_by_role('button', name='＋ 添加资料', exact=True).click()
    dialog.get_by_label('标题', exact=True).fill('保存时保护输入')
    dialog.get_by_label('我的笔记', exact=True).fill('首次保存的内容')
    held = {}

    def hold_save(route):
        held.update(route=route, response=route.fetch())

    page.route('**/api/learning', hold_save)
    dialog.get_by_role('button', name='保存资料', exact=True).click()
    deadline = time.monotonic() + 5
    while 'route' not in held and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert 'route' in held
    try:
        # Either freezing the form or retaining a newer draft is valid. The
        # current UI uses the simpler freeze-until-save-completes behavior.
        assert dialog.locator('.wc-editor').evaluate('(form)=>form.inert')
        note = dialog.locator('textarea').nth(2)
        note.evaluate('(input)=>input.focus()')
        page.keyboard.type('This must not enter the inert form')
        expect(note).to_have_value('首次保存的内容')
        dialog.get_by_label('关闭我的空间').click()
        expect(dialog).to_be_visible()
    finally:
        held['route'].fulfill(response=held['response'])
        page.unroute('**/api/learning', hold_save)
    expect(dialog.locator('.wc-card')).to_contain_text('保存时保护输入')


def search_records(page):
    base = page.url.rstrip('/')
    headers = {'X-CSRF-Token': api_data(page, '/api/bootstrap')['csrf']}
    title = 'Searchnote <img src=x onerror="window.searchXss=1">'
    note = page.request.post(base + '/api/learning', headers=headers,
                             data={'kind': 'note', 'title': title, 'note': 'My searchable note'})
    pack = page.request.post(base + '/api/course-packs', headers=headers,
                             data={'title': 'Searchlesson', 'description': 'My searchable lesson'})
    assert note.ok and pack.ok
    return note.json()['item'], pack.json()['item']


def test_global_search_opens_learning_pack_and_formula_without_interpreting_html(workbench):
    page, _ = workbench
    note, pack = search_records(page)
    page.keyboard.press('Control+k')
    search = page.locator('#global-search')
    expect(search).to_be_visible()
    search.get_by_label('搜索全站', exact=True).fill('Searchnote')
    result = search.locator('.gs-result').filter(has_text=note['title'])
    expect(result).to_be_visible()
    expect(search.locator('img')).to_have_count(0)
    assert page.evaluate('window.searchXss === undefined')
    result.click()
    workspace = page.locator('#workspace-center')
    expect(workspace.get_by_label('标题', exact=True)).to_have_value(note['title'])
    expect(workspace.get_by_label('我的笔记', exact=True)).to_have_value('My searchable note')
    workspace.get_by_label('关闭我的空间').click()
    page.keyboard.press('Control+k')
    search.get_by_label('搜索全站', exact=True).fill('Searchlesson')
    search.locator('.gs-result').filter(has_text=pack['title']).click()
    expect(workspace.locator('.wc-section-title h3')).to_have_text(pack['title'])
    expect(workspace).to_contain_text('My searchable lesson')
    workspace.get_by_label('关闭我的空间').click()
    page.keyboard.press('Control+k')
    search.get_by_label('搜索全站', exact=True).fill('全反射临界角')
    search.locator('.gs-result').filter(has_text='全反射临界角').click()
    expect(search).not_to_be_visible()
    expect(page.locator('#prompt')).not_to_have_value('')
    assert '\\theta_c' in page.locator('#prompt').input_value()
    assert not page.evaluate('window.searchXss === 1')


def test_global_search_ignores_stale_results_and_fast_enter_uses_current_query(workbench):
    page, _ = workbench
    note, pack = search_records(page)
    page.keyboard.press('Control+k')
    search = page.locator('#global-search')
    query = search.get_by_label('搜索全站', exact=True)
    query.fill('Searchnote')
    expect(search.locator('.gs-result').filter(has_text=note['title'])).to_be_visible()
    # Enter arrives before the debounce timer. An old result must not open.
    query.fill('Searchlesson')
    query.press('Enter')
    expect(search).to_be_visible()
    expect(search.locator('.gs-result').filter(has_text=pack['title'])).to_be_visible()
    expect(search.locator('.gs-result').filter(has_text=note['title'])).to_have_count(0)
    held = {}

    def hold_old(route):
        params = parse_qs(urlparse(route.request.url).query)
        if params.get('q') == ['Searchnote']:
            held.update(route=route, response=route.fetch())
        else:
            route.continue_()

    page.route('**/api/search?**', hold_old)
    query.fill('Searchnote')
    deadline = time.monotonic() + 5
    while 'route' not in held and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert 'route' in held
    query.fill('Searchlesson')
    expect(search.locator('.gs-result').filter(has_text=pack['title'])).to_be_visible()
    held['route'].fulfill(response=held['response'])
    page.unroute('**/api/search?**', hold_old)
    query.press('ArrowDown')
    expect(search.locator('.gs-result').filter(has_text=pack['title'])).to_be_focused()
    page.keyboard.press('Enter')
    expect(search).not_to_be_visible()
    expect(page.locator('#workspace-center .wc-section-title h3')).to_have_text(pack['title'])
