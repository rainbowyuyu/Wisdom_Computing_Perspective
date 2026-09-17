import { escapeText as esc } from './solution-visual.js';
import { textWithMath } from './math-text.js';

const labels={new:'待复习',reviewing:'复习中',mastered:'已掌握'};
const grades={again:'仍需练习',good:'基本掌握',mastered:'已掌握'};
const localKey='wcp_examples_wrongbook_v1';
const notify=()=>window.dispatchEvent(new CustomEvent('wrongbook-updated'));
const date=value=>value?new Date(value).toLocaleString('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'无需安排';
const time=value=>Math.floor(value/60)+':'+String(Math.floor(value%60)).padStart(2,'0');
export async function wrongbookRequest(path,options={}){
    const response=await fetch('/api/wrongbook'+path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...options.headers}});
    const result=await response.json();
    if(!response.ok||result.status!=='success'){const error=new Error(typeof result.detail==='string'?result.detail:result.message||'操作未完成，请检查输入后重试');error.status=response.status;throw error;}
    return result;
}
function status(d,message){if(d.isConnected)d.querySelector('[role=status]').textContent=message;}
function modal(title){
    const d=document.createElement('dialog');d.className='course-dialog wrongbook-dialog';d.setAttribute('aria-label',title);
    d.innerHTML=`<header><div><span class="assistant-eyebrow">智算视界 / REVIEW</span><h2>${esc(title)}</h2></div><button data-wb-close aria-label="关闭">×</button></header><div class="course-body"></div><p class="course-status" role="status" aria-live="polite"></p>`;
    document.body.append(d);d.showModal();d.querySelector('[data-wb-close]').onclick=()=>d.close();d.addEventListener('close',()=>d.remove(),{once:true});return d;
}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function localEntries(){try{const data=JSON.parse(localStorage.getItem(localKey)||'[]');return Array.isArray(data)?data:[];}catch{return [];}}

export async function editWrongbook(initial={}){
    const d=modal(initial.id?'编辑错题':'收录一道错题');status(d,'正在读取…');
    try{
        // Authenticate before showing an editable form, preserving entered content on later errors.
        const account=await wrongbookRequest('/list?page_size=1');if(!d.isConnected)return;
        const record=initial.id?(await wrongbookRequest('/'+initial.id)).data:initial;if(!d.isConnected)return;
        let dirty=false,saving=false;
        const body=d.querySelector('.course-body');body.innerHTML=`<form class="course-editor wrongbook-editor"><div class="course-form-row"><label>标题<input name="title" required maxlength="512" placeholder="为这道题起一个简短标题" value="${esc(record.title||'')}"></label><label>知识点标签<input name="tags" placeholder="用逗号分隔，最多 12 个" value="${esc((record.tags||[]).join(', '))}"></label><label>难度（1–5）<input name="difficulty" type="number" min="1" max="5" required value="${record.difficulty||3}"></label></div><label>题目<textarea name="problem" required maxlength="12000" rows="4" placeholder="输入完整题目，支持 LaTeX">${esc(record.problem||'')}</textarea></label><label>参考解答<textarea name="answer" maxlength="60000" rows="5" placeholder="记录正确思路或答案">${esc(record.answer||'')}</textarea></label><label>错因与订正<textarea name="note" maxlength="12000" rows="4" placeholder="哪里出错了？下次如何避免？">${esc(record.note||'')}</textarea></label><div class="wrongbook-preview" hidden></div><div class="course-form-actions"><button type="button" data-wb-preview>预览公式</button><button type="submit">保存错题</button></div></form>`;
        const form=body.querySelector('form');form.oninput=()=>dirty=true;
        const collect=()=>{const f=new FormData(form);return {...record,username:account.username,title:f.get('title'),problem:f.get('problem'),answer:f.get('answer'),note:f.get('note'),difficulty:Number(f.get('difficulty')),tags:String(f.get('tags')).split(/[,，]/).map(t=>t.trim()).filter(Boolean)};};
        const close=()=>{if(!saving&&(!dirty||confirm('有未保存的修改，确定关闭？')))d.close();};
        d.querySelector('[data-wb-close]').onclick=close;d.addEventListener('cancel',e=>{e.preventDefault();close();});
        form.querySelector('[data-wb-preview]').onclick=()=>{const p=body.querySelector('.wrongbook-preview');p.hidden=!p.hidden;textWithMath(p,[collect().problem,collect().answer,collect().note].join('\n\n'));};
        form.onsubmit=async e=>{e.preventDefault();if(saving)return;saving=true;form.querySelector('[type=submit]').disabled=true;status(d,'正在保存…');try{const result=await wrongbookRequest(record.id?'/'+record.id:'/add',{method:record.id?'PUT':'POST',body:JSON.stringify(collect())});dirty=false;notify();if(result.duplicate)window.showToast?.('这道题已收录，已打开已有记录','info');if(d.isConnected){d.close();await openWrongbookEntry(result.id);}}catch(error){status(d,error.message);}finally{saving=false;if(d.isConnected)form.querySelector('[type=submit]').disabled=false;}};
        status(d,record.video_id?'来源：教学视频 '+time(record.time_sec||0)+' · 保存至当前账户':record.snapshot?'保留原题解快照，修改笔记不影响原题解':'保存至当前账户，支持 LaTeX 与复习计划');
    }catch(error){if(error.status===401){d.close();window.toggleAuthModal?.(true);}else status(d,error.message);}
}

export async function openWrongbookEntry(id,review=false,next=null){
    const d=modal(review?'专注复习':'错题详情');status(d,'正在读取…');
    try{
        let {data:r}=await wrongbookRequest('/'+id);if(!d.isConnected)return;
        const body=d.querySelector('.course-body');
        body.innerHTML=`<article class="wrongbook-reader"><div class="wrongbook-meta"><span>${labels[r.status]} · 难度 ${r.difficulty} · 复习 ${r.review_count} 次</span><span>${r.tags.map(esc).join(' / ')}</span></div><h2>${esc(r.title)}</h2><section><h3>题目</h3><div data-math="problem"></div></section><details class="wrongbook-answer" ${review?'':'open'}><summary>查看参考解答与订正</summary><section><h3>参考解答</h3><div data-math="answer"></div></section><section><h3>错因与订正</h3><div data-math="note"></div></section><div class="wrongbook-snapshot"></div></details><div class="course-reader-actions"><button data-wb-edit>编辑</button>${r.video_id?'<button data-wb-video>回看视频 '+time(r.time_sec)+'</button>':''}<button data-wb-solve>继续可视化解题</button><button data-wb-pack>加入课包</button><button data-wb-exercise>让智能体出同类题</button><button data-wb-delete>删除</button></div><section class="wrongbook-review"><h3>本次复习</h3><p>根据自己的理解程度记录，系统据此安排下次复习。</p><label>复习心得<textarea rows="2" maxlength="4000" placeholder="这次理解了什么？"></textarea></label><div class="course-reader-actions">${Object.entries(grades).map(([g,label])=>`<button data-grade="${g}">${label}</button>`).join('')}</div><button data-wb-next hidden>继续下一题 →</button></section><details class="wrongbook-history"><summary>复习记录（最近 100 次）</summary><div></div></details></article>`;
        for(const key of ['problem','answer','note'])textWithMath(body.querySelector(`[data-math=${key}]`),r[key]||'尚未填写');
        const snapshot=body.querySelector('.wrongbook-snapshot');
        if(r.snapshot?.solution){snapshot.innerHTML='<h3>收录时的分步题解</h3>';r.snapshot.solution.steps.forEach((step,i)=>{const section=document.createElement('section');const h=document.createElement('h4');textWithMath(h,`${i+1}. ${step.title}`);const content=document.createElement('div');textWithMath(content,step.explanation+'\n\n'+(step.formula?'$$'+step.formula+'$$':''));section.append(h,content);snapshot.append(section);});}
        const renderHistory=()=>{const history=body.querySelector('.wrongbook-history>div');history.innerHTML=r.reviews?.length?r.reviews.map(item=>`<p><b>${grades[item.grade]}</b> · ${esc(date(item.reviewed_at))}<br>${esc(item.note||'未填写心得')}</p>`).join(''):'<p>尚无复习记录。</p>';};renderHistory();
        body.querySelector('[data-wb-edit]').onclick=()=>{d.close();editWrongbook(r);};
        body.querySelector('[data-wb-video]')?.addEventListener('click',async()=>{d.close();window.showSection?.('examples');const E=await import('./examples.js');await E.ensurePlayer();E.playExampleByVideoId(r.video_id,r.time_sec);});
        body.querySelector('[data-wb-solve]')?.addEventListener('click',async()=>{if(!window.StepTutor)await(window.loadStepTutor?window.loadStepTutor():import('./step-tutor.js'));const st=window.StepTutor.getState();if(st.busy||st.rendering||st.saving){status(d,'请先完成或停止当前解题任务');return;}if(r.snapshot?window.StepTutor.restore(r.snapshot):(window.StepTutor.prefill(r.problem),true)){d.close();window.showSection?.('calculate');}else status(d,'请先完成或停止当前解题任务');});
        body.querySelector('[data-wb-pack]').onclick=async()=>{d.close();const C=await import('./course-packs.js');C.chooseCourseMaterial({kind:'wrongbook',source_id:r.id});};
        body.querySelector('[data-wb-exercise]').onclick=async()=>{d.close();const A=await import('./agent-workspace.js');A.prefillAgent('请根据这道错题设计一道同类练习，并解释如何避免类似错误。\n题目：'+r.problem+'\n错因：'+r.note);};
        body.querySelector('[data-wb-delete]').onclick=async()=>{if(!confirm('确定删除这道错题及其复习记录？'))return;try{await wrongbookRequest('/'+id,{method:'DELETE'});d.close();notify();}catch(error){status(d,error.message);}};
        body.querySelectorAll('[data-grade]').forEach(button=>{button.onclick=async()=>{const buttons=body.querySelectorAll('[data-grade]');buttons.forEach(b=>b.disabled=true);try{await wrongbookRequest('/'+id+'/review',{method:'POST',body:JSON.stringify({revision:r.revision,grade:button.dataset.grade,note:body.querySelector('textarea').value})});r=(await wrongbookRequest('/'+id)).data;notify();renderHistory();body.querySelector('.wrongbook-meta>span').textContent=`${labels[r.status]} · 难度 ${r.difficulty} · 复习 ${r.review_count} 次`;status(d,r.status==='mastered'?'已标记掌握；若要再练习，可选择“仍需练习”':'复习已记录 · 下次复习 '+date(r.next_review_at));if(next){const b=body.querySelector('[data-wb-next]');b.hidden=false;b.onclick=()=>{d.close();next();};}else buttons.forEach(b=>b.disabled=false);}catch(error){status(d,error.message);buttons.forEach(b=>b.disabled=false);}};});
        status(d,'下次复习：'+date(r.next_review_at)+' · 参考答案可折叠，先尝试独立解答');
    }catch(error){status(d,error.message);}
}

export async function startWrongbookReview(){
    try{const result=await wrongbookRequest('/list?status=due&page_size=1');if(result.data.length)openWrongbookEntry(result.data[0].id,true,startWrongbookReview);else window.showToast?.('今天的待复习题目已完成','success');}catch(error){window.showToast?.(error.message,'error');}
}

export async function renderWrongbook(host,isCurrent=()=>true,options={}){
    host.classList.add('wrongbook-host');host.innerHTML='<p role="status">正在读取错题本…</p>';
    const state=options.video_id?{page:1,status:'all',q:'',tag:'',video_id:options.video_id}:host.wrongbookState||{page:1,status:'all',q:'',tag:'',video_id:''};host.wrongbookState=state;let generation=0;
    async function refresh(){
        const current=++generation;try{
            const result=await wrongbookRequest('/list?'+new URLSearchParams({...state,page_size:12}));if(!host.isConnected||!isCurrent()||current!==generation)return;
            if(state.page>Math.max(1,Math.ceil(result.total/12))){state.page=Math.max(1,Math.ceil(result.total/12));return refresh();}
            const stats=result.stats;host.innerHTML=`<div class="wrongbook-toolbar"><div><h3>我的错题本</h3><p>记录错因，回看过程，把薄弱环节逐一弄懂。</p></div><button data-wb-new>手动收录</button><button data-wb-review ${stats.due?'':'disabled'}>开始复习 · ${stats.due}</button><button data-wb-export>导出错题本</button>${localEntries().length?'<button data-wb-import>同步本地记录 · '+localEntries().length+'</button>':''}</div><div class="wrongbook-stats"><span>共 <b>${stats.total}</b> 题</span><span>待复习 <b>${stats.due}</b></span><span>已掌握 <b>${stats.mastered}</b></span><span>累计复习 <b>${stats.reviews}</b> 次</span></div><form class="wrongbook-search"><input name="q" aria-label="搜索错题" placeholder="搜索题目、标题或错因" value="${esc(state.q)}"><select name="status" aria-label="复习状态">${Object.entries({all:'全部状态',due:'当前待复习',...labels}).map(([v,t])=>`<option value="${v}" ${v===state.status?'selected':''}>${t}</option>`).join('')}</select><select name="tag" aria-label="知识点"><option value="">全部知识点</option>${result.tags.map(t=>`<option ${t===state.tag?'selected':''}>${esc(t)}</option>`).join('')}</select><button type="submit">筛选</button>${state.video_id?'<button type="button" data-wb-all>查看全部视频与题目</button>':''}</form><div class="wrongbook-cards">${result.data.map(r=>`<article class="wrongbook-card"><span>${labels[r.status]} · ${esc(r.source_type==='video'?'视频 '+time(r.time_sec):r.source_type==='solution'?'分步题解':'手动记录')}</span><h3>${esc(r.title)}</h3><div data-problem="${r.id}"></div><p>${r.tags.map(esc).join(' / ')||'未分类'} · 难度 ${r.difficulty}</p><small>下次复习：${date(r.next_review_at)}</small><button data-wb-open="${r.id}">阅读与复习 ↗</button></article>`).join('')||'<div class="course-empty"><h3>暂无符合条件的错题</h3><p>可手动收录，或从题解与教学视频加入错题本。</p></div>'}</div><div class="wrongbook-pagination"><button data-page="-1" ${state.page===1?'disabled':''}>上一页</button><span>第 ${state.page} 页 · ${result.total} 题</span><button data-page="1" ${state.page*12>=result.total?'disabled':''}>下一页</button></div><p class="wrongbook-status" role="status"></p>`;
            for(const r of result.data)textWithMath(host.querySelector(`[data-problem="${r.id}"]`),r.problem.slice(0,400));
            host.querySelector('form').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target);state.q=String(f.get('q'));state.status=String(f.get('status'));state.tag=String(f.get('tag'));state.page=1;refresh();};
            host.onclick=async e=>{const b=e.target.closest('button');if(!b)return;
                try{
                    if(b.hasAttribute('data-wb-new'))editWrongbook();
                    if(b.hasAttribute('data-wb-review'))startWrongbookReview();
                    if(b.dataset.wbOpen)openWrongbookEntry(Number(b.dataset.wbOpen));
                    if(b.dataset.page){state.page+=Number(b.dataset.page);refresh();}
                    if(b.hasAttribute('data-wb-all')){state.video_id='';state.page=1;refresh();}
                    if(b.hasAttribute('data-wb-export')){const pack=await wrongbookRequest('/export');download('我的错题本.json',JSON.stringify(pack,null,2),'application/json;charset=utf-8');}
                    if(b.hasAttribute('data-wb-import')){b.disabled=true;const account=await wrongbookRequest('/list?page_size=1');let imported=0;for(const item of localEntries()){await wrongbookRequest('/add',{method:'POST',body:JSON.stringify({username:account.username,video_id:item.video_id||'',time_sec:Math.max(0,Math.floor(item.time_sec||0)),title:item.title||'视频复习',note:item.note||'',problem:item.title||'视频复习'})});imported++;}notify();window.showToast?.(`已同步 ${imported} 条，本地备份保留；重复同步不会重复收录。`,'success');}
                }catch(error){if(host.isConnected&&isCurrent())host.querySelector('.wrongbook-status').textContent=error.message;b.disabled=false;}
            };
        }catch(error){if(host.isConnected&&isCurrent()){host.innerHTML=`<div class="course-empty"><h3>${esc(error.message)}</h3><button data-wb-login>${error.status===401?'登录后使用错题本':'重新读取'}</button></div>`;host.querySelector('button').onclick=()=>error.status===401?window.toggleAuthModal?.(true):refresh();}}
    }
    await refresh();
}

export function openWrongbook(options={}){window.pendingWrongbookOptions=options;window.showSection?.('examples');const start=Date.now();const open=()=>{if(document.getElementById('examples-filter')&&window.Examples?.switchExamplesFilter){window.Examples.switchExamplesFilter('wrongbook');return;}if(Date.now()-start<15000)setTimeout(open,70);else window.showToast?.('错题本加载超时，请刷新重试','error');};open();}
window.openWrongbook=openWrongbook;
window.addEventListener('auth-state-change',()=>document.querySelectorAll('.wrongbook-dialog').forEach(d=>d.close()));
