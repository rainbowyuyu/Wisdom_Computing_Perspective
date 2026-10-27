import { mountEmailAuthDialog } from './email-auth-dialog.js';

const START_URL = '/api/auth/github/start';
const AUTH_ERRORS = {
  not_configured: 'GitHub 登录尚未配置。',
  busy: '请先等待当前任务完成或取消任务，再登录。',
  state: '登录验证已过期或不属于当前浏览器，请重新登录。',
  denied: '已取消 GitHub 授权。',
  upstream: 'GitHub 登录暂时不可用，请稍后重试。',
  session: '页面会话已失效，请刷新后重新登录。',
  already_signed_in: '请先退出当前账号，再切换 GitHub 账号。',
};
const text = (value, fallback = '', limit = 180) => typeof value === 'string' && value.trim() ? value.trim().slice(0, limit) : fallback;

function node(tag, className, content = '') {
  const element = document.createElement(tag); element.className = className;
  if (content) element.textContent = content;
  return element;
}

function icon(kind = 'github') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  if (kind === 'github') {
    path.setAttribute('d', 'M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.86c-2.78.61-3.37-1.18-3.37-1.18-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.99 1.03-2.69-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.03a9.56 9.56 0 0 1 5 0c1.91-1.3 2.75-1.03 2.75-1.03.55 1.38.2 2.4.1 2.65.64.7 1.03 1.6 1.03 2.69 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85v2.76c0 .27.18.58.69.48A10 10 0 0 0 12 2Z');
    svg.setAttribute('fill', 'currentColor');
  } else {
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '1.7');
    svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
    path.setAttribute('d', kind === 'close' ? 'm6 6 12 12M18 6 6 18' : kind === 'user' ? 'M20 21v-2a6 6 0 0 0-6-6h-4a6 6 0 0 0-6 6v2M16 5a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z' : 'm7 10 5 5 5-5');
  }
  svg.append(path); return svg;
}

function button(className, label) {
  const element = node('button', className, label); element.type = 'button'; return element;
}

function checkSession(data) {
  if (!data || typeof data.authenticated !== 'boolean' || typeof data.github?.configured !== 'boolean' || !text(data.csrf) ||
      (data.authenticated && !text(data.user?.login))) throw new Error('无法读取账号状态，请重试。');
  return data;
}

function checkUsage(value) {
  if (!value || !['site', 'account'].includes(value.scope) || value.unit !== 'model_tasks') return null;
  if (value.unlimited === true) return ['used', 'available', 'site_remaining'].every(key => Number.isSafeInteger(value[key]) && value[key] >= 0) && value.available <= value.site_remaining ? value : null;
  if (!['total', 'used', 'remaining', 'available', 'site_remaining'].every(key => Number.isSafeInteger(value[key]) && value[key] >= 0)) return null;
  if (value.available > value.remaining || value.available > value.site_remaining) return null;
  return value;
}

/**
 * The injected api owns CSRF and same-origin credentials. Session callbacks receive
 * the server response plus {reason:'initial'|'refresh'|'login'|'register'|'verify'|'logout'}.
 * Return {navigating:true} to keep editing suspended until the host navigates.
 * beforeNavigate({reason:'login'|'logout'|'verify'|'reset'}) saves edits and drafts;
 * returning false or throwing prevents the transition. No external avatar is loaded.
 * onBusyChange('login'|'logout'|null) lets the caller suspend workspace editing.
 */
export function mountAccountMenu({ api, onSessionChange = () => {}, beforeNavigate = () => {}, onSessionEnding = () => {}, onBusyChange = () => {}, notify = () => {} } = {}) {
  const host = document.querySelector('#account-menu');
  if (!host) throw new Error('账号入口需要 #account-menu 挂载节点。');
  if (typeof api !== 'function') throw new Error('账号入口需要 api 请求函数。');
  let callbackMessage = '';
  try {
    const url = new URL(window.location.href), code = url.searchParams.get('auth_error');
    if (code !== null) {
      callbackMessage = Object.hasOwn(AUTH_ERRORS, code) ? AUTH_ERRORS[code] : 'GitHub 登录未完成，请重试。';
      url.searchParams.delete('auth_error'); history.replaceState(history.state, '', url);
    }
  } catch { /* A restricted history API does not prevent using the account menu. */ }
  const root = node('div', 'account-root');
  const trigger = button('account-trigger', '');
  trigger.setAttribute('aria-haspopup', 'dialog'); trigger.setAttribute('aria-expanded', 'false');
  const triggerIcon = node('span', 'account-trigger-icon'); triggerIcon.append(icon('user'));
  const initials = node('span', 'account-initials'); initials.hidden = true; initials.setAttribute('aria-hidden', 'true');
  const triggerCopy = node('span', 'account-trigger-copy');
  const triggerFull = node('span', 'account-trigger-full', '登录 / 注册');
  const triggerCompact = node('span', 'account-trigger-compact', '登录'); triggerCopy.append(triggerFull, triggerCompact);
  const chevron = icon('chevron'); chevron.classList.add('account-chevron');
  trigger.append(triggerIcon, initials, triggerCopy, chevron); root.append(trigger); host.append(root);

  // The header uses backdrop-filter, so the popover is portalled to the body.
  const panel = node('section', 'account-panel'); panel.hidden = true;
  const uid = `account-${globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  panel.id = `${uid}-panel`; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'false');
  panel.setAttribute('aria-labelledby', `${uid}-title`); trigger.setAttribute('aria-controls', panel.id);
  const header = node('div', 'account-panel-header');
  const title = node('h2', 'account-title', '登录智算视界'); title.id = `${uid}-title`;
  const closeButton = button('account-close', ''); closeButton.append(icon('close')); closeButton.setAttribute('aria-label', '关闭账号菜单');
  header.append(title, closeButton);
  const body = node('div', 'account-panel-body');
  const loading = node('p', 'account-loading', '正在读取账号状态…'); loading.setAttribute('role', 'status');
  const guidance = node('p', 'account-guidance'); guidance.hidden = true;
  const guest = node('div', 'account-guest');
  const guestIntro = node('p', 'account-description', '登录账号，继续你的作品与学习记录。');
  const ownership = node('p', 'account-ownership', '登录后，当前浏览器中的作品会归入此账号。');
  const availability = node('p', 'account-availability'); availability.hidden = true;
  const setupHelp = node('details', 'account-setup'); setupHelp.hidden = true;
  const setupTitle = node('summary', 'account-setup-title', '本机 GitHub 配置说明');
  const setupCopy = node('p', '', '在项目文件夹双击「配置GitHub登录.cmd」，按提示在终端填写凭据。已有 Client ID 可回车保留，完成后重启工作台。');
  const setupLink = node('a', 'account-help-link', '查看 GitHub 配置步骤 ↗');
  setupLink.href = '/web/github-setup.html'; setupLink.target = '_blank'; setupLink.rel = 'noopener noreferrer';
  setupHelp.append(setupTitle, setupCopy, setupLink);
  const loginButton = button('account-primary', ''); loginButton.append(icon(), node('span', 'account-login-label', '继续使用 GitHub'));
  const emailButton = button('account-email-login', '邮箱 / 用户名登录');
  const registerButton = button('account-register', '还没有账号？注册');
  guest.append(guestIntro, emailButton, loginButton, registerButton, ownership, availability, setupHelp);
  const member = node('div', 'account-member'); member.hidden = true;
  const profile = node('div', 'account-profile');
  const profileInitial = node('span', 'account-profile-initial'); profileInitial.setAttribute('aria-hidden', 'true');
  const profileInfo = node('div', 'account-profile-info');
  const displayName = node('p', 'account-display-name');
  const loginName = node('p', 'account-login-name');
  profileInfo.append(displayName, loginName); profile.append(profileInitial, profileInfo);
  const signedIn = node('p', 'account-signed-in');
  const role = node('span', 'account-role');
  const emailRow = node('div', 'account-email-row');
  const emailAddress = node('span', 'account-email-address');
  const verifyButton = button('account-verify', '验证邮箱'); emailRow.append(emailAddress, verifyButton);
  const modelAccess = node('p', 'account-model-access'); modelAccess.hidden = true;
  const logoutNote = node('p', 'account-description', '退出后，此浏览器将回到访客空间。账号中的作品会保留。');
  const logoutButton = button('account-logout', '退出登录'); profileInfo.append(role); member.append(profile, signedIn, emailRow, modelAccess, logoutNote, logoutButton);
  const error = node('p', 'account-error'); error.hidden = true; error.setAttribute('role', 'alert');
  const retryButton = button('account-retry', '重新读取账号状态'); retryButton.hidden = true;
  const pendingMessage = node('p', 'account-pending'); pendingMessage.hidden = true; pendingMessage.setAttribute('role', 'status');
  const usage = node('section', 'account-usage'); usage.hidden = true; usage.setAttribute('aria-label', '模型任务额度');
  const usageHeader = node('div', 'account-usage-header');
  const usageTitle = node('h3', 'account-usage-title');
  const usageRefresh = button('account-usage-refresh', '刷新'); usageRefresh.setAttribute('aria-label', '刷新模型任务额度');
  usageHeader.append(usageTitle, usageRefresh);
  const usageBalance = node('p', 'account-usage-balance'); usageBalance.setAttribute('aria-live', 'polite');
  const usageMeter = node('div', 'account-usage-meter'); usageMeter.setAttribute('role', 'progressbar'); usageMeter.setAttribute('aria-label', '已使用模型任务');
  const usageFill = node('span', 'account-usage-fill'); usageMeter.append(usageFill);
  const usageDetail = node('p', 'account-usage-detail');
  const usageNote = node('p', 'account-usage-note', '示例与参数调整免费。模型任务提交后计入额度，失败也计入。');
  usage.append(usageHeader, usageBalance, usageMeter, usageDetail, usageNote);
  body.append(loading, guidance, guest, member, usage, error, retryButton, pendingMessage); panel.append(header, body); document.body.append(panel);

  let disposed = false, opened = false, session = null, busy = '', reading = false, readFailed = false, busyReason = null;
  let reasonText = '', request = 0, frame = 0, controller = null;
  const removeListeners = [];
  const emailDialog = mountEmailAuthDialog({ api, getSession: () => session, onSubmit: submitEmail, onGitHub: login, notify, onClose: () => trigger.focus({ preventScroll: true }) });
  function listen(target, event, callback, options) {
    target.addEventListener(event, callback, options); removeListeners.push(() => target.removeEventListener(event, callback, options));
  }
  function viewport() {
    const view = window.visualViewport;
    return { left: view?.offsetLeft || 0, top: view?.offsetTop || 0, width: view?.width || window.innerWidth, height: view?.height || window.innerHeight };
  }
  function layout() {
    frame = 0; if (disposed || !opened) return;
    const view = viewport(), bounds = trigger.getBoundingClientRect();
    panel.style.width = `${Math.min(328, Math.max(0, view.width - 24))}px`;
    panel.style.maxHeight = `${Math.max(0, view.height - 24)}px`;
    const left = Math.max(view.left + 12, Math.min(bounds.right - panel.offsetWidth, view.left + view.width - panel.offsetWidth - 12));
    const below = bounds.bottom + 10;
    const top = Math.max(view.top + 12, Math.min(below, view.top + view.height - panel.offsetHeight - 12));
    panel.style.left = `${left}px`; panel.style.top = `${top}px`;
  }
  function scheduleLayout() { if (!disposed && !frame) frame = requestAnimationFrame(layout); }
  function setOpen(next, restoreFocus = true, refreshSession = true) {
    if (disposed) return;
    const justOpened = next && !opened;
    opened = next; panel.hidden = !next; trigger.setAttribute('aria-expanded', String(next));
    if (next) { render(); layout(); closeButton.focus({ preventScroll: true }); }
    else if (restoreFocus) trigger.focus({ preventScroll: true });
    if (justOpened && refreshSession && !busy && !reading) refresh('refresh', { preserveError: true });
  }
  function render() {
    if (disposed) return;
    const focusedAction = [loginButton, logoutButton, retryButton, emailButton, registerButton, verifyButton].includes(document.activeElement) ? document.activeElement : null;
    const authenticated = session?.authenticated === true;
    const available = session?.github?.configured === true;
    const name = text(session?.user?.name, text(session?.user?.login, '我的账号'), 80);
    const initial = Array.from(name)[0]?.toLocaleUpperCase() || 'G';
    root.dataset.authenticated = String(authenticated); root.dataset.pending = String(Boolean(busy || reading));
    triggerIcon.hidden = authenticated; initials.hidden = !authenticated;
    initials.textContent = initial; profileInitial.textContent = initial;
    triggerFull.textContent = authenticated ? name : readFailed ? '账号' : '登录 / 注册';
    triggerCompact.textContent = authenticated ? '' : readFailed ? '账号' : '登录';
    trigger.setAttribute('aria-label', authenticated ? `账号：${name}` : readFailed ? '查看账号状态' : '登录或注册智算视界');
    trigger.title = authenticated ? `账号：${text(session.user.login)}` : readFailed ? '账号状态暂不可用' : '邮箱或 GitHub 登录';
    title.textContent = authenticated ? '我的账号' : '登录智算视界';
    loading.hidden = !reading; guest.hidden = authenticated || !session; member.hidden = !authenticated;
    guidance.hidden = !reasonText || authenticated; guidance.textContent = reasonText;
    availability.hidden = available; availability.textContent = text(session?.github?.message, 'GitHub 登录尚未配置。');
    setupHelp.hidden = available || session?.public_mode !== false;
    if (!available && session?.public_mode === true) availability.textContent += ' 请联系站点维护者完成设置。';
    const quota = checkUsage(session?.usage);
    usage.hidden = !quota;
    if (quota) {
      usageTitle.textContent = quota.scope === 'account' ? '今日账号模型任务' : '今日本机模型任务';
      usageRefresh.disabled = Boolean(busy || reading);
      usageBalance.textContent = readFailed ? '额度暂不可用，请刷新' : quota.requires_login ? '登录后可使用模型任务' : quota.unlimited ? '账号不限次数' : `还可提交 ${quota.available} 次`;
      usageMeter.hidden = readFailed || quota.unlimited === true;
      usageMeter.setAttribute('aria-valuemin', '0'); usageMeter.setAttribute('aria-valuemax', String(Math.max(1, quota.total)));
      usageMeter.setAttribute('aria-valuenow', String(Math.min(quota.used, quota.total)));
      usageMeter.setAttribute('aria-valuetext', `今日已用 ${quota.used} 次，共 ${quota.total} 次`);
      usageFill.style.width = `${quota.total ? Math.min(100, quota.used / quota.total * 100) : 0}%`;
      const reset = new Date(quota.reset_at);
      const resetText = Number.isFinite(reset.getTime()) ? ` · ${reset.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })} 重置` : '';
      const siteLimit = quota.scope === 'account' && quota.site_remaining < quota.remaining ? ` · 受全站剩余 ${quota.site_remaining} 次限制` : '';
      usageDetail.textContent = readFailed ? '重新读取后显示最新额度。' : quota.unlimited ? `今日已用 ${quota.used} 次 · 全站当前可提交 ${quota.available} 次${resetText}` : `已用 ${quota.used} / ${quota.total} 次${siteLimit}${resetText}`;
    }
    loginButton.disabled = !available || Boolean(busy || reading || readFailed);
    emailButton.hidden = !session?.email; registerButton.hidden = !session?.email;
    emailButton.disabled = !(session?.email?.login_available || session?.email?.configured) || Boolean(busy || reading || readFailed);
    registerButton.disabled = !session?.email?.configured || Boolean(busy || reading || readFailed);
    role.textContent = { vip: 'VIP', admin: '管理员', owner: '站点所有者', member: '普通账号', user: '普通账号' }[session?.user?.role] || '普通账号';
    role.dataset.role = ['vip', 'admin', 'owner'].includes(session?.user?.role) ? session.user.role : 'member';
    signedIn.textContent = session?.user?.email_verified === true ? '邮箱已验证' : session?.user?.email_verified === false ? '验证邮箱后可继续使用账号功能' : '已登录智算视界';
    emailRow.hidden = !session?.email;
    emailAddress.textContent = text(session?.user?.email, '尚未绑定邮箱');
    verifyButton.hidden = session?.user?.email_verified !== false;
    verifyButton.textContent = session?.user?.email ? '验证邮箱' : '绑定邮箱';
    verifyButton.disabled = Boolean(busy || reading || readFailed);
    const allowed = session?.model_access?.allowed;
    modelAccess.hidden = !Array.isArray(allowed);
    if (Array.isArray(allowed)) modelAccess.textContent = allowed.length ? `可用模型：${allowed.map(id => ({ qwen: 'Qwen', chatgpt: 'ChatGPT', claude: 'Claude' })[id]).filter(Boolean).join(' · ')}` : text(session?.model_access?.message, '暂无可用创作模型。');
    logoutButton.disabled = Boolean(busy || reading || readFailed);
    retryButton.disabled = Boolean(busy || reading); retryButton.hidden = !readFailed;
    displayName.textContent = name; loginName.textContent = `@${text(session?.user?.login)}`;
    loginName.hidden = !session?.user?.name;
    pendingMessage.hidden = !busy;
    pendingMessage.textContent = busy === 'redirecting' ? '正在前往 GitHub…' : busy === 'logout' ? '正在保存并退出…' : busy === 'login' ? '正在保存当前内容…' : '';
    loginButton.querySelector('.account-login-label').textContent = busy === 'login' ? '正在保存…' : busy === 'redirecting' ? '正在前往 GitHub…' : '继续使用 GitHub';
    logoutButton.textContent = busy === 'logout' ? '正在退出…' : '退出登录';
    if (opened && focusedAction?.disabled) closeButton.focus({ preventScroll: true });
    scheduleLayout();
  }
  function showError(cause, report = false) {
    error.textContent = text(cause?.message, '操作未完成，请稍后重试。', 260); error.hidden = false;
    if (report) notify(error.textContent, true);
    scheduleLayout();
  }
  function setBusy(next) {
    busy = next;
    const reason = next === 'redirecting' ? 'login' : next || null;
    if (reason === busyReason) return;
    busyReason = reason;
    try { onBusyChange(reason); } catch { /* Host UI failures must not interrupt the account transition. */ }
  }
  async function refresh(reason = 'refresh', { preserveError = false } = {}) {
    if (disposed || busy) return session;
    const sequence = ++request; controller?.abort(); controller = new AbortController();
    reading = true; if (!preserveError) error.hidden = true; render();
    try {
      const data = checkSession(await api('/api/auth/session', { signal: controller.signal }));
      if (disposed || sequence !== request) return null;
      session = data; readFailed = false;
      await onSessionChange(data, { reason });
      return data;
    } catch (cause) {
      if (disposed || sequence !== request || cause?.name === 'AbortError') return null;
      readFailed = true; showError(cause); return null;
    } finally {
      if (!disposed && sequence === request) { reading = false; render(); }
    }
  }
  async function login() {
    if (disposed || busy || reading || !session?.github?.configured || session.authenticated || readFailed) return;
    setBusy('login'); error.hidden = true; render();
    try {
      if (await beforeNavigate({ reason: 'login' }) === false) throw new Error('请先保存当前修改，再继续登录。');
      if (disposed) return;
      await onSessionEnding({ reason: 'login', provider: 'github' });
      if (disposed) return;
      setBusy('redirecting'); render(); window.location.assign(START_URL);
    } catch (cause) {
      if (!disposed) { setBusy(''); render(); showError(cause, true); }
    }
  }
  async function logout() {
    if (disposed || busy || reading || !session?.authenticated || readFailed) return;
    setBusy('logout'); error.hidden = true; render(); let navigating = false;
    try {
      if (await beforeNavigate({ reason: 'logout' }) === false) throw new Error('请先保存当前修改，再退出登录。');
      if (disposed) return;
      await onSessionEnding({ reason: 'logout' });
      if (disposed) return;
      const data = checkSession(await api('/api/auth/logout', { method: 'POST', body: {} }));
      if (disposed) return;
      if (data.authenticated) throw new Error('退出登录尚未完成，请重试。');
      session = data; readFailed = false; reasonText = ''; setOpen(false);
      navigating = (await onSessionChange(data, { reason: 'logout' }))?.navigating === true;
    } catch (cause) {
      if (!disposed) { setOpen(true); showError(cause, true); }
    } finally { if (!disposed) { if (!navigating) setBusy(''); render(); } }
  }
  async function submitEmail(mode, payload) {
    if (disposed || busy) throw new Error('账号操作正在进行，请稍候。');
    const reason = mode === 'register' || mode === 'login' ? 'login' : mode;
    controller?.abort(); request++; reading = false;
    setBusy(reason); render(); let navigating = false;
    try {
      if (await beforeNavigate({ reason, provider: 'email' }) === false) throw new Error('请先保存当前修改，再继续账号操作。');
      if (disposed) return false;
      if (reason === 'login') await onSessionEnding({ reason, provider: 'email' });
      if (disposed) return false;
      const data = await api(`/api/auth/email/${mode}`, { method: 'POST', body: payload });
      if (disposed) return false;
      if (mode === 'reset') return data;
      const next = checkSession(data);
      if (!next.authenticated) throw new Error('登录状态尚未更新，请重试。');
      session = next; readFailed = false; reasonText = '';
      navigating = (await onSessionChange(next, { reason: mode }))?.navigating === true;
      return next;
    } finally { if (!disposed) { if (!navigating) setBusy(''); render(); } }
  }
  function openEmail(mode = 'login') {
    if (disposed || busy || reading || readFailed || !session) return false;
    setOpen(false, true, false); return emailDialog.open(mode);
  }
  listen(trigger, 'click', () => setOpen(!opened));
  listen(closeButton, 'click', () => setOpen(false));
  listen(loginButton, 'click', login); listen(logoutButton, 'click', logout);
  listen(emailButton, 'click', () => openEmail('login')); listen(registerButton, 'click', () => openEmail('register')); listen(verifyButton, 'click', () => openEmail('verify'));
  listen(retryButton, 'click', () => refresh());
  listen(usageRefresh, 'click', () => refresh());
  listen(document, 'pointerdown', (event) => { if (opened && !root.contains(event.target) && !panel.contains(event.target)) setOpen(false, false); });
  listen(document, 'keydown', (event) => { if (opened && event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); setOpen(false); } });
  listen(document, 'focusin', (event) => { if (opened && !root.contains(event.target) && !panel.contains(event.target)) setOpen(false, false); });
  listen(window, 'resize', scheduleLayout); listen(window, 'scroll', scheduleLayout, { passive: true });
  if (window.visualViewport) { listen(window.visualViewport, 'resize', scheduleLayout); listen(window.visualViewport, 'scroll', scheduleLayout); }
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(scheduleLayout) : null; observer?.observe(panel);
  const ready = refresh('initial').then(data => {
    if (callbackMessage && !disposed) { showError(new Error(callbackMessage), true); setOpen(true, true, false); }
    return data;
  });
  return {
    ready,
    get session() { return session; },
    refresh: () => refresh(),
    open(reason = '') { reasonText = text(reason); setOpen(true); },
    openEmail,
    close: () => setOpen(false),
    dispose() {
      if (disposed) return;
      const restore = panel.contains(document.activeElement);
      disposed = true; emailDialog.dispose(); setBusy(''); request++; controller?.abort(); observer?.disconnect();
      removeListeners.forEach(remove => remove()); if (frame) cancelAnimationFrame(frame);
      if (restore) host.focus?.({ preventScroll: true }); root.remove(); panel.remove();
    },
  };
}
