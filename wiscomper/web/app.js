import { ScenePlayer } from './engine.js';
import { mountKnowledgeWorkspace } from './knowledge-workspace.js';
import { mountFloatingHub } from './floating-hub.js';
import { mountAccountMenu } from './account-menu.js';
import { mountWorkspaceCenter } from './workspace-center.js';
import { mountOnboarding } from './onboarding.js';
import { mountSketchInput } from './sketch-input.js';
import { mountGlobalSearch } from './global-search.js';

const $ = (selector) => document.querySelector(selector);
const ACTIVE = new Set(['queued', 'planning', 'validating', 'building', 'rendering']);
const STATUS = { queued: '排队中', planning: '理解内容', validating: '校验场景', building: '构建画面', rendering: '渲染中', completed: '已完成', failed: '失败', cancelled: '已取消', needs_input: '等待补充' };
const KINDS = { circle: '圆', rect: '矩形', line: '线', arrow: '向量', path: '路径', text: '文字', formula: '公式', image: '图片', box: '立方体', sphere: '球体', cylinder: '圆柱', group: '组', torus: '圆环', cone: '圆锥', prism: '挤出体' };
const state = {
  bootstrap: null, csrf: '', project: null, projects: [], jobs: new Map(), timers: new Map(),
  handled: new Set(), autoOpen: new Set(), createJob: null, submitting: false, uploading: false,
  assetId: null, inputMode: 'text', selected: null, visibility: new Map(), parameters: {},
  recomputePending: null, recomputing: false, recomputePromise: null, recomputeTimer: null, sceneEpoch: 0, loadChain: Promise.resolve(),
  projectRequest: 0, toastTimer: null, exporting: false, exportProjectId: null, exportSceneMode: null, disposed: false,
  sceneLoading: false, manipulationMode: 'observe', interactionNodes: new Map(), explorationPending: new Map(),
  explorationVersions: new Map(), explorationSave: null, explorationTimer: null, explorationErrors: new Map(),
  preview: null, conflictId: null, restoring: false, versionsRequest: 0, account: null, publicMode: false,
  accountTransition: null, assetRestore: 0, restoringDraft: false, preferences: null,
};
let accountMenu = null;
const AUTH_DRAFT = 'wiscomper.auth-draft';
const player = new ScenePlayer($('#scene-host'));
const knowledge = mountKnowledgeWorkspace({ api, onAction: ecosystemAction, getProject: () => state.project, getPrompt: () => $('#prompt').value, notify: toast });
const floatingHub = mountFloatingHub({ onAction: (action, value) => ecosystemAction(action, value).catch(error => toast(message(error), true)), onPositionChange: patch => workspaceCenter.savePreferences(patch) });
const workspaceCenter = mountWorkspaceCenter({api,onAction:ecosystemAction,getProject:()=>state.project,getPrompt:()=>$('#prompt').value,getTime:()=>player.time,onPreferences:applyPreferences,notify:toast});
const onboarding = mountOnboarding({onComplete:()=>workspaceCenter.savePreferences({tutorial_completed:true}).catch(()=>{}),notify:toast});
const sketchInput = mountSketchInput({onImage:uploadImage,notify:toast});
const globalSearch = mountGlobalSearch({api,onAction:ecosystemAction,notify:toast,canOpen:()=>!state.accountTransition});
const systemTheme = matchMedia('(prefers-color-scheme: dark)');
const systemMotion = matchMedia('(prefers-reduced-motion: reduce)');
function applyPreferences(prefs) {
  const previous=state.preferences; state.preferences=prefs;
  document.documentElement.dataset.theme=prefs.theme==='system'?(systemTheme.matches?'dark':'light'):prefs.theme;
  document.documentElement.dataset.reducedMotion=String(prefs.reduced_motion || systemMotion.matches);
  knowledge.setPreferences(prefs);floatingHub.setPreferences(prefs);
  if(!previous || previous.default_speed!==prefs.default_speed){$('#speed').value=String(prefs.default_speed);player.setSpeed(prefs.default_speed);}
  if(!previous && !$('#prompt').value && !state.assetId)setInputMode(prefs.default_input);
  if(prefs.reduced_motion || systemMotion.matches || !prefs.autoplay)player.pause();
  $('#welcome-hint').hidden=!!prefs.tutorial_completed;
}
const applySystemPreferences=()=>{if(state.preferences)applyPreferences(state.preferences);};
systemTheme.addEventListener('change',applySystemPreferences);systemMotion.addEventListener('change',applySystemPreferences);

function savedMessage() {
  return state.account?.authenticated ? '作品与历史已保存到账号' : state.publicMode ? '作品保存在当前浏览器的访客空间' : '作品与历史保存在本机';
}
async function syncAccount(session, { reason } = {}) {
  const priorAccess=JSON.stringify(state.account?.model_access?.allowed || []);
  state.account = session;
  if (session.csrf) state.csrf = session.csrf;
  $('#storage-note').textContent = savedMessage();
  if (!state.preview) $('#save-status').textContent = `${savedMessage()}${state.project ? ` · v${state.project.revision || 1}` : ''}`;
  $('#login-for-creation').hidden = !state.publicMode || !!session.authenticated;
  if (['login','register'].includes(reason) && session.legacy_import) {
    const result=session.legacy_import;
    const notice=[result.imported ? `已迁入 ${result.imported} 条旧站资料。` : '',...(result.warnings || []),result.warning || ''].filter(Boolean).join(' ');
    if(notice)try { sessionStorage.setItem('wiscomper.account-notice',notice.slice(0,600)); } catch {}
  }
  if (['logout','login','register'].includes(reason)) { location.replace('/'); return {navigating:true}; }
  if (state.bootstrap && priorAccess!==JSON.stringify(session.model_access?.allowed || []) && priorAccess!=='[]') {
    try {
      const data=await api('/api/bootstrap');
      if (state.account===session) { state.bootstrap=data;state.csrf=data.csrf; }
    } catch(error) { toast(message(error),true); }
  }
  refreshProviderChoices();
  updateCreateState();
}
function accountBusy(reason) {
  state.accountTransition = reason;
  for (const node of document.querySelectorAll('.workspace,.ecosystem-nav,.workspace-jumps,.hub-root,.brand,#new-project')) node.inert = !!reason;
  updateCreateState();
}
async function beforeAccountNavigate({ reason }) {
  if (knowledge.dirty || workspaceCenter.dirty) throw new Error('还有未保存的修改，请先保存或取消编辑。');
  if (state.uploading || state.submitting) throw new Error('正在处理当前输入，请完成后再切换账号。');
  if (!state.preview && !state.conflictId) await flushProjectChanges();
  // Store a one-use draft only for the OAuth round trip in this tab.
  if (reason === 'login') {
    const draft = { prompt: $('#prompt').value, mode: state.inputMode, provider: $('#provider').value,
      duration: document.querySelector('input[name="duration"]:checked').value, assetId: state.assetId,
      targetId: $('#iterate').checked ? state.project?.id : null, saved: Date.now() };
    try { sessionStorage.setItem(AUTH_DRAFT, JSON.stringify(draft)); }
    catch { throw new Error('浏览器无法暂存输入，请先复制内容后再登录。'); }
  } else { try { sessionStorage.removeItem(AUTH_DRAFT); } catch {} }
}
async function restoreAccountDraft() {
  let draft;
  try { draft = JSON.parse(sessionStorage.getItem(AUTH_DRAFT) || 'null'); } catch { return; }
  if (!draft || Date.now() - draft.saved > 30 * 60 * 1000) { try { sessionStorage.removeItem(AUTH_DRAFT); } catch {} return; }
  if (typeof draft.prompt === 'string') $('#prompt').value = draft.prompt.slice(0, 6000);
  if (['text','image','formula'].includes(draft.mode)) setInputMode(draft.mode);
  if (state.bootstrap?.providers?.some(p=>p.id===draft.provider && p.permitted!==false)) $('#provider').value = draft.provider;
  if (['12','20','30'].includes(draft.duration)) document.querySelector(`input[name="duration"][value="${draft.duration}"]`).checked = true;
  if (safeId(draft.targetId) && state.projects.some(p => p.id === draft.targetId)) { await loadProject(draft.targetId); $('#iterate').checked = true; }
  else $('#iterate').checked = false;
  // Asset ownership is rechecked before restoring its preview after login.
  if (safeId(draft.assetId)) {
    const token = ++state.assetRestore;
    state.restoringDraft = true; updateCreateState();
    const img = new Image(); let timer;
    try {
      await new Promise((resolve,reject) => {
        timer = setTimeout(() => reject(new Error('图片恢复超时，请重新添加参考图片。')), 10000);
        img.onload = resolve; img.onerror = () => reject(new Error('图片未恢复，请重新添加参考图片。'));
        img.src = assetUrl(draft.assetId);
      });
      if (state.assetRestore === token) {
        state.assetId = draft.assetId; $('#asset-image').src = img.src;
        $('#asset-preview').hidden = false; $('#image-input').hidden = true;
      }
    } catch(error) { if(state.assetRestore === token) toast(message(error),true); }
    finally { clearTimeout(timer); img.onload = null; img.onerror = null; if(state.assetRestore===token) state.restoringDraft = false; }
  }
  try { sessionStorage.removeItem(AUTH_DRAFT); } catch {}
  updatePromptCount(); providerStatus(); updateCreateState();
  toast('登录前的输入已保留，可以继续创作。');
}

async function ecosystemAction(action, value) {
  if(action === 'search'){globalSearch.open();return;}
  if(action === 'sketch') {if(state.publicMode&&!state.account?.authenticated){accountMenu?.open('登录后可将手写草图送入创作。');return;}sketchInput.open();return;}
  if(action === 'learning-item' || action === 'course-pack-item'){await workspaceCenter.openItem(action==='learning-item'?'learning':'course-pack',value);return;}
  if(action === 'open-formula'){const data=await api('/api/library');const formula=data.items.find(x=>x.id===value);if(!formula)throw new Error('公式已更新或归档，请重新搜索。');await ecosystemAction('formula',formula);return;}
  if (['settings','learning','course-packs','achievements','releases'].includes(action)) { await workspaceCenter.open(action); return; }
  if (action === 'tutorial') { onboarding.start(); return; }
  if (action === 'open-study-project') { await loadProject(value.id);player.pause();player.seek(Number(value.time)||0);$('.stage-panel').scrollIntoView({block:'start',behavior:'smooth'});return; }
  if (['library', 'knowledge', 'help'].includes(action)) { knowledge.open(action); return; }
  if (action === 'formula') {
    const input = `请可视化解释：${value.latex}${value.note ? `\n条件与说明：${value.note}` : ''}${value.prompt ? `\n${value.prompt}` : ''}`;
    const existing = $('#prompt').value.trim();
    const next = existing ? `${existing}\n\n${input}` : input;
    if (next.length > 6000) throw new Error('当前输入较长，请先精简内容后再带入公式。');
    $('#prompt').value = next; $('#iterate').checked = false; setInputMode('formula'); updatePromptCount(); updateCreateState();
    switchTabs(['creation', 'history'], 'creation'); $('#prompt').focus(); $('#prompt').scrollIntoView({ block: 'center', behavior: 'smooth' });
    toast('公式已带入，补充想观察的关系后点击生成'); return;
  }
  if (action === 'sample') {
    const sample = state.bootstrap?.samples?.find(x => x.id === value);
    if (!sample) throw new Error('示例暂未载入，请稍后再试。');
    await createScene(sample); return;
  }
  if (action === 'open-project') { state.autoOpen.clear(); await loadProject(value); switchTabs(['detail', 'process'], 'detail'); return; }
  if (action === 'cancel-job') { const data = await api(jobUrl(value, '/cancel'), { method: 'POST', body: {} }); await observeJob(data.job); return; }
  if (action === 'clarify-job') {
    const job=state.jobs.get(value); if(!job)throw new Error('任务记录尚未载入。');
    if(job.target_project_id && state.project?.id!==job.target_project_id) await loadProject(job.target_project_id);
    $('#iterate').checked=!!job.target_project_id; updateCreateState();
    switchTabs(['creation','history'],'creation'); formMessage(job.message || '请补充说明后重新生成。');
    $('#prompt').focus(); $('#prompt').scrollIntoView({block:'center',behavior:'smooth'}); return;
  }
  if (action === 'versions') { await openVersions(); return; }
  if (action === 'export') { await openExport(); return; }
  if (action === 'projects') { switchTabs(['creation', 'history'], 'history'); await refreshProjects(); $('#history-tab').scrollIntoView({ block: 'center', behavior: 'smooth' }); return; }
  if (action === 'jobs') {
    switchTabs(['detail', 'process'], 'process');
    const target = safeId(value?.jobId) ? document.querySelector(`.job-card[data-job-id="${value.jobId}"]`) : null;
    (target || $('#process-tab')).scrollIntoView({ block: 'center', behavior: 'smooth' }); return;
  }
  if (action === 'samples') { switchTabs(['creation', 'history'], 'creation'); $('#sample-filter').value = 'all'; renderSamples(state.bootstrap?.samples || []); updateCreateState(); $('#samples').scrollIntoView({ block: 'center', behavior: 'smooth' }); return; }
  if (action === 'create' || action.startsWith('input-')) {
    $('#iterate').checked = false; updateCreateState(); switchTabs(['creation', 'history'], 'creation');
    if (action.startsWith('input-')) setInputMode(action.slice(6));
    $('#prompt').focus(); $('#prompt').scrollIntoView({ block: 'center', behavior: 'smooth' }); return;
  }
  if (action === 'provider') { switchTabs(['creation', 'history'], 'creation'); $('#provider').focus(); $('#provider').scrollIntoView({ block: 'center', behavior: 'smooth' }); }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function button(className, text, onClick) {
  const node = element('button', className, text);
  node.type = 'button';
  if (onClick) node.addEventListener('click', onClick);
  return node;
}
function safeId(value) { return typeof value === 'string' && /^[a-zA-Z0-9_-]{1,64}$/.test(value); }
function assetUrl(id) { if (!safeId(id)) throw new Error('素材标识无效。'); return `/api/assets/${encodeURIComponent(id)}`; }
function projectUrl(id, suffix = '') { if (!safeId(id)) throw new Error('项目标识无效。'); return `/api/projects/${encodeURIComponent(id)}${suffix}`; }
function jobUrl(id, suffix = '') { if (!safeId(id)) throw new Error('任务标识无效。'); return `/api/jobs/${encodeURIComponent(id)}${suffix}`; }
function formatTime(value) {
  const t = Math.max(0, Number(value) || 0);
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${(t % 60).toFixed(1).padStart(4, '0')}`;
}
function formatDate(value) {
  const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? '本地保存' : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}
function message(error) { return error instanceof Error ? error.message : '操作未完成，请重试。'; }
function toast(text, error = false) {
  clearTimeout(state.toastTimer);
  $('#toast').textContent = text;
  $('#toast').classList.toggle('error', error);
  $('#toast').hidden = false;
  state.toastTimer = setTimeout(() => { $('#toast').hidden = true; }, error ? 7000 : 3500);
}
function formMessage(text = '', error = false) {
  $('#form-message').textContent = text;
  $('#form-message').hidden = !text;
  $('#form-message').classList.toggle('error', error);
}
async function api(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') { headers['Content-Type'] = 'application/json'; headers['X-CSRF-Token'] = state.csrf; }
  let response;
  try { response = await fetch(path, { method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body), signal }); }
  catch (error) { if (error.name === 'AbortError') throw error; throw new Error('暂时无法连接服务，请检查网络后重试。输入内容仍保留。'); }
  let data;
  try { data = await response.json(); } catch { throw new Error('服务返回了无法读取的结果，请稍后重试。'); }
  if (!response.ok) {
    const detail = data?.detail ?? data?.error ?? data?.message;
    const text = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((item) => item.msg || '输入格式不正确').join('；') : '请求未完成，请稍后重试。';
    const error = new Error(text); error.status = response.status; throw error;
  }
  return data;
}
function switchTabs(group, active) {
  for (const id of group) {
    const selected = id === active;
    $(`#${id}-tab`).classList.toggle('active', selected);
    $(`#${id}-tab`).setAttribute('aria-selected', String(selected));
    $(`#${id}-content`).hidden = !selected;
  }
}
function setInputMode(mode) {
  state.inputMode = mode;
  for (const tab of document.querySelectorAll('.input-tab')) {
    const active = tab.dataset.mode === mode;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  }
  $('#image-input').hidden = mode !== 'image' || !!state.assetId;
  $('#prompt').placeholder = mode === 'formula'
    ? '输入公式与想解释的关系，例如：y = sin(x)，展示振幅和频率如何改变波形……'
    : mode === 'image'
      ? '描述这张图片里你想解释的部分，例如：标记结构，并用箭头说明运动方向……'
      : '例如：用动画解释单摆的运动，展示角度与周期的关系……';
}
function providerStatus() {
  const provider = state.bootstrap?.providers?.find((item) => item.id === $('#provider').value);
  const policy=state.account?.model_access || state.bootstrap?.model_access;
  $('#provider-status').textContent = provider ? (provider.available ? provider.id==='qwen' ? '支持文字、公式与图片。生成时会将输入发送给 Qwen。' : '生成时会将输入内容发送给所选模型。' : (provider.message || '模型暂不可用，仍可探索本地示例'))+(policy?.reason==='qwen_only'?' ChatGPT / Claude 需 VIP 或管理员权限。':'') : '正在检查模型连接…';
  $('#provider-status').classList.toggle('unavailable', !!provider && !provider.available);
}
function refreshProviderChoices() {
  if (!state.bootstrap) return;
  const access=state.account?.model_access || state.bootstrap.model_access;
  for(const option of $('#provider').options) {
    const provider=state.bootstrap.providers?.find(p=>p.id===option.value);
    const allowed=access ? access.allowed.includes(option.value) : provider?.permitted!==false;
    option.disabled=!allowed;
    option.textContent=({qwen:'Qwen · 通义千问',chatgpt:'ChatGPT',claude:'Claude'})[option.value]+(!allowed?' · VIP / 管理员':'');
  }
  if ($('#provider').selectedOptions[0]?.disabled || !$('#provider').value) $('#provider').value='qwen';
  providerStatus();
}
function updateCreateState() {
  const busy = state.submitting || state.uploading || state.restoringDraft || state.accountTransition || (state.createJob && ACTIVE.has(state.jobs.get(state.createJob)?.status));
  const iterating = state.project && $('#iterate').checked;
  $('#generate').disabled = !state.bootstrap || !!busy || !!(iterating && (state.preview || state.conflictId || state.restoring));
  $('#generate-label').textContent = state.uploading ? '正在上传图片…' : busy ? '正在创作…' : iterating ? '更新当前项目' : '生成可视化';
  $('#upload-image').disabled = state.uploading;
  for (const sample of document.querySelectorAll('.sample-card')) sample.disabled = !!busy;
  $('#iteration-context').hidden = !iterating;
  $('#iteration-context').textContent = state.preview ? '正在回看历史版本。恢复后即可继续修改。' : iterating
    ? `基于「${state.project.title}」v${state.project.revision || 1} 修改，已有版本会保留。${!state.assetId && state.project.asset_id ? '沿用项目中的参考图片。' : ''}` : '';
}
function renderSamples(samples) {
  const icons = { projectile: '∠', pendulum: '∿', function: 'ƒ', wave: '∿', field: '⊙', model3d: '◇', fan: '✺', formula: '∑', diagram: '↻', image: '▧', riemann: '∫', refraction: '↗', queue: '⇥' };
  const categories = { math: ['function', 'formula', 'riemann'], physics: ['projectile', 'pendulum', 'wave', 'field', 'refraction'], spatial: ['model3d', 'fan'], process: ['diagram', 'queue'] };
  const filter = $('#sample-filter').value;
  $('#samples').replaceChildren(...samples.filter(s => filter === 'all' || categories[filter]?.includes(s.id)).map((sample) => {
    const card = button('sample-card', null, () => createScene(sample));
    card.dataset.sample = sample.id;
    card.append(element('span', 'sample-icon', icons[sample.id] || '◇'));
    const copy = element('span', 'sample-copy');
    copy.append(element('strong', '', sample.title), element('small', '', sample.description));
    card.append(copy, element('span', '', '↗'));
    card.title = sample.description || sample.title;
    return card;
  }));
}
async function refreshProjects() {
  const data = await api('/api/projects');
  state.projects = data.projects || [];
  renderProjects();
  return state.projects;
}
function renderProjects() {
  $('#project-count').textContent = state.projects.length;
  if (!state.projects.length) { $('#projects').replaceChildren(element('p', 'empty-note', '还没有保存的探索。选择一个示例，开始第一段动画。')); return; }
  $('#projects').replaceChildren(...state.projects.map((project) => {
    const card = button(`project-card${state.project?.id === project.id ? ' active' : ''}`, null, () => {
      state.autoOpen.clear();
      loadProject(project.id).catch((error) => toast(message(error), true));
    });
    card.dataset.projectId = project.id;
    card.append(element('strong', '', project.title || '未命名探索'), element('p', '', project.prompt || project.scene?.summary || ''), element('small', '', `${formatDate(project.updated || project.created)}${project.revision ? ` · v${project.revision}` : ''}`));
    return card;
  }));
}
function projectLocked() {
  return !!(state.preview || state.restoring || state.conflictId === state.project?.id ||
    [...state.jobs.values()].some(job => ACTIVE.has(job.status) && job.target_project_id === state.project?.id));
}
function updateEditingState() {
  floatingHub.update({ jobs: [...state.jobs.values()], project: state.project });
  const locked = projectLocked();
  $('#versions-toggle').disabled = !state.project || state.restoring;
  $('#export-toggle').disabled = !state.project || !!state.preview || !!state.conflictId || state.restoring;
  $('#revision-preview').hidden = !state.preview;
  $('#project-conflict').hidden = state.conflictId !== state.project?.id;
  if (state.preview) $('#revision-preview-label').textContent = `正在回看 v${state.project.revision} · 最新版 v${state.preview.currentRevision}`;
  for (const node of document.querySelectorAll('#controls input, #interactions input, #interaction-reset, #interaction-save-retry')) node.disabled = locked;
  $('#camera-interact').disabled = locked || !state.project?.scene.interactions?.length;
  $('#revision-restore').disabled = state.restoring || !!state.conflictId;
  $('#revision-return').disabled = state.restoring;
  if (state.preview) $('#save-status').textContent = '历史预览 · 调整视角不会改写已保存版本';
  updateCreateState();
}
function handleConflict(error, id) {
  if (error.status !== 409 || state.project?.id !== id) return;
  state.conflictId = id;
  state.recomputePending = null; clearTimeout(state.recomputeTimer);
  state.explorationPending.delete(id); state.explorationErrors.delete(id);
  updateEditingState();
}
async function openVersions() {
  if (!state.project) return;
  const id = state.project.id, sequence = ++state.versionsRequest;
  $('#versions-project-title').textContent = state.project.title;
  $('#versions-list').replaceChildren(element('p', 'empty-note', '正在读取版本…'));
  $('#versions-message').hidden = true;
  if (!$('#versions-dialog').open) $('#versions-dialog').showModal();
  try {
    if (!state.preview && !state.conflictId) await flushProjectChanges();
    const data = await api(projectUrl(id, '/revisions'));
    if (sequence !== state.versionsRequest || state.project?.id !== id) return;
    const actions = { create: '开始探索', iterate: '继续修改', recompute: '参数实验', restore: '恢复版本' };
    $('#versions-list').replaceChildren(...data.revisions.map(revision => {
      const card = element('article', `revision-card${revision.is_current ? ' current' : ''}`);
      card.setAttribute('role', 'listitem'); card.dataset.revision = revision.revision;
      const top = element('header');
      top.append(element('strong', '', `v${revision.revision} · ${actions[revision.action] || '保存版本'}`), element('small', '', revision.is_current ? '当前版本' : formatDate(revision.updated)));
      card.append(top, element('p', '', revision.change_summary || revision.prompt || revision.title));
      card.append(button('button secondary', revision.is_current ? '查看最新版' : '回看此版本', async (event) => {
        const trigger = event.currentTarget; trigger.disabled = true;
        const canApply = () => sequence === state.versionsRequest && state.project?.id === id && $('#versions-dialog').open;
        try {
          if (!canApply()) return;
          if (revision.is_current) await loadProject(id, { canApply });
          else {
            const request = ++state.projectRequest;
            const result = await api(projectUrl(id, `/revisions/${revision.revision}`));
            if (!canApply() || request !== state.projectRequest) return;
            await showProject(result.project, { preview: { currentRevision: data.current_revision } });
          }
          if (canApply()) $('#versions-dialog').close();
        } catch (error) { if (canApply()) { $('#versions-message').textContent = message(error); $('#versions-message').hidden = false; } }
        finally { trigger.disabled = false; }
      }));
      return card;
    }));
  } catch (error) { if (sequence === state.versionsRequest) { $('#versions-message').textContent = message(error); $('#versions-message').hidden = false; } }
}
async function restoreVersion() {
  if (!state.preview || state.restoring || !state.project) return;
  const id = state.project.id, revision = state.project.revision;
  state.restoring = true; updateEditingState();
  try {
    const data = await api(projectUrl(id, '/restore'), { method: 'POST', body: { revision, expected_revision: state.preview.currentRevision } });
    if (state.project?.id !== id) return;
    await showProject(data.project);
    await refreshProjects(); toast(`已恢复 v${revision}，保存为 v${data.project.revision}`);
  } catch (error) { handleConflict(error, id); toast(message(error), true); }
  finally { state.restoring = false; updateEditingState(); }
}
async function loadProject(id, { canApply = () => true, ...options } = {}) {
  const request = ++state.projectRequest;
  if (!state.preview && !state.conflictId) await flushProjectChanges();
  if (!canApply()) return;
  const explorationVersion = state.explorationVersions.get(id) || 0;
  const data = await api(projectUrl(id));
  if (request !== state.projectRequest || state.disposed || !canApply()) return;
  if (state.project?.id === id) {
    // Reading a project must not roll back work completed while its response was in flight.
    if ((state.project.revision || 0) > (data.project.revision || 0)) data.project = { ...state.project };
    else if ((state.explorationVersions.get(id) || 0) !== explorationVersion) data.project.exploration = state.project.exploration;
  }
  state.conflictId = null;
  await showProject(data.project, options);
}
async function showProject(project, { preservePlayback = false, preview = null } = {}) {
  if (!project?.scene || !safeId(project.id)) throw new Error('项目数据不完整，无法显示场景。');
  const sameProject = project.id === state.project?.id;
  const oldTime = preservePlayback ? player.time : 0;
  const wasPlaying = preservePlayback ? player.playing : (state.preferences?.autoplay !== false && !state.preferences?.reduced_motion && !systemMotion.matches);
  const epoch = ++state.sceneEpoch;
  state.sceneLoading = true;
  state.preview = preview;
  state.project = project;
  if (!preview && (!sameProject || project.asset_id === state.assetId)) clearAsset();
  state.parameters = Object.fromEntries((project.scene.controls || []).map((control) => [control.id, control.value]));
  if (!sameProject || preview || project.revision !== state.displayedRevision) { state.visibility.clear(); state.selected = null; state.recomputePending = null; clearTimeout(state.recomputeTimer); }
  state.displayedRevision = project.revision;
  $('#scene-title').textContent = project.title || project.scene.title;
  $('#detail-title').textContent = project.scene.title;
  $('#scene-summary').textContent = project.scene.summary;
  $('#scene-meta').textContent = `${project.scene.mode.toUpperCase()} 动态解释 · ${project.scene.duration} 秒 · v${project.revision || 1}`;
  $('#scene-mode').textContent = project.scene.mode.toUpperCase();
  $('#evidence-label').textContent = { computed: '计算生成', schematic: '概念示意', image_annotation: '图片标注' }[project.scene.evidence] || '动态解释';
  $('#canvas-hint').textContent = '拖动时间轴探索 · 点击对象查看图层';
  $('#seek').max = project.scene.duration;
  $('#total-time').textContent = formatTime(project.scene.duration);
  $('#iterate-label').hidden = false;
  if (!preservePlayback || !sameProject) $('#iterate').checked = true;
  $('#save-status').textContent = `${savedMessage()} · v${project.revision || 1}`;
  $('#export-toggle').disabled = false;
  $('#play').disabled = true;
  $('#restart').disabled = true;
  $('#seek').disabled = true;
  renderAssumptions(project.scene.assumptions || []);
  renderSelection(project);
  renderInteractions(project);
  renderControls(project.scene.controls || []);
  renderSteps(project.scene.steps || [], project.scene.duration);
  renderLayers(project.scene.objects || []);
  renderProjects();
  updateEditingState();
  state.loadChain = state.loadChain.catch(() => {}).then(async () => {
    if (epoch !== state.sceneEpoch || state.disposed) return;
    await player.load(project.scene);
    if (epoch !== state.sceneEpoch || state.disposed) return;
    player.setInteractionValues?.(project.exploration?.values || {});
    player.setView?.(project.exploration?.camera || null);
    setManipulationMode(sameProject ? state.manipulationMode : project.scene.mode === '3d' ? 'observe' : 'interact');
    for (const [id, visible] of state.visibility) player.setVisible(id, visible);
    player.setSpeed(Number($('#speed').value));
    player.seek(Math.min(oldTime, project.scene.duration));
    if (state.selected) player.select(state.selected);
    if (wasPlaying) player.play();
    $('#canvas-empty').hidden = true;
    $('#play').disabled = false;
    $('#restart').disabled = false;
    $('#seek').disabled = false;
    updateEditingState();
    state.sceneLoading = false;
    syncInteractionValues(player.getInteractionValues?.() || project.exploration?.values || {});
    syncCameraState();
    updateTime({ time: player.time, duration: project.scene.duration, playing: player.playing });
  });
  try { await state.loadChain; }
  catch (error) {
    if (epoch !== state.sceneEpoch) return;
    state.sceneLoading = false;
    $('#empty-message').textContent = `场景加载失败：${message(error)}`;
    $('#canvas-empty').hidden = false;
    throw error;
  }
}
function renderAssumptions(items) {
  $('#assumptions').hidden = !items.length;
  const list = element('ul');
  list.append(...items.map((item) => element('li', '', item)));
  $('#assumptions').replaceChildren(element('strong', '', '解释边界'), list);
}
function renderSelection(project) {
  const scene = project.scene;
  const selection = scene.selection || project.proposal?.selection;
  const actualRenderer = scene.mode === '3d' ? 'Three.js' : 'Canvas 2D';
  const engine = scene.mode === '3d' ? 'threejs' : selection?.engine === 'manim' ? 'manim' : 'canvas2d';
  const labels = { threejs: 'Three.js · 三维建模', canvas2d: 'Canvas 2D · 二维可视化', manim: 'Manim · 数学动画' };
  const recipe = project.proposal?.recipe;
  const fallbackReason = scene.mode === '3d'
    ? '当前项目包含三维空间与立体对象，使用浏览器三维引擎呈现。'
    : recipe === 'formula'
      ? '当前项目以公式关系为主，使用二维画布与数学排版呈现。'
      : '当前项目为二维场景，使用画布呈现对象、轨迹与动态关系。';
  $('#scene-selection').hidden = false;
  $('#selection-title').textContent = labels[engine];
  $('#selection-reason').textContent = typeof selection?.reason === 'string' && selection.reason.trim() ? selection.reason : fallbackReason;
  $('#selection-renderer').textContent = engine === 'manim'
    ? `画布预览 ${actualRenderer} · 视频推荐 Manim`
    : `浏览器引擎 ${actualRenderer}${selection ? '' : ' · 按现有场景识别'}`;
  $('#scene-selection').dataset.engine = engine;
}
function setExplorationStatus(text, error = false) {
  $('#interaction-save-state').textContent = text;
  $('#interaction-save-state').classList.toggle('interaction-save-error', error);
  $('#interaction-save-retry').hidden = !error;
}
function setManipulationMode(mode) {
  state.manipulationMode = state.project?.scene.mode === '3d' ? mode : 'interact';
  player.setManipulationMode?.(state.manipulationMode);
  $('#camera-free').setAttribute('aria-pressed', String(state.manipulationMode === 'observe'));
  $('#camera-interact').setAttribute('aria-pressed', String(state.manipulationMode === 'interact'));
  const hasDrag = state.project?.scene.interactions?.some((item) => item.drag);
  $('#canvas-hint').textContent = state.project?.scene.mode === '3d'
    ? state.manipulationMode === 'observe' ? '拖动旋转 · 滚轮 / 双指缩放' : hasDrag ? '拖动可操控构件 · 空白处旋转视角' : '点击对象选择 · 使用侧栏调整构件'
    : hasDrag ? '拖动可操控对象 · 点击查看图层' : '拖动时间轴探索 · 点击对象查看图层';
}
function syncCameraState() {
  $('#camera-state').textContent = player.getView?.() ? '观察视角 · 已手动调整' : '默认镜头 · 跟随场景';
}
function renderInteractions(project) {
  const interactions = project.scene.interactions || [];
  const is3d = project.scene.mode === '3d';
  state.interactionNodes.clear();
  $('#camera-toolbar').hidden = !is3d;
  $('#camera-state').hidden = !is3d;
  $('#camera-interact').disabled = !interactions.length;
  $('#interaction-reset').hidden = !is3d && !interactions.length;
  $('#interaction-hint').textContent = interactions.length
    ? `${is3d ? '调整构件的允许自由度，或切换操控模式直接拖动。' : '调整对象的允许自由度，支持拖动的对象会在下方注明。'}修改会自动保存，不进行物理重算。`
    : is3d ? '此场景没有可操控构件，可自由旋转与缩放观察视角。' : project.scene.controls?.length ? '此场景没有构件自由度，可通过下方参数实验重算，或使用时间轴探索。' : '此场景没有构件自由度，可通过时间轴探索过程。';
  setExplorationStatus(state.explorationErrors.has(project.id) ? '保存失败' : interactions.length || is3d ? '已同步' : '无构件自由度', state.explorationErrors.has(project.id));
  $('#interactions').replaceChildren(...interactions.map((item, index) => {
    const row = element('div', 'interaction-control'); row.dataset.interactionId = item.id;
    const top = element('div', 'control-top');
    const label = element('label', '', item.label); label.htmlFor = `interaction-${index}`; top.append(label);
    const value = project.exploration?.values?.[item.id] ?? item.value;
    const input = element('input', item.kind === 'toggle' ? 'interaction-toggle' : 'interaction-slider');
    input.id = `interaction-${index}`; input.dataset.interactionId = item.id;
    input.type = item.kind === 'toggle' ? 'checkbox' : 'range';
    let numeric = null;
    if (item.kind === 'toggle') { input.checked = value === 1; top.append(input); row.append(top); }
    else {
      input.min = item.min; input.max = item.max; input.step = item.step; input.value = value;
      const wrap = element('span', 'control-value');
      numeric = element('input'); numeric.type = 'number'; numeric.min = item.min; numeric.max = item.max; numeric.step = item.step; numeric.value = value; numeric.setAttribute('aria-label', `${item.label}数值`);
      wrap.append(numeric, element('span', '', item.unit)); top.append(wrap);
      const limits = element('div', 'control-limits'); limits.append(element('span', '', item.min), element('span', '', item.max));
      row.append(top, input, limits);
      numeric.addEventListener('change', () => changeInteraction(item, numeric.value));
    }
    input.addEventListener('input', () => changeInteraction(item, input.type === 'checkbox' ? Number(input.checked) : input.value));
    if (item.description) row.append(element('p', 'interaction-description', item.description));
    if (item.drag) row.append(element('p', 'interaction-drag-note', item.drag.axis === 'horizontal' ? '可在画布左右拖动对应构件' : '可在画布上下拖动对应构件'));
    state.interactionNodes.set(item.id, { input, numeric, item });
    return row;
  }));
  syncInteractionValues(project.exploration?.values || Object.fromEntries(interactions.map((item) => [item.id, item.value])));
}
function syncInteractionValues(values) {
  for (const [id, node] of state.interactionNodes) {
    const value = values[id] ?? node.item.value;
    if (node.input.type === 'checkbox') node.input.checked = value === 1;
    else {
      node.input.value = value;
      node.input.style.setProperty('--progress', `${100 * (value - node.item.min) / (node.item.max - node.item.min)}%`);
      node.numeric.value = Number(Number(value).toFixed(6));
    }
  }
}
function changeInteraction(item, rawValue) {
  if (state.sceneLoading || projectLocked() || !player.setInteractionValues) return;
  const value = Number(rawValue);
  if (!Number.isFinite(value) || value < item.min || value > item.max) {
    syncInteractionValues(player.getInteractionValues()); toast(`请输入 ${item.min} 至 ${item.max} 之间的数值。`, true); return;
  }
  player.pause(); player.setInteractionValues({ [item.id]: value });
  syncInteractionValues(player.getInteractionValues()); queueExplorationSave();
}
function queueExplorationSave() {
  if (!state.project || state.sceneLoading || projectLocked() || !player.getInteractionValues) return;
  const id = state.project.id;
  const version = (state.explorationVersions.get(id) || 0) + 1;
  state.explorationVersions.set(id, version);
  const snapshot = { values: player.getInteractionValues(), camera: player.getView() };
  state.project.exploration = snapshot;
  state.explorationPending.set(id, { snapshot, version, revision: state.project.revision });
  state.explorationErrors.delete(id);
  setExplorationStatus('等待保存…');
  syncCameraState();
  clearTimeout(state.explorationTimer);
  state.explorationTimer = setTimeout(() => flushExploration().catch(() => {}), 450);
}
async function flushExploration({ duringRecompute = false } = {}) {
  clearTimeout(state.explorationTimer);
  if (state.recomputePromise && !duringRecompute) await state.recomputePromise;
  if (state.explorationSave) return state.explorationSave;
  if (!state.explorationPending.size) return;
  state.explorationSave = (async () => {
    while (state.explorationPending.size) {
      const [id, pending] = state.explorationPending.entries().next().value;
      state.explorationPending.delete(id);
      if (state.project?.id === id) setExplorationStatus('正在保存…');
      try {
        const data = await api(projectUrl(id, '/interaction-state'), { method: 'POST', body: { ...pending.snapshot, expected_revision: pending.revision } });
        state.explorationErrors.delete(id);
        if (state.project?.id === id && !state.preview && state.project.revision === pending.revision && data.project.revision === pending.revision) {
          if (data.project.updated !== undefined) state.project.updated = data.project.updated;
          if (state.explorationVersions.get(id) === pending.version) {
            state.project.exploration = data.project.exploration;
            setExplorationStatus('已保存');
            $('#save-status').textContent = `${savedMessage()} · v${state.project.revision || 1}`;
          }
        }
      } catch (error) {
        if (error.status !== 409 && !state.explorationPending.has(id)) state.explorationPending.set(id, pending);
        state.explorationErrors.set(id, message(error));
        if (state.project?.id === id) setExplorationStatus('保存失败', true);
        handleConflict(error, id);
        throw error;
      }
    }
  })();
  try { await state.explorationSave; }
  finally { state.explorationSave = null; }
}
function renderControls(controls) {
  $('#parameter-state').textContent = '调整后重算';
  if (!controls.length) { $('#controls').replaceChildren(element('p', 'empty-note', '这个场景没有可调参数。可在左侧补充想法，继续迭代。')); return; }
  $('#controls').replaceChildren(...controls.map((control, index) => {
    const row = element('div', 'control');
    const top = element('div', 'control-top');
    const label = element('label', '', control.label); label.htmlFor = `parameter-${index}`;
    const numericWrap = element('span', 'control-value');
    const numeric = element('input'); numeric.type = 'number'; numeric.value = control.value; numeric.min = control.min; numeric.max = control.max; numeric.step = control.step; numeric.setAttribute('aria-label', `${control.label}数值`);
    numericWrap.append(numeric, element('span', '', control.unit)); top.append(label, numericWrap);
    const range = element('input', 'control-slider'); range.type = 'range'; range.id = `parameter-${index}`; range.dataset.controlId = control.id;
    range.min = control.min; range.max = control.max; range.step = control.step; range.value = control.value;
    const paint = (value) => { range.style.setProperty('--progress', `${100 * (value - control.min) / Math.max(control.max - control.min, .001)}%`); };
    paint(control.value);
    const update = (value) => {
      const n = Number(value);
      if (!Number.isFinite(n) || n < control.min || n > control.max) return false;
      state.parameters[control.id] = n; range.value = n; numeric.value = n; paint(n);
      queueRecompute(); return true;
    };
    range.addEventListener('input', () => update(range.value));
    numeric.addEventListener('change', () => { if (!update(numeric.value)) { numeric.value = state.parameters[control.id]; toast(`请输入 ${control.min} 至 ${control.max} 之间的数值。`, true); } });
    const limits = element('div', 'control-limits'); limits.append(element('span', '', control.min), element('span', '', control.max));
    row.append(top, range, limits); return row;
  }));
}
function queueRecompute() {
  if (!state.project || projectLocked()) return;
  state.recomputePending = { id: state.project.id, parameters: { ...state.parameters } };
  $('#parameter-state').textContent = '等待重算…';
  clearTimeout(state.recomputeTimer);
  state.recomputeTimer = setTimeout(() => flushRecompute().catch(() => {}), 300);
}
async function flushRecompute() {
  clearTimeout(state.recomputeTimer);
  if (state.recomputePromise) return state.recomputePromise;
  if (!state.recomputePending) return;
  state.recomputing = true;
  state.recomputePromise = (async () => {
    while (state.recomputePending && !state.disposed) {
      const pending = state.recomputePending;
      state.recomputePending = null;
      if (state.project?.id !== pending.id) continue;
      $('#parameter-state').textContent = '正在重算…';
      try {
        await flushExploration({ duringRecompute: true });
        const data = await api(projectUrl(pending.id, '/recompute'), { method: 'POST', body: { parameters: pending.parameters, expected_revision: state.project.revision } });
        if (state.project?.id !== pending.id) continue;
        state.project.revision = data.project.revision;
        // Pending gestures belong to the newly recomputed scene with stable controls.
        const exploration = state.explorationPending.get(pending.id);
        if (exploration) exploration.revision = data.project.revision;
        if (!state.recomputePending) {
          await flushExploration({ duringRecompute: true });
          // A parameter gesture may arrive while its observation state is saving.
          if (state.project?.id !== pending.id || state.recomputePending) continue;
          if (state.project.exploration) data.project.exploration = state.project.exploration;
          await showProject(data.project, { preservePlayback: true });
          $('#parameter-state').textContent = '参数已更新';
          refreshProjects().catch(() => {});
        }
      } catch (error) {
        if (state.project?.id === pending.id) {
          if (error.status !== 409 && !state.recomputePending) state.recomputePending = pending;
          handleConflict(error, pending.id);
          $('#parameter-state').textContent = '重算失败'; toast(message(error), true);
          throw error;
        }
      }
    }
  })();
  try { await state.recomputePromise; }
  finally { state.recomputing = false; state.recomputePromise = null; }
}
async function flushProjectChanges() {
  // Recompute itself saves exploration. Waiting sequentially avoids a circular wait.
  do {
    await flushRecompute();
    await flushExploration();
  } while (state.recomputePending || state.recomputePromise || state.explorationPending.size || state.explorationSave);
}
function seekStep(step) {
  player.pause(); player.seek(step.start);
  if (step.focus?.length) player.select(step.focus[0]);
}
function renderSteps(steps, duration) {
  $('#step-count').textContent = `${steps.length} 步`;
  $('#steps').replaceChildren(...steps.map((step, index) => {
    const card = button('step-card', null, () => seekStep(step)); card.dataset.step = index;
    card.append(element('span', 'step-number', String(index + 1).padStart(2, '0')));
    const copy = element('div'); copy.append(element('strong', '', step.title), element('p', '', step.explanation)); card.append(copy);
    card.title = `${step.title} · ${step.start} 秒`; return card;
  }));
  if (!steps.length) $('#steps').append(element('p', 'empty-note', '自由探索画布中的对象。'));
  $('#step-tracks').replaceChildren(...steps.map((step, index) => {
    const track = button('step-track', `${String(index + 1).padStart(2, '0')} ${step.title}`, () => seekStep(step));
    track.dataset.step = index; track.style.flex = Math.max(.1, step.end - step.start);
    track.title = `${step.title}（${step.start}–${step.end} 秒）`; return track;
  }));
  $('#timeline-ticks').replaceChildren(...Array.from({ length: 7 }, (_, index) => element('span', '', `${Number((duration * index / 6).toFixed(1))}s`)));
}
function renderLayers(objects) {
  $('#layer-count').textContent = objects.length;
  $('#layers').replaceChildren(...objects.map((object) => {
    const row = element('div', 'layer'); row.dataset.layerId = object.id;
    const select = button('layer-select', null, () => player.select(object.id));
    const swatch = element('span', 'layer-swatch'); swatch.style.backgroundColor = /^#[0-9a-f]{6}$/i.test(object.color) ? object.color : '#7be7c4';
    select.append(swatch, element('span', 'layer-name', object.label || object.text || KINDS[object.kind] || object.id), element('span', 'layer-type', KINDS[object.kind] || object.kind));
    const visibility = button('layer-visibility', state.visibility.get(object.id) === false ? '○' : '◉', () => {
      const visible = state.visibility.get(object.id) === false;
      state.visibility.set(object.id, visible); player.setVisible(object.id, visible);
      visibility.textContent = visible ? '◉' : '○';
      visibility.setAttribute('aria-label', `${visible ? '隐藏' : '显示'}图层 ${object.label || object.id}`);
      visibility.setAttribute('aria-pressed', String(visible));
      row.classList.toggle('hidden-layer', !visible);
    });
    const visible = state.visibility.get(object.id) !== false;
    visibility.setAttribute('aria-label', `${visible ? '隐藏' : '显示'}图层 ${object.label || object.id}`);
    visibility.setAttribute('aria-pressed', String(visible)); row.classList.toggle('hidden-layer', !visible);
    row.append(select, visibility); return row;
  }));
  selectedObject(state.selected);
}
function selectedObject(id) {
  state.selected = id;
  for (const row of document.querySelectorAll('.layer')) row.classList.toggle('selected', row.dataset.layerId === id);
  const object = state.project?.scene.objects.find((item) => item.id === id);
  $('#selected-object').hidden = !object;
  if (object) {
    $('#selected-object').textContent = `${object.label || object.id} · ${KINDS[object.kind] || object.kind}\n位置 ${Number(object.x || 0).toFixed(2)}, ${Number(object.y || 0).toFixed(2)}${state.project.scene.mode === '3d' ? `, ${Number(object.z || 0).toFixed(2)}` : ''} · 缩放 ${object.scale ?? 1}`;
    const edit = button('button secondary', '继续修改这个对象', () => {
      $('#iterate').checked = true;
      if (!$('#prompt').value.trim()) $('#prompt').value = `请修改「${object.label || object.text || object.id}」（对象 ${object.id}），保留其他内容：`;
      updatePromptCount(); updateCreateState(); switchTabs(['creation', 'history'], 'creation'); $('#prompt').focus();
      $('#prompt').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
    edit.disabled = projectLocked(); $('#selected-object').append(edit);
  }
}
function updateTime({ time, duration, playing }) {
  $('#current-time').textContent = formatTime(time);
  $('#total-time').textContent = formatTime(duration);
  $('#seek').value = time;
  $('#seek').style.setProperty('--progress', `${Math.max(0, Math.min(100, time / (duration || 1) * 100))}%`);
  $('#play-symbol').textContent = playing ? 'Ⅱ' : '▶';
  $('#play').setAttribute('aria-label', playing ? '暂停动画' : '播放动画');
  const steps = state.project?.scene.steps || [];
  for (const node of document.querySelectorAll('[data-step]')) {
    const step = steps[Number(node.dataset.step)];
    node.classList.toggle('active', !!step && time >= step.start && (time < step.end || time === duration && step.end === duration));
  }
}
function togglePlay() {
  if (!state.project || $('#play').disabled) return;
  if (player.playing) player.pause();
  else { if (player.time >= state.project.scene.duration) player.seek(0); player.play(); }
}
async function createScene(sample = null, { automatic = false } = {}) {
  if (state.submitting || state.uploading || state.restoringDraft || state.accountTransition || (state.createJob && ACTIVE.has(state.jobs.get(state.createJob)?.status))) return;
  if (!sample && state.publicMode && !state.account?.authenticated) { accountMenu?.open('登录后即可创作自己的内容；示例可以直接体验。'); return; }
  const prompt = sample?.prompt || $('#prompt').value.trim();
  const targetId = !sample && state.project && $('#iterate').checked ? state.project.id : null;
  if (targetId && projectLocked()) { formMessage('请先返回最新版，或等当前修改完成后再继续。'); return; }
  if (!sample && !prompt && !state.assetId) { formMessage('写下一点想法，或上传一张参考图片。'); $('#prompt').focus(); return; }
  if (!sample) {
    const provider = state.bootstrap?.providers?.find((item) => item.id === $('#provider').value);
    if (!provider?.available) { formMessage(provider?.message || '所选模型暂不可用，请先连接模型，或使用下方本地示例。', true); return; }
  }
  state.submitting = true; formMessage(); updateCreateState();
  if (!automatic) switchTabs(['detail', 'process'], 'process');
  if (sample && !automatic) { $('#prompt').value = sample.prompt || ''; updatePromptCount(); }
  const body = {
    prompt, provider: $('#provider').value, duration: Number($('input[name="duration"]:checked').value),
    request_key: crypto.randomUUID(),
  };
  try {
    if (!state.preview && !state.conflictId) await flushProjectChanges();
    if (targetId && targetId !== state.project?.id) throw new Error('当前项目已切换，输入已保留，请检查后重新提交。');
    if (sample) body.sample = sample.id;
    else {
      if (state.assetId) body.asset_id = state.assetId;
      if (targetId) { body.parent_id = targetId; body.expected_revision = state.project.revision; }
    }
    const data = await api('/api/jobs', { method: 'POST', body });
    state.createJob = data.job.id; state.autoOpen.add(data.job.id);
    await observeJob(data.job);
    if (!automatic) toast(sample ? '正在准备本地示例' : '创作任务已开始，你可以继续查看当前场景');
  } catch (error) {
    if (targetId) handleConflict(error, targetId);
    formMessage(message(error), true);
    if (!state.project) { $('#empty-message').textContent = message(error); $('#retry-bootstrap').hidden = false; }
  } finally { state.submitting = false; updateCreateState(); }
}
function schedulePoll(id, delay = 900) {
  if (state.disposed || state.timers.has(id)) return;
  state.timers.set(id, setTimeout(async () => {
    state.timers.delete(id);
    try { const data = await api(jobUrl(id)); await observeJob(data.job); }
    catch (error) {
      const job = state.jobs.get(id);
      if (job && ACTIVE.has(job.status)) { job.connectionError = message(error); renderJobs(); schedulePoll(id, 3500); }
    }
  }, delay));
}
async function observeJob(job, { historical = false } = {}) {
  if (!job?.id) return;
  state.jobs.set(job.id, job); renderJobs(); updateEditingState();
  if (ACTIVE.has(job.status)) { schedulePoll(job.id); return; }
  clearTimeout(state.timers.get(job.id)); state.timers.delete(job.id);
  if (state.handled.has(job.id)) return;
  state.handled.add(job.id);
  if (job.kind === 'create' && job.status === 'completed' && job.project_id) {
    await refreshProjects().catch(() => {});
    if (state.autoOpen.has(job.id)) {
      state.autoOpen.delete(job.id);
      try { await loadProject(job.project_id); switchTabs(['detail', 'process'], 'detail'); }
      catch (error) { toast(message(error), true); }
    }
  } else if (!historical && job.status === 'needs_input') {
    formMessage(job.message || '请补充你希望解释的内容，然后重新生成。');
    switchTabs(['detail', 'process'], 'process');
  } else if (!historical && job.status === 'failed') {
    toast(job.message || '任务执行失败，请查看过程面板。', true);
  } else if (!historical && job.kind === 'export' && job.status === 'completed') {
    toast('视频已生成，可在过程面板预览或下载');
  }
  if (!state.project && (job.status === 'failed' || job.status === 'cancelled' || job.status === 'needs_input')) $('#empty-message').textContent = job.message || '可以选择另一个示例继续探索。';
}
function renderJobs() {
  const jobs = [...state.jobs.values()].sort((a, b) => String(b.created || '').localeCompare(String(a.created || '')));
  floatingHub.update({ jobs, project: state.project });
  $('#active-jobs').hidden = !jobs.some((job) => ACTIVE.has(job.status));
  $('#job-count').textContent = `${jobs.length} 个任务`;
  if (!jobs.length) return;
  $('#jobs').replaceChildren(...jobs.map((job) => {
    const card = element('article', 'job-card'); card.dataset.jobId = job.id; card.dataset.status = job.status;
    const top = element('div', 'job-top'); top.append(element('span', 'job-kind', job.kind === 'export' ? '视频导出' : '场景创作'), element('span', `job-status ${job.status}`, STATUS[job.status] || job.status)); card.append(top);
    card.append(element('p', 'job-message', job.message || job.stage || '任务已创建'));
    if (ACTIVE.has(job.status)) {
      const progress = element('div', `job-progress${job.progress == null ? ' indeterminate' : ''}`);
      progress.setAttribute('role', 'progressbar'); progress.setAttribute('aria-label', '任务进度'); progress.setAttribute('aria-valuemin', '0'); progress.setAttribute('aria-valuemax', '100');
      const fill = element('span');
      if (job.progress != null) { const n = Math.max(0, Math.min(100, Number(job.progress))); fill.style.width = `${n}%`; progress.setAttribute('aria-valuenow', n); }
      progress.append(fill); card.append(progress);
    }
    if (job.events?.length) {
      const events = element('ol', 'job-events');
      events.append(...job.events.slice(-6).map((event) => element('li', '', event.message || event.stage))); card.append(events);
    }
    if (job.error) card.append(element('p', 'job-error', job.message || '任务执行失败，已有版本保持可用。'));
    if (job.connectionError) card.append(element('p', 'job-error', `${job.connectionError} 正在尝试恢复状态。`));
    const actions = element('div', 'job-footer');
    if (ACTIVE.has(job.status)) actions.append(button('button secondary', '取消任务', async (event) => {
      event.currentTarget.disabled = true;
      try { const data = await api(jobUrl(job.id, '/cancel'), { method: 'POST', body: {} }); await observeJob(data.job); }
      catch (error) { toast(message(error), true); renderJobs(); }
    }));
    if (job.status === 'needs_input') actions.append(button('button primary', '补充说明', () => {
      switchTabs(['creation', 'history'], 'creation'); formMessage(job.message || '请补充说明后重新生成。'); $('#prompt').focus();
    }));
    if (job.project_id && job.status === 'completed') actions.append(button('button secondary', '打开场景', () => {
      state.autoOpen.clear(); loadProject(job.project_id).then(() => switchTabs(['detail', 'process'], 'detail')).catch((error) => toast(message(error), true));
    }));
    if (job.kind === 'export' && job.status === 'completed' && safeId(job.id)) {
      const preview = element('a', 'button primary', '预览视频'); preview.href = `/api/media/${encodeURIComponent(job.id)}`; preview.target = '_blank'; preview.rel = 'noopener';
      const download = element('a', 'button secondary', '下载 MP4'); download.href = `/api/media/${encodeURIComponent(job.id)}?download=true`; download.download = `${job.id}.mp4`;
      actions.append(preview, download);
    }
    if (actions.childNodes.length) card.append(actions);
    return card;
  }));
}
async function uploadImage(file) {
  if (!file || state.uploading) return false;
  const uploadToken=++state.assetRestore;state.restoringDraft=false;
  if (state.publicMode && !state.account?.authenticated) { accountMenu?.open('登录后可上传参考图片，文件仅在自己的空间中使用。'); return false; }
  if (!/^image\/(png|jpeg|webp|gif)$/i.test(file.type)) { toast('请选择 PNG、JPEG、WebP 或 GIF 图片。', true); return false; }
  if (file.size > 5 * 1024 * 1024) { toast('图片不能超过 5 MB，请缩小后再上传。', true); return false; }
  state.uploading = true; updateCreateState();
  try {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('无法读取图片，请重新选择。')); reader.readAsDataURL(file);
    });
    const data = await api('/api/assets', { method: 'POST', body: { data_url: dataUrl } });
    if(uploadToken!==state.assetRestore || state.accountTransition || state.disposed)return false;
    const preview=new Image();preview.src=assetUrl(data.asset_id);await preview.decode();
    if(uploadToken!==state.assetRestore || state.accountTransition || state.disposed)return false;
    $('#asset-image').src=preview.src;state.assetId=data.asset_id;
    $('#asset-preview').hidden = false; setInputMode('image'); toast('图片已添加，可以描述你想解释的内容');
    return true;
  } catch (error) { toast(message(error), true); return false; }
  finally { state.uploading = false; updateCreateState(); $('#image-file').value = ''; }
}
function clearAsset() {
  state.assetRestore++; state.restoringDraft = false;
  state.assetId = null; $('#asset-preview').hidden = true; $('#asset-image').removeAttribute('src'); setInputMode(state.inputMode);
  updateCreateState();
}
function updatePromptCount() { $('#prompt-count').textContent = `${$('#prompt').value.length} / 6000`; }
function startNew() {
  state.autoOpen.clear(); $('#prompt').value = ''; updatePromptCount(); clearAsset(); setInputMode(state.preferences?.default_input || 'text');
  $('#iterate').checked = false; formMessage(); switchTabs(['creation', 'history'], 'creation'); $('#prompt').focus();
  toast('已准备新探索，当前画布可继续查看');
}
function openExport() {
  if (!state.project || state.preview || state.conflictId) return;
  state.exportProjectId = state.project.id;
  state.exportSceneMode = state.project.scene.mode;
  $('#export-project-title').textContent = state.project.title;
  $('#export-message').hidden = true;
  $('#export-message').classList.remove('error');
  const renderers = state.bootstrap?.renderers || {};
  const manimAvailable = !!renderers.manim && state.exportSceneMode === '2d';
  const preferManim = state.project.scene.selection?.engine === 'manim' && manimAvailable;
  const actualRenderer = state.exportSceneMode === '3d' ? 'Three.js' : 'Canvas 2D';
  $('#browser-engine-title').textContent = `浏览器渲染 · ${actualRenderer}`;
  $('#browser-engine-status').textContent = renderers.browser ? '逐帧还原当前画布与时间轴' : '本机尚未配置浏览器渲染';
  $('#manim-engine').disabled = !manimAvailable;
  $('#manim-engine').checked = preferManim;
  $('#manim-status').textContent = state.exportSceneMode === '3d'
    ? '仅支持二维场景 · 三维请使用浏览器渲染'
    : renderers.manim ? '二维数学动画渲染' : '本机尚未配置 Manim';
  $('input[name="export-engine"][value="browser"]').disabled = !renderers.browser;
  $('input[name="export-engine"][value="browser"]').checked = !!renderers.browser && !preferManim;
  if (!renderers.browser && manimAvailable) $('#manim-engine').checked = true;
  $('#export-video').disabled = !(renderers.browser || manimAvailable) || state.exporting;
  if (!renderers.browser && !manimAvailable) {
    $('#export-message').textContent = state.exportSceneMode === '3d'
      ? '当前三维场景需要浏览器渲染，但本机尚未配置该引擎。你仍可下载场景文件。'
      : '本机尚未配置可用的视频渲染引擎。你仍可下载场景文件。';
    $('#export-message').hidden = false;
  }
  $('#export-dialog').showModal(); $('#export-toggle').setAttribute('aria-expanded', 'true');
}
async function exportVideo() {
  if (state.publicMode && !state.account?.authenticated) { $('#export-dialog').close(); accountMenu?.open('登录后可导出自己的可视化视频。'); return; }
  const projectId = state.exportProjectId;
  const engine = $('input[name="export-engine"]:checked')?.value;
  if (!projectId || !engine || state.exporting) return;
  if (engine === 'manim' && state.exportSceneMode !== '2d') {
    $('#export-message').textContent = 'Manim 仅支持二维场景，请选择浏览器渲染导出当前三维场景。';
    $('#export-message').hidden = false;
    return;
  }
  state.exporting = true; $('#export-video').disabled = true; $('#export-message').hidden = true;
  try {
    await flushProjectChanges();
    const data = await api(projectUrl(projectId, '/export'), { method: 'POST', body: { engine, fps: Number($('#export-fps').value) } });
    await observeJob(data.job); $('#export-dialog').close(); switchTabs(['detail', 'process'], 'process'); toast('视频正在后台渲染，当前场景仍可播放');
  } catch (error) { $('#export-message').textContent = message(error); $('#export-message').hidden = false; $('#export-message').classList.add('error'); }
  finally { state.exporting = false; $('#export-video').disabled = false; }
}
async function bootstrap() {
  $('#retry-bootstrap').hidden = true;
  $('#connection').className = 'connection'; $('#connection-text').textContent = '正在连接';
  try {
    const data = await api('/api/bootstrap'); state.bootstrap = data; state.csrf = data.csrf; state.publicMode = !!data.public_mode;
    if (!accountMenu) accountMenu = mountAccountMenu({ api, beforeNavigate: beforeAccountNavigate, onSessionChange: syncAccount, onBusyChange: accountBusy, notify: toast });
    await accountMenu.ready;
    try { await workspaceCenter.loadPreferences(); } catch(error) { toast(`偏好设置暂未读取：${message(error)}`,true); }
    $('#connection').classList.add('connected'); $('#connection-text').textContent = '创作引擎已连接';
    let preferred; try { preferred = localStorage.getItem('wisdom.creator.provider'); } catch {}
    const available = data.providers?.find((item) => item.id === preferred && item.available && item.permitted!==false);
    $('#provider').value = available?.id || 'qwen';
    refreshProviderChoices(); renderSamples(data.samples || []); updateCreateState();
    const results = await Promise.allSettled([refreshProjects(), api('/api/jobs')]);
    if (results[1].status === 'fulfilled') {
      for (const job of results[1].value.jobs || []) {
        state.jobs.set(job.id, job);
        if (ACTIVE.has(job.status)) {
          schedulePoll(job.id);
          if (job.kind === 'create' && !state.createJob) { state.createJob = job.id; state.autoOpen.add(job.id); }
        } else state.handled.add(job.id);
      }
      renderJobs(); updateCreateState();
    }
    const locationParams = new URLSearchParams(location.search);
    const requestedSample = data.samples?.find(sample => sample.id === locationParams.get('sample'));
    if (requestedSample) { locationParams.delete('sample'); history.replaceState(null, '', `${location.pathname}${locationParams.size ? '?' + locationParams : ''}${location.hash}`); await createScene(requestedSample); }
    else if (results[0].status === 'fulfilled' && results[0].value.length) await loadProject(results[0].value[0].id);
    else if (state.createJob) $('#empty-message').textContent = '正在恢复尚未完成的创作任务…';
    else if (results.some((result) => result.status === 'rejected')) {
      $('#empty-message').textContent = '历史记录暂时无法加载，请重新连接后继续。'; $('#retry-bootstrap').hidden = false;
    } else if (data.samples?.length) await createScene(data.samples[0], { automatic: true });
    else { $('#empty-message').textContent = '输入想法，开始你的第一段动态解释。'; }
    await restoreAccountDraft();
    try { const notice=sessionStorage.getItem('wiscomper.account-notice');sessionStorage.removeItem('wiscomper.account-notice');if(notice)toast(notice); } catch {}
  } catch (error) {
    $('#connection').classList.add('error'); $('#connection-text').textContent = '连接中断';
    $('#empty-message').textContent = message(error); $('#retry-bootstrap').hidden = false;
    formMessage(message(error), true); updateCreateState();
  }
}

$('#creation-tab').addEventListener('click', () => switchTabs(['creation', 'history'], 'creation'));
$('#login-for-creation').addEventListener('click', () => accountMenu?.open());
for (const node of document.querySelectorAll('[data-workspace-jump]')) node.addEventListener('click', () => {
  const where = node.dataset.workspaceJump;
  if (where === 'create') { switchTabs(['creation','history'],'creation'); $('#prompt').focus({preventScroll:true}); }
  if (where === 'details' || where === 'jobs') switchTabs(['detail','process'],where === 'jobs' ? 'process' : 'detail');
  const target = $(where === 'create' ? '.creation-panel' : where === 'preview' ? '.stage-panel' : '.inspector-panel');
  target.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
});
for (const view of ['library', 'knowledge', 'help']) $(`#open-${view}`).addEventListener('click', () => knowledge.open(view));
for (const entry of document.querySelectorAll('[data-ecosystem-action]')) entry.addEventListener('click',()=>{entry.closest('details')?.removeAttribute('open');ecosystemAction(entry.dataset.ecosystemAction).catch(error=>toast(message(error),true));});
for (const entry of document.querySelectorAll('[data-study-kind]')) entry.addEventListener('click',()=>{workspaceCenter.capture(entry.dataset.studyKind).catch(error=>toast(message(error),true));});
$('#dismiss-welcome').addEventListener('click',()=>workspaceCenter.savePreferences({tutorial_completed:true}).catch(()=>{}));
document.addEventListener('click',event=>{if(!event.target.closest('.workspace-more'))$('.workspace-more')?.removeAttribute('open');});
$('#history-tab').addEventListener('click', () => { switchTabs(['creation', 'history'], 'history'); refreshProjects().catch((error) => toast(message(error), true)); });
$('#detail-tab').addEventListener('click', () => switchTabs(['detail', 'process'], 'detail'));
$('#process-tab').addEventListener('click', () => switchTabs(['detail', 'process'], 'process'));
$('#refresh-history').addEventListener('click', () => refreshProjects().catch((error) => toast(message(error), true)));
$('#sample-filter').addEventListener('change', () => { renderSamples(state.bootstrap?.samples || []); updateCreateState(); });
$('#iterate').addEventListener('change', updateCreateState);
$('#versions-toggle').addEventListener('click', openVersions);
$('#versions-dialog').addEventListener('close', () => { state.versionsRequest++; });
$('#revision-return').addEventListener('click', () => loadProject(state.project.id).catch(error => toast(message(error), true)));
$('#revision-restore').addEventListener('click', restoreVersion);
$('#reload-latest').addEventListener('click', () => loadProject(state.project.id).catch(error => toast(message(error), true)));
document.querySelectorAll('.input-tab').forEach((tab) => tab.addEventListener('click', () => setInputMode(tab.dataset.mode)));
$('#provider').addEventListener('change', () => { try { localStorage.setItem('wisdom.creator.provider', $('#provider').value); } catch {} providerStatus(); });
$('#prompt').addEventListener('input', updatePromptCount);
$('#prompt').addEventListener('keydown', (event) => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); createScene(); } });
$('#create-form').addEventListener('submit', (event) => { event.preventDefault(); createScene(); });
$('#upload-image').addEventListener('click', () => $('#image-file').click());
$('#image-file').addEventListener('change', (event) => uploadImage(event.target.files?.[0]));
$('#remove-image').addEventListener('click', clearAsset);
$('#composer').addEventListener('paste', (event) => {
  const image = [...(event.clipboardData?.items || [])].find((item) => item.type.startsWith('image/'));
  if (image) { event.preventDefault(); uploadImage(image.getAsFile()); }
});
$('#composer').addEventListener('dragover', (event) => { event.preventDefault(); $('#composer').classList.add('dragover'); });
$('#composer').addEventListener('dragleave', () => $('#composer').classList.remove('dragover'));
$('#composer').addEventListener('drop', (event) => { event.preventDefault(); $('#composer').classList.remove('dragover'); uploadImage(event.dataTransfer?.files?.[0]); });
$('#new-project').addEventListener('click', startNew);
$('#play').addEventListener('click', togglePlay);
$('#restart').addEventListener('click', () => { player.seek(0); player.play(); });
$('#seek').addEventListener('input', (event) => { const time = Number(event.target.value); player.pause(); player.seek(time); });
$('#speed').addEventListener('change', (event) => player.setSpeed(Number(event.target.value)));
$('#scene-host').addEventListener('scene-time', (event) => updateTime(event.detail));
$('#scene-host').addEventListener('scene-select', (event) => selectedObject(event.detail.id));
$('#scene-host').addEventListener('scene-interaction', (event) => {
  if (state.sceneLoading) return;
  syncInteractionValues(event.detail.values);
  queueExplorationSave();
});
$('#scene-host').addEventListener('scene-view', () => { if (!state.sceneLoading) queueExplorationSave(); });
$('#camera-free').addEventListener('click', () => setManipulationMode('observe'));
$('#camera-interact').addEventListener('click', () => setManipulationMode('interact'));
$('#camera-reset').addEventListener('click', () => { player.setView?.(null); syncCameraState(); queueExplorationSave(); });
$('#interaction-reset').addEventListener('click', () => {
  player.pause(); player.resetExploration?.();
  syncInteractionValues(player.getInteractionValues?.() || {}); syncCameraState(); queueExplorationSave();
});
$('#interaction-save-retry').addEventListener('click', () => flushExploration().catch((error) => toast(message(error), true)));
document.addEventListener('keydown', (event) => {
  if (event.code === 'Space' && !event.repeat && !event.altKey && !event.ctrlKey && !event.metaKey && !document.querySelector('dialog[open]') && !event.target.closest('input,textarea,select,button,a,[contenteditable="true"]')) { event.preventDefault(); togglePlay(); }
});
$('#export-toggle').addEventListener('click', openExport);
$('#export-dialog').addEventListener('close', () => $('#export-toggle').setAttribute('aria-expanded', 'false'));
$('#export-dialog').addEventListener('click', (event) => { if (event.target === $('#export-dialog')) { const r = event.target.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.target.close(); } });
$('#export-json').addEventListener('click', async () => {
  if (!state.exportProjectId) return;
  const id = state.exportProjectId;
  try {
    await flushProjectChanges();
    const link = element('a'); link.href = projectUrl(id, '/scene?bundle=true'); link.download = `${id}.json`; document.body.append(link); link.click(); link.remove(); $('#export-dialog').close();
  } catch (error) { $('#export-message').textContent = `当前修改尚未保存：${message(error)}`; $('#export-message').hidden = false; $('#export-message').classList.add('error'); }
});
$('#export-video').addEventListener('click', exportVideo);
$('#retry-bootstrap').addEventListener('click', bootstrap);
window.addEventListener('pagehide', () => {
  state.disposed = true; clearTimeout(state.recomputeTimer); clearTimeout(state.toastTimer); clearTimeout(state.explorationTimer);
  for (const timer of state.timers.values()) clearTimeout(timer);
  player.dispose();
  knowledge.dispose(); floatingHub.dispose(); workspaceCenter.dispose();onboarding.dispose();sketchInput.dispose();globalSearch.dispose();accountMenu?.dispose();
  systemTheme.removeEventListener('change',applySystemPreferences);systemMotion.removeEventListener('change',applySystemPreferences);
}, { once: true });
window.addEventListener('beforeunload', (event) => {
  if (knowledge.dirty || workspaceCenter.dirty || state.explorationPending.size || state.explorationSave || state.recomputePending || state.recomputePromise) { event.preventDefault(); event.returnValue = ''; }
});
bootstrap();
