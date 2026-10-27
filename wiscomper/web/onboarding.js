const STEPS = [
  { target: ['#composer', '#creation-tab'], title: '写下你想看懂的内容', copy: '在创作面板输入一句描述、一个公式，或切换到图片输入。说明对象、运动和想观察的关系，生成后还可以继续修改。' },
  { target: ['#sample-filter', '#creation-tab'], title: '先试一个本地示例', copy: '从「灵感起点」选择示例，也可以按数学、科学或三维分类筛选。示例不调用模型，不消耗模型任务额度。' },
  { target: ['.timeline', '#scene-host'], title: '用时间轴看清变化', copy: '播放、暂停或拖动进度，停在你想观察的一刻。三维场景还可以调整观察视角；画布下方会显示当前操作提示。' },
  { target: ['#interaction-section', '#detail-tab'], title: '动手调整，观察结果', copy: '场景面板列出可操控构件、参数和解释步骤。改变参数或拖动构件后观察画面，工作台会保存你的调整。' },
  { target: ['.stage-actions', '#history-tab'], title: '保存每一步探索', copy: '左侧「项目」可以打开已有作品。「版本」用于回看与恢复，「导出」可保存场景文件或生成视频。按钮会在场景准备好后启用。' },
  { target: ['.ecosystem-nav', '#open-help'], title: '继续寻找关联', copy: '顶部公式库提供公式与可视化入口，知识图谱帮助整理概念之间的关系。需要时可从帮助菜单重新播放这份引导。' },
  { target: ['#account-menu'], title: '查看账号与创作额度', copy: '可用原来的邮箱或用户名登录，也支持 GitHub。账号菜单能查看身份、模型权限与今日额度；登录后，当前浏览器的作品会归入账号。' },
];

function element(tag, className, text = '') {
  const result = document.createElement(tag); result.className = className; result.textContent = text; return result;
}
function control(className, text) { const result = element('button', className, text); result.type = 'button'; return result; }
function visibleTarget(step) {
  for (const selector of step.target) {
    const target = document.querySelector(selector);
    if (!target || !target.getClientRects().length) continue;
    const style = getComputedStyle(target);
    if (style.visibility !== 'hidden' && style.display !== 'none') return target;
  }
  return null;
}

/**
 * Call start() from the help menu or once after the workspace has loaded.
 * onComplete({completed, skipped}) fires once after finish/skip/Escape. Persistence
 * belongs to the host. The guide never submits work or changes project/tab state.
 */
export function mountOnboarding({ onComplete = () => {}, notify = () => {} } = {}) {
  const dialog = element('dialog', 'onboarding-overlay');
  dialog.setAttribute('aria-modal', 'true');
  const uid = `tour-${globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  dialog.setAttribute('aria-labelledby', `${uid}-title`); dialog.setAttribute('aria-describedby', `${uid}-copy`);
  const ring = element('div', 'onboarding-highlight'); ring.setAttribute('aria-hidden', 'true');
  const card = element('section', 'onboarding-card');
  const head = element('div', 'onboarding-head');
  const eyebrow = element('span', 'onboarding-eyebrow', '认识智算视界');
  const skip = control('onboarding-skip', '跳过'); skip.setAttribute('aria-label', '跳过新手引导'); head.append(eyebrow, skip);
  const title = element('h2', 'onboarding-title'); title.id = `${uid}-title`;
  const copy = element('p', 'onboarding-copy'); copy.id = `${uid}-copy`;
  const missing = element('p', 'onboarding-missing', '此区域暂不可见，可以继续下一步。'); missing.hidden = true;
  const footer = element('div', 'onboarding-footer');
  const progress = element('span', 'onboarding-progress'); progress.setAttribute('role', 'status'); progress.setAttribute('aria-live', 'polite');
  const actions = element('div', 'onboarding-actions');
  const previous = control('onboarding-previous', '上一步');
  const next = control('onboarding-next', '下一步'); actions.append(previous, next); footer.append(progress, actions);
  const replay = control('onboarding-replay', '从头再看一遍'); replay.hidden = true;
  card.append(head, title, copy, missing, footer, replay); dialog.append(ring, card); document.body.append(dialog);
  let disposed = false, active = false, index = 0, steps = [], frame = 0, initialFocus = null;
  const scrollPositions = new Map(), listeners = [];
  function listen(target, event, handler, options) { target.addEventListener(event, handler, options); listeners.push(() => target.removeEventListener(event, handler, options)); }
  function viewport() { const view = window.visualViewport; return { x: view?.offsetLeft || 0, y: view?.offsetTop || 0, width: view?.width || innerWidth, height: view?.height || innerHeight }; }
  function rememberScroll(target) {
    for (let item = target; item; item = item.parentElement) {
      if (!scrollPositions.has(item)) scrollPositions.set(item, { top: item.scrollTop, left: item.scrollLeft });
    }
  }
  function layout() {
    frame = 0; if (disposed || !active) return;
    const view = viewport(), pad = 14, gap = 16;
    card.style.width = `${Math.max(0, Math.min(360, view.width - pad * 2))}px`;
    card.style.maxHeight = `${Math.max(0, view.height - pad * 2)}px`;
    const target = visibleTarget(steps[index]), bounds = target?.getBoundingClientRect();
    ring.hidden = !bounds; missing.hidden = Boolean(bounds);
    if (bounds) {
      const left = Math.max(view.x + 4, bounds.left - 5), top = Math.max(view.y + 4, bounds.top - 5);
      const right = Math.min(view.x + view.width - 4, bounds.right + 5), bottom = Math.min(view.y + view.height - 4, bounds.bottom + 5);
      ring.style.left = `${left}px`; ring.style.top = `${top}px`;
      ring.style.width = `${Math.max(0, right - left)}px`; ring.style.height = `${Math.max(0, bottom - top)}px`;
      ring.hidden = right <= left || bottom <= top;
    }
    dialog.classList.toggle('onboarding-no-target', ring.hidden);
    const width = card.offsetWidth, height = card.offsetHeight;
    let left = view.x + (view.width - width) / 2, top = view.y + (view.height - height) / 2;
    if (bounds) {
      const rightRoom = view.x + view.width - bounds.right, leftRoom = bounds.left - view.x;
      if (view.width > 680 && rightRoom >= width + gap + pad) { left = bounds.right + gap; top = bounds.top; }
      else if (view.width > 680 && leftRoom >= width + gap + pad) { left = bounds.left - width - gap; top = bounds.top; }
      else if (bounds.bottom + gap + height <= view.y + view.height - pad) { left = bounds.left; top = bounds.bottom + gap; }
      else if (bounds.top - gap - height >= view.y + pad) { left = bounds.left; top = bounds.top - height - gap; }
      else { left = view.x + (view.width - width) / 2; top = bounds.top + bounds.height / 2 > view.y + view.height / 2 ? view.y + pad : view.y + view.height - height - pad; }
    }
    card.style.left = `${Math.max(view.x + pad, Math.min(left, view.x + view.width - width - pad))}px`;
    card.style.top = `${Math.max(view.y + pad, Math.min(top, view.y + view.height - height - pad))}px`;
  }
  function schedule() { if (active && !disposed && !frame) frame = requestAnimationFrame(layout); }
  function showStep() {
    const step = steps[index]; title.textContent = step.title; copy.textContent = step.copy;
    progress.textContent = `${index + 1} / ${steps.length}`;
    previous.disabled = index === 0; next.textContent = index === steps.length - 1 ? '开始探索' : '下一步';
    replay.hidden = index !== steps.length - 1;
    dialog.dataset.step = String(index + 1);
    const target = visibleTarget(step);
    if (target) { rememberScroll(target); target.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' }); }
    layout(); next.focus({ preventScroll: true });
  }
  function finish(completed, report = true) {
    if (!active) return;
    active = false; if (frame) { cancelAnimationFrame(frame); frame = 0; }
    if (dialog.open) dialog.close();
    for (const [item, position] of scrollPositions) if (item.isConnected) item.scrollTo({ ...position, behavior: 'instant' });
    scrollPositions.clear();
    if (initialFocus?.isConnected && typeof initialFocus.focus === 'function') initialFocus.focus({ preventScroll: true });
    if (report) { try { onComplete({ completed, skipped: !completed }); } catch { notify('引导已关闭。'); } }
  }
  function advance(delta) { if (!active) return; index = Math.max(0, Math.min(steps.length - 1, index + delta)); showStep(); }
  listen(previous, 'click', () => advance(-1));
  listen(next, 'click', () => index === steps.length - 1 ? finish(true) : advance(1));
  listen(skip, 'click', () => finish(false));
  listen(replay, 'click', () => { index = 0; showStep(); });
  listen(dialog, 'cancel', event => { event.preventDefault(); finish(false); });
  listen(dialog, 'close', () => { if (active && !dialog.open) finish(false); });
  listen(dialog, 'keydown', event => {
    // Keep workspace shortcuts from seeking or generating behind the modal.
    event.stopPropagation();
    if (event.key === 'Escape') { event.preventDefault(); finish(false); }
    if (event.key === 'ArrowRight') { event.preventDefault(); advance(1); }
    if (event.key === 'ArrowLeft') { event.preventDefault(); advance(-1); }
    if (event.key === 'Tab') {
      const controls = [...card.querySelectorAll('button:not(:disabled)')].filter(item => !item.hidden);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  listen(window, 'resize', schedule); listen(document, 'scroll', schedule, { capture: true, passive: true });
  if (window.visualViewport) { listen(window.visualViewport, 'resize', schedule); listen(window.visualViewport, 'scroll', schedule); }
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(schedule) : null; observer?.observe(card);
  return {
    start() {
      if (disposed) return false;
      if (!active && document.querySelector('dialog[open]')) { notify('请先关闭当前窗口，再开始新手引导。'); return false; }
      steps = STEPS.filter(step => visibleTarget(step));
      if (!steps.length) { notify('工作区尚未准备好，请稍后重新打开引导。'); return false; }
      if (!active) { initialFocus = document.activeElement; active = true; dialog.showModal(); }
      index = 0; showStep(); return true;
    },
    dispose() {
      if (disposed) return;
      finish(false, false); disposed = true;
      if (frame) cancelAnimationFrame(frame); observer?.disconnect(); listeners.forEach(remove => remove()); dialog.remove();
    },
  };
}
