import { textWithMath, renderFormula, normalizeSolution } from './math-text.js';
import { consumeEvents } from './event-stream.js';
import { escapeText as esc, visualMarkup } from './solution-visual.js';
import { libraryRequest, solutionMarkdown, exportSolution, openSavedSolution } from './solution-library.js';

const state = {problem:'',context:'',draftProblem:'',draftContext:'', solution:null, steps:[], index:0, progress:1, status:'', busy:false, rendering:false, video:null, error:false, tools:[], capabilities:null,libraryId:null,libraryOwner:null,saving:false,savedVersion:''};
let controller=null, renderController=null, generation=0, timer=null, playing=false, playbackFrame=0;
const mounts = new Set();
const HISTORY_KEY='wisdom.tutor.history.v1';
function historyItems() { try { return JSON.parse(localStorage.getItem(HISTORY_KEY)||'[]').slice(0,8); } catch { return []; } }
function publish() {
    mounts.forEach(view=>view.update());
    window.dispatchEvent(new CustomEvent('tutor-state', {detail:{problem:state.problem,status:state.status,busy:state.busy||state.rendering,index:state.index,total:state.steps.length,error:state.error}}));
}
function stopPlayback() { clearInterval(timer); cancelAnimationFrame(playbackFrame); playbackFrame=0; timer=null; playing=false; }
function selectStep(index, fromVideo=false) {
    state.index=Math.max(0,Math.min(index,state.steps.length-1)); state.progress=1;
    mounts.forEach(view=> { view.showStep(); if(!fromVideo&&state.video) view.seek(state.index); });
    publish();
}
function remember() {
    if (!state.solution) return;
    try {
        const items=historyItems().filter(item=>item.problem!==state.problem);
        items.unshift({problem:state.problem,context:state.context,solution:state.solution,video:state.video,id:state.libraryId,username:state.libraryOwner,date:Date.now()});
        localStorage.setItem(HISTORY_KEY,JSON.stringify(items.slice(0,8)));
    } catch { /* A full or disabled browser store must not interrupt a solution. */ }
}
export function cancelTutor() {
    generation++; controller?.abort(); renderController?.abort();
    controller=null; renderController=null; state.busy=false; state.rendering=false;
    stopPlayback(); state.status='已停止。已生成的步骤仍可阅读和操作。'; publish();
}

export async function solveProblem(problem, {autoRender=true, context=''}={}) {
    problem=String(problem||'').trim();
    if(!problem) { state.status='请先输入完整题目。'; publish(); return false; }
    if(problem.length>6000) {state.status='题目请控制在 6000 字以内。';publish();return false;}
    controller?.abort(); renderController?.abort(); stopPlayback();
    const run=++generation; const aborter=new AbortController(); controller=aborter;
    Object.assign(state,{problem,context,draftProblem:problem,draftContext:context,solution:null,steps:[],index:0,progress:1,busy:true,rendering:false,video:null,error:false,tools:['planner'],libraryId:null,libraryOwner:null,savedVersion:'',status:'正在分析题目…'});
    mounts.forEach(view=>view.reset()); publish();
    let succeeded=false;
    try {
        const response=await fetch('/api/solve/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({problem,context}),signal:aborter.signal});
        await consumeEvents(response,event=> {
            if(run!==generation) return;
            if(event.type==='error') throw new Error(event.message);
            if(event.message) state.status=event.message;
            if(event.tool&&!state.tools.includes(event.tool)) state.tools.push(event.tool);
            if(event.type==='plan') {state.status=event.title;state.tools.push(event.source,'interactive_svg');}
            if(event.type==='step') {
                state.steps[event.index]=normalizeSolution({steps:[event.step]}).steps[0];
                mounts.forEach(view=>view.showStep());
            }
            if(event.type==='complete') {
                state.solution=normalizeSolution(event.solution);state.steps=state.solution.steps;state.status='分步解答已完成，可切换步骤或播放讲解。';succeeded=true;
                remember(); mounts.forEach(view=>view.showStep());
            }
            publish();
        },aborter.signal);
    } catch(error) {
        if(run===generation&&error.name!=='AbortError') {state.error=true;state.status=error.message||'解题失败，请重试。';}
    } finally {
        if(run===generation) {state.busy=false;controller=null;publish();}
    }
    if(succeeded&&run===generation&&autoRender) await renderTutor();
    return succeeded&&run===generation&&!state.error;
}

export async function renderTutor() {
    if(!state.solution||state.busy||state.rendering) return;
    const run=generation; const aborter=new AbortController(); renderController=aborter;
    state.rendering=true;state.error=false;state.status='准备生成分步 Manim 动画…';
    if(!state.tools.includes('manim'))state.tools.push('manim');publish();
    try {
        const response=await fetch('/api/solve/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({solution:state.solution}),signal:aborter.signal});
        await consumeEvents(response,event=> {
            if(run!==generation)return;
            if(event.type==='error')throw new Error(event.message);
            if(event.message)state.status=event.message;
            if(event.type==='complete') {
                if(!/^\/videos\/solution_[a-f0-9]+\.mp4$/.test(event.video_url))throw new Error('视频地址无效。');
                state.video={url:event.video_url,chapters:event.chapters};state.status='解答与动画均已完成。点击步骤可跳到对应视频章节。';remember();
                mounts.forEach(view=>view.showVideo());
            }
            publish();
        },aborter.signal);
    } catch(error) {
        if(run===generation&&error.name!=='AbortError') {state.error=true;state.status=error.message||'动画未完成，交互解答已保留。';}
    } finally {
        if(run===generation) {state.rendering=false;renderController=null;publish();}
    }
    if(run===generation&&state.libraryId&&state.video&&!state.error)await saveToLibrary();
}

const recordSnapshot=()=>({problem:state.problem,context:state.context,solution:state.solution,video:state.video});
export async function saveToLibrary() {
    if(!state.solution||state.saving||state.rendering||state.busy)return;
    const run=generation,snapshot=recordSnapshot(),savedId=state.libraryId,savedOwner=state.libraryOwner;state.saving=true;publish();
    try {
        const meResponse=await fetch('/api/user/me',{credentials:'include'});
        if(meResponse.status===401){window.toggleAuthModal?.(true);throw new Error('请先登录，登录后可将题解保存到我的算式。');}
        const me=await meResponse.json();if(!me.username)throw new Error('暂时无法确认账户，请稍后重试。');
        const id=savedOwner===me.username?savedId:null;
        const result=await libraryRequest('',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...snapshot,id})});
        if(run===generation){state.libraryId=result.id;state.libraryOwner=result.username;state.savedVersion=JSON.stringify(snapshot);state.status='已保存到我的算式，可随时阅读题解与动画。';remember();}
        window.dispatchEvent(new CustomEvent('formula-library-updated'));
    }catch(error){if(run===generation){state.status=error.message||'保存失败，请重试。';if(error.status===404){state.libraryId=null;state.savedVersion='';state.status='原记录已删除，可重新保存当前题解。';}}}
    finally{state.saving=false;publish();}
}

export function restoreSavedSolution(record) {
    if(state.busy||state.rendering||state.saving)return false;
    stopPlayback();generation++;
    record={...record,solution:normalizeSolution(record.solution)};
    Object.assign(state,{problem:record.problem,context:record.context||'',draftProblem:record.problem,draftContext:record.context||'',solution:record.solution,steps:record.solution.steps,index:0,progress:1,video:record.video||null,error:false,libraryId:record.id||null,libraryOwner:record.username||null,status:record.id?'正在阅读已保存题解':'已恢复最近的题解。',tools:[record.solution.source,'interactive_svg']});
    state.savedVersion=record.id?JSON.stringify(recordSnapshot()):'';
    mounts.forEach(view=>{view.reset();view.showStep();view.showVideo();});publish();return true;
}

export function mountTutor(host) {
    if(!host||host.dataset.tutorMounted)return()=>{};
    host.dataset.tutorMounted='true';host.classList.add('step-tutor');
    host.innerHTML=`<form class="tutor-composer"><div class="tutor-composer-heading"><label for="tutor-problem">开始一道新题</label><div><button type="button" data-action="detect"><i class="fa-regular fa-image"></i> 图片识题</button><button type="button" data-action="library"><i class="fa-regular fa-bookmark"></i> 我的算式</button></div></div><div class="tutor-input-tabs" role="group" aria-label="输入方式"><button type="button" data-input-mode="text" aria-pressed="true">题目 / LaTeX</button><button type="button" data-input-mode="math" aria-pressed="false">可视化公式</button><span class="tutor-input-help">支持完整题面与 LaTeX</span></div><math-field class="tutor-math-input" aria-label="可视化题目公式" virtual-keyboard-mode="manual" hidden></math-field><textarea id="tutor-problem" name="problem" rows="3" maxlength="6000" placeholder="输入题目或 LaTeX，探索每一步推导与图形变化…"></textarea><div class="tutor-input-preview" aria-label="题目预览" hidden></div>
      <div class="tutor-compose-actions"><label class="tutor-check"><input name="autoRender" type="checkbox" checked> 同步生成动画</label><span class="tutor-key-hint">Ctrl / ⌘ + Enter</span><button type="submit" class="tutor-primary">开始解题 <i class="fa-solid fa-arrow-right"></i></button><button type="button" data-action="cancel" hidden>停止</button></div></form>
      <div class="tutor-examples" aria-label="示例题"><span>从示例开始</span>${[['一元方程','解方程 x^2-5*x+6=0'],['函数求导','求导 sin(x)'],['定积分','定积分 x^2 从 0 到 1'],['矩阵变换','矩阵 [[1,2],[0,1]]']].map(([label,t])=>`<button type="button" data-example="${esc(t)}">${label}<i class="fa-solid fa-arrow-up-right-from-square"></i></button>`).join('')}</div>
      <div class="tutor-status-row"><p class="tutor-status" role="status" aria-live="polite"></p><button type="button" data-action="retry" hidden>重试解题</button></div>
      <div class="tutor-workspace" hidden><nav class="tutor-step-list" aria-label="解题步骤"></nav><div class="tutor-stage"><div class="tutor-step-header"><span class="tutor-step-count"></span><h4></h4></div><p class="tutor-explanation"></p><div class="tutor-formula"></div><div class="tutor-visual"></div><p class="tutor-caption"></p><label class="tutor-slider-label">探索图形 <input type="range" min="0" max="1000" value="1000" aria-label="图形探索进度"><output>100%</output></label><details class="tutor-hint"><summary>这一步的提示</summary><p></p></details><div class="tutor-player"><button type="button" data-action="prev" aria-label="上一步">← 上一步</button><button type="button" data-action="play">▶ 自动讲解</button><label>速度 <select aria-label="讲解速度"><option value="6500">0.75×</option><option value="5000" selected>1×</option><option value="3000">1.5×</option></select></label><button type="button" data-action="next" aria-label="下一步">下一步 →</button></div></div></div>
      <div class="tutor-result" hidden><span class="tutor-result-label">解题结论</span><p class="tutor-answer"></p><p class="tutor-verification"></p><div class="tutor-result-actions"><button type="button" class="tutor-primary" data-action="save"><i class="fa-regular fa-bookmark"></i> 保存到我的算式</button><button type="button" data-action="read" hidden>阅读已保存题解</button><button type="button" data-action="render">生成动画</button><details class="tutor-more"><summary>更多 <i class="fa-solid fa-chevron-down"></i></summary><div><button type="button" data-action="wrongbook">加入错题本</button><button type="button" data-action="pack">加入课包</button><button type="button" data-action="export">导出笔记</button><button type="button" data-action="copy">复制解答</button></div></details></div></div>
      <div class="tutor-video" hidden><div class="tutor-video-header"><h4>Manim 分步动画</h4><a download="解题动画.mp4">下载视频 ↓</a></div><video controls playsinline preload="metadata"></video><div class="tutor-chapters"></div></div>
      <details class="tutor-history"><summary>最近练习 <span>仅当前设备</span></summary><div></div><button type="button" data-action="clear-history">清空记录</button></details>`;
    const $=s=>host.querySelector(s), $$=s=>host.querySelectorAll(s);
    const input=$('textarea'), mathInput=$('math-field');input.value=state.draftProblem;
    let inputMode='text';
    const mathReady=()=>typeof mathInput.setValue==='function';
    function syncInput(value) {
        input.value=value;
        if(mathReady())mathInput.setValue(value,{silenceNotifications:true});
        const preview=$('.tutor-input-preview');
        preview.hidden=inputMode==='math'||!value.trim();textWithMath(preview,value);
    }
    function inputModeTo(mode, focus=true) {
        if(mode==='math'&&!mathReady()) {
            $('.tutor-input-help').textContent='公式组件正在加载，可继续输入 LaTeX';return;
        }
        inputMode=mode;input.hidden=mode==='math';mathInput.hidden=mode!=='math';
        $$('[data-input-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.inputMode===mode)));
        $('.tutor-input-help').textContent=mode==='math'?'点击公式编辑 · 支持粘贴 LaTeX':'支持完整题面与 LaTeX';
        syncInput(input.value);if(focus)(mode==='math'?mathInput:input).focus();
    }
    function changed(value) {
        if(value!==state.draftProblem)state.draftContext='';state.draftProblem=value;
        syncInput(value);
    }
    customElements.whenDefined('math-field').then(()=>{
        if(!host.isConnected)return;
        mathInput.mathVirtualKeyboardPolicy='manual';syncInput(input.value);
    });
    syncInput(input.value);
    let lastStep=null,lastIndex=-1,lastHistory='',lastSteps='', lastCapabilities=null;
    const bindings=new AbortController();const on=(el,type,fn)=>el.addEventListener(type,fn,{signal:bindings.signal});
    function draw() {
        const step=state.steps[state.index]; if(!step)return;
        $('.tutor-visual').innerHTML=visualMarkup(step.visual,state.progress);
        const reasoning=$('.tutor-reasoning p');if(reasoning)textWithMath(reasoning,step.visual?.caption||reasoning.textContent);
        $('input[type=range]').value=String(state.progress*1000);$('output').textContent=Math.round(state.progress*100)+'%';
    }
    function showStep() {
        const step=state.steps[state.index];if(!step)return;
        if(lastStep===step&&lastIndex===state.index)return;
        lastStep=step;lastIndex=state.index;
        textWithMath($('.tutor-step-header h4'),step.title);
        $('.tutor-step-count').textContent=`步骤 ${state.index+1} / ${state.steps.length}`;
        textWithMath($('.tutor-explanation'),step.explanation);
        renderFormula($('.tutor-formula'),step.formula);
        textWithMath($('.tutor-caption'),step.visual?.caption||'');
        $('.tutor-hint').hidden=!step.hint;textWithMath($('.tutor-hint p'),step.hint||'');$('.tutor-hint').open=false;
        $('.tutor-slider-label').hidden=!['plot','matrix','geometry'].includes(step.visual?.kind);
        if(!matchMedia('(prefers-reduced-motion: reduce)').matches) $('.tutor-stage').animate([{opacity:.5,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:200});
        draw();
    }
    function showVideo() {
        const video=$('video');$('.tutor-video').hidden=!state.video;
        if(!state.video) {video.pause();video.removeAttribute('src');video.load();return;}
        if(video.getAttribute('src')!==state.video.url)video.src=state.video.url;
        $('.tutor-video a').href=state.video.url;
        $('.tutor-chapters').innerHTML=state.video.chapters.map((c,i)=>`<button type="button" data-chapter="${i}">${i+1}. ${esc(c.title)}</button>`).join('');
    }
    function update() {
        $('.tutor-step-count').textContent=`步骤 ${state.index+1} / ${state.steps.length}`;
        $('.tutor-status').textContent=state.status;host.classList.toggle('tutor-has-error',state.error);
        $('button[type=submit]').disabled=state.busy||state.rendering;
        $('[data-action=cancel]').hidden=!(state.busy||state.rendering);
        $('[data-action=retry]').hidden=!state.error||state.busy||state.rendering;
        $('[data-action=render]').disabled=state.busy||state.rendering;
        $('[data-action=render]').textContent=state.rendering?'动画生成中…':state.video?'重新生成动画':state.error?'重试动画':'生成动画';
        const saved=state.savedVersion===JSON.stringify(recordSnapshot());
        $('[data-action=save]').disabled=state.busy||state.rendering||state.saving||saved;
        $('[data-action=save]').textContent=state.saving?'正在保存…':saved?'已保存到我的算式':state.libraryId?'更新到我的算式':'保存到我的算式';
        $('[data-action=read]').hidden=!state.libraryId;
        $('.tutor-workspace').hidden=!state.steps.length;$('.tutor-result').hidden=!state.solution;
        textWithMath($('.tutor-answer'),state.solution?.summary||'');textWithMath($('.tutor-verification'),state.solution?.verification||'');
        const listKey=state.steps.map(s=>s.title).join('|');
        if(listKey!==lastSteps) {lastSteps=listKey;$('.tutor-step-list').innerHTML=state.steps.map((s,i)=>`<button type="button" data-step="${i}"><span>${String(i+1).padStart(2,'0')}</span><span class="tutor-step-title">${esc(s.title)}</span></button>`).join('');$$('.tutor-step-title').forEach((el,i)=>textWithMath(el,state.steps[i].title));}
        $$('[data-step]').forEach(b=>{b.classList.toggle('is-current',Number(b.dataset.step)===state.index);b.setAttribute('aria-current',Number(b.dataset.step)===state.index?'step':'false');});
        $('[data-action=prev]').disabled=state.index===0;$('[data-action=next]').disabled=state.index>=state.steps.length-1;
        $('[data-action=play]').textContent=playing?'Ⅱ 暂停讲解':'▶ 自动讲解';
        const items=historyItems(),key=items.map(i=>i.date).join(',');
        if(key!==lastHistory) {lastHistory=key;$('.tutor-history div').innerHTML=items.map((item,i)=>`<button type="button" data-history="${i}">${esc(item.problem.slice(0,80))}</button>`).join('')||'<p>完成的解答会出现在这里。</p>';}
        if(state.capabilities!==lastCapabilities) {
            lastCapabilities=state.capabilities;
            if(state.capabilities&&!state.capabilities.manim) {$('[name=autoRender]').checked=false;$('[name=autoRender]').disabled=true;}
        }
    }
    const view={update,showStep,showVideo,prefill(problem){syncInput(problem);inputModeTo('text');},seek(index){const c=state.video?.chapters[index];if(c)$('video').currentTime=c.start;},reset(){lastStep=null;lastIndex=-1;syncInput(state.problem);showVideo();}};
    mounts.add(view);showStep();showVideo();update();
    const submit=()=>solveProblem(input.value,{autoRender:$('[name=autoRender]').checked,context:input.value===state.draftProblem?state.draftContext:''});
    on($('form'),'submit',e=>{e.preventDefault();submit();});
    on(input,'input',()=>changed(input.value));
    on(mathInput,'input',()=>{
        const value=String(mathInput.value||'');
        if(value!==state.draftProblem)state.draftContext='';state.draftProblem=value;input.value=value;
    });
    on(mathInput,'keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!state.busy&&!state.rendering){e.preventDefault();submit();}});
    on(input,'keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!state.busy&&!state.rendering){e.preventDefault();submit();}});
    on($('input[type=range]'),'input',e=>{state.progress=Number(e.target.value)/1000;draw();});
    on($('video'),'timeupdate',()=>{const t=$('video').currentTime;const index=state.video?.chapters.findIndex(c=>t>=c.start&&t<c.end);if(index>=0&&index!==state.index)selectStep(index,true);});
    function play() {
        if(playing){stopPlayback();publish();return;}
        if(state.index===state.steps.length-1)selectStep(0);
        $('video').pause();playing=true;
        let stepStarted=performance.now(), lastFrame=0, lastAnimatedIndex=state.index;
        const animate = now => {
            if(!playing)return;
            if(document.hidden||!host.checkVisibility()){stopPlayback();publish();return;}
            if(state.index!==lastAnimatedIndex){lastAnimatedIndex=state.index;stepStarted=now;}
            if(now-lastFrame>32&&!matchMedia('(prefers-reduced-motion: reduce)').matches){state.progress=Math.min(1,(now-stepStarted)/(Number($('select').value)*.8));draw();lastFrame=now;}
            playbackFrame=requestAnimationFrame(animate);
        };
        playbackFrame=requestAnimationFrame(animate);
        timer=setInterval(()=>{if(document.hidden||!host.checkVisibility()){stopPlayback();publish();return;}if(state.index>=state.steps.length-1){stopPlayback();publish();}else selectStep(state.index+1);},Number($('select').value));publish();
    }
    on($('select'),'change',()=>{if(playing){stopPlayback();play();}});
    on(host,'click',async e=> {
        const b=e.target.closest('button');if(!b)return;
        if(b.dataset.inputMode){inputModeTo(b.dataset.inputMode);return;}
        if(b.dataset.example){prefillProblem(b.dataset.example);input.focus();return;}
        if(b.dataset.step!=null){stopPlayback();selectStep(Number(b.dataset.step));return;}
        if(b.dataset.chapter!=null){stopPlayback();selectStep(Number(b.dataset.chapter));$('video').play().catch(()=>{});return;}
        if(b.dataset.history!=null){const item=historyItems()[Number(b.dataset.history)];if(item&&!restoreSavedSolution(item)){state.status='请先完成或停止当前任务，再打开历史题解。';publish();}return;}
        const action=b.dataset.action;
        if(action==='cancel')cancelTutor();
        if(action==='retry')submit();
        if(action==='prev'||action==='next'){stopPlayback();selectStep(state.index+(action==='next'?1:-1));}
        if(action==='play')play();
        if(action==='render')renderTutor();
        if(action==='save')saveToLibrary();
        if(action==='wrongbook'&&state.solution){const W=await import('./wrongbook.js');W.editWrongbook({source_type:'solution',formula_id:state.libraryId,snapshot:recordSnapshot(),problem:state.problem,title:state.solution.title,answer:state.solution.summary});}
        if(action==='read')openSavedSolution(state.libraryId).catch(error=>{state.status=error.message;publish();});
        if(action==='detect')window.showSection?.('detect');
        if(action==='library')window.showSection?.('my-formulas');
        if(action==='pack'&&state.solution){const C=await import('./course-packs.js');C.chooseCourseMaterial({kind:'solution',source_id:state.libraryId,snapshot:{title:state.solution.title,problem:state.problem,answer:state.solution.summary,solution:recordSnapshot()}});}
        if(action==='export'&&state.solution)exportSolution(recordSnapshot());
        if(action==='copy'&&state.solution){try{await navigator.clipboard.writeText(solutionMarkdown(recordSnapshot()));state.status='解答已复制。';}catch{state.status='无法访问剪贴板，请使用导出笔记。';}publish();}
        if(action==='clear-history'){try{localStorage.removeItem(HISTORY_KEY);}catch{}lastHistory='pending';update();}
    });
    return()=>{mounts.delete(view);bindings.abort();$('video').pause();stopPlayback();delete host.dataset.tutorMounted;};
}

export function initStepTutor() {
    const page=document.getElementById('calculate');
    if(page&&!page.querySelector('.step-tutor')) {
        const host=document.createElement('div');(page.querySelector('.section-subtitle')||page.querySelector('.section-title'))?.after(host);mountTutor(host);
    }
}

export function prefillProblem(problem, context='') {
    state.draftProblem=String(problem||'');
    state.draftContext=String(context||'');
    mounts.forEach(view=>view.prefill(state.draftProblem));
}

window.StepTutor={prefill:prefillProblem,mount:mountTutor,solve:solveProblem,cancel:cancelTutor,render:renderTutor,getState:()=>({...state}),selectStep,save:saveToLibrary,restore:restoreSavedSolution};
window.addEventListener('auth-state-change',event=>{if(state.libraryOwner&&state.libraryOwner!==event.detail?.username){state.libraryId=null;state.libraryOwner=null;state.savedVersion='';publish();}});
window.addEventListener('formula-library-deleted',event=>{if(state.libraryId===event.detail?.id){state.libraryId=null;state.savedVersion='';publish();}});
fetch('/api/solve/capabilities').then(r=>r.ok?r.json():null).then(c=>{state.capabilities=c;publish();}).catch(()=>{});
