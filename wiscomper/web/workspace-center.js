import katex from '/vendor/katex/katex.mjs';

const VIEWS = { learning: ['学习资料', '把发现留下，把不懂的再看一遍'], 'course-packs': ['教案与课包', '把作品、公式和笔记组织成一堂课'], settings: ['偏好设置', '按自己的习惯探索'], achievements: ['探索足迹', '每一步探索，都有记录'], releases: ['版本动态', '智算视界，一点点变得更好用'] };
const KINDS = { note: '笔记', favorite: '收藏', watch_later: '稍后看', wrongbook: '错题本' };
const date = value => value ? new Date(value * 1000).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
function el(tag, cls, text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=String(text); return n; }
function btn(text, fn, cls='button secondary') { const n=el('button',cls,text); n.type='button'; n.addEventListener('click',event=>{Promise.resolve().then(()=>fn(event)).catch(error=>{const status=n.closest('.workspace-center')?.querySelector('.wc-status');if(status){status.hidden=false;status.className='wc-status error';status.textContent=error.message||'操作未完成，请重试。';}});}); return n; }
function field(label, value='', type='text', max=4000) { const wrap=el('label','wc-field'); wrap.append(el('span','',label)); const n=el(type==='textarea'?'textarea':'input'); if(type!=='textarea')n.type=type; n.value=value??''; n.maxLength=max; wrap.append(n); return {wrap,input:n}; }
function select(label, options, value) { const wrap=el('label','wc-field'); wrap.append(el('span','',label)); const n=el('select'); for(const [id,title] of options){const o=el('option','',title);o.value=id;n.append(o);} n.value=value; wrap.append(n);return {wrap,input:n}; }
function download(data,name) { const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})); const a=el('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000); }
function rich(parent,text) {
  const source=String(text||'').slice(0,12000), re=/(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^\n$]+?\$)/g;let last=0;
  for(const m of source.matchAll(re)){parent.append(document.createTextNode(source.slice(last,m.index)));const math=el('span','wc-math'); const block=m[0].startsWith('$$')||m[0].startsWith('\\[');const trim=m[0].startsWith('$')&&!block?1:2;
    try{katex.render(m[0].slice(trim,-trim),math,{displayMode:block,throwOnError:true,trust:false,strict:'ignore',maxExpand:300,maxSize:15});}catch{math.textContent=m[0];} parent.append(math);last=m.index+m[0].length;}
  parent.append(document.createTextNode(source.slice(last)));
}

export function mountWorkspaceCenter({api,onAction,getProject,getPrompt,getTime,onPreferences,notify}) {
  const dialog=el('dialog','workspace-center');dialog.id='workspace-center';dialog.setAttribute('aria-labelledby','wc-title');
  dialog.innerHTML=`<div class="wc-shell"><aside class="wc-rail"><div class="wc-brand"><img src="/web/assets/wisdom-logo.svg" alt="" width="32" height="32"><span>我的空间<small>Wiscomper</small></span></div><nav aria-label="个人空间栏目"></nav><div class="wc-rail-bottom"><button class="button quiet" type="button" id="wc-tutorial">新手教程 ↗</button><button class="button quiet" type="button" id="wc-help">使用帮助 ↗</button></div></aside><section class="wc-main"><header class="wc-head"><div><h2 id="wc-title"></h2><p id="wc-subtitle"></p></div><button type="button" class="icon-button" id="wc-close" aria-label="关闭我的空间">×</button></header><div class="wc-status" role="status" hidden></div><div class="wc-confirm" hidden><span>还有未保存的修改。</span><button class="button primary" type="button" id="wc-keep">继续编辑</button><button class="button secondary" type="button" id="wc-discard">放弃修改并离开</button></div><div class="wc-body"></div></section></div>`;
  document.body.append(dialog);const $=s=>dialog.querySelector(s), body=$('.wc-body'),status=$('.wc-status');
  let view='learning',dirty=false,busy=false,sequence=0,disposed=false,prefs=null,prefRevision=0,prefChain=Promise.resolve(),prefPending=0,prefError=false,queuedLeave=null;
  let kind='all',filter='all',query='',packArchived=false;
  const nav=$('.wc-rail nav'); for(const [key,[name]] of Object.entries(VIEWS)) {const b=btn(name,()=>leave(()=>show(key)),'wc-nav');b.dataset.view=key;nav.append(b);}
  function report(error){status.hidden=false;status.className='wc-status error';status.textContent=error?.message||'操作未完成，请重试。';if(!dialog.open)notify(status.textContent,true);}
  function info(text){status.hidden=!text;status.className='wc-status';status.textContent=text;}
  async function work(fn){if(busy)return;busy=true;dialog.setAttribute('aria-busy','true');try{return await fn();}catch(error){report(error);}finally{busy=false;dialog.removeAttribute('aria-busy');}}
  function leave(fn){if(busy||prefPending){info('正在保存，请稍候。');return;}if(dirty){queuedLeave=fn;$('.wc-confirm').hidden=false;$('#wc-keep').focus();return;}fn();}
  $('#wc-keep').onclick=()=>{$('.wc-confirm').hidden=true;queuedLeave=null;};
  $('#wc-discard').onclick=()=>{dirty=false;$('.wc-confirm').hidden=true;const fn=queuedLeave;queuedLeave=null;fn?.();};
  const close=()=>leave(()=>dialog.close());$('#wc-close').onclick=close;dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
  dialog.addEventListener('close',()=>{sequence++;body.replaceChildren();dirty=false;});
  $('#wc-tutorial').onclick=()=>dispatch('tutorial');$('#wc-help').onclick=()=>dispatch('help');
  function dispatch(action,value){leave(()=>{dialog.close();Promise.resolve(onAction(action,value)).catch(error=>notify(error.message,true));});}
  function heading(title,description){const block=el('div','wc-section-title');block.append(el('h3','',title));if(description)block.append(el('p','',description));return block;}
  function empty(title,description){const box=el('div','wc-empty');box.append(el('span','wc-empty-mark','✦'),el('h3','',title),el('p','',description));body.append(box);}
  function toolbar(){const n=el('div','wc-toolbar');body.append(n);return n;}
  function mark(form){form.addEventListener('input',()=>{dirty=true;});form.addEventListener('change',()=>{dirty=true;});}
  function listCard(title,subtitle){const card=el('article','wc-card');card.append(el('h3','',title));if(subtitle)card.append(el('p','wc-meta',subtitle));return card;}
  async function show(next){
    view=VIEWS[next]?next:'learning';const token=++sequence;dirty=false;info('');$('.wc-confirm').hidden=true;
    $('#wc-title').textContent=VIEWS[view][0];$('#wc-subtitle').textContent=VIEWS[view][1];
    nav.querySelectorAll('button').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});
    body.replaceChildren(el('p','wc-loading','正在读取…'));
    try{ if(view==='settings'){if(!prefs)await loadPreferences();if(token===sequence)renderSettings();}
      else if(view==='learning')await renderLearning(token);
      else if(view==='course-packs')await renderPacks(token);
      else if(view==='achievements')await renderAchievements(token);
      else await renderReleases(token);
    }catch(error){if(token===sequence){body.replaceChildren();report(error);body.append(btn('重新读取',()=>show(view)));}}
  }
  async function open(next='learning'){if(disposed)return; if(dialog.open){leave(()=>show(next));return;}dialog.showModal();await show(next);}
  async function loadPreferences(){const data=await api('/api/preferences');prefs=data.preferences;prefRevision=data.revision;onPreferences?.(prefs);return prefs;}
  function savePreferences(patch){
    prefPending++;const task=prefChain.then(async()=>{try{const data=await api('/api/preferences',{method:'PUT',body:{expected_revision:prefRevision,preferences:patch}});prefs=data.preferences;prefRevision=data.revision;prefError=false;onPreferences?.(prefs);return prefs;}catch(error){prefError=true;try{await loadPreferences();}catch{}if(dialog.open&&view==='settings'){renderSettings();report(error);}else notify(error.message,true);throw error;}});
    prefChain=task.catch(()=>{});
    return task.finally(()=>{prefPending--;});
  }
  function renderSettings(){
    body.replaceChildren();const grid=el('div','wc-settings-grid');body.append(grid);
    function group(name,desc){const c=el('section','wc-setting-group');c.append(heading(name,desc));grid.append(c);return c;}
    function control(group,label,key,options){const row=el('label','wc-setting-row');row.append(el('span','',label));let input;
      if(options){input=select('',options,String(prefs[key])).input;} else{input=el('input');input.type='checkbox';input.checked=prefs[key];input.setAttribute('role','switch');}
      input.setAttribute('aria-label',label); row.append(input);group.append(row);
      input.addEventListener('change',async()=>{input.disabled=true;info('正在保存设置…');const value=options?(typeof prefs[key]==='number'?Number(input.value):input.value):input.checked;
        try{await savePreferences({[key]:value});info('设置已保存');}catch{}finally{input.disabled=false;if(options)input.value=String(prefs[key]);else input.checked=prefs[key];}});return input;}
    const look=group('外观与动效','场景的原始颜色不会随界面主题改变。');
    control(look,'界面主题','theme',[['system','跟随系统'],['light','浅色'],['dark','深色']]);control(look,'减少界面动效','reduced_motion');
    const play=group('创作与播放','为新打开的项目设置习惯。');
    control(play,'默认输入','default_input',[['text','文字'],['formula','公式'],['image','图片']]);control(play,'载入后自动播放','autoplay');
    control(play,'默认播放速度','default_speed',[['0.5','0.5×'],['0.75','0.75×'],['1','1×'],['1.25','1.25×'],['1.5','1.5×'],['2','2×']]);
    const graph=group('三维知识图谱','拖动旋转，滚动缩放，沿关联继续探索。');control(graph,'图谱自动缓慢旋转','graph_motion');control(graph,'显示关联节点标签','graph_labels');
    const hub=group('悬浮球','随时查看任务进度，快速回到工作区。');control(hub,'显示悬浮球','floating_visible');
    control(hub,'悬浮球大小','floating_size',[['48','小 · 48'],['64','标准 · 64'],['80','大 · 80'],['96','特大 · 96']]);
    control(hub,'悬浮球不透明度','floating_opacity',[['0.4','40%'],['0.65','65%'],['0.85','85%'],['1','100%']]);
    hub.append(btn('重置悬浮球位置',()=>work(async()=>{await savePreferences({floating_x:null,floating_y:null});info('悬浮球已回到默认位置。');})));
    const resources=group('学习与帮助','把资料留在自己的空间。');resources.append(btn('查看使用教程',()=>dispatch('tutorial')),btn('作品版本管理',()=>dispatch('versions')),btn('查看版本动态',()=>leave(()=>show('releases'))));
    body.append(el('p','wc-footnote','设置会保存在当前空间；登录 GitHub 后跟随账号。更换账号不会混用偏好或学习资料。'));
  }
  function exportLink(path,name){return btn('导出',()=>work(async()=>download(await api(path),name)));}
  function importButton(path,limit,refresh){const input=el('input');input.type='file';input.accept='.json,application/json';input.hidden=true;body.append(input);
    input.addEventListener('change',()=>work(async()=>{try{const file=input.files?.[0];if(!file)return;if(file.size>limit)throw new Error('文件过大，请选择导出的学习资料文件。');let data;try{data=JSON.parse(await file.text());}catch{throw new Error('文件不是有效的 JSON。');}await api(path,{method:'POST',body:data});await refresh();notify('资料已导入，相同内容不会重复添加。');}finally{input.value='';}}));return btn('导入',()=>input.click());}
  async function renderLearning(token){
    const data=await api(`/api/learning?kind=${kind}&status=${filter}&q=${encodeURIComponent(query)}`);if(token!==sequence)return;body.replaceChildren();
    const bar=toolbar(),kindInput=select('资料类型',[['all','全部资料'],...Object.entries(KINDS)],kind),statusInput=select('复习状态',[['all','全部'],['due','待复习'],['mastered','已掌握'],['archived','已归档']],filter),search=field('搜索资料',query,'search',200);
    for(const [entry,key] of [[kindInput,'kind'],[statusInput,'filter']])entry.input.onchange=()=>{if(key==='kind')kind=entry.input.value;else filter=entry.input.value;show('learning');};
    search.input.placeholder='标题、公式或笔记';search.input.onkeydown=e=>{if(e.key==='Enter'){query=search.input.value;show('learning');}};
    bar.append(kindInput.wrap,statusInput.wrap,search.wrap,btn('搜索',()=>{query=search.input.value;show('learning');}),btn('＋ 添加资料',()=>editLearning(null),'button primary'),exportLink('/api/learning/export','wiscomper-learning.json'),importButton('/api/learning/import',5_000_000,()=>show('learning')));
    const stats=el('div','wc-stats');for(const [name,value] of [['学习资料',data.stats.total],['待复习',data.stats.due],['复习次数',data.stats.reviews],['已掌握',data.stats.mastered]]){const n=el('div');n.append(el('strong','',value),el('span','',name));stats.append(n);}body.append(stats);
    if(!data.items.length){empty('留住这次探索','可以在画面下方收藏当前作品、记笔记或加入错题本，也可以直接添加资料。');return;}
    const list=el('div','wc-card-grid');body.append(list);
    for(const item of data.items){const card=listCard(item.title,`${KINDS[item.kind]} · ${date(item.updated)}${item.time_sec!=null?` · ${item.time_sec.toFixed(1)} 秒`:''}`);
      const content=el('div','wc-rich wc-clamp');rich(content,item.problem||item.note||item.answer);card.append(content);
      if(item.kind==='wrongbook')card.append(el('p','wc-meta',`${item.status==='mastered'?'已自评掌握':`下次复习：${date(item.next_review_at)}`} · 已复习 ${item.review_count} 次`));
      const actions=el('div','wc-actions');actions.append(btn('查看与编辑',()=>editLearning(item)),btn(item.archived?'恢复':'归档',()=>work(async()=>{await api(`/api/learning/${item.id}`,{method:'PATCH',body:{expected_revision:item.revision,archived:!item.archived}});await show('learning');})));
      if(item.project_id)actions.append(btn('打开作品',()=>dispatch('open-study-project',{id:item.project_id,time:item.time_sec})));
      if(item.kind==='wrongbook'&&!item.archived)actions.append(btn('开始复习',()=>reviewLearning(item),'button primary'));
      card.append(actions);list.append(card);
    }
  }
  async function editLearning(item,seed={}){
    if(busy)return;const token=++sequence;info('');body.replaceChildren();const form=el('form','wc-editor');body.append(form);
    const data=item||{kind:'note',title:'',note:'',problem:'',answer:'',tags:[],...seed};
    const type=select('资料类型',Object.entries(KINDS),data.kind);type.input.disabled=!!item;
    const title=field('标题',data.title,'text',120),problem=field('题目 / 观察对象',data.problem,'textarea'),answer=field('解答 / 结论',data.answer,'textarea'),note=field('我的笔记',data.note,'textarea'),tags=field('标签（逗号分隔，最多 8 个）',(data.tags||[]).join('，'),'text',199);
    title.input.required=true; form.append(type.wrap,title.wrap,problem.wrap,answer.wrap,note.wrap,tags.wrap);
    const preview=el('details','wc-preview');preview.append(el('summary','','公式预览'));const pv=el('div','wc-rich');preview.append(pv);form.append(preview);const renderPreview=()=>{pv.replaceChildren();rich(pv,[problem.input.value,answer.input.value,note.input.value].join('\n\n'));};preview.ontoggle=renderPreview;form.addEventListener('input',()=>{if(preview.open)renderPreview();});
    const linked=el('p','wc-meta',data.project_id?`已关联作品${data.time_sec!=null?` · ${Number(data.time_sec).toFixed(1)} 秒`:''}`:'独立资料，可在课包中再次使用。');form.append(linked);
    const actions=el('div','wc-actions'),save=el('button','button primary','保存资料');save.type='submit';actions.append(save,btn('返回列表',()=>leave(()=>show('learning'))));form.append(actions);mark(form);
    if(seed.title)dirty=true;
    form.onsubmit=e=>{e.preventDefault();work(async()=>{save.disabled=true;form.inert=true;try{const payload={title:title.input.value.trim(),problem:problem.input.value,answer:answer.input.value,note:note.input.value,tags:tags.input.value.split(/[,，]/).map(x=>x.trim()).filter(Boolean)};
      if(item)payload.expected_revision=item.revision;else Object.assign(payload,{kind:type.input.value,project_id:data.project_id||null,formula_id:data.formula_id||null,sample_id:data.sample_id||null,time_sec:data.time_sec??null});
      await api(item?`/api/learning/${item.id}`:'/api/learning',{method:item?'PATCH':'POST',body:payload});if(sequence!==token)return;dirty=false;await show('learning');notify('资料已保存。');}finally{save.disabled=false;form.inert=false;}});};
  }
  async function reviewLearning(item){
    const token=++sequence;body.replaceChildren();info('');const card=listCard(item.title,`第 ${item.review_count+1} 次复习`),question=el('div','wc-rich');rich(question,item.problem);card.append(question);
    const answer=el('details','wc-preview');answer.append(el('summary','','查看解答与笔记'));const content=el('div','wc-rich');rich(content,[item.answer,item.note].filter(Boolean).join('\n\n')||'还没有解答，可以返回编辑补充。');answer.append(content);card.append(answer);
    card.append(el('p','wc-meta','先独立回想，再按自己的掌握情况记录。'));
    const actions=el('div','wc-actions');for(const [grade,label] of [['again','还不会 · 10 分钟后'],['hard','有点难 · 明天'],['good','已理解 · 稍后复习'],['easy','已掌握']])actions.append(btn(label,()=>work(async()=>{await api(`/api/learning/${item.id}/review`,{method:'POST',body:{expected_revision:item.revision,grade}});if(sequence!==token)return;await show('learning');notify('复习记录已保存。');}),grade==='good'?'button primary':'button secondary'));
    card.append(actions,btn('返回列表',()=>show('learning')));body.append(card);
    try{const data=await api(`/api/learning/${item.id}`);if(sequence!==token)return;const history=el('details','wc-preview');history.append(el('summary','','复习记录'));const grades={again:'还不会',hard:'有点难',good:'已理解',easy:'已掌握'};for(const r of [...data.item.reviews].reverse())history.append(el('p','wc-meta',`${date(r.reviewed_at)} · ${grades[r.grade]}${r.note?` · ${r.note}`:''}`));if(!data.item.reviews.length)history.append(el('p','wc-meta','完成第一次复习后，会在这里留下记录。'));card.append(history);}catch(error){if(sequence===token)report(error);}
  }
  async function capture(kindValue){
    const project=getProject();if(!project){notify('请先打开一个作品。',true);return;}const seed={kind:kindValue,title:(project.title||project.scene?.title||'我的探索').slice(0,120),project_id:project.id,time_sec:Number(getTime())||0,problem:(project.prompt||getPrompt()||project.title||'探索当前作品').slice(0,4000),answer:'',note:''};
    if(['favorite','watch_later'].includes(kindValue)){await work(async()=>{const data=await api('/api/learning',{method:'POST',body:seed});notify(data.duplicate?'已在你的资料中。':`已加入${KINDS[kindValue]}。`);});return;}
    await open('learning');editLearning(null,seed);if((project.prompt||getPrompt()||'').length>4000)info('已带入前 4000 字作为题目摘要，完整描述仍保存在关联作品中。');
  }
  async function renderPacks(token){
    const data=await api(`/api/course-packs?archived=${packArchived}`);if(sequence!==token)return;body.replaceChildren();
    const bar=toolbar();bar.append(btn('＋ 创建课包',()=>editPack(null),'button primary'),btn(packArchived?'查看使用中的课包':'已归档',()=>{packArchived=!packArchived;show('course-packs');}),importButton('/api/course-packs/import',1_500_000,()=>show('course-packs')));
    if(!data.items.length){empty('从一个想讲清楚的概念开始','加入作品、公式、示例和学习笔记，编写教案，再按顺序演示。');return;}
    const list=el('div','wc-card-grid');body.append(list);
    for(const item of data.items){const card=listCard(item.title,`${item.item_count} 份材料 · ${date(item.updated)}`);card.append(el('p','wc-rich wc-clamp',item.description));const actions=el('div','wc-actions');
      actions.append(btn('打开课包',()=>work(async()=>{const data=await api(`/api/course-packs/${item.id}`);await viewPack(data.item);}),'button primary'),btn('编辑',()=>work(async()=>{const data=await api(`/api/course-packs/${item.id}`);await editPack(data.item);})),exportLink(`/api/course-packs/${item.id}/export`,'wiscomper-course-pack.json'),btn(item.archived?'恢复':'归档',()=>work(async()=>{await api(`/api/course-packs/${item.id}`,{method:'PATCH',body:{expected_revision:item.revision,archived:!item.archived}});await show('course-packs');})));
      card.append(actions);list.append(card);}
  }
  async function viewPack(item){
    ++sequence;body.replaceChildren();body.append(heading(item.title,item.description));
    const infoCard=el('section','wc-card');infoCard.append(el('p','wc-meta',`${item.lesson.audience||'适用对象未填写'} · ${item.lesson.duration} 分钟`));
    const labels={objectives:'学习目标',key_points:'重点与难点',preparation:'课前准备',procedure:'教学过程',exercises:'练习与提问',reflection:'课后反思'};
    for(const [key,title] of Object.entries(labels))if(item.lesson[key]){infoCard.append(el('h3','',title));const text=el('div','wc-rich');rich(text,item.lesson[key]);infoCard.append(text);}body.append(infoCard);
    const list=el('div','wc-pack-materials');body.append(list);
    item.items.forEach((entry,i)=>{const c=listCard(`${i+1}. ${entry.snapshot.title}`,entry.note);const text=el('div','wc-rich');rich(text,[entry.snapshot.latex?`\\[${entry.snapshot.latex}\\]`:'',entry.snapshot.problem,entry.snapshot.answer,entry.snapshot.note,entry.snapshot.prompt].filter(Boolean).join('\n\n'));c.append(text);
      if(entry.id){let action,value;if(entry.kind==='project'){action='open-project';value=entry.id;}else if(entry.kind==='sample'){action='sample';value=entry.id;}else if(entry.kind==='formula'){action='formula';value=entry.snapshot;}else{action='learning';}
        c.append(btn(entry.kind==='sample'?'打开示例':entry.kind==='formula'?'带入创作':entry.kind==='learning'?'打开学习资料':'打开作品',()=>dispatch(action,value)));}else c.append(el('p','wc-meta','便携资料 · 可在此阅读内容'));list.append(c);});
    body.append(btn('返回课包',()=>show('course-packs')));
  }
  async function editPack(item){
    const token=++sequence;info('');body.replaceChildren(el('p','wc-loading','正在准备课包…'));
    let resources;try{resources=await Promise.all([api('/api/projects'),api('/api/library'),api('/api/learning'),api('/api/bootstrap')]);}catch(error){if(sequence===token){report(error);body.replaceChildren(btn('重新准备课包',()=>editPack(item)),btn('返回课包列表',()=>show('course-packs')));}return;}if(sequence!==token)return;
    body.replaceChildren();const data=item||{title:'',description:'',lesson:{duration:45},items:[]},form=el('form','wc-editor');body.append(form);
    const title=field('课包名称',data.title,'text',120),description=field('课包介绍',data.description,'textarea',2000);title.input.required=true;form.append(title.wrap,description.wrap);
    const lessonSection=el('details','wc-preview');lessonSection.open=true;lessonSection.append(el('summary','','教案'));const lessonFields={};
    for(const [key,label,type,max] of [['audience','适用对象','text',160],['duration','预计时长（分钟）','number',3],['objectives','学习目标','textarea',4000],['key_points','重点与难点','textarea',4000],['preparation','课前准备','textarea',4000],['procedure','教学过程','textarea',8000],['exercises','练习与提问','textarea',4000],['reflection','课后反思','textarea',4000]]){const f=field(label,data.lesson[key]||'',type,max);if(key==='duration'){f.input.min=1;f.input.max=480;f.input.required=true;}lessonFields[key]=f.input;lessonSection.append(f.wrap);}form.append(lessonSection);
    const materials=el('section','wc-material-editor');materials.append(heading('学习材料','调整顺序，按你的讲解方式组织内容。'));form.append(materials);
    const entries=data.items.map(x=>structuredClone(x)),pool=[];
    for(const project of resources[0].projects||[])pool.push({kind:'project',id:project.id,title:`作品 · ${project.title}`});
    for(const formula of resources[1].items||[])if(!formula.archived)pool.push({kind:'formula',id:formula.id,title:`公式 · ${formula.title}`});
    for(const record of resources[2].items||[])pool.push({kind:'learning',id:record.id,title:`${KINDS[record.kind]} · ${record.title}`});
    for(const sample of resources[3].samples||[])pool.push({kind:'sample',id:sample.id,title:`示例 · ${sample.title}`});
    const picker=select('添加材料',pool.map((x,i)=>[String(i),x.title]),'0'),rows=el('ol','wc-material-rows');materials.append(picker.wrap,btn('加入课包',()=>{const source=pool[Number(picker.input.value)];if(!source)return;if(entries.length>=40){info('一个课包最多 40 份材料。');return;}if(entries.some(x=>x.kind===source.kind&&x.id===source.id)){info('这份材料已在课包中。');return;}entries.push({kind:source.kind,id:source.id,note:'',snapshot:{title:source.title}});dirty=true;renderRows();}),rows);
    function renderRows(){rows.replaceChildren();entries.forEach((entry,index)=>{const row=el('li','wc-material-row');row.append(el('strong','',entry.snapshot?.title||entry.id));const note=field('讲解备注',entry.note,'text',2000);note.input.oninput=()=>{entry.note=note.input.value;dirty=true;};row.append(note.wrap);const actions=el('div','wc-actions');const up=btn('上移',()=>{[entries[index-1],entries[index]]=[entries[index],entries[index-1]];dirty=true;renderRows();});up.disabled=index===0;const down=btn('下移',()=>{[entries[index+1],entries[index]]=[entries[index],entries[index+1]];dirty=true;renderRows();});down.disabled=index===entries.length-1;actions.append(up,down,btn('移除',()=>{entries.splice(index,1);dirty=true;renderRows();}));row.append(actions);rows.append(row);});}renderRows();
    const actions=el('div','wc-actions'),save=el('button','button primary','保存课包');save.type='submit';actions.append(save,btn('返回列表',()=>leave(()=>show('course-packs'))));form.append(actions);mark(form);
    form.onsubmit=e=>{e.preventDefault();work(async()=>{save.disabled=true;form.inert=true;try{const lesson={};for(const [key,input] of Object.entries(lessonFields))lesson[key]=key==='duration'?Number(input.value):input.value;
      const payload={title:title.input.value,description:description.input.value,lesson,items:entries.map(x=>x.id?{kind:x.kind,id:x.id,note:x.note}:x)};if(item)payload.expected_revision=item.revision;
      await api(item?`/api/course-packs/${item.id}`:'/api/course-packs',{method:item?'PATCH':'POST',body:payload});dirty=false;await show('course-packs');notify('课包已保存。');}finally{save.disabled=false;form.inert=false;}});};
  }
  async function renderAchievements(token){const data=await api('/api/achievements');if(token!==sequence)return;body.replaceChildren();const grid=el('div','wc-card-grid wc-achievements');body.append(grid);for(const item of data.items){const card=listCard(item.title,item.description);card.classList.toggle('unlocked',item.unlocked);card.prepend(el('div','wc-medal',item.unlocked?'✦':'◇'));const progress=el('progress');progress.max=item.target;progress.value=item.progress;progress.setAttribute('aria-label',item.title);card.append(progress,el('p','wc-meta',`${item.progress} / ${item.target}${item.unlocked?' · 已点亮':''}`));grid.append(card);}body.append(el('p','wc-footnote',data.note));}
  async function renderReleases(token){const data=await api('/api/releases');if(token!==sequence)return;body.replaceChildren();const timeline=el('div','wc-release-list');body.append(timeline);for(const item of data.items){const card=el('article','wc-release');card.append(el('p','wc-meta',`${item.date} · ${item.version}${item.channel==='legacy'?' · 旧站记录':''}`),el('h3','',item.title));const list=el('ul');item.changes.forEach(text=>list.append(el('li','',text)));card.append(list);if(item.source)card.append(el('p','wc-footnote',item.source));timeline.append(card);}body.append(btn('查看当前作品的版本',()=>dispatch('versions')));}
  async function openItem(type,id){await open(type==='learning'?'learning':'course-packs');await work(async()=>{const data=await api(type==='learning'?`/api/learning/${encodeURIComponent(id)}`:`/api/course-packs/${encodeURIComponent(id)}`);if(type==='learning'){busy=false;await editLearning(data.item);}else await viewPack(data.item);});}
  return {open,openItem,capture,loadPreferences,savePreferences,get dirty(){return dirty||prefPending>0;},get preferences(){return prefs;},dispose(){disposed=true;sequence++;dialog.remove();}};
}
