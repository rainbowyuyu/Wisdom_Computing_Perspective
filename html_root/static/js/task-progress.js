/** Shared task lifecycle: real step counts when available, otherwise indeterminate. */
export function createTaskStore() {
    const tasks=new Map(),listeners=new Set();
    const notify=()=>listeners.forEach(fn=>fn([...tasks.values()]));
    return {
        set(id,value){tasks.set(id,{...tasks.get(id),...value,id});notify();},
        get:id=>tasks.get(id),all:()=>[...tasks.values()],
        remove(id){if(tasks.delete(id))notify();},
        clear(){tasks.clear();notify();},
        subscribe(fn){listeners.add(fn);fn([...tasks.values()]);return()=>listeners.delete(fn);},
    };
}

export function applyProgressEvent(task,event) {
    const type=event.type||event.step;
    const next={message:type==='log'?'正在渲染动画…':String(event.message||task.message||'').slice(0,240)};
    if(type==='plan'&&Number.isInteger(event.total)&&event.total>0)Object.assign(next,{total:event.total,completed:0,progress:0});
    if(type==='step'&&Number.isInteger(event.index)&&task.total>0)Object.assign(next,{completed:event.index+1,progress:Math.min(99,(event.index+1)/task.total*100)});
    if(type==='progress'&&Number.isInteger(event.chapter)&&event.total>0)Object.assign(next,{progress:Math.min(99,Math.max(0,event.chapter/event.total*100))});
    if(type==='repair'||event.repairing)next.progress=null;
    if(type==='complete'&&!event.part)Object.assign(next,{status:'done',progress:100,message:'已完成'});
    if(type==='handoff')Object.assign(next,{status:'done',progress:100,message:'已转交后台任务'});
    if(type==='error')Object.assign(next,{status:'error',progress:null});
    return next;
}

export const activities=typeof window!=='undefined'?(window.__wisdomActivities??=createTaskStore()):createTaskStore();
const routes={
    '/api/solve/stream':['分步解题','calculate'], '/api/solve/render':['分步动画','calculate'],
    '/api/agent/execute':['智能体','agent'], '/api/detect':['识别题目','detect'],
    '/api/animate':['矩阵动画','calculate'], '/api/animate/stream':['动态计算','calculate'],
    '/api/devtools/edit_code':['创作助手','devtools'], '/api/devtools/render_keyframe':['关键帧预览','devtools'],
    '/api/devtools/run_manim_stream':['动画渲染','devtools'], '/api/devtools/run_manim':['动画渲染','devtools'],
    '/api/devtools/generate_video_copy':['脚本说明','devtools'],
};
const expiry=new Map();
function settle(id,status,message) {
    const task=activities.get(id);if(!task||task.status!=='running')return;
    activities.set(id,{status,message:message||({done:'已完成',error:'未完成，请查看提示',cancelled:'已停止'}[status]),progress:status==='done'?100:null,cancel:null});
    clearTimeout(expiry.get(id));expiry.set(id,setTimeout(()=>{expiry.delete(id);activities.remove(id);},status==='error'?5000:1600));
}

function installNetworkProgress() {
    if(window.__wisdomProgressFetch)return;window.__wisdomProgressFetch=true;
    const original=window.fetch.bind(window);
    window.fetch=async(input,options={})=>{
        const url=new URL(typeof input==='string'||input instanceof URL?String(input):input.url,location.href);
        const info=url.origin===location.origin?routes[url.pathname]:null;
        if(!info||(options.method||input?.method||'GET').toUpperCase()!=='POST')return original(input,options);
        const id='request:'+crypto.randomUUID(),controller=new AbortController();
        const upstream=options.signal||input?.signal;
        const abort=()=>controller.abort(upstream?.reason);
        if(upstream?.aborted)abort();else upstream?.addEventListener('abort',abort,{once:true});
        activities.set(id,{label:info[0],section:info[1],status:'running',message:'正在提交…',progress:null,cancel:()=>{
            controller.abort();
            if(url.pathname.startsWith('/api/solve/'))window.StepTutor?.cancel();
        },started:Date.now()});
        let ended=false;
        const finish=(status,message)=>{if(ended)return;ended=true;upstream?.removeEventListener('abort',abort);settle(id,status,message);};
        try {
            const response=await original(input,{...options,signal:controller.signal});
            if(!response.body){finish(response.ok?'done':'error');return response;}
            const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',legacyCompleted=false;
            const sse=response.headers.get('content-type')?.includes('text/event-stream');
            activities.set(id,{message:sse?'正在处理…':'正在等待结果…'});
            const inspect=event=>{
                if(event.step==='complete')legacyCompleted=true;
                const task=activities.get(id);if(!task||ended)return;
                const update=applyProgressEvent(task,event);
                if(update.status)finish(update.status,update.message);
                else activities.set(id,update);
            };
            const body=new ReadableStream({
                async pull(out){
                    try{
                        const {done,value}=await reader.read();
                        buffer+=decoder.decode(value,{stream:!done});
                        if(sse){
                            let boundary;
                            while((boundary=/\r?\n\r?\n/.exec(buffer))){
                                const frame=buffer.slice(0,boundary.index);buffer=buffer.slice(boundary.index+boundary[0].length);
                                const json=frame.split(/\r?\n/).filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
                                try{if(json)inspect(JSON.parse(json));}catch{}
                            }
                        }
                        // Observing progress must never accumulate an unlimited response.
                        if(buffer.length>2_000_000)buffer='';
                        if(done){
                            if(!sse){let result;try{result=JSON.parse(buffer);}catch{}finish(response.ok&&result?.status!=='error'?'done':'error',result?.status==='error'?result.message:undefined);}
                            else finish(legacyCompleted?'done':'error',legacyCompleted?'已完成':'连接已结束，请查看任务结果');
                            reader.releaseLock();out.close();
                        }else out.enqueue(value);
                    }catch(error){finish(controller.signal.aborted?'cancelled':'error');out.error(error);}
                },
                cancel(reason){finish('cancelled');return reader.cancel(reason);},
            });
            const wrapped=new Response(body,{status:response.status,statusText:response.statusText,headers:response.headers});
            Object.defineProperties(wrapped,{url:{value:response.url},redirected:{value:response.redirected},type:{value:response.type}});
            return wrapped;
        }catch(error){finish(controller.signal.aborted?'cancelled':'error');throw error;}
    };
    window.addEventListener('auth-state-change',()=>{activities.all().forEach(t=>t.cancel?.());activities.clear();});
}

export function syncBackgroundTasks(jobs) {
    const ids=new Set();
    for(const job of jobs){
        const id='job:'+job.id;ids.add(id);
        if(!['queued','planning','running'].includes(job.status)){
            if(activities.get(id))settle(id,job.status==='done'?'done':job.status==='cancelled'?'cancelled':'error',job.message);
            continue;
        }
        clearTimeout(expiry.get(id));expiry.delete(id);
        let total=0,done=0;
        for(const node of job.nodes||[]){
            total++;if(node.status==='done')done++;
            if(job.auto_render||!['skipped',undefined].includes(node.render_status)){total++;if(node.render_status==='done')done++;}
        }
        activities.set(id,{label:job.title||'后台解题',section:'agent',status:'running',message:job.message||'后台处理中',progress:total?Math.min(99,done/total*100):null,started:Date.now()});
    }
    activities.all().filter(t=>t.id.startsWith('job:')&&!ids.has(t.id)).forEach(t=>activities.remove(t.id));
}

export function mountTaskProgress() {
    const panel=document.getElementById('knowledge-panel'),bubble=document.getElementById('knowledge-panel-bubble');
    if(!panel||!bubble||panel.dataset.progressReady)return;
    panel.dataset.progressReady='true';
    const logo=panel.querySelector('.knowledge-bubble-logo');
    let wrap=document.getElementById('knowledge-bubble-render-wrap');
    if(!wrap){wrap=document.createElement('div');wrap.id='knowledge-bubble-render-wrap';wrap.className='knowledge-bubble-render-wrap';(bubble.querySelector('.knowledge-panel-bubble-inner')||bubble).append(wrap);}
    wrap.innerHTML='<div id="knowledge-bubble-water" class="knowledge-bubble-water"><div class="knowledge-bubble-wave"></div></div><span id="knowledge-bubble-render-pct" class="knowledge-bubble-render-pct"></span><span class="knowledge-bubble-render-text"></span>';
    let block=document.getElementById('knowledge-panel-render-progress');
    if(!block){block=document.createElement('section');block.id='knowledge-panel-render-progress';document.getElementById('knowledge-panel-header').after(block);}
    block.className='knowledge-panel-render-progress task-progress-panel';
    block.innerHTML='<div class="task-progress-heading"><strong>任务进度</strong><span data-task-count></span></div><div class="task-progress-track" role="progressbar" aria-label="当前任务进度" aria-valuemin="0" aria-valuemax="100"><i></i></div><div class="task-progress-items"></div>';
    const water=wrap.querySelector('.knowledge-bubble-water'),percent=wrap.querySelector('#knowledge-bubble-render-pct'),caption=wrap.querySelector('.knowledge-bubble-render-text'),track=block.querySelector('[role=progressbar]'),list=block.querySelector('.task-progress-items');
    let frame=0,pending=[],lastRows='';
    function render(){
        frame=0;const all=pending,running=all.filter(t=>t.status==='running'),visible=all.length>0;
        wrap.style.display=visible?'flex':'none';if(logo)logo.style.display=visible?'none':'';block.hidden=!visible;block.style.display=visible?'':'none';
        panel.classList.toggle('has-active-tasks',running.length>0);
        if(!visible){panel.removeAttribute('data-task-state');bubble.setAttribute('aria-label','打开智算星云');return;}
        const selected=running.length?running:all;
        const known=selected.every(t=>Number.isFinite(t.progress));
        const progress=known?selected.reduce((sum,t)=>sum+t.progress,0)/selected.length:null;
        const status=running.length?'running':all.some(t=>t.status==='error')?'error':all.some(t=>t.status==='cancelled')?'cancelled':'done';
        panel.dataset.taskState=status;
        water.style.height=(progress==null?45:Math.max(8,progress))+'%';
        percent.textContent=progress==null?(running.length>1?running.length+'项':'…'):Math.round(progress)+'%';
        caption.textContent=running.length>1?'任务进行中':status==='running'?(progress==null?'处理中':'步骤进度'):status==='done'?'已完成':status==='cancelled'?'已停止':'需查看';
        bubble.setAttribute('aria-label',running.length?`${running.length} 项任务进行中，打开查看进度`:'打开智算星云查看任务结果');
        track.classList.toggle('is-indeterminate',!known);track.firstElementChild.style.width=(known?progress:35)+'%';
        if(known)track.setAttribute('aria-valuenow',Math.round(progress));else track.removeAttribute('aria-valuenow');
        track.setAttribute('aria-valuetext',known?Math.round(progress)+'%':'处理中，尚无可计算的完成比例');
        block.querySelector('[data-task-count]').textContent=running.length?running.length+' 项进行中':'本次任务结果';
        const key=JSON.stringify(all.map(({id,label,message,status,progress,cancel})=>({id,label,message,status,progress,cancel:!!cancel})));
        if(key!==lastRows){lastRows=key;list.replaceChildren(...all.map(task=>{
            const row=document.createElement('div');row.className='task-progress-item';
            const open=document.createElement('button');open.type='button';open.className='task-progress-open';
            const label=document.createElement('strong'),note=document.createElement('span');label.textContent=task.label;note.textContent=task.message||'处理中';open.append(label,note);open.onclick=()=>window.showSection?.(task.section);row.append(open);
            if(task.cancel&&task.status==='running'){const stop=document.createElement('button');stop.type='button';stop.textContent='停止';stop.setAttribute('aria-label','停止'+task.label);stop.onclick=()=>task.cancel();row.append(stop);}
            return row;
        }));}
    }
    activities.subscribe(tasks=>{pending=tasks;if(!frame)frame=requestAnimationFrame(render);});
    const visibility=()=>panel.classList.toggle('tasks-page-hidden',document.hidden);
    document.addEventListener('visibilitychange',visibility);visibility();
}

if(typeof window!=='undefined'){
    installNetworkProgress();
    if(!document.getElementById('task-progress-css')){const css=document.createElement('link');css.id='task-progress-css';css.rel='stylesheet';css.href='/static/css/components/task-progress.css';document.head.append(css);}
}
