import { solutionMarkdown } from './solution-library.js';
import { escapeText as esc } from './solution-visual.js';
import { textWithMath } from './math-text.js';

const fields={objectives:'教学目标',key_points:'重点与难点',preparation:'课前准备',procedure:'教学过程',exercises:'练习与作业',reflection:'课后反思'};
let catalog=[];
export async function teachingRequest(path='',options={}) {
    const response=await fetch('/api/examples/course-packs'+path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...options.headers}});
    const data=await response.json();
    if(!response.ok||data.status!=='success') {
        if(response.status===401){
            if(document.querySelector('.course-editor'))throw Object.assign(new Error('请登录后保存课包，已填写的内容会保留。'),{status:401});
            document.querySelectorAll('.course-dialog').forEach(d=>d.close());window.toggleAuthModal?.(true);
        }
        throw new Error(typeof data.detail==='string'?data.detail:data.message||'操作未完成，请重试');
    }
    return data;
}
async function videos(){const r=await fetch('/api/examples');const d=await r.json();if(!r.ok||d.status!=='success'||d.error)throw new Error(d.message||d.error||'视频目录读取失败');catalog=d.data||[];return catalog;}
function label(id){return catalog.find(v=>v.video_id===id)?.title||id;}
function dialog(title){const d=document.createElement('dialog');d.className='course-dialog';d.innerHTML=`<header><div><span class="assistant-eyebrow">智算视界 / TEACHING</span><h2>${esc(title)}</h2></div><button type="button" data-close aria-label="关闭">×</button></header><div class="course-body"></div><p class="course-status" role="status" aria-live="polite"></p>`;document.body.append(d);d.showModal();d.querySelector('[data-close]').onclick=()=>d.close();d.addEventListener('close',()=>{if(!d.dataset.authSuspended)d.remove();});return d;}
function loginForCourse(d){
    if(d.dataset.authSuspended)return;
    d.dataset.authSuspended='true';d.close();
    const cleanup=()=>{
        window.removeEventListener('auth-dialog-closed',resume);
        window.removeEventListener('auth-state-change',signedIn);
        delete d.courseAuthCleanup;
    };
    const resume=()=>{
        cleanup();
        setTimeout(()=>{delete d.dataset.authSuspended;if(d.isConnected)d.showModal();},0);
    };
    const signedIn=event=>{if(event.detail?.username){status(d,'已登录为 '+event.detail.username+'，请确认内容后再次点击保存。');resume();}};
    window.addEventListener('auth-dialog-closed',resume);
    window.addEventListener('auth-state-change',signedIn);
    d.courseAuthCleanup=cleanup;
    window.toggleAuthModal?.(true);
}
export function disposeCourseDialogs(){document.querySelectorAll('.course-dialog').forEach(d=>{d.courseAuthCleanup?.();d.close();d.remove();});}
function status(d,text){d.querySelector('[role=status]').textContent=text;}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function changed(){window.dispatchEvent(new CustomEvent('course-packs-updated'));}
function markdown(pack){const lesson=pack.lesson||{};return `# ${pack.name}\n\n${pack.description||''}\n\n适用对象：${lesson.audience||'未填写'}\n\n课时：${lesson.duration||45} 分钟\n\n`+Object.entries(fields).map(([key,title])=>`## ${title}\n\n${lesson[key]||'待补充'}\n\n`).join('')+'## 课堂视频\n\n'+pack.video_ids.map((id,i)=>`${i+1}. [${label(id)}](${location.origin}/?section=examples&video=${encodeURIComponent(id)})`).join('\n')+'\n\n## 题解与练习\n\n'+(pack.resources||[]).map((r,i)=>`${i+1}. ${r.snapshot.title}\n\n${r.snapshot.problem}\n\n${r.snapshot.solution?solutionMarkdown(r.snapshot.solution):r.snapshot.answer}\n\n${r.snapshot.note}`).join('\n\n');}

export async function renderCoursePacks(host,isCurrent=()=>true){
    host.classList.add('course-pack-grid');host.innerHTML='<p>正在读取课包…</p>';
    try{const {data}=await teachingRequest();if(!host.isConnected||!isCurrent())return;
        host.innerHTML=data.length?data.map(p=>`<article class="course-card"><span class="course-count">${p.video_count} 个视频 · ${p.resource_count||0} 份学习材料</span><h3>${esc(p.name)}</h3><p>${esc(p.description||'将教案、演示视频和课堂活动整理在一起。')}</p><button data-pack="${p.id}">阅读教案与课包 ↗</button></article>`).join(''):'<div class="course-empty"><h3>为下一堂课做好准备</h3><p>填写教案，挑选视频，按课堂顺序保存为课包。</p><button data-new-pack>创建第一个课包</button></div>';
        host.onclick=e=>{const b=e.target.closest('button');if(b?.dataset.pack)openCoursePack(Number(b.dataset.pack));if(b?.hasAttribute('data-new-pack'))editCoursePack();};
    }catch(error){if(host.isConnected&&isCurrent())host.textContent=error.message;}
}

export async function editCoursePack(ident=null,selectedVideo=null,selectedResource=null){
    const d=dialog(ident?'编辑课包与教案':'创建课包与教案');status(d,'正在加载…');
    try{
        const record=ident?await teachingRequest('/'+ident):{data:{name:'',description:'',lesson:{duration:45},video_ids:selectedVideo?[selectedVideo]:[],resources:selectedResource?[selectedResource]:[]}};
        let list=[],catalogError='',catalogLoading=true;
        if(!d.isConnected)return;
        const pack=record.data,lesson=pack.lesson||{};if(!ident&&selectedVideo)pack.name=label(selectedVideo)+' · 课堂教案';let selected=[...pack.video_ids],dirty=false,saving=false;
        const body=d.querySelector('.course-body');body.innerHTML=`<form class="course-editor"><div class="course-form-row"><label>课包名称<input name="name" required maxlength="128" placeholder="例如：二次函数的图像与性质" value="${esc(pack.name)}"></label><label>适用对象<input name="audience" maxlength="200" placeholder="年级 / 学情" value="${esc(lesson.audience||'')}"></label><label>课时（分钟）<input name="duration" type="number" min="1" max="480" value="${lesson.duration||45}" required></label></div><label>课程简介<textarea name="description" maxlength="2000" rows="2">${esc(pack.description||'')}</textarea></label><div class="course-editor-tools"><span>支持文字与 LaTeX 公式</span><button type="button" data-outline>填入教案结构</button><button type="button" data-preview>预览排版</button></div><div class="lesson-fields">${Object.entries(fields).map(([key,title])=>`<label>${title}<textarea name="${key}" rows="${key==='procedure'?6:3}" maxlength="12000" placeholder="${key==='procedure'?'按导入、探究、演示、练习和总结安排课堂活动…':'填写'+title+'…'}">${esc(lesson[key]||'')}</textarea></label>`).join('')}</div><section class="course-video-picker"><h3>课堂视频</h3><p>按教学顺序排列，可在下方调整或移除。</p><ol data-selected-videos></ol><label>查找案例<input type="search" data-video-search placeholder="按标题、标签查找"></label><div class="course-video-options"></div></section><div class="course-form-actions"><button type="button" data-cancel>取消</button><button type="submit" class="action-btn primary">保存课包与教案</button></div></form>`;
        const form=body.querySelector('form');
        if(pack.resources?.length){const hint=document.createElement('p');hint.textContent=pack.resources.length+' 份题解与练习将随教案保留，可在课包阅读页调整顺序或移除。';form.querySelector('.course-form-actions').before(hint);}
        const collect=()=>{const fd=new FormData(form);return {name:String(fd.get('name')||''),description:String(fd.get('description')||''),video_ids:selected,resources:pack.resources,revision:pack.revision,lesson:{audience:String(fd.get('audience')||''),duration:Number(fd.get('duration')), ...Object.fromEntries(Object.keys(fields).map(k=>[k,String(fd.get(k)||'')]))}};};
        function renderSelection(){body.querySelector('[data-selected-videos]').innerHTML=selected.map((id,i)=>`<li><span>${i+1}. ${esc(label(id))}</span><button type="button" data-move="${i}" data-offset="-1" ${i===0?'disabled':''} aria-label="上移 ${esc(label(id))}">↑</button><button type="button" data-move="${i}" data-offset="1" ${i===selected.length-1?'disabled':''} aria-label="下移 ${esc(label(id))}">↓</button><button type="button" data-remove="${i}" aria-label="移除 ${esc(label(id))}">移除</button></li>`).join('')||'<li>尚未选择视频，也可以先保存教案。</li>';renderOptions();}
        function renderOptions(){const host=body.querySelector('.course-video-options');if(catalogLoading){host.innerHTML='<p>正在读取视频目录…</p>';return;}if(catalogError){host.innerHTML='<p>视频目录暂时不可用，可以先保存教案。</p><button type="button" data-reload-videos>重新加载视频</button>';return;}const q=body.querySelector('[data-video-search]').value.toLowerCase();host.innerHTML=list.filter(v=>[v.title,...(v.tags||[])].join(' ').toLowerCase().includes(q)).map(v=>`<button type="button" data-add="${esc(v.video_id)}" ${selected.includes(v.video_id)?'disabled':''}>${selected.includes(v.video_id)?'✓':'+'} ${esc(v.title)}</button>`).join('')||'<p>没有匹配的视频</p>';}
        async function loadVideos(){catalogLoading=true;catalogError='';renderOptions();try{list=await videos();}catch(error){catalogError=error.message;}finally{catalogLoading=false;if(d.isConnected)renderSelection();}}
        function close(){if(saving)return;if(dirty&&!confirm('有尚未保存的教案修改，确定关闭？'))return;d.close();}
        d.querySelector('[data-close]').onclick=close;d.addEventListener('cancel',e=>{e.preventDefault();close();});
        form.oninput=e=>{if(e.target.matches('[data-video-search]'))renderOptions();else dirty=true;};
        form.onclick=e=>{const b=e.target.closest('button');if(!b)return;
            if(b.hasAttribute('data-reload-videos'))loadVideos();
            if(b.hasAttribute('data-add')){selected.push(b.dataset.add);dirty=true;renderSelection();}
            if(b.hasAttribute('data-remove')){selected.splice(Number(b.dataset.remove),1);dirty=true;renderSelection();}
            if(b.hasAttribute('data-move')){const i=Number(b.dataset.move),j=i+Number(b.dataset.offset);[selected[i],selected[j]]=[selected[j],selected[i]];dirty=true;renderSelection();}
            if(b.hasAttribute('data-cancel'))close();
            if(b.hasAttribute('data-preview')){const p=dialog('教案排版预览');showLesson(p.querySelector('.course-body'),collect());}
            if(b.hasAttribute('data-outline')){const area=form.elements.namedItem('procedure');if(!area.value){area.value='1. 情境导入（5 分钟）\n提出本课问题，了解已有知识。\n\n2. 探究与视频演示（20 分钟）\n观察动画，暂停关键步骤，引导学生解释公式变化。\n\n3. 巩固练习（15 分钟）\n独立解答并交流思路。\n\n4. 总结与反馈（5 分钟）\n归纳方法，记录疑问。';dirty=true;}status(d,'已填入可编辑结构，请结合实际课时与教学内容调整。');}
        };
        form.onsubmit=async e=>{e.preventDefault();if(saving)return;saving=true;form.querySelector('[type=submit]').disabled=true;status(d,'正在保存…');try{const r=await teachingRequest(ident?'/'+ident:'',{method:ident?'PUT':'POST',body:JSON.stringify(collect())});dirty=false;changed();if(d.isConnected){d.close();await openCoursePack(r.id);}}catch(error){status(d,error.message);if(error.status===401)loginForCourse(d);}finally{saving=false;if(d.isConnected)form.querySelector('[type=submit]').disabled=false;}};
        renderSelection();status(d,'保存后可从“我的课件”继续阅读和编辑。');
        loadVideos();
    }catch(error){status(d,error.message);}
}
function showLesson(host,pack){
    const content=Object.entries(fields).filter(([key])=>String(pack.lesson?.[key]||'').trim());
    host.innerHTML=`<div class="lesson-reader"><h2>${esc(pack.name||'未命名课包')}</h2><p data-description></p><p class="course-count">${esc(pack.lesson?.audience||'适用对象待补充')} · ${pack.lesson?.duration||45} 分钟</p>${content.length?content.map(([key,title])=>`<section><h3>${title}</h3><div data-lesson="${key}"></div></section>`).join(''):'<p class="course-count">尚未填写教案，可先阅读学习材料，或点击编辑补充教学安排。</p>'}</div>`;
    textWithMath(host.querySelector('[data-description]'),pack.description||'');
    host.querySelectorAll('[data-lesson]').forEach(el=>textWithMath(el,pack.lesson[el.dataset.lesson]));
}
export async function openCoursePack(ident){
    const d=dialog('教案与课包');status(d,'正在读取…');
    try{const {data:pack}=await teachingRequest('/'+ident);if(!d.isConnected)return;
        const body=d.querySelector('.course-body');showLesson(body,pack);
        const actions=document.createElement('div');actions.className='course-reader-actions';actions.innerHTML='<button data-play-all>开始上课</button><button data-edit>编辑教案与视频</button><button data-md>导出教案</button><button data-json>导出课包 JSON</button><button data-delete>删除课包</button>';body.prepend(actions);
        const playlist=document.createElement('section');playlist.className='course-playlist';playlist.innerHTML='<h3>课堂播放顺序</h3>'+pack.video_ids.map((id,i)=>`<button data-play="${esc(id)}">${i+1}. ${esc(label(id))} <span>播放 ↗</span></button>`).join('');playlist.hidden=!pack.video_ids.length;body.append(playlist);
        renderMaterials(body,pack,d);
        actions.querySelector('[data-play-all]').disabled=!pack.video_ids.length&&!pack.resources?.length;
        if(!pack.video_ids.length&&pack.resources?.length)actions.querySelector('[data-play-all]').textContent='开始学习';
        actions.querySelector('[data-play-all]').onclick=()=>{if(!pack.video_ids.length){body.querySelector('[data-material-read]')?.click();return;}d.close();playPack(pack,0);};
        actions.querySelector('[data-edit]').onclick=()=>{d.close();editCoursePack(ident);};
        actions.querySelector('[data-md]').onclick=()=>download('教案-'+pack.id+'.md',markdown(pack),'text/markdown;charset=utf-8');
        actions.querySelector('[data-json]').onclick=()=>download('课包-'+pack.id+'.json',JSON.stringify({format:'wisdom-course-pack',version:1,...pack},null,2),'application/json');
        actions.querySelector('[data-delete]').onclick=async()=>{if(!confirm('确定删除此课包和教案？原视频会保留。'))return;try{await teachingRequest('/'+ident,{method:'DELETE'});d.close();changed();}catch(error){status(d,error.message);}};
        playlist.onclick=e=>{const id=e.target.closest('[data-play]')?.dataset.play;if(id){d.close();playPack(pack,pack.video_ids.indexOf(id));}};
        status(d,(pack.resources?.length||0)+' 份学习材料 · '+pack.video_ids.length+' 个视频 · 已保存在当前账户。JSON 课包含教案与视频引用，播放视频需连接本站。');
    }catch(error){status(d,error.message);}
}
export async function chooseCoursePack(videoId){
    const d=dialog('加入课包');status(d,'正在读取课包…');
    try{const {data}=await teachingRequest();if(!d.isConnected)return;const body=d.querySelector('.course-body');body.innerHTML='<p>选择课包，保留已有教案与播放顺序。</p><div class="course-pack-choices">'+data.map(p=>`<button data-choose="${p.id}">${esc(p.name)} <small>${p.video_count} 个视频</small></button>`).join('')+'</div><button data-create>新建课包并加入</button>';
        body.querySelector('[data-create]').onclick=()=>{d.close();editCoursePack(null,videoId);};
        body.onclick=async e=>{const b=e.target.closest('[data-choose]');if(!b)return;b.disabled=true;try{const {data:pack}=await teachingRequest('/'+b.dataset.choose);if(!pack.video_ids.includes(videoId))pack.video_ids.push(videoId);await teachingRequest('/'+pack.id,{method:'PUT',body:JSON.stringify(pack)});changed();status(d,'已加入“'+pack.name+'”');b.textContent='已加入';}catch(error){status(d,error.message);b.disabled=false;}};status(d,data.length?'':'还没有课包，可以从当前视频创建。');
    }catch(error){status(d,error.message);}
}
export async function importCoursePack(file){
    if(!file||file.size>32*1024*1024)throw new Error('请选择不超过 32MB 的课包 JSON');
    const p=JSON.parse(await file.text());if(p.format!=='wisdom-course-pack'||p.version!==1)throw new Error('课包格式不支持');
    const r=await teachingRequest('',{method:'POST',body:JSON.stringify({name:p.name,description:p.description,lesson:p.lesson,video_ids:p.video_ids,resources:(p.resources||[]).map(r=>({kind:r.kind,snapshot:r.snapshot}))})});changed();return openCoursePack(r.id);
}


export async function chooseCourseMaterial(resource){
    const d=dialog('将题解或错题加入课包');status(d,'正在读取课包…');
    try{
        const {data}=await teachingRequest();if(!d.isConnected)return;
        const body=d.querySelector('.course-body');
        body.innerHTML='<p>材料会保留收录时的题目、解答和分步题解，原记录删除后仍可阅读。</p><div class="course-pack-choices">'+data.map(p=>`<button data-material-pack="${p.id}">${esc(p.name)}</button>`).join('')+'</div><button data-material-new>新建课包并加入</button>';
        body.querySelector('[data-material-new]').onclick=()=>{d.close();editCoursePack(null,null,resource);};
        body.onclick=async e=>{
            const b=e.target.closest('[data-material-pack]');if(!b)return;b.disabled=true;
            try{
                const {data:pack}=await teachingRequest('/'+b.dataset.materialPack);
                if(resource.source_id&&pack.resources.some(r=>r.kind===resource.kind&&r.source_id===resource.source_id)){status(d,'此材料已在课包中');return;}
                pack.resources.push(resource);
                await teachingRequest('/'+pack.id,{method:'PUT',body:JSON.stringify(pack)});
                changed();b.textContent='已加入';status(d,'已加入“'+pack.name+'”，可从我的课件阅读');
            }catch(error){status(d,error.message);b.disabled=false;}
        };status(d,'选择已有课包，或创建新的课包');
    }catch(error){status(d,error.message);}
}
function renderMaterials(body,pack,d){
    const host=document.createElement('section');host.className='course-materials';body.append(host);
    const rows=pack.resources||[];
    const start=body.querySelector('[data-play-all]');if(start){start.disabled=!pack.video_ids.length&&!rows.length;start.textContent=pack.video_ids.length?'开始上课':'开始学习';}
    host.innerHTML='<h3>题解与练习</h3><p>在我的算式、解题结果或错题本中选择“加入课包”，即可收录到这里。</p>'+rows.map((r,i)=>`<article class="course-material" data-material="${i}"><h4>${esc(r.snapshot.title)}</h4><div data-material-problem></div><details><summary>参考解答与订正</summary><div data-material-answer></div></details><div class="course-reader-actions"><button data-material-read="${i}">阅读 / 继续解题</button>${r.source_id?`<button data-material-source="${i}">${r.kind==='wrongbook'?'复习原错题':'阅读原题解'}</button>`:''}<button data-material-up="${i}" ${i===0?'disabled':''} aria-label="上移材料">↑</button><button data-material-down="${i}" ${i===rows.length-1?'disabled':''} aria-label="下移材料">↓</button><button data-material-remove="${i}">移除</button></div></article>`).join('');
    host.querySelectorAll('[data-material]').forEach(el=>{const r=rows[Number(el.dataset.material)].snapshot;textWithMath(el.querySelector('[data-material-problem]'),r.problem);textWithMath(el.querySelector('[data-material-answer]'),r.answer+'\n\n'+r.note);});
    let saving=false;
    host.onclick=async e=>{
        const b=e.target.closest('button');if(!b||saving)return;
        try{
            if(b.dataset.materialRead!=null){const r=rows[Number(b.dataset.materialRead)];
                if(r.snapshot.solution){const S=await import('./solution-library.js');d.close();S.openSolutionRecord({...r.snapshot.solution,id:null});}
                else {if(!window.StepTutor)await(window.loadStepTutor?window.loadStepTutor():import('./step-tutor.js'));const st=window.StepTutor.getState();if(st.busy||st.rendering||st.saving)throw new Error('请先完成或停止当前解题任务');window.StepTutor.prefill(r.snapshot.problem);d.close();window.showSection?.('calculate');}return;}
            if(b.dataset.materialSource!=null){const r=rows[Number(b.dataset.materialSource)];if(r.kind==='wrongbook'){const W=await import('./wrongbook.js');d.close();await W.openWrongbookEntry(r.source_id,true);}else{const S=await import('./solution-library.js');d.close();await S.openSavedSolution(r.source_id);}return;}
            const updated=[...rows];
            if(b.dataset.materialRemove!=null){if(!confirm('从课包移除此材料？原记录会保留。'))return;updated.splice(Number(b.dataset.materialRemove),1);}
            else {const i=Number(b.dataset.materialUp??b.dataset.materialDown),j=i+(b.dataset.materialUp!=null?-1:1);[updated[i],updated[j]]=[updated[j],updated[i]];}
            saving=true;b.disabled=true;
            const result=await teachingRequest('/'+pack.id,{method:'PUT',body:JSON.stringify({...pack,resources:updated})});
            pack.resources=updated;pack.revision=result.revision;changed();host.remove();renderMaterials(body,pack,d);status(d,'学习材料已更新');
        }catch(error){status(d,error.message);}finally{saving=false;b.disabled=false;}
    };
}

async function playPack(pack,index){
    window.showSection?.('examples');
    for(let i=0;i<80;i++){if(window.Examples&&document.querySelector('#examples-filter')){await window.Examples.playCoursePack(pack,index);return;}await new Promise(resolve=>setTimeout(resolve,100));}
    window.showToast?.('案例页面仍在加载，请稍后重试','error');
}
