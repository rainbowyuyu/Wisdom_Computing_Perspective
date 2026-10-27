"""Account UI acceptance with same-origin mocked OAuth boundaries; no external login."""
from __future__ import annotations

import pytest
from pathlib import Path
from playwright.sync_api import expect

from test_browser import browser  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def session(*, authenticated=False, configured=True, user=None, csrf="csrf_initial"):
    return {
        "authenticated": authenticated,
        "user": user,
        "github": {"configured": configured, "message": "" if configured else "GitHub 登录尚未配置。"},
        "csrf": csrf,
    }


@pytest.fixture
def account_page(browser):
    context = browser.new_context(viewport={"width": 900, "height": 700})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # A fully intercepted origin isolates this UI suite from in-progress server changes.
    page.route("**/*", lambda route: route.abort())
    page.route("**/web/account-menu.js", lambda route: route.fulfill(path=str(ROOT / "web" / "account-menu.js"), content_type="text/javascript"))
    page.route("**/web/account-menu.css", lambda route: route.fulfill(path=str(ROOT / "web" / "account-menu.css"), content_type="text/css"))
    page.route("**/web/email-auth-dialog.js", lambda route: route.fulfill(path=str(ROOT / "web" / "email-auth-dialog.js"), content_type="text/javascript"))
    page.route("**/web/email-auth-dialog.css", lambda route: route.fulfill(path=str(ROOT / "web" / "email-auth-dialog.css"), content_type="text/css"))
    page.route("**/account-test**", lambda route: route.fulfill(content_type="text/html", body='''
      <!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <link rel="stylesheet" href="/web/account-menu.css"><link rel="stylesheet" href="/web/email-auth-dialog.css"></head>
      <body style="margin:0;font-family:Arial,sans-serif;background:#f8fafc">
      <header style="display:flex;align-items:center;justify-content:space-between;height:64px;padding:0 14px;box-sizing:border-box;backdrop-filter:blur(16px)">
      <span>智算视界</span><div id="account-menu"></div></header><button id="outside">继续探索</button></body></html>
    '''))
    page.test_base = "http://account.test"
    yield page
    context.close()
    assert not errors


def mount(page, data, suffix=""):
    page.route("**/api/auth/session", lambda route: route.fulfill(json=data))
    page.goto(page.test_base + "/account-test" + suffix)
    page.evaluate("""async () => {
      window.accountEvents = []; window.accountNotifications = []; window.accountRequests = []; window.accountBusy = [];
      window.beforeMode = 'resolve'; window.accountCsrf = '';
      const {mountAccountMenu} = await import('/web/account-menu.js');
      window.account = mountAccountMenu({
        api: async (path, options = {}) => {
          const method = options.method || 'GET'; window.accountRequests.push({path, method});
          const response = await fetch(path, {
            method, credentials:'same-origin', signal:options.signal,
            headers:{'Content-Type':'application/json','X-CSRF-Token':window.accountCsrf},
            body:options.body === undefined ? undefined : JSON.stringify(options.body)
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || '请求失败'); return data;
        },
        beforeNavigate: async ({reason}) => {
          window.accountEvents.push({type:'before',reason});
          if(window.beforeMode === 'reject') throw new Error('当前修改尚未保存，请重试。');
          if(window.beforeMode === 'hold') await new Promise(resolve => window.releaseSave = resolve);
          sessionStorage.setItem('account-test-draft', '保留草稿');
          window.accountEvents.push({type:'saved',reason});
        },
        onSessionChange: (data, meta) => {
          window.accountCsrf=data.csrf;
          window.accountEvents.push({type:'session',authenticated:data.authenticated,reason:meta.reason});
          return {navigating:window.returnNavigation === true};
        },
        onBusyChange: reason => {
          window.accountBusy.push(reason);
          if (window.throwBusy) throw new Error('Host UI callback failed');
        },
        notify: (message, error) => window.accountNotifications.push({message,error})
      });
      await window.account.ready;
    }""")


def test_unconfigured_login_keyboard_mobile_and_retry(account_page):
    page = account_page
    mount(page, session(configured=False))
    page.set_viewport_size({"width": 320, "height": 568})
    trigger = page.locator(".account-trigger")
    trigger.focus(); trigger.press("Enter")
    panel = page.locator(".account-panel")
    expect(panel).to_be_visible()
    expect(panel).to_contain_text("当前浏览器中的作品会归入此账号")
    expect(panel.locator(".account-availability")).to_have_text("GitHub 登录尚未配置。")
    expect(panel.get_by_role("button", name="继续使用 GitHub")).to_be_disabled()
    bounds = panel.bounding_box()
    assert bounds["x"] >= 11 and bounds["x"] + bounds["width"] <= 309
    assert bounds["y"] >= 11 and bounds["y"] + bounds["height"] <= 557
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden(); expect(trigger).to_be_focused()
    page.route("**/api/auth/session", lambda route: route.fulfill(status=503, json={"detail":"暂时无法读取账号"}))
    page.evaluate("window.account.refresh()")
    trigger.click()
    expect(panel.locator(".account-error")).to_have_text("暂时无法读取账号")
    page.route("**/api/auth/session", lambda route: route.fulfill(json=session()))
    panel.get_by_role("button", name="重新读取账号状态").click()
    expect(panel.get_by_role("button", name="继续使用 GitHub")).to_be_enabled()
    expect(panel.locator(".account-error")).to_be_hidden()


def test_login_waits_for_save_and_redirects_only_to_same_origin_start(account_page):
    page = account_page
    mount(page, session())
    starts = []
    def github_start(route):
        starts.append(route.request.url)
        route.fulfill(content_type="text/html", body="<p>OAuth redirect boundary</p>")
    page.route("**/api/auth/github/start", github_start)
    page.evaluate("window.beforeMode='hold'; window.account.open('请先登录，再开始生成。')")
    expect(page.locator(".account-guidance")).to_have_text("请先登录，再开始生成。")
    page.get_by_role("button", name="继续使用 GitHub").click()
    expect(page.get_by_role("button", name="正在保存…")).to_be_disabled()
    expect(page.get_by_role("button", name="关闭账号菜单")).to_be_focused()
    assert not starts
    assert page.evaluate("window.accountBusy") == ["login"]
    assert page.evaluate("window.accountEvents.at(-1)") == {"type":"before", "reason":"login"}
    page.evaluate("window.releaseSave()")
    page.wait_for_url("**/api/auth/github/start")
    assert starts == [page.test_base + "/api/auth/github/start"]
    assert page.evaluate("sessionStorage.getItem('account-test-draft')") == "保留草稿"


def test_save_failure_blocks_login_and_allows_retry(account_page):
    page = account_page
    mount(page, session())
    page.evaluate("window.beforeMode='reject'; window.throwBusy=true; window.account.open()")
    page.get_by_role("button", name="继续使用 GitHub").click()
    expect(page.locator(".account-error")).to_have_text("当前修改尚未保存，请重试。")
    expect(page.get_by_role("button", name="继续使用 GitHub")).to_be_enabled()
    assert page.url.endswith("/account-test")
    assert page.evaluate("window.accountRequests") == [{"path":"/api/auth/session", "method":"GET"}]*2
    assert page.evaluate("window.accountNotifications.at(-1).error") is True
    assert page.evaluate("window.accountBusy") == ["login", None]


def test_signed_in_profile_is_inert_and_logout_flushes_then_rotates_session(account_page):
    page = account_page
    user = {"login":"rainbow-user", "name":"<img src=x onerror=alert(1)>", "avatar_url":"https://avatars.githubusercontent.com/private", "profile_url":"https://github.com/rainbow-user"}
    external = []
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(page.test_base) else None)
    mount(page, session(authenticated=True, user=user))
    page.locator(".account-trigger").click()
    expect(page.locator(".account-display-name")).to_have_text(user["name"])
    expect(page.locator(".account-login-name")).to_have_text("@rainbow-user")
    expect(page.locator(".account-panel img")).to_have_count(0)
    assert not external
    logout_requests = []
    page.route("**/api/auth/logout", lambda route: logout_requests.append(route))
    page.evaluate("window.beforeMode='hold'")
    page.get_by_role("button", name="退出登录", exact=True).click()
    expect(page.get_by_role("button", name="正在退出…")).to_be_disabled()
    assert not logout_requests
    assert page.evaluate("window.accountBusy") == ["logout"]
    page.evaluate("window.releaseSave()")
    page.wait_for_function("window.accountRequests.some(item=>item.path === '/api/auth/logout')")
    assert len(logout_requests) == 1
    assert logout_requests[0].request.headers["x-csrf-token"] == "csrf_initial"
    logout_requests[0].fulfill(json=session(csrf="csrf_rotated"))
    expect(page.locator(".account-panel")).to_be_hidden()
    expect(page.locator(".account-trigger")).to_be_focused()
    assert page.evaluate("window.accountCsrf") == "csrf_rotated"
    assert page.evaluate("window.accountBusy") == ["logout", None]
    assert page.evaluate("window.accountEvents.slice(-3)") == [
        {"type":"before", "reason":"logout"}, {"type":"saved", "reason":"logout"},
        {"type":"session", "authenticated":False, "reason":"logout"},
    ]
    assert page.evaluate("window.accountRequests") == [
        {"path":"/api/auth/session", "method":"GET"}, {"path":"/api/auth/session", "method":"GET"}, {"path":"/api/auth/logout", "method":"POST"},
    ]


def test_oauth_callback_error_is_safe_and_removed_from_url(account_page):
    page = account_page
    mount(page, session(), "?keep=1&auth_error=state#workspace")
    expect(page.locator(".account-panel")).to_be_visible()
    expect(page.locator(".account-error")).to_have_text("登录验证已过期或不属于当前浏览器，请重新登录。")
    assert page.url.endswith("?keep=1#workspace")
    assert page.evaluate("window.accountNotifications") == [{"message":"登录验证已过期或不属于当前浏览器，请重新登录。", "error":True}]
    page.keyboard.press('Escape');page.locator('.account-trigger').click()
    expect(page.locator('.account-loading')).to_be_hidden()
    expect(page.locator('.account-error')).to_have_text('登录验证已过期或不属于当前浏览器，请重新登录。')
    page.evaluate("window.beforeMode='hold'")
    page.get_by_role("button", name="继续使用 GitHub").click()
    assert page.evaluate("window.accountBusy") == ["login"]
    page.evaluate("window.account.dispose(); window.account.dispose(); window.account.open(); window.releaseSave()")
    expect(page.locator(".account-panel")).to_have_count(0)
    expect(page.locator(".account-trigger")).to_have_count(0)
    assert page.evaluate("window.accountBusy") == ["login", None]


def quota(**changes):
    return {"scope":"site", "unit":"model_tasks", "total":10, "used":3, "remaining":7,
            "available":7, "site_remaining":7, "requires_login":False, "reset_at":"2026-10-24T00:00:00Z", **changes}


def test_local_setup_guide_and_real_usage_refresh(account_page):
    page=account_page
    mount(page,{**session(configured=False),"public_mode":False,"usage":quota()})
    page.locator('.account-trigger').click()
    expect(page.locator('.account-setup')).to_be_visible()
    expect(page.locator('.account-setup')).to_contain_text('配置GitHub登录.cmd')
    expect(page.locator('.account-help-link')).to_have_attribute('href','/web/github-setup.html')
    expect(page.locator('.account-panel input')).to_have_count(0)
    expect(page.locator('.account-usage-balance')).to_have_text('还可提交 7 次')
    expect(page.locator('.account-usage-meter')).to_have_attribute('aria-valuenow','3')
    output=ROOT/'tmp'/'browser-qa';output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'account-usage-local.png'))
    page.route('**/api/auth/session',lambda route:route.fulfill(json={**session(),"public_mode":False,"usage":quota(used=5,remaining=5,available=5,site_remaining=5)}))
    page.get_by_role('button',name='刷新模型任务额度').click()
    expect(page.locator('.account-usage-balance')).to_have_text('还可提交 5 次')
    expect(page.locator('.account-setup')).to_be_hidden()
    page.set_viewport_size({"width":320,"height":480})
    bounds=page.locator('.account-panel').bounding_box()
    assert bounds['x']>=11 and bounds['x']+bounds['width']<=309 and bounds['y']+bounds['height']<=469


def test_public_setup_and_account_quota_do_not_expose_admin_form(account_page):
    page=account_page
    mount(page,{**session(configured=False),"public_mode":True,"usage":quota(scope='account',total=3,used=0,remaining=3,available=0,requires_login=True)})
    page.locator('.account-trigger').click()
    expect(page.locator('.account-setup')).to_be_hidden()
    expect(page.locator('.account-availability')).to_contain_text('请联系站点维护者')
    expect(page.locator('.account-usage-balance')).to_have_text('登录后可使用模型任务')
    page.route('**/api/auth/session',lambda route:route.fulfill(json={**session(authenticated=True,user={"login":"rainbow"}),"public_mode":True,"usage":quota(scope='account',total=3,used=1,remaining=2,available=1,site_remaining=1)}))
    page.get_by_role('button',name='刷新模型任务额度').click()
    expect(page.locator('.account-usage-balance')).to_have_text('还可提交 1 次')
    expect(page.locator('.account-usage-detail')).to_contain_text('受全站剩余 1 次限制')
    page.route('**/api/auth/session',lambda route:route.fulfill(status=503,json={"detail":"暂时不可用"}))
    page.get_by_role('button',name='刷新模型任务额度').click()
    expect(page.locator('.account-usage-balance')).to_have_text('额度暂不可用，请刷新')
    expect(page.locator('.account-usage-meter')).to_be_hidden()


def test_invalid_usage_never_fabricates_allowance(account_page):
    page=account_page
    mount(page,{**session(),"usage":quota(available='Infinity')})
    page.locator('.account-trigger').click()
    expect(page.locator('.account-usage')).to_be_hidden()
