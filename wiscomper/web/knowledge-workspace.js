import katex from '/vendor/katex/katex.mjs';
import { graphPath, mountNebulaGraph } from './nebula-graph.js';

const el = (tag, className = '', text) => { const n = document.createElement(tag); n.className = className; if (text !== undefined) n.textContent = text; return n; };
const btn = (text, action, className = 'button secondary') => { const n = el('button', className, text); n.type = 'button'; n.addEventListener('click', action); return n; };
const normalize = value => String(value || '').trim().replace(/^\$\$([\s\S]*)\$\$$/, '$1').replace(/^\$([^$]*)\$$/, '$1').replace(/^\\\[([\s\S]*)\\\]$/, '$1').replace(/^\\\(([\s\S]*)\\\)$/, '$1').trim();
function math(node, latex) {
  const source = normalize(latex);
  node.replaceChildren(); node.classList.remove('kw-math-fallback');
  if (!source) { node.textContent = '输入 LaTeX，在这里预览'; return true; }
  try { katex.render(source, node, { displayMode: true, throwOnError: true, trust: false, strict: 'error', maxExpand: 300, maxSize: 15 }); return true; }
  catch { node.textContent = source; node.classList.add('kw-math-fallback'); return false; }
}

export function mountKnowledgeWorkspace({ api, onAction, getProject, getPrompt, notify }) {
  const dialog = el('dialog', 'kw-dialog'); dialog.id = 'knowledge-workspace'; dialog.setAttribute('aria-labelledby', 'kw-title');
  // Only fixed application markup is inserted as HTML. Saved content uses textContent/KaTeX.
  dialog.innerHTML = `
    <header class="kw-header"><div><span class="section-eyebrow">连接想法与作品</span><h2 id="kw-title">探索空间</h2></div><button class="icon-button" id="kw-close" aria-label="关闭探索空间" type="button">×</button></header>
    <nav class="kw-tabs" aria-label="探索空间栏目"><button type="button" data-view="library" aria-pressed="true">ƒ 公式库</button><button type="button" data-view="knowledge" aria-pressed="false">◈ 知识图谱</button><button type="button" data-view="help" aria-pressed="false">? 使用帮助</button></nav>
    <p id="kw-message" class="kw-message" role="status" hidden></p>
    <section id="kw-library" class="kw-view">
      <div class="kw-intro"><div><h3>让公式成为下一次探索的起点</h3><p>保存公式与笔记，连接已有作品，随时带回创作。</p></div><button type="button" class="button primary" id="kw-new">＋ 新增公式</button></div>
      <div class="kw-library-tools"><label class="kw-search"><span class="sr-only">搜索公式</span><input id="kw-search" type="search" maxlength="200" placeholder="搜索名称、公式、标签或笔记"></label><select id="kw-scope" aria-label="公式范围"><option value="all">全部公式</option><option value="saved">我的公式</option><option value="builtin">常用公式</option><option value="favorites">我的收藏</option><option value="archived">已归档</option></select><button type="button" class="button secondary" id="kw-import">导入</button><button type="button" class="button secondary" id="kw-export">导出</button><input id="kw-import-file" type="file" accept=".json,application/json" hidden></div>
      <div class="kw-context-tools"><button type="button" class="button quiet" id="kw-capture">收录当前场景的公式</button><button type="button" class="button quiet" id="kw-save-input">保存输入的公式</button><span id="kw-count"></span></div>
      <div id="kw-library-list" class="kw-library-list" aria-live="polite"></div>
      <form id="kw-editor" class="kw-editor" hidden>
        <div class="section-heading"><h3 id="kw-editor-title">新增公式</h3><button type="button" class="icon-button" id="kw-editor-close" aria-label="收起公式编辑">×</button></div>
        <label>名称<input id="kw-form-title" required maxlength="120" placeholder="给这个公式起个名字"></label>
        <label>LaTeX 公式<textarea id="kw-form-latex" required maxlength="4000" rows="3" spellcheck="false" placeholder="例如：E = mc^2"></textarea></label>
        <div id="kw-form-preview" class="kw-math kw-editor-preview" aria-label="公式实时预览"></div>
        <label>笔记<textarea id="kw-form-note" maxlength="2000" rows="2" placeholder="使用条件、解释或下次想探索的内容"></textarea></label>
        <label>标签<input id="kw-form-tags" maxlength="200" placeholder="逗号分隔，最多8个，例如：物理，能量"></label>
        <label class="kw-check"><input id="kw-form-link" type="checkbox">关联当前项目</label>
        <p id="kw-editor-message" role="status"></p><div class="kw-editor-actions"><button type="submit" class="button primary" id="kw-save">保存公式</button><button type="button" class="button secondary" id="kw-editor-cancel">取消</button></div>
      </form>
    </section>
    <section id="kw-knowledge" class="kw-view" hidden>
      <div class="kw-intro"><div><h3>沿着关系，发现下一步</h3><p>公式、主题、示例与作品连在一起。点击节点查看，沿连线继续探索。</p></div><button type="button" class="button secondary" id="kw-graph-reset">回到中心</button></div>
      <label class="kw-search"><span class="sr-only">搜索图谱节点</span><input id="kw-graph-search" type="search" placeholder="寻找一个主题、公式或项目" maxlength="200"></label>
      <div id="kw-graph-results" class="kw-graph-results" hidden></div>
      <div class="kw-graph-toolbar"><div class="kw-graph-modes" aria-label="图谱显示方式"><button id="kw-graph-3d" type="button" aria-pressed="true">3D 星图</button><button id="kw-graph-2d" type="button" aria-pressed="false">2D 关系图</button></div><div class="kw-graph-tools"><button id="kw-graph-motion" type="button" aria-pressed="true">暂停漫游</button><button id="kw-graph-zoom-in" type="button" aria-label="放大图谱">＋</button><button id="kw-graph-zoom-out" type="button" aria-label="缩小图谱">−</button></div></div>
      <p id="kw-graph-status" class="kw-graph-status" role="status"></p>
      <div class="kw-graph-layout"><div id="kw-graph" class="kw-graph" aria-label="知识关系图"></div><aside id="kw-node-detail" class="kw-node-detail"></aside></div>
      <nav id="kw-stations" class="kw-stations" aria-label="沿知识连线到站"></nav>
      <div class="kw-route"><button id="kw-graph-back" type="button" class="button secondary">← 上一站</button><span id="kw-graph-count"></span><button id="kw-graph-more" type="button" class="button secondary">更多关联 →</button></div>
    </section>
    <section id="kw-help" class="kw-view kw-help" hidden>
      <h3>从一个想法，到一个可以探索的世界</h3>
      <ol><li><strong>写下对象与关系</strong><p>描述想看见什么、如何运动、想调整什么；也可以输入公式或上传参考图。只有点击生成才会调用模型。</p></li><li><strong>选择模型，开始创作</strong><p>ChatGPT、Claude 或 Qwen 会按内容选择二维画布、三维结构或数学动画。Qwen 的文字与图片输入使用对应的语言或视觉模型。</p></li><li><strong>在同一作品里继续改</strong><p>勾选“在当前项目中继续修改”，描述需要改变的部分。参数实验会重算结果，构件操作即时响应。版本入口可以回看和恢复。</p></li><li><strong>把成果连起来</strong><p>公式库保存公式、笔记与关联作品；图谱沿主题连接公式与示例。悬浮球可以随时查看任务、取消任务或打开结果。</p></li></ol>
      <div class="kw-help-note"><strong>关于保存与登录</strong><p>可用邮箱、原用户名或 GitHub 登录，当前浏览器的作品会归入账号。旧邮箱账号登录后可继续使用原有公式、笔记和错题；不同登录方式不会因名称相同而自动合并。本机运行时数据留在本机，在线部署时保存在本站服务器。示例、阅读、公式管理和参数实验不调用模型。</p><p>普通在线账号使用 Qwen；VIP、管理员和本机工作台可选择已配置的 ChatGPT、Claude。账号菜单可以查看权限、剩余额度和邮箱验证入口。</p></div>
      <div class="kw-help-note"><strong>把探索变成学习资料</strong><p>画布下方可以收藏作品、加入稍后看、记笔记或加入错题本。笔记保留作品链接和记录时刻；在「学习资料」中可搜索、编辑、归档和导入导出。错题复习先回想，再查看解答，按自己的掌握程度安排下次复习。</p></div>
      <div class="kw-help-note"><strong>组织教案与课包</strong><p>在「教案与课包」中填写学习目标、教学过程和练习，再加入作品、公式、示例与学习资料。材料可以排序、添加讲解备注，打开课包后按顺序讲解；导出的课包保留文字快照，导入后可阅读便携资料。</p></div>
      <div class="kw-help-note"><strong>按习惯设置工作台</strong><p>「偏好设置」可调整主题、默认输入、播放速度与自动播放，也能设置图谱动效、悬浮球大小、透明度和位置。设置保存在当前空间。新手教程会依次指出工作区入口，可随时跳过或重播。</p></div>
      <div class="kw-help-note"><strong>区分作品版本与站点动态</strong><p>画布上方的「版本」保存同一作品每次修改的历史，恢复会生成新版本。这里的「版本动态」介绍工作台功能更新；「探索足迹」根据实际保存与学习记录显示进度。</p></div>
      <div class="kw-help-note"><strong>让解释保持合理</strong><p>明确的计算模型会显示适用条件。通用场景用于解释关系，不等于精确工程求解；条件不足时先补充描述。图片可用于理解与标注，不保证精确三维还原。</p></div>
      <div class="kw-help-actions" aria-label="帮助快捷入口"><button type="button" class="button secondary" data-help-action="tutorial">跟着教程操作</button><button type="button" class="button secondary" data-help-action="learning">学习资料与错题本</button><button type="button" class="button secondary" data-help-action="course-packs">教案与课包</button><button type="button" class="button secondary" data-help-action="settings">显示与偏好</button><button type="button" class="button secondary" data-help-action="achievements">探索足迹</button><button type="button" class="button secondary" data-help-action="releases">版本动态</button></div>
    </section>`;
  document.body.append(dialog);
  const $ = id => dialog.querySelector(`#${id}`);
  let items = [], graph = { nodes: [], links: [] }, selected = null, page = 0, trail = [], view = 'library';
  let request = 0, graphRequest = 0, editing = null, originFocus = null, dirty = false, saving = false, searchTimer, graphTimer;
  let nebula = null, graphMode = '3d', graphGeneration = 0, disposed = false, graphLoading = false, route = [], routeCursor = 0;
  let preferences = { reducedMotion: false, graphMotion: true, graphLabels: true };
  const systemMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const tell = text => { $('kw-message').textContent = text; $('kw-message').hidden = !text; };
  const error = e => { const text=e.message || '操作未完成，请重试。'; if(dialog.open)tell(text);else notify(text,true); };
  async function run(action) { try { await action(); } catch (e) { error(e); } }
  function closeEditor() { if(saving)return; $('kw-editor').hidden = true; editing = null; dirty = false; }
  function showView(value) {
    view = value;
    for (const v of ['library', 'knowledge', 'help']) { $(`kw-${v}`).hidden = v !== value; dialog.querySelector(`[data-view="${v}"]`).setAttribute('aria-pressed', String(v === value)); }
    if (value !== 'knowledge') releaseGraph();
    tell('');
  }
  function open(value = 'library') {
    if (disposed) return;
    if (!dialog.open) { originFocus = document.activeElement; dialog.showModal(); document.documentElement.classList.add('kw-open'); }
    showView(value);
    if (value === 'library') run(refreshLibrary);
    if (value === 'knowledge') run(refreshGraph);
  }
  function close() { dialog.close(); }
  $('kw-close').addEventListener('click', close);
  dialog.addEventListener('close', () => { request++; graphRequest++; releaseGraph(); document.documentElement.classList.remove('kw-open'); originFocus?.focus?.(); });
  for (const tab of dialog.querySelectorAll('[data-view]')) tab.addEventListener('click', () => open(tab.dataset.view));
  async function refreshLibrary() {
    const sequence = ++request, scope = $('kw-scope').value;
    const data = await api(`/api/library?q=${encodeURIComponent($('kw-search').value.trim())}&scope=${scope === 'favorites' ? 'saved' : scope}`);
    if (sequence !== request || !dialog.open) return;
    items = data.items || []; renderLibrary();
  }
  async function patch(item, fields) {
    await api(`/api/library/${encodeURIComponent(item.id)}`, { method: 'PATCH', body: { ...fields, expected_revision: item.revision } });
    await refreshLibrary();
  }
  function createEditor(item = null) {
    if (saving) { tell('正在保存当前公式，请稍候。'); return; }
    if (dirty) { tell('当前公式还有未保存的修改，请先保存或取消。'); return; }
    const project = getProject(); editing = item;
    $('kw-editor-title').textContent = item && !item.builtin && item.id ? '编辑公式' : '新增公式';
    $('kw-form-title').value = item?.title || '';
    $('kw-form-latex').value = item?.latex || '';
    $('kw-form-note').value = item?.note || '';
    $('kw-form-tags').value = (item?.tags || []).join('，');
    $('kw-form-link').checked = !!project && (item?.project_id === project.id || (!item?.id && !!item?.fromScene));
    $('kw-form-link').disabled = !project;
    $('kw-editor-message').textContent = item?.project_id && item.project_id !== project?.id ? '原关联项目会保留；勾选上方选项可改为当前项目。' : '';
    $('kw-editor').hidden = false; math($('kw-form-preview'), $('kw-form-latex').value);
    $('kw-editor').scrollIntoView({ block: 'nearest', behavior: 'smooth' }); $('kw-form-title').focus();
  }
  async function useFormula(item) { close(); await onAction('formula', item); }
  function renderLibrary() {
    const list = $('kw-library-list'); list.replaceChildren();
    const shown = $('kw-scope').value === 'favorites' ? items.filter(x => x.favorite) : items;
    $('kw-count').textContent = `${shown.length} 条公式`;
    if (!shown.length) { list.append(el('p', 'kw-empty', '这里还没有公式。可以新增，或从当前场景收录。')); return; }
    for (const item of shown) {
      const card = el('article', 'kw-formula-card'); card.dataset.formulaId = item.id;
      const heading = el('div', 'section-heading'); heading.append(el('h3', '', item.title), el('span', 'kw-origin', item.builtin ? '常用公式' : item.archived ? '已归档' : '我的公式'));
      const preview = el('div', 'kw-math'); math(preview, item.latex);
      card.append(heading, preview, el('p', 'kw-note', item.note || ''));
      if (item.sample_note) card.append(el('p','kw-sample-note',`示例范围：${item.sample_note}`));
      const tags = el('div', 'kw-tags'); for (const tag of item.tags || []) tags.append(btn(tag, () => { $('kw-search').value = tag; run(refreshLibrary); }, 'kw-tag')); card.append(tags);
      const actions = el('div', 'kw-card-actions');
      actions.append(btn('带入创作', () => run(() => useFormula(item)), 'button primary'), btn('复制', () => run(async () => { await navigator.clipboard.writeText(item.latex); notify('已复制 LaTeX'); })));
      if (item.sample) actions.append(btn('探索示例', () => run(async () => { close(); await onAction('sample', item.sample); })));
      if (item.project_id) actions.append(btn('关联作品', () => run(async () => { close(); await onAction('open-project', item.project_id); })));
      if (item.builtin) actions.append(btn('存入我的公式', () => createEditor({ ...item, id: null, builtin: false })));
      else {
        actions.append(btn(item.favorite ? '★ 已收藏' : '☆ 收藏', () => run(() => patch(item, { favorite: !item.favorite }))), btn('编辑', () => createEditor(item)));
        actions.append(btn(item.archived ? '恢复' : '归档', () => run(() => patch(item, { archived: !item.archived }))));
      }
      card.append(actions); list.append(card);
    }
  }
  $('kw-search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => run(refreshLibrary), 220); });
  $('kw-scope').addEventListener('change', () => run(refreshLibrary));
  $('kw-new').addEventListener('click', () => createEditor());
  $('kw-editor-close').addEventListener('click', closeEditor); $('kw-editor-cancel').addEventListener('click', closeEditor);
  $('kw-editor').addEventListener('input', () => { dirty = true; });
  $('kw-form-latex').addEventListener('input', () => { $('kw-form-preview').classList.remove('kw-math-fallback'); math($('kw-form-preview'), $('kw-form-latex').value); });
  $('kw-editor').addEventListener('submit', event => { event.preventDefault(); run(async () => {
    if(saving)return;
    const body = { title: $('kw-form-title').value.trim(), latex: normalize($('kw-form-latex').value), note: $('kw-form-note').value.trim(), tags: $('kw-form-tags').value.split(/[,，]/).map(x => x.trim()).filter(Boolean) };
    const project = getProject();
    body.project_id = $('kw-form-link').checked && project ? project.id : editing?.project_id && editing.project_id !== project?.id ? editing.project_id : null;
    if (!body.title || !body.latex) throw new Error('请填写名称与公式。');
    saving = true;
    for (const control of $('kw-editor').querySelectorAll('input,textarea,button')) control.disabled=true;
    try {
      if (editing?.id && !editing.builtin) await api(`/api/library/${encodeURIComponent(editing.id)}`, { method: 'PATCH', body: { ...body, expected_revision: editing.revision } });
      else await api('/api/library', { method: 'POST', body });
      saving=false; closeEditor(); tell(''); $('kw-search').value = ''; $('kw-scope').value = 'saved'; await refreshLibrary(); notify('公式已保存');
    } finally {
      saving=false;
      for (const control of $('kw-editor').querySelectorAll('input,textarea,button')) control.disabled=false;
      $('kw-form-link').disabled=!getProject();
    }
  }); });
  $('kw-save-input').addEventListener('click', () => createEditor({ latex: getPrompt(), title: '', note: '', tags: [] }));
  $('kw-capture').addEventListener('click', () => {
    const p = getProject(), formulas = p?.scene?.objects?.filter(x => x.kind === 'formula' && x.latex) || [];
    if (!formulas.length && !p?.proposal?.formula && !p?.proposal?.expression) { tell('当前场景没有公式图层。可以使用“保存输入的公式”或手动新增。'); return; }
    if (formulas.length > 1) {
      tell('选择需要收录的公式：');
      for (const f of formulas) $('kw-message').append(btn(f.label || f.latex.slice(0,50), () => createEditor({ title: f.label || p.title, latex: f.latex, note: p.scene.summary, project_id: p.id, fromScene: true })));
    } else createEditor({ title: formulas[0]?.label || p.title, latex: formulas[0]?.latex || p.proposal.formula || p.proposal.expression, note: p.scene.summary, project_id: p.id, fromScene: true });
  });
  $('kw-export').addEventListener('click', () => { const a = el('a'); a.href = '/api/library/export'; a.download = 'wisdom-formulas.json'; a.click(); });
  $('kw-import').addEventListener('click', () => $('kw-import-file').click());
  $('kw-import-file').addEventListener('change', event => run(async () => {
    const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
    if (file.size > 6_000_000) throw new Error('请选择不超过 6 MB 的公式 JSON 文件。');
    let source; try { source = JSON.parse(await file.text()); } catch { throw new Error('文件不是有效的 JSON。'); }
    const imported = Array.isArray(source) ? source : source.items || source.formulas;
    if (!Array.isArray(imported)) throw new Error('需要包含 items 或 formulas 数组的公式文件。');
    const result = await api('/api/library/import', { method: 'POST', body: { items: imported } });
    $('kw-search').value = ''; $('kw-scope').value = 'saved'; await refreshLibrary(); tell(`已导入 ${result.imported ?? result.count ?? imported.length} 条公式${result.skipped ? `，跳过 ${result.skipped} 条重复内容` : ''}。`);
  }));

  async function refreshGraph() {
    const sequence = ++graphRequest, data = await api('/api/knowledge');
    if (sequence !== graphRequest || !dialog.open || view !== 'knowledge' || disposed) return;
    releaseGraph();
    graph = data; if (!graph.nodes.some(x => x.id === selected)) selected = graph.nodes.find(x => x.kind === 'hub')?.id || graph.nodes[0]?.id;
    trail = trail.filter(id => graph.nodes.some(n => n.id === id));
    route = route.filter(id => graph.nodes.some(n => n.id === id));
    page = 0; drawGraph();
  }
  function selectNode(id, push = true) {
    if (!graph.nodes.some(x => x.id === id)) return;
    if (push && selected && selected !== id) { trail.push(selected); trail = trail.slice(-50); route = graphPath(graph, selected, id); routeCursor = Math.max(0, route.length - 1); }
    selected = id; page = 0; drawGraph();
  }
  function neighbors(id) {
    const ids = new Set(graph.links.flatMap(l => l.source === id ? [l.target] : l.target === id ? [l.source] : []));
    return graph.nodes.filter(n => ids.has(n.id));
  }
  function drawGraph() {
    const node = graph.nodes.find(n => n.id === selected); if (!node) return;
    const connected = neighbors(selected), visible = connected.slice(page * 8, page * 8 + 8);
    if (graphMode === '2d') drawFlatGraph(node, visible);
    else if (nebula) nebula.select(selected, visible.map(n => n.id), route);
    else if (!graphLoading) startGraph(visible);
    renderGraphControls();
    const detail = $('kw-node-detail'); detail.replaceChildren(el('span','section-eyebrow','当前节点'),el('h3','',node.label));
    if (node.latex) { const m=el('div','kw-math'); math(m,node.latex); detail.append(m); }
    detail.append(el('p','kw-note',node.description || '选择关联节点，沿知识关系继续探索。'));
    if (node.sample_note) detail.append(el('p','kw-sample-note',`示例范围：${node.sample_note}`));
    if (node.action) detail.append(btn({sample:'探索这个示例',formula:'查看公式',project:'打开作品',navigate:'打开功能'}[node.action.type] || '打开', () => run(() => activateNode(node)), 'button primary'));
    const links = el('div','kw-neighbor-list'); links.append(el('strong','','沿连线到下一站'));
    for(const n of connected) {
      const link = graph.links.find(l => l.source === selected && l.target === n.id || l.target === selected && l.source === n.id);
      const next = btn('', () => selectNode(n.id), 'kw-neighbor'); next.dataset.stationId = n.id;
      next.append(el('span', 'kw-neighbor-name', n.label), el('small', 'kw-relation', link?.label || '关联')); links.append(next);
    }
    if (!connected.length) links.append(el('p','kw-note','此节点暂无连线，可通过搜索选择其他节点。'));
    detail.append(links); renderStations();
    $('kw-graph-back').disabled = !trail.length; $('kw-graph-more').disabled = connected.length <= 8;
    $('kw-graph-count').textContent = `${graph.nodes.length} 个节点 · ${connected.length} 个关联${connected.length > 8 ? ` · 第 ${page+1}/${Math.ceil(connected.length/8)} 组` : ''}${graph.omitted?.projects ? ` · 另有 ${graph.omitted.projects} 个较早作品，可从“我的作品”打开` : ''}`;
  }
  function drawFlatGraph(node, visible) {
    const host = $('kw-graph'); host.replaceChildren(); host.dataset.renderer = '2d'; host.dataset.graphState = 'still';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', '0 0 720 450'); svg.setAttribute('preserveAspectRatio','none'); svg.setAttribute('aria-hidden','true'); host.append(svg);
    function makeNode(n, x, y, center = false) {
      const b = btn('', () => selectNode(n.id), `kw-graph-node${center ? ' selected' : ''}`); b.dataset.nodeId = n.id;
      b.style.left = `${x / 7.2}%`; b.style.top = `${y / 4.5}%`; b.title = n.label;
      b.append(el('span', 'kw-node-kind', { hub:'探索中心',topic:'主题',formula:'公式',sample:'示例',project:'作品',feature:'功能' }[n.kind] || '关联'));
      b.append(el('strong', '', n.label));
      if (n.latex) { const m = el('span', 'kw-node-math'); math(m, n.latex); b.append(m); }
      host.append(b);
    }
    visible.forEach((n, i) => {
      const angle = -Math.PI / 2 + i * Math.PI * 2 / Math.max(visible.length, 1), x = 360 + Math.cos(angle) * 245, y = 225 + Math.sin(angle) * 160;
      const line = document.createElementNS(svg.namespaceURI, 'line'); for (const [key, value] of Object.entries({x1:360,y1:225,x2:x,y2:y})) line.setAttribute(key,value); svg.append(line); makeNode(n,x,y);
    }); makeNode(node, 360, 225, true);
  }
  function releaseGraph() {
    graphGeneration++; graphLoading = false; nebula?.dispose(); nebula = null;
  }
  async function startGraph(visible) {
    const generation = ++graphGeneration; graphLoading = true;
    $('kw-graph-status').textContent = '正在打开三维知识图谱…';
    try {
      const result = await mountNebulaGraph($('kw-graph'), { graph, selected, labelIds: visible.map(n => n.id), route, onSelect: id => selectNode(id), renderMath: math, preferences,
        isCurrent: () => generation === graphGeneration && !disposed && dialog.open && view === 'knowledge',
        onUnavailable: text => { if (disposed || !dialog.open || generation !== graphGeneration) return; releaseGraph(); graphMode = '2d'; drawGraph(); $('kw-graph-status').textContent = text; },
      });
      if (generation !== graphGeneration || disposed || !dialog.open || view !== 'knowledge') { result?.dispose(); return; }
      nebula = result; graphLoading = false; nebula?.select(selected,neighbors(selected).slice(page*8,page*8+8).map(n=>n.id),route);renderGraphControls();
    } catch (cause) {
      if (generation !== graphGeneration || disposed) return;
      releaseGraph(); graphMode = '2d'; drawGraph(); $('kw-graph-status').textContent = cause.message || '此设备暂不支持三维图谱，已切换二维。';
    }
  }
  function renderGraphControls() {
    const moving = preferences.graphMotion !== false && !preferences.reducedMotion && !systemMotion.matches;
    $('kw-graph-3d').setAttribute('aria-pressed', String(graphMode === '3d')); $('kw-graph-2d').setAttribute('aria-pressed', String(graphMode === '2d'));
    $('kw-graph-motion').disabled = graphMode !== '3d' || preferences.reducedMotion || systemMotion.matches;
    $('kw-graph-motion').setAttribute('aria-pressed', String(moving)); $('kw-graph-motion').textContent = moving ? '暂停漫游' : '开启漫游';
    for (const id of ['kw-graph-zoom-in','kw-graph-zoom-out']) $(id).disabled = graphMode !== '3d';
    if (!graphLoading) $('kw-graph-status').textContent = graphMode === '3d' ? '拖动旋转 · 双指或滚轮缩放 · 点击节点选择，沿连线继续探索' : '二维关系图 · 点击节点或使用下方关联导航';
  }
  function renderStations() {
    const stations = $('kw-stations'); stations.replaceChildren();
    if (route.length < 2) { stations.append(el('span','kw-station-hint','选择一个关联节点，开始沿线探索。')); return; }
    stations.append(el('span','kw-station-hint','本次路线'));
    route.forEach((id, i) => {
      const node = graph.nodes.find(n => n.id === id); if (!node) return;
      if (i) {
        const link = graph.links.find(l => l.source === route[i-1] && l.target === id || l.target === route[i-1] && l.source === id);
        stations.append(el('span','kw-station-edge', `— ${link?.label || '关联'} →`));
      }
      const station = btn(node.label, () => { routeCursor = i; selected = id; page = 0; drawGraph(); }, 'kw-station');
      station.dataset.stationId = id; station.setAttribute('aria-current', String(id === selected)); stations.append(station);
    });
    if (routeCursor < route.length - 1) stations.append(btn('下一站 →', () => { selected = route[++routeCursor]; page = 0; drawGraph(); }, 'kw-station-next'));
  }
  async function activateNode(node) {
    const action=node.action;
    if (action.type === 'formula') {
      const data=await api('/api/library?scope=all'); const item=data.items.find(x=>x.id===action.id);
      if(!item)throw new Error('公式已归档或更新，请刷新图谱。');
      showView('library'); $('kw-search').value=item.title; $('kw-scope').value='all'; await refreshLibrary();
    } else if(action.type==='navigate' && ['library','knowledge','help'].includes(action.id)) {
      if (action.id === 'library' && node.kind === 'topic') { $('kw-search').value=node.tags?.[0] || node.label; $('kw-scope').value='all'; }
      open(action.id);
    }
    else { close(); await onAction(action.type==='project'?'open-project':action.type==='navigate'?action.id:action.type,action.id); }
  }
  $('kw-graph-reset').addEventListener('click',()=>{route=[];routeCursor=0;trail=[];selectNode(graph.nodes.find(x=>x.kind==='hub')?.id||graph.nodes[0]?.id,false);nebula?.reset();});
  $('kw-graph-back').addEventListener('click',()=>selectNode(trail.pop(),false));
  $('kw-graph-more').addEventListener('click',()=>{page=(page+1)%Math.ceil(neighbors(selected).length/8);drawGraph();});
  for (const mode of ['2d','3d']) $(`kw-graph-${mode}`).addEventListener('click',()=>{if(graphMode===mode && (nebula || mode==='2d'))return;releaseGraph();graphMode=mode;drawGraph();});
  $('kw-graph-motion').addEventListener('click',()=>{preferences.graphMotion=!preferences.graphMotion;nebula?.setPreferences(preferences);renderGraphControls();});
  $('kw-graph-zoom-in').addEventListener('click',()=>nebula?.zoom(.82)); $('kw-graph-zoom-out').addEventListener('click',()=>nebula?.zoom(1.22));
  const motionChanged=()=>{nebula?.setPreferences(preferences);renderGraphControls();};systemMotion.addEventListener('change',motionChanged);
  for(const entry of dialog.querySelectorAll('[data-help-action]'))entry.addEventListener('click',()=>run(async()=>{close();await onAction(entry.dataset.helpAction);}));
  $('kw-graph-search').addEventListener('input',()=>{clearTimeout(graphTimer);graphTimer=setTimeout(()=>{
    const q=$('kw-graph-search').value.trim().toLowerCase(),results=$('kw-graph-results'); results.hidden=!q; results.replaceChildren(); if(!q)return;
    const found=graph.nodes.filter(n=>`${n.label} ${n.latex||''} ${(n.tags||[]).join(' ')}`.toLowerCase().includes(q)).slice(0,30);
    for(const n of found)results.append(btn(n.label,()=>{selectNode(n.id);results.hidden=true;$('kw-graph-search').value='';},'kw-neighbor'));
    if(!found.length)results.append(el('p','kw-empty','没有找到对应节点。'));
  },150);});
  return { open, close, setPreferences(value={}){
    preferences={...preferences,...value};
    if('reduced_motion' in value)preferences.reducedMotion=!!value.reduced_motion;
    if('graph_motion' in value)preferences.graphMotion=!!value.graph_motion;
    if('graph_labels' in value)preferences.graphLabels=!!value.graph_labels;
    nebula?.setPreferences(preferences);renderGraphControls();
  }, get dirty(){return dirty||saving;}, dispose(){disposed=true;request++;graphRequest++;releaseGraph();systemMotion.removeEventListener('change',motionChanged);clearTimeout(searchTimer);clearTimeout(graphTimer);document.documentElement.classList.remove('kw-open');dialog.remove();} };
}
