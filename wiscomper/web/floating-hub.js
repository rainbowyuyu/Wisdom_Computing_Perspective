const ACTIVE = new Set(['queued', 'planning', 'validating', 'building', 'rendering', 'checking', 'finalizing', 'cancelling']);
const STATUS = {
  queued: '排队中', planning: '理解内容', validating: '校验场景', building: '构建画面',
  rendering: '渲染中', checking: '检查结果', finalizing: '整理结果', cancelling: '正在取消',
  completed: '已完成', failed: '失败', cancelled: '已取消', needs_input: '等待补充',
};
const STORAGE_KEY = 'visualize-dsh.floating-hub.v1';
const validId = (value) => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,64}$/.test(value);
const copyText = (value, fallback = '', limit = 180) => typeof value === 'string' && value.trim() ? value.trim().slice(0, limit) : fallback;
const finite = (value) => typeof value === 'number' && Number.isFinite(value);
const timestamp = (value) => finite(value) ? value : typeof value === 'string' ? Date.parse(value) || 0 : 0;

/** Only actual finite numeric progress is quantitative; null and strings stay unknown. */
export function hubSnapshot(jobs = []) {
  const seen = new Set();
  const normalized = (Array.isArray(jobs) ? jobs : []).flatMap((job) => {
    if (!job || !validId(job.id) || seen.has(job.id)) return [];
    seen.add(job.id);
    const status = Object.hasOwn(STATUS, job.status) ? job.status : 'unknown';
    const stage = copyText(job.stage, status, 40);
    return [{
      id: job.id, kind: job.kind === 'export' ? 'export' : 'create', status,
      active: ACTIVE.has(status), stage: Object.hasOwn(STATUS, stage) ? STATUS[stage] : stage === 'unknown' ? '状态待确认' : stage,
      message: copyText(job.message, STATUS[status] || '等待任务状态'),
      connectionError: copyText(job.connectionError),
      progress: finite(job.progress) ? Math.max(0, Math.min(100, job.progress)) : null,
      projectId: validId(job.project_id) ? job.project_id : null,
      created: timestamp(job.created),
    }];
  }).sort((a, b) => b.created - a.created);
  const active = normalized.filter((job) => job.active);
  const ordered = [...active, ...normalized.filter((job) => !job.active)];
  return { total: normalized.length, activeCount: active.length, selected: ordered[0] || null, rows: ordered.slice(0, 3) };
}

/** Clamp against the visual viewport, including a mobile keyboard or pinch zoom. */
export function clampHubPosition(position, viewport, size = 64, margin = 12) {
  const left = finite(viewport?.left) ? viewport.left : 0;
  const top = finite(viewport?.top) ? viewport.top : 0;
  const width = finite(viewport?.width) ? Math.max(0, viewport.width) : 0;
  const height = finite(viewport?.height) ? Math.max(0, viewport.height) : 0;
  const insetX = Math.min(margin, Math.max(0, (width - size) / 2));
  const insetY = Math.min(margin, Math.max(0, (height - size) / 2));
  const minX = left + insetX, minY = top + insetY;
  const maxX = Math.max(minX, left + width - size - insetX);
  const maxY = Math.max(minY, top + height - size - insetY);
  return {
    x: Math.min(maxX, Math.max(minX, finite(position?.x) ? position.x : maxX)),
    y: Math.min(maxY, Math.max(minY, finite(position?.y) ? position.y : maxY - 72)),
  };
}

export function readHubPosition(raw) {
  try {
    const value = JSON.parse(raw);
    return value?.v === 1 && finite(value.x) && finite(value.y) ? { x: value.x, y: value.y } : null;
  } catch { return null; }
}

export function relativeHubPosition(position, viewport, size = 64) {
  const min = clampHubPosition({x:-1e9,y:-1e9},viewport,size), max = clampHubPosition({x:1e9,y:1e9},viewport,size);
  const current = clampHubPosition(position,viewport,size);
  return { x: (current.x-min.x)/Math.max(1,max.x-min.x), y: (current.y-min.y)/Math.max(1,max.y-min.y) };
}

export function absoluteHubPosition(relative, viewport, size = 64) {
  const min=clampHubPosition({x:-1e9,y:-1e9},viewport,size),max=clampHubPosition({x:1e9,y:1e9},viewport,size);
  return {x:min.x+Math.max(0,Math.min(1,relative.x))*(max.x-min.x),y:min.y+Math.max(0,Math.min(1,relative.y))*(max.y-min.y)};
}

const ICONS = {
  library: ['M4 5h6v14H4z', 'M14 5h6v14h-6z', 'M7 8v8', 'M17 8v8'],
  knowledge: ['M12 4v16', 'M12 6C8 3 4 4 3 5v14c3-2 6-2 9 0 3-2 6-2 9 0V5c-1-1-5-2-9 1'],
  help: ['M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4', 'M12 17h.01', 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20'],
  projects: ['M3 7V5h7l2 2h9v13H3z'],
  create: ['M12 3v18', 'M3 12h18'],
  jobs: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M3 6h1', 'M3 12h1', 'M3 18h1'],
  close: ['M6 6l12 12', 'M18 6 6 18'],
  arrow: ['M5 12h14', 'm14 7 5 5-5 5'],
  grip: ['M8 5h.01', 'M16 5h.01', 'M8 12h.01', 'M16 12h.01', 'M8 19h.01', 'M16 19h.01'],
  settings: ['M4 7h16','M4 17h16','M8 4v6','M16 14v6'],
  learning: ['m3 8 9-5 9 5-9 5z','M6 10v7l6 4 6-4v-7'],
  releases: ['M5 3h14v18H5z','M9 7h6','M9 12h6','M9 17h3'],
  tutorial: ['M4 4h16v16H4z','m10 8 6 4-6 4z'],
};

function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [key, value] of Object.entries({ viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) svg.setAttribute(key, value);
  for (const d of ICONS[name] || ICONS.jobs) {
    const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', d); svg.append(path);
  }
  return svg;
}

function node(tag, className, text = '') {
  const result = document.createElement(tag); result.className = className;
  if (text) result.textContent = text;
  return result;
}

function button(className, label, iconName) {
  const result = node('button', className); result.type = 'button';
  if (iconName) result.append(icon(iconName));
  if (label) result.append(node('span', 'hub-button-label', label));
  return result;
}

/**
 * Caller supplies the existing job stream. No polling, network requests or model calls.
 * onAction: navigation names; open-project/cancel-job/clarify-job receive an ID string;
 * a job result uses jobs with {jobId}. Return a promise to keep cancel pending.
 */
export function mountFloatingHub({ onAction = () => {}, onPositionChange = () => {} } = {}) {
  const cleanup = [];
  const root = node('div', 'hub-root');
  const orb = button('hub-orb', '');
  orb.setAttribute('aria-expanded', 'false'); orb.title = '打开创作助手 · 拖动可调整位置';
  const orbVisual = node('span', 'hub-orb-visual'); orbVisual.setAttribute('aria-hidden', 'true');
  const water = node('span', 'hub-water'), drift = node('span', 'hub-drift');
  const orbLabel = node('span', 'hub-orb-label');
  const orbValue = node('span', 'hub-orb-value', '✦'), orbCaption = node('span', 'hub-orb-caption', '创作助手');
  orbLabel.append(orbValue, orbCaption); orbVisual.append(water, drift, orbLabel);
  const count = node('span', 'hub-count'); count.hidden = true; count.setAttribute('aria-hidden', 'true');
  orb.append(orbVisual, count);
  const panel = node('section', 'hub-panel'); panel.hidden = true;
  const uniqueId = `hub-${globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  panel.id = `${uniqueId}-panel`; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'false');
  panel.setAttribute('aria-labelledby', `${uniqueId}-title`); orb.setAttribute('aria-controls', panel.id);
  const header = node('header', 'hub-header');
  const grip = button('hub-grip', '', 'grip'); grip.setAttribute('aria-label', '移动助手面板，使用方向键调整位置'); grip.title = '拖动或使用方向键移动';
  const heading = node('div', 'hub-heading');
  const title = node('h2', 'hub-title', '创作助手'); title.id = `${uniqueId}-title`;
  heading.append(title, node('p', 'hub-subtitle', '从一个想法，到一幅画面'));
  const close = button('hub-icon-button', '', 'close'); close.setAttribute('aria-label', '收起创作助手');
  header.append(grip, heading, close);
  const body = node('div', 'hub-body');
  const navigation = node('nav', 'hub-navigation'); navigation.setAttribute('aria-label', '创作助手快捷入口');
  const menu = [['library', '公式库'], ['knowledge', '知识图谱'], ['help', '使用帮助'], ['projects', '我的项目'], ['create', '开始创作'], ['jobs', '任务中心']];
  for (const [action, label] of menu) {
    const item = button('hub-nav-button', label, action); item.dataset.action = action;
    listen(item, 'click', () => requestAction(action)); navigation.append(item);
  }
  const shortcuts = node('nav','hub-shortcuts'); shortcuts.setAttribute('aria-label','学习与偏好');
  for(const [action,label] of [['settings','设置'],['learning','学习'],['releases','版本'],['tutorial','教程']]) {
    const entry=button('hub-shortcut',label,action);entry.dataset.action=action;listen(entry,'click',()=>requestAction(action));shortcuts.append(entry);
  }
  const current = button('hub-current-project', '', 'projects'); current.hidden = true;
  const currentText = node('span', 'hub-current-text'), currentLabel = node('span', 'hub-current-label', '当前项目');
  const currentTitle = node('span', 'hub-current-title'); currentText.append(currentLabel, currentTitle); current.append(currentText, icon('arrow'));
  const tasks = node('section', 'hub-tasks'); tasks.setAttribute('aria-label', '最近任务');
  const taskHeading = node('div', 'hub-task-heading');
  const taskTitle = node('h3', 'hub-task-title', '最近任务');
  const allTasks = button('hub-text-button', '全部', 'arrow');
  listen(allTasks, 'click', () => requestAction('jobs')); taskHeading.append(taskTitle, allTasks);
  const taskList = node('div', 'hub-task-list');
  const empty = node('p', 'hub-empty', '创作或导出开始后，可在这里查看进度。');
  const note = node('p', 'hub-progress-note'); note.hidden = true;
  tasks.append(taskHeading, empty, taskList, note);
  const error = node('p', 'hub-action-error'); error.hidden = true; error.setAttribute('role', 'alert');
  body.append(navigation, shortcuts, current, tasks, error);
  const footer = node('p', 'hub-footer', '拖动圆球调整位置 · Esc 收起'); panel.append(header, body, footer);
  const live = node('span', 'hub-sr-only'); live.setAttribute('aria-live', 'polite'); live.setAttribute('aria-atomic', 'true');
  root.append(panel, orb, live); document.body.append(root);

  let disposed = false, opened = false, projectId = null, frame = 0, drag = null, suppressClickUntil = 0;
  let snapshot = hubSnapshot(), position = null, relativePosition = null, priorFocus = null;
  const rows = new Map(), pending = new Set();
  try {
    const raw=localStorage.getItem(STORAGE_KEY), saved=JSON.parse(raw);
    if(saved?.v===2 && finite(saved.x) && finite(saved.y))relativePosition={x:Math.max(0,Math.min(1,saved.x)),y:Math.max(0,Math.min(1,saved.y))};
    else position=readHubPosition(raw);
  } catch { /* Storage can be disabled. */ }
  function listen(target, name, callback, options) {
    target.addEventListener(name, callback, options); cleanup.push(() => target.removeEventListener(name, callback, options));
  }
  function viewport() {
    const view = window.visualViewport;
    return { left: view?.offsetLeft || 0, top: view?.offsetTop || 0, width: view?.width || window.innerWidth, height: view?.height || window.innerHeight };
  }
  function savePosition() {
    relativePosition=relativeHubPosition(position,viewport(),orb.offsetWidth||64);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ v: 2, ...relativePosition })); } catch { /* Private browsing may reject writes. */ }
    try { Promise.resolve(onPositionChange({floating_x:relativePosition.x,floating_y:relativePosition.y})).catch(()=>{}); } catch { /* A host callback must not break dragging. */ }
  }
  function layout() {
    frame = 0; if (disposed) return;
    const view = viewport(), size = orb.offsetWidth || 64;
    if(relativePosition)position=absoluteHubPosition(relativePosition,view,size);
    position = clampHubPosition(position, view, size);
    orb.style.left = `${position.x}px`; orb.style.top = `${position.y}px`;
    panel.style.width = `${Math.max(0, Math.min(348, view.width - 24))}px`;
    panel.style.maxHeight = `${Math.max(0, view.height - 24)}px`;
    if (!opened) return;
    const width = panel.offsetWidth, height = panel.offsetHeight;
    const x = Math.max(view.left + 12, Math.min(position.x + size - width, view.left + view.width - width - 12));
    const above = position.y - height - 12;
    const below = position.y + size + 12;
    const y = above >= view.top + 12 ? above : below + height <= view.top + view.height - 12 ? below : view.top + 12;
    panel.style.left = `${x}px`; panel.style.top = `${y}px`;
  }
  function scheduleLayout() { if (!disposed && !frame) frame = requestAnimationFrame(layout); }
  function setOpen(next, returnFocus = true) {
    if (disposed || opened === next) return;
    opened = next; panel.hidden = !next; root.dataset.open = String(next); orb.setAttribute('aria-expanded', String(next));
    if (next) {
      priorFocus = document.activeElement; layout(); close.focus({ preventScroll: true });
    } else if (returnFocus) {
      const target = priorFocus?.isConnected && !panel.contains(priorFocus) && typeof priorFocus.focus === 'function' ? priorFocus : orb;
      target.focus({ preventScroll: true });
    }
    renderOrb();
  }
  async function requestAction(action, payload, keepOpen = false) {
    if (disposed || (action === 'cancel-job' && pending.has(payload))) return;
    error.hidden = true;
    if (!keepOpen) setOpen(false);
    if (action === 'cancel-job') { pending.add(payload); renderRows(); }
    try { await onAction(action, payload); }
    catch {
      if (!disposed) {
        setOpen(true); error.textContent = '暂时无法完成操作，请稍后重试。'; error.hidden = false; scheduleLayout();
      }
    } finally {
      if (action === 'cancel-job') pending.delete(payload);
      if (!disposed) renderRows();
    }
  }
  function renderOrb() {
    const selected = snapshot.selected, active = selected?.active;
    const progress = active ? selected.progress : null;
    const percent = progress === null ? null : Math.round(progress);
    root.dataset.state = active ? 'active' : selected?.status || 'idle';
    orb.dataset.progress = active ? progress === null ? 'unknown' : 'known' : 'idle';
    orb.style.setProperty('--hub-level', `${progress ?? 0}%`);
    orb.dataset.zero = String(progress === 0);
    orbValue.textContent = active ? percent === null ? '···' : `${percent}%` : selected?.status === 'completed' ? '✓' : ['failed', 'needs_input'].includes(selected?.status) ? '!' : '✦';
    orbCaption.textContent = active ? selected.stage : selected ? STATUS[selected.status] || '创作助手' : '创作助手';
    count.hidden = snapshot.activeCount < 2; count.textContent = snapshot.activeCount > 9 ? '9+' : String(snapshot.activeCount);
    const summary = active ? `${snapshot.activeCount} 个任务进行中，当前${selected.kind === 'export' ? '视频导出' : '场景创作'}，${selected.stage}` : selected ? `最近任务${STATUS[selected.status] || '状态待确认'}` : '暂无任务';
    const progressText = active ? percent === null ? '，进度待更新' : `，${percent}%` : '';
    orb.setAttribute('aria-label', `创作助手，${summary}${progressText}，${opened ? '收起' : '展开'}面板`);
    if (live.textContent !== summary) live.textContent = summary;
  }
  function createRow(id) {
    const element = node('article', 'hub-task'); element.tabIndex = -1; element.dataset.hubJobId = id;
    const top = node('div', 'hub-task-top'), kind = node('span', 'hub-task-kind'), status = node('span', 'hub-task-status');
    top.append(kind, status);
    const message = node('p', 'hub-task-message');
    const progress = node('div', 'hub-task-progress'); progress.setAttribute('role', 'progressbar');
    progress.setAttribute('aria-valuemin', '0'); progress.setAttribute('aria-valuemax', '100');
    const fill = node('span', 'hub-task-fill'); progress.append(fill);
    const meta = node('div', 'hub-task-meta'), stage = node('span', 'hub-task-stage'), value = node('span', 'hub-task-value'); meta.append(stage, value);
    const connection = node('p', 'hub-task-connection', '连接中断，正在恢复状态…'); connection.hidden = true;
    const actions = node('div', 'hub-task-actions');
    const result = button('hub-result-button', '查看任务', 'arrow');
    const cancel = button('hub-cancel-button', '取消任务');
    const openResult = () => {
      const job = snapshot.rows.find((entry) => entry.id === id); if (!job) return;
      if (job.status === 'completed' && job.kind !== 'export' && job.projectId) requestAction('open-project', job.projectId);
      else if (job.status === 'needs_input') requestAction('clarify-job', id);
      else requestAction('jobs', { jobId: id });
    };
    const cancelJob = () => requestAction('cancel-job', id, true);
    result.addEventListener('click', openResult); cancel.addEventListener('click', cancelJob);
    actions.append(result, cancel); element.append(top, message, progress, meta, connection, actions);
    return { element, kind, status, message, progress, fill, stage, value, connection, result, cancel,
      destroy() { result.removeEventListener('click', openResult); cancel.removeEventListener('click', cancelJob); element.remove(); },
    };
  }
  function renderRows() {
    const focused = panel.contains(document.activeElement) ? document.activeElement : null;
    const keep = new Set(snapshot.rows.map((job) => job.id));
    for (const [id, row] of rows) if (!keep.has(id)) {
      if (row.element.contains(document.activeElement)) allTasks.focus({ preventScroll: true });
      row.destroy(); rows.delete(id);
    }
    snapshot.rows.forEach((job, index) => {
      let row = rows.get(job.id); if (!row) { row = createRow(job.id); rows.set(job.id, row); }
      if (taskList.children[index] !== row.element) taskList.insertBefore(row.element, taskList.children[index] || null);
      row.element.dataset.state = job.status;
      row.kind.textContent = job.kind === 'export' ? '视频导出' : '场景创作';
      row.status.textContent = STATUS[job.status] || '待确认';
      row.message.textContent = job.message; row.message.title = job.message;
      row.progress.hidden = !job.active; row.progress.dataset.unknown = String(job.progress === null);
      row.progress.setAttribute('aria-label', `${row.kind.textContent}进度`);
      row.progress.setAttribute('aria-valuetext', job.progress === null ? `${job.stage}，进度待更新` : `${job.progress}%，${job.stage}`);
      if (job.progress === null) row.progress.removeAttribute('aria-valuenow');
      else row.progress.setAttribute('aria-valuenow', String(job.progress));
      row.fill.style.width = job.progress === null ? '' : `${job.progress}%`;
      row.stage.textContent = job.active ? job.stage : STATUS[job.status] || '状态待确认';
      row.value.textContent = job.active ? job.progress === null ? '进度待更新' : `${Math.round(job.progress)}%` : '';
      row.connection.hidden = !job.connectionError;
      const cancelFocused = document.activeElement === row.cancel;
      row.cancel.hidden = !job.active;
      row.cancel.disabled = pending.has(job.id) || job.status === 'cancelling' || job.stage === STATUS.cancelling;
      row.cancel.querySelector('.hub-button-label').textContent = row.cancel.disabled ? '正在取消…' : '取消任务';
      row.result.querySelector('.hub-button-label').textContent = job.status === 'completed' ? job.kind === 'export' ? '查看视频' : job.projectId ? '打开场景' : '查看结果' : job.status === 'needs_input' ? '补充说明' : '查看任务';
      if ((row.cancel.hidden || row.cancel.disabled) && cancelFocused) row.result.focus({ preventScroll: true });
    });
    empty.hidden = snapshot.total > 0; allTasks.hidden = snapshot.total === 0;
    taskTitle.textContent = snapshot.activeCount ? `正在进行 · ${snapshot.activeCount}` : '最近任务';
    note.hidden = snapshot.activeCount < 2;
    note.textContent = snapshot.activeCount > 1 ? '圆球显示最近一个进行中任务的进度。' : '';
    if (opened && focused?.isConnected && !focused.closest('[hidden]') && document.activeElement === document.body) focused.focus({ preventScroll: true });
    scheduleLayout();
  }
  function finishDrag(event) {
    if (!drag || (event && event.pointerId !== drag.id)) return;
    const previous = drag; drag = null; root.removeAttribute('data-dragging');
    if (previous.target.hasPointerCapture?.(previous.id)) previous.target.releasePointerCapture(previous.id);
    if (previous.moved) { suppressClickUntil = performance.now() + 400; savePosition(); }
  }
  for (const handle of [orb, grip]) {
    listen(handle, 'pointerdown', (event) => {
      if (event.button !== 0 || !event.isPrimary || drag) return;
      layout(); drag = { id: event.pointerId, target: handle, x: event.clientX, y: event.clientY, origin: { ...position }, moved: false };
      handle.setPointerCapture(event.pointerId);
    });
    listen(handle, 'pointermove', (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      if (!drag.moved && dx * dx + dy * dy <= 36) return;
      drag.moved = true; root.dataset.dragging = 'true'; event.preventDefault();
      relativePosition=null;position = { x: drag.origin.x + dx, y: drag.origin.y + dy }; layout();
    });
    listen(handle, 'pointerup', finishDrag);
    listen(handle, 'pointercancel', finishDrag);
    listen(handle, 'lostpointercapture', finishDrag);
    listen(handle, 'keydown', (event) => {
      const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      if (!Object.hasOwn(directions, event.key)) return;
      event.preventDefault(); const [x, y] = directions[event.key], step = event.shiftKey ? 40 : 16;
      relativePosition=null;position = { x: position.x + x * step, y: position.y + y * step }; layout(); savePosition();
    });
  }
  listen(orb, 'click', (event) => {
    if (event.detail > 0 && performance.now() < suppressClickUntil) { event.preventDefault(); return; }
    setOpen(!opened);
  });
  listen(close, 'click', () => setOpen(false));
  listen(current, 'click', () => { if (projectId) requestAction('open-project', projectId); });
  listen(document, 'keydown', (event) => {
    if (event.key === 'Escape' && opened && !event.defaultPrevented && !document.querySelector('dialog[open]')) {
      event.preventDefault(); setOpen(false);
    }
  });
  listen(document, 'pointerdown', (event) => { if (opened && !root.contains(event.target)) setOpen(false, false); });
  listen(window, 'resize', scheduleLayout);
  if (window.visualViewport) {
    listen(window.visualViewport, 'resize', scheduleLayout);
    listen(window.visualViewport, 'scroll', scheduleLayout);
  }
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(scheduleLayout) : null;
  observer?.observe(panel); observer?.observe(orb);
  layout(); renderOrb(); renderRows();
  return {
    setPreferences(preferences={}) {
      if(disposed)return;
      if(typeof preferences.floating_visible==='boolean'){
        if(!preferences.floating_visible){setOpen(false,false);if(root.contains(document.activeElement))document.querySelector('#open-help, #account-menu button')?.focus({preventScroll:true});}
        root.hidden=!preferences.floating_visible;
      }
      if(finite(preferences.floating_size)){
        const size=Math.max(44,Math.min(96,preferences.floating_size));root.style.setProperty('--hub-size',`${size}px`);root.style.setProperty('--hub-scale',String(size/66));
      }
      if(finite(preferences.floating_opacity))orb.style.opacity=String(Math.max(.35,Math.min(1,preferences.floating_opacity)));
      if(typeof preferences.reduced_motion==='boolean')root.dataset.reducedMotion=String(preferences.reduced_motion);
      if(Object.hasOwn(preferences,'floating_x')||Object.hasOwn(preferences,'floating_y')){
        if(preferences.floating_x===null||preferences.floating_y===null){relativePosition=null;position=null;try{localStorage.removeItem(STORAGE_KEY);}catch{}}
        else if(finite(preferences.floating_x)&&finite(preferences.floating_y))relativePosition={x:Math.max(0,Math.min(1,preferences.floating_x)),y:Math.max(0,Math.min(1,preferences.floating_y))};
      }
      layout();
    },
    update({ jobs = [], project = null } = {}) {
      if (disposed) return;
      snapshot = hubSnapshot(jobs); projectId = validId(project?.id) ? project.id : null;
      current.hidden = !projectId;
      currentTitle.textContent = copyText(project?.title, copyText(project?.scene?.title, '未命名项目'), 80);
      current.title = projectId ? `打开当前项目：${currentTitle.textContent}` : '';
      renderOrb(); renderRows();
    },
    dispose() {
      if (disposed) return;
      const ownsFocus = root.contains(document.activeElement);
      finishDrag(); disposed = true; cleanup.forEach((remove) => remove()); observer?.disconnect();
      if (frame) cancelAnimationFrame(frame);
      for (const row of rows.values()) row.destroy();
      root.remove(); rows.clear(); pending.clear();
      if (ownsFocus && priorFocus?.isConnected && !root.contains(priorFocus)) priorFocus.focus?.({ preventScroll: true });
    },
  };
}
