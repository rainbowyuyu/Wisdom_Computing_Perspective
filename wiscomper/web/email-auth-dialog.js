const MODES = new Set(['login', 'register', 'reset', 'verify']);
const safeText = (value, fallback = '') => typeof value === 'string' && value.trim() ? value.trim().slice(0, 240) : fallback;
function node(tag, className = '', text = '') { const value = document.createElement(tag); value.className = className; value.textContent = text; return value; }
function button(className, label) { const value = node('button', className, label); value.type = 'button'; return value; }

/** Credentials stay in this form and are cleared on close/mode changes. */
export function mountEmailAuthDialog({ api, getSession, onSubmit, onGitHub, notify = () => {}, onClose = () => {} }) {
  const dialog = node('dialog', 'email-auth-dialog');
  const uid = `email-auth-${globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  dialog.setAttribute('aria-labelledby', `${uid}-title`); dialog.setAttribute('aria-describedby', `${uid}-intro`);
  const header = node('header', 'email-auth-header'), brand = node('div', 'email-auth-brand');
  brand.append(node('span', 'email-auth-mark', '◈'), node('span', '', '智算视界'));
  const close = button('email-auth-close', '×'); close.setAttribute('aria-label', '关闭登录窗口'); header.append(brand, close);
  const tabs = node('div', 'email-auth-tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', '登录或注册');
  const loginTab = button('email-auth-tab', '登录'), registerTab = button('email-auth-tab', '注册');
  for (const tab of [loginTab, registerTab]) tab.setAttribute('role', 'tab'); tabs.append(loginTab, registerTab);
  const body = node('div', 'email-auth-body');
  const title = node('h2', 'email-auth-title'); title.id = `${uid}-title`;
  const intro = node('p', 'email-auth-intro'); intro.id = `${uid}-intro`;
  const form = node('form', 'email-auth-form'); form.noValidate = false;
  const fields = {};
  function field(key, label, type, autocomplete, maxLength) {
    const wrap = node('label', `email-auth-field email-auth-${key}`); const caption = node('span', '', label);
    const input = node('input'); input.id = `${uid}-${key}`; input.name = key; input.type = type; input.autocomplete = autocomplete; input.maxLength = maxLength;
    caption.id = `${uid}-${key}-label`; input.setAttribute('aria-labelledby', caption.id);
    input.required = true; wrap.append(caption, input); fields[key] = { wrap, input, caption }; return wrap;
  }
  form.append(field('identifier', '邮箱或用户名', 'text', 'username', 255));
  form.append(field('username', '用户名', 'text', 'username', 64));
  form.append(field('email', '邮箱', 'email', 'email', 254));
  const codeWrap = field('code', '邮箱验证码', 'text', 'one-time-code', 6);
  fields.code.input.inputMode = 'numeric'; fields.code.input.pattern = '[0-9]{6}'; fields.code.input.placeholder = '6 位验证码';
  const codeRow = node('div', 'email-auth-code-row'); codeRow.append(fields.code.input);
  const sendCode = button('email-auth-send-code', '获取验证码'); codeRow.append(sendCode); codeWrap.append(codeRow); form.append(codeWrap);
  form.append(field('password', '密码', 'password', 'current-password', 72));
  form.append(field('confirm', '确认密码', 'password', 'new-password', 72));
  const passwordNote = node('p', 'email-auth-password-note', '至少 6 位，建议组合字母、数字和符号。');
  const message = node('p', 'email-auth-message'); message.hidden = true; message.setAttribute('role', 'status'); message.setAttribute('aria-live', 'polite');
  const submit = node('button', 'email-auth-submit'); submit.type = 'submit';
  form.append(passwordNote, message, submit);
  const links = node('div', 'email-auth-links');
  const forgot = button('email-auth-link', '忘记密码？'), back = button('email-auth-link', '返回登录'); links.append(forgot, back);
  const alternative = node('div', 'email-auth-alternative');
  const divider = node('div', 'email-auth-divider', '或');
  const github = button('email-auth-github', '使用 GitHub 继续'); alternative.append(divider, github);
  const availability = node('p', 'email-auth-availability'); availability.hidden = true;
  const ownership = node('p', 'email-auth-footnote', '登录后，当前浏览器中的作品将归入此账号。');
  body.append(title, intro, form, links, alternative, availability, ownership); dialog.append(header, tabs, body); document.body.append(dialog);
  let mode = 'login', pending = '', disposed = false, originFocus = null, timer = null, epoch = 0;
  const deadlines = new Map(), removers = [];
  const listen = (target, event, handler) => { target.addEventListener(event, handler); removers.push(() => target.removeEventListener(event, handler)); };
  const clearSecrets = () => { for (const key of ['password', 'confirm', 'code']) fields[key].input.value = ''; };
  const emailKey = () => `${mode}:${fields.email.input.value.trim().toLowerCase()}`;
  function tell(text, error = false) { message.textContent = text; message.hidden = !text; message.classList.toggle('error', error); message.setAttribute('role', error ? 'alert' : 'status'); }
  function cooldown() { return Math.max(0, Math.ceil(((deadlines.get(emailKey()) || 0) - Date.now()) / 1000)); }
  function update() {
    const session = getSession?.(), email = session?.email;
    const mailReady = email?.configured === true;
    const loginReady = email?.login_available === true || mailReady;
    const seconds = cooldown();
    for (const { input, wrap } of Object.values(fields)) input.disabled = Boolean(pending) || wrap.hidden;
    for (const control of [close, loginTab, registerTab, forgot, back]) control.disabled = Boolean(pending);
    submit.disabled = Boolean(pending) || (mode === 'login' ? !loginReady : !mailReady);
    sendCode.disabled = Boolean(pending) || !mailReady || seconds > 0;
    sendCode.textContent = pending === 'code' ? '发送中…' : seconds ? `${seconds} 秒后重发` : '获取验证码';
    submit.textContent = pending === 'submit' ? (mode === 'verify' ? '正在验证…' : mode === 'reset' ? '正在重设…' : '正在保存并登录…') : { login: '登录', register: '注册并登录', reset: '重设密码', verify: '验证邮箱' }[mode];
    github.disabled = Boolean(pending) || session?.github?.configured !== true;
    alternative.hidden = mode === 'verify';
    availability.hidden = mode === 'login' ? loginReady : mailReady;
    availability.textContent = safeText(email?.message, '邮箱服务暂不可用，请稍后再试。');
    dialog.setAttribute('aria-busy', String(Boolean(pending)));
  }
  function show(next, { prefill = '', status = '' } = {}) {
    if (!MODES.has(next) || disposed || pending) return;
    mode = next; epoch++; clearSecrets(); tell(status);
    const verify = mode === 'verify', login = mode === 'login';
    tabs.hidden = verify || mode === 'reset';
    loginTab.setAttribute('aria-selected', String(login)); registerTab.setAttribute('aria-selected', String(mode === 'register'));
    loginTab.tabIndex = login ? 0 : -1; registerTab.tabIndex = mode === 'register' ? 0 : -1;
    const wanted = login ? ['identifier', 'password'] : mode === 'register' ? ['username', 'email', 'code', 'password', 'confirm'] : mode === 'reset' ? ['email', 'code', 'password', 'confirm'] : ['email', 'code'];
    for (const [key, field] of Object.entries(fields)) field.wrap.hidden = !wanted.includes(key);
    fields.password.input.autocomplete = login ? 'current-password' : 'new-password';
    fields.password.input.minLength = login ? 1 : 6;
    fields.password.caption.textContent = mode === 'reset' ? '新密码' : mode === 'register' ? '设置密码' : '密码';
    fields.confirm.input.minLength = 6;
    passwordNote.hidden = login || verify;
    const accountEmail = getSession?.()?.user?.email;
    const boundEmail = typeof accountEmail === 'string' ? accountEmail.trim().slice(0, 254) : '';
    if (verify) fields.email.input.value = boundEmail.includes('*') ? '' : boundEmail;
    if (prefill) (login ? fields.identifier : fields.email).input.value = prefill;
    title.textContent = { login: '欢迎回来', register: '开启你的探索', reset: '找回密码', verify: boundEmail ? '验证你的邮箱' : '绑定常用邮箱' }[mode];
    intro.textContent = { login: '登录后，继续你的作品与学习记录。', register: '保存作品，把每一次发现留在自己的空间。', reset: '用邮箱验证码设置新密码，完成后重新登录。', verify: '原有作品和学习资料会保留。验证邮箱后，即可继续使用账号功能。' }[mode];
    forgot.hidden = !login; back.hidden = mode !== 'reset'; ownership.hidden = verify || mode === 'reset';
    dialog.dataset.mode = mode; update();
    if (dialog.open) fields[wanted[0]].input.focus({ preventScroll: true });
  }
  async function send() {
    if (disposed || pending || mode === 'login' || sendCode.disabled) return;
    const email = fields.email.input;
    if (!email.reportValidity()) return;
    const purpose = mode, key = emailKey(), value = email.value.trim(), token = epoch;
    pending = 'code'; tell(''); update();
    try {
      const data = await api('/api/auth/email/send-code', { method: 'POST', body: { email: value, purpose } });
      if (disposed || epoch !== token) return;
      const wait = Number.isFinite(data?.retry_after) ? Math.max(1, Math.min(3600, data.retry_after)) : 60;
      deadlines.set(key, Date.now() + wait * 1000);
      tell(safeText(data?.message, purpose === 'reset' ? '如果该邮箱可用于找回密码，你会收到验证码。请查看收件箱和垃圾邮件。' : '验证码已发送，请查看收件箱和垃圾邮件。'));
    } catch (error) { if (!disposed && token === epoch) tell(safeText(error?.message, '验证码未发送，请稍后重试。'), true); }
    finally { if (!disposed && token === epoch) { pending = ''; update(); if (!sendCode.disabled) sendCode.focus(); } }
  }
  async function submitForm(event) {
    event.preventDefault(); if (disposed || pending || submit.disabled || !form.reportValidity()) return;
    if ((mode === 'register' || mode === 'reset') && fields.password.input.value !== fields.confirm.input.value) { tell('两次密码不一致，请检查后重试。', true); fields.confirm.input.focus(); return; }
    if (mode !== 'verify' && new TextEncoder().encode(fields.password.input.value).length > 72) { tell('密码过长，请使用不超过 72 字节的密码。', true); fields.password.input.focus(); return; }
    const email = fields.email.input.value.trim(), password = fields.password.input.value;
    const payload = mode === 'login' ? { identifier: fields.identifier.input.value.trim(), password }
      : mode === 'register' ? { username: fields.username.input.value.trim(), email, password, code: fields.code.input.value.trim() }
      : mode === 'reset' ? { email, new_password: password, code: fields.code.input.value.trim() }
      : { email, code: fields.code.input.value.trim() };
    const submittedMode = mode, token = epoch; pending = 'submit'; tell(''); update();
    try {
      const result = await onSubmit(submittedMode, payload);
      if (disposed || token !== epoch) return;
      pending = '';
      if (result === false) { tell('操作尚未完成，请重试。', true); return; }
      clearSecrets();
      if (submittedMode === 'reset') show('login', { prefill: email, status: '密码已重设，请使用新密码登录。' });
      else if (submittedMode !== 'verify' && result?.user?.email_verified === false) show('verify');
      else closeDialog();
    } catch (error) { if (!disposed && token === epoch) tell(safeText(error?.message, '操作未完成，请重试。'), true); }
    finally { if (!disposed && token === epoch) { pending = ''; update(); } }
  }
  function closeDialog() { if (pending || disposed) return false; epoch++; clearSecrets(); dialog.close(); return true; }
  listen(close, 'click', closeDialog); listen(loginTab, 'click', () => show('login')); listen(registerTab, 'click', () => show('register'));
  listen(forgot, 'click', () => show('reset', { prefill: fields.identifier.input.value.includes('@') ? fields.identifier.input.value.trim() : '' }));
  listen(back, 'click', () => show('login')); listen(sendCode, 'click', send); listen(form, 'submit', submitForm);
  listen(fields.email.input, 'input', update);
  listen(dialog, 'cancel', event => { event.preventDefault(); closeDialog(); });
  listen(dialog, 'close', () => { if (dialog.open) return; clearSecrets(); clearInterval(timer); timer = null; originFocus?.isConnected && originFocus.focus?.({ preventScroll: true }); onClose(); });
  listen(dialog, 'keydown', event => { event.stopPropagation(); if (event.target.getAttribute('role') === 'tab' && ['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); if (!pending) { show(mode === 'login' ? 'register' : 'login'); (mode === 'login' ? loginTab : registerTab).focus(); } } });
  listen(github, 'click', async () => { if (pending || github.disabled) return; closeDialog(); try { await onGitHub?.(); } catch (error) { notify(safeText(error?.message, 'GitHub 登录未完成。'), true); } });
  return {
    open(next = 'login') {
      if (disposed || pending) return false;
      if (!dialog.open && document.querySelector('dialog[open]')) { notify('请先关闭当前窗口，再打开账号登录。'); return false; }
      if (next === 'verify' && !getSession?.()?.authenticated) next = 'login';
      if (!dialog.open) { originFocus = document.activeElement; dialog.showModal(); }
      show(next); clearInterval(timer); timer = setInterval(update, 1000); return true;
    },
    get opened() { return dialog.open; },
    close: closeDialog,
    dispose() { if (disposed) return; disposed = true; epoch++; clearSecrets(); clearInterval(timer); removers.forEach(remove => remove()); if (dialog.open) dialog.close(); dialog.remove(); deadlines.clear(); },
  };
}
