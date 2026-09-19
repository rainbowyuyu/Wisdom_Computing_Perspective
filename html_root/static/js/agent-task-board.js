import { escapeText as esc } from './solution-visual.js';
import { textWithMath } from './math-text.js';
import { syncBackgroundTasks } from '/static/js/task-progress.js';

const state={jobs:[],pending:null,error:'',owner:null,loading:false};
const views=new Set();let timer=null,polling=false,epoch=0,submitting=false;
const active=job=>['queued','planning','running'].includes(job.status);
const statusNames={queued:'排队中',planning:'正在拆解',running:'处理中',done:'已完成',error:'部分失败',partial:'待补充条件',needs_information:'待补充条件',cancelled:'已停止',interrupted:'待恢复',blocked:'等待前置结果'};
const publish=()=>{syncBackgroundTasks(state.jobs);views.forEach(view=>view());window.dispatchEvent(new CustomEvent('math-tasks-state'));};
export const hasMathTasks=()=>state.jobs.length>0||!!state.pending;
export const activeMathTasks=()=>state.jobs.filter(active).length;
function schedule(){clearTimeout(timer);if(!document.hidden&&(views.size||state.jobs.some(active)))timer=setTimeout(refreshTasks,state.jobs.some(active)?2000:10000);}

async function api(path='',options={}){
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),15000);
    try{
        const response=await fetch('/api/agent/tasks'+path,{credentials:'include',...options,signal:controller.signal});
        const data=await response.json();
        if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:data.message||'任务请求未完成，请稍后重试。');error.status=response.status;throw error;}
        return data;
    }catch(error){if(error.name==='AbortError')throw new Error('连接超时，题目已保留；重试提交不会重复创建任务。');throw error;}
    finally{clearTimeout(timeout);}
}

export async function refreshTasks(){
    if(polling)return;
    const run=epoch;polling=true;
    try{const data=await api();if(run!==epoch)return;state.jobs=data.items;state.owner=data.owner;state.error='';}
    catch(error){if(run!==epoch)return;if(error.status===401){state.jobs=[];state.owner=null;}else state.error=error.message;}
    finally{polling=false;if(run===epoch)publish();schedule();}
}

export function shouldDelegate(problem){return String(problem).length>1800||(String(problem).match(/[（(][1-9一二三四五六][)）]/g)||[]).length>=3;}

export async function queueMathTask(problem,context='',autoRender=true,forceDecompose=false){
    if(submitting){state.error='上一道题正在提交，请稍候再添加。';publish();return false;}
    const previous=state.pending;
    const request=previous&&previous.problem===problem&&previous.context===context&&previous.auto_render===autoRender&&!!previous.force_decompose===forceDecompose?previous:
        {problem:String(problem).trim(),context,auto_render:autoRender,force_decompose:forceDecompose,request_key:crypto.randomUUID()};
    state.pending=request;state.error='';window.showSection?.('agent');
    if(!request.problem){state.error='请先输入完整题目。';publish();return false;}
    const run=epoch;submitting=true;publish();
    try{
        const job=await api('',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});
        if(run!==epoch)return false;
        state.pending=null;state.jobs=[job,...state.jobs.filter(j=>j.id!==job.id)];
        publish();schedule();return true;
    }catch(error){if(run===epoch){state.error=error.message;if(error.status===401)window.toggleAuthModal?.(true);publish();}return false;}
    finally{submitting=false;publish();}
}

export function mountTaskBoard(host){
    host.innerHTML=`<section class="math-task-board"><header><div><span class="assistant-eyebrow">后台解题任务</span><h3>拆开难题，一步步完成。</h3><p>最多同时安排 3 道题；独立小问并行，有依赖的步骤按顺序生成。切换页面不影响后台任务。</p></div><button type="button" data-task-new>新增题目</button></header><p class="math-task-feedback" role="status"></p><div class="math-task-pending" hidden><p></p><button type="button" data-task-submit>继续提交</button></div><div class="math-task-list"></div></section>`;
    let last='',alive=true;const binding=new AbortController();
    const $=selector=>host.querySelector(selector);
    const update=()=>{
        if(!alive)return;
        $('.math-task-feedback').textContent=state.error||(!state.jobs.length?'可以提交复杂题，查看拆解计划与每个子任务的进度。':'');
        $('.math-task-pending').hidden=!state.pending;
        if(state.pending)textWithMath($('.math-task-pending p'),'待提交题目：'+state.pending.problem);
        $('[data-task-submit]').disabled=submitting;
        const key=JSON.stringify(state.jobs);if(key===last)return;last=key;
        const expanded=new Set([...host.querySelectorAll('[data-job] details[open]')].map(el=>el.closest('[data-job]').dataset.job));
        $('.math-task-list').innerHTML=state.jobs.map(job=>{
            const total=job.nodes.length,done=job.completed||0;
            return `<article class="math-task-card" data-job="${esc(job.id)}"><div class="math-task-heading"><h4 data-job-title></h4><span class="math-task-badge ${esc(job.status)}">${esc(statusNames[job.status]||job.status)}</span></div><details><summary>原题与条件</summary><p data-job-problem></p></details><p class="math-task-message">${esc(job.message)}</p><div class="math-task-progress" role="progressbar" aria-label="子题完成进度" aria-valuemin="0" aria-valuemax="${Math.max(1,total)}" aria-valuenow="${done}"><span style="width:${total?Math.round(done/total*100):0}%"></span></div><small>${total?`${done} / ${total} 个子目标已解答`:'正在等待或整理拆解计划'}</small><ol>${job.nodes.map((node,i)=>`<li><div class="math-subtask-heading"><strong data-node-title="${i}"></strong><span>${esc(statusNames[node.status]||node.status)}</span></div><p>${esc(node.message)}</p><small>${node.depends_on.length?'依赖第 '+node.depends_on.map(d=>d+1).join('、')+' 个子目标':'独立任务，可并行'}</small>${node.render_status!=='skipped'&&node.render_status!=='pending'?`<p class="math-render-state">动画：${esc(node.render_message||({queued:'等待渲染资源',running:'正在渲染',cancelled:'已停止',interrupted:'待恢复'}[node.render_status]||statusNames[node.render_status]||node.render_status))}</p>`:''}${['done','partial'].includes(node.status)?`<button type="button" data-task-read="${i}">阅读解答${node.render_status==='done'?'与动画':''}</button>`:''}</li>`).join('')}</ol><footer>${active(job)?'<button type="button" data-task-cancel>停止本题</button>':''}${['error','cancelled','interrupted'].includes(job.status)?'<button type="button" data-task-retry>只继续未完成部分</button>':''}${['partial','needs_information'].includes(job.status)?'<button type="button" data-task-edit>补充条件后重新提交</button>':''}</footer></article>`;
        }).join('');
        host.querySelectorAll('[data-job]').forEach(el=>{
            const job=state.jobs.find(j=>j.id===el.dataset.job);
            el.querySelector('details').open=expanded.has(job.id);
            textWithMath(el.querySelector('[data-job-title]'),job.title);
            textWithMath(el.querySelector('[data-job-problem]'),job.problem+(job.context?'\n补充条件：'+job.context:''));
            el.querySelectorAll('[data-node-title]').forEach(node=>textWithMath(node,`${Number(node.dataset.nodeTitle)+1}. ${job.nodes[Number(node.dataset.nodeTitle)].title}`));
        });
    };
    host.addEventListener('click',async event=>{
        const button=event.target.closest('button');if(!button)return;
        const job=state.jobs.find(j=>j.id===button.closest('[data-job]')?.dataset.job);
        if(button.hasAttribute('data-task-new')){window.dispatchEvent(new CustomEvent('agent-new-math-task'));return;}
        if(button.hasAttribute('data-task-edit')&&job){window.dispatchEvent(new CustomEvent('agent-new-math-task',{detail:{problem:job.problem,context:job.context}}));return;}
        if(button.hasAttribute('data-task-submit')&&state.pending){const p=state.pending;await queueMathTask(p.problem,p.context,p.auto_render,p.force_decompose);return;}
        if(!job)return;
        button.disabled=true;const run=epoch;
        try{
            if(button.hasAttribute('data-task-read')){
                const detail=await api('/'+job.id);if(run!==epoch||!alive)return;
                const node=detail.nodes[Number(button.dataset.taskRead)];
                const {openSolutionRecord}=await import('./solution-library.js?v=20260919-teaching-2');
                if(run!==epoch||!alive)return;
                openSolutionRecord({problem:detail.problem,context:detail.context,solution:node.solution,video:node.video});
            }else{
                const updated=await api('/'+job.id+(button.hasAttribute('data-task-cancel')?'/cancel':'/retry'),{method:'POST'});
                if(run!==epoch)return;
                state.jobs=state.jobs.map(j=>j.id===job.id?updated:j);state.error='';publish();schedule();
            }
        }catch(error){if(run===epoch){state.error=error.message;publish();}}
        finally{button.disabled=false;}
    },{signal:binding.signal});
    views.add(update);update();refreshTasks();
    return()=>{alive=false;binding.abort();views.delete(update);schedule();};
}

document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(timer);else if(views.size||state.jobs.some(active))refreshTasks();});

window.addEventListener('auth-state-change',event=>{
    const next=event.detail?.username||null;
    const pending=state.owner===null?state.pending:null;
    epoch++;state.jobs=[];state.owner=next;state.error='';state.pending=pending;publish();
    if(next&&pending&&!submitting)queueMathTask(pending.problem,pending.context,pending.auto_render,pending.force_decompose);
    else if(views.size)refreshTasks();
});
