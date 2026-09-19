import { mountTaskBoard, queueMathTask, shouldDelegate, hasMathTasks, activeMathTasks } from '/static/js/agent-task-board.js?v=20260919-tasks-1';
import { escapeText as esc } from './solution-visual.js';
import { textWithMath } from './math-text.js';
import { recoverRequest, requestFailure } from './automatic-recovery.js';
import { libraryRequest, openSavedSolution } from './solution-library.js';

const state={messages:[],busy:false,status:'准备就绪',steps:[],index:-1,error:'',draft:'',image:null,lastRequest:null,result:null,username:null,templateSaved:false,templateSaving:false};
const views=new Set();let controller=null,version=0;
let executionContext={toolDone:new Set(),failedTutor:new Map()};
function enterSends(){try{return localStorage.getItem('agent_enter_send')!=='false';}catch{return true;}}
const names={calculate:'分步解题与动画',detect:'图片识别',devtools:'开发者工具','my-formulas':'我的算式',examples:'教学案例',help:'帮助',settings:'设置',chat:'回复'};
const samples=[['分步解题','解方程 x^2-5*x+6=0'],['理解函数','求导 sin(x)'],['创作动画','打开 Manim 工作台，编写并运行正方形变成圆的动画'],['整理学习','打开我的算式']];
function publish(){views.forEach(view=>view());updateDock();}
function abortCheck(signal){if(signal?.aborted)throw new DOMException('已停止','AbortError');}
async function waitFor(check,signal){const start=Date.now();while(!check()){abortCheck(signal);if(Date.now()-start>25000)throw new Error('工具加载超时，请刷新后重试。');await new Promise(r=>setTimeout(r,70));}return check();}
async function tutor(){if(!window.StepTutor)await(window.loadStepTutor?window.loadStepTutor():import('./step-tutor.js'));return window.StepTutor;}
async function navigate(section,signal){abortCheck(signal);window.showSection?.(section);await waitFor(()=>document.getElementById(section),signal);}
async function account(signal){const response=await fetch('/api/user/me',{credentials:'include',signal});if(response.status===401){window.toggleAuthModal?.(true);throw new Error('请先登录，登录后可继续执行。');}const data=await response.json();if(!response.ok||!data.username)throw new Error('无法确认账户，请稍后重试。');return data.username;}

export async function performDevtool(step,signal){
    const D=window.DevTools||await import('/static/js/devtools.js?v=20260917-creator-2');window.DevTools=D;D.initDevTools();const tool=step.devtool||'manim';
    D.switchDevTool(tool);
    if(tool==='latex'){D.fillLatexInDevtools(step.fill_latex||step.formula||'');return '公式已填入 LaTeX 编辑器';}
    if(tool!=='manim')return '已打开扩展库';
    await D.ensureManimEditor();abortCheck(signal);
    if(step.fill_manim_code)await D.openManimWorkbenchWithCode(step.fill_manim_code);
    const action=step.devtool_action||step.action;
    if(action==='run'){if(!await D.runDevManim({signal}))throw new Error('脚本运行未完成，请查看工作台日志。');return '脚本已运行，视频可播放';}
    if(action==='keyframe'){if(!await D.previewKeyframes({signal}))throw new Error('关键帧预览失败，请查看工作台日志。');return '关键帧已渲染';}
    if(action==='ai_edit'){document.getElementById('manim-ai-edit-float').style.display='flex';document.getElementById('manim-ai-edit-float').codeAssistant?.prefill(step.instruction||state.lastRequest?.prompt||'');return '代码助手已就绪，请检查需求并生成建议';}
    if(action==='import'){D.toggleImportPanel();return '已打开脚本库，请选择要导入的脚本';}
    if(action==='save'){await D.saveScriptDirect();return '脚本已保存到我的算式';}
    if(action==='summary'){if(!await D.generateVideoCopy())throw new Error('脚本说明生成失败');return '脚本说明已生成';}
    return step.fill_manim_code?'完整脚本已填入，可编辑或运行':'Manim 工作台已打开';
}

async function perform(step,context,signal,retry=false){
    abortCheck(signal);
    if(!context.toolDone.has(step)){
        if(step.section==='calculate'){
            const T=await tutor();const problem=step.formula||context.recognized;
            if(!problem)throw new Error('缺少题目内容，请补充完整题目。');
            if(step.trigger==='generate'){
                if(T.getState().busy||T.getState().rendering)throw new Error('另一个解题任务仍在运行，请先完成或停止该任务。');
                const listener=event=>{if(state.busy){state.status=event.detail.status;publish();}};
                window.addEventListener('tutor-state',listener);
                const cancel=()=>T.cancel();signal.addEventListener('abort',cancel,{once:true});
                try{
                    const previous=retry?context.failedTutor.get(step):null;
                    let ok;
                    if(previous?.failedStage==='render'&&previous.solution){
                        T.restore(previous);await T.render({retry:true});ok=!T.getState().error;
                    }else{ok=await T.solve(problem,{autoRender:true,retry:!!previous});}
                    abortCheck(signal);
                    if(!ok){context.failedTutor.set(step,T.getState());throw new Error(T.getState().status||'解题未完成');}
                    context.failedTutor.delete(step);
                }
                finally{window.removeEventListener('tutor-state',listener);signal.removeEventListener('abort',cancel);}
                context.solution=T.getState();state.result={section:'calculate',label:'查看分步解答与动画'};
            }else{T.prefill(problem);state.result={section:'calculate',label:'继续编辑题目'};}
        }else if(step.section==='detect'){
            if(!step.formula)throw new Error('未取得可用的识别结果，请重新上传清晰图片。');
            context.recognized=step.formula;
            state.messages.push({role:'assistant',text:'识别结果：\n'+step.formula});
            (await tutor()).prefill(step.formula);state.result={section:'calculate',label:'编辑并解答识别题目'};
        }else if(step.section==='devtools'){
            await navigate('devtools',signal);await waitFor(()=>document.getElementById('devtools')?.dataset.devInitialized,signal);const detail=await performDevtool(step,signal);step.detail=detail;state.result={section:'devtools',label:'打开工作台'};
        }else if(step.section==='settings'){
            if(!window.Settings?.applySingleSetting&&step.setting_key)throw new Error('当前页面不支持自动修改设置，请打开设置手动调整。');
            window.openSettings?.(step.settings_section);if(step.setting_key)window.Settings.applySingleSetting(step.setting_key,step.setting_value);
        }else if(step.section!=='chat'){
            if(!names[step.section])throw new Error('无法执行未知工具：'+step.section);
            await navigate(step.section,signal);
            if(step.section==='examples'){
                const E=await waitFor(()=>document.getElementById('examples-filter')&&window.Examples?.openCoursePackModal&&window.Examples,signal);
                if(step.examples_filter)await E.switchExamplesFilter(step.examples_filter);
                if(step.examples_action==='review'){const W=await import('./wrongbook.js');await E.switchExamplesFilter('wrongbook');await W.startWrongbookReview();step.detail='已读取当前账户的到期错题，按理解程度记录复习结果';}
                if(['create_pack','lesson'].includes(step.examples_action)){await E.openCoursePackModal();step.detail='已打开教案编辑器，填写内容后保存到我的课件';}
                if(['danmaku','notes'].includes(step.examples_action)){await E.switchExamplesFilter('all');E.focusPlayerFeature(step.examples_action);step.detail='选择一个案例后进入'+(step.examples_action==='notes'?'时间戳笔记':'播放器弹幕');}
            }
            state.result={section:step.section,label:'打开'+names[step.section]};
        }
        abortCheck(signal);
        context.toolDone.add(step);
    }
    if(step.save_to_formulas){
        if(context.solution){const s=context.solution;const result=await libraryRequest('',{method:'POST',headers:{'Content-Type':'application/json'},signal,body:JSON.stringify({problem:s.problem,context:s.context,solution:s.solution,video:s.video})});state.result={id:result.id,label:'阅读已保存题解'};}
        else{const latex=context.recognized||step.formula;if(!latex)throw new Error('尚无可保存的识别结果或题解。');
            const response=await fetch('/api/formulas/save',{method:'POST',headers:{'Content-Type':'application/json'},signal,body:JSON.stringify({username:state.username,latex,note:'智能体识别结果'})});const data=await response.json();if(!response.ok||data.status!=='success')throw new Error(data.message||'保存失败');}
        window.dispatchEvent(new CustomEvent('formula-library-updated'));step.detail='已保存到我的算式';
    }
}

export function stopAgent(){version++;controller?.abort();controller=null;
    if(state.steps[state.index]?.status==='running')state.steps[state.index].status='stopped';state.busy=false;state.status='已停止，已完成的结果保留。';publish();}

export async function executeAgent(prompt=state.draft,image=state.image,{retry=false}={}){
    prompt=String(prompt||'').trim();
    if(!retry&&!image&&shouldDelegate(prompt)){await queueMathTask(prompt);return;}
    if(state.busy)return;if(!prompt&&!image)return;
    const previous=state.messages.slice(-8),id=++version,aborter=new AbortController();controller=aborter;
    const request=retry?state.lastRequest:{prompt:prompt||'识别图片中的完整题目并分步解答。',image_base64:image,
        last_user_message:previous.filter(m=>m.role==='user').at(-1)?.text?.slice(-4000),last_assistant_message:previous.filter(m=>m.role==='assistant').at(-1)?.text?.slice(-4000)};
    if(!request)return;
    if(!retry){
        executionContext={toolDone:new Set(),failedTutor:new Map()};
        Object.assign(state,{steps:[],index:-1,result:null});
        state.messages.push({role:'user',text:request.prompt,image});
    }
    Object.assign(state,{busy:true,error:'',status:retry?'正在继续未完成的步骤，不重复扣额度…':'正在理解需求并选择工具…',lastRequest:request,draft:'',image:null,templateSaved:false,templateSaving:false});publish();
    try{
        const who=await fetch('/api/user/me',{credentials:'include',signal:aborter.signal});
        if(who.status!==401&&!who.ok)throw new Error('账户服务暂不可用，请稍后重试。');
        const username=who.ok?(await who.json()).username:null;
        if(retry&&username!==state.username)throw new Error('账户已切换，请在原账户中继续任务。');
        state.username=username;
        if(!retry||!state.steps.length){
            const data=await recoverRequest(async attempt=>{
                const transport=new AbortController();
                const abort=()=>transport.abort(aborter.signal.reason);
                aborter.signal.addEventListener('abort',abort,{once:true});
                const timeout=setTimeout(()=>transport.abort(new Error('等待执行计划超时，请稍后重试。')),180000);
                try{
                    const response=await fetch('/api/agent/execute',{method:'POST',headers:{'Content-Type':'application/json',...(retry||attempt?{'X-Wisdom-Retry':'1'}:{})},signal:transport.signal,body:JSON.stringify(request)});
                    let data;
                    try{data=await response.json();}catch{throw requestFailure('智能体响应未完整返回，请稍后重试。',{},response.status);}
                    if(!response.ok||data.status!=='success')throw requestFailure(data.message||'智能体未能生成计划，请补充要求。',data,response.status);
                    return data;
                }finally{clearTimeout(timeout);aborter.signal.removeEventListener('abort',abort);}
            },{signal:aborter.signal,maxRetries:retry?0:2,onRetry:attempt=>{
                state.status=`智能体正在自动修复执行计划（${attempt}/2），不重复扣额度…`;publish();
            }});
            abortCheck(aborter.signal);
            if(!Array.isArray(data.steps)||!data.steps.length)throw new Error('未收到可执行的计划，请重试。');
            const hasTools=data.steps.some(s=>s.section!=='chat');
            const reply=hasTools?'已安排以下步骤，执行完成后可以打开结果。':data.steps.map(s=>s.reply).filter(Boolean).join('\n');if(reply)state.messages.push({role:'assistant',text:reply});
            state.steps=data.steps.filter(s=>s.section!=='chat').map(s=>({...s,status:'pending'}));publish();
        }
        const context=executionContext;
        for(let i=0;i<state.steps.length;i++){
            if(state.steps[i].status==='done')continue;
            abortCheck(aborter.signal);state.index=i;const step=state.steps[i];step.status='running';state.status='正在执行：'+(names[step.section]||step.section);publish();
            await perform(step,context,aborter.signal,retry);abortCheck(aborter.signal);step.status='done';publish();
        }
        state.status=state.steps.length?'任务已完成':'已回复';
        if(context.solution)state.messages.push({role:'assistant',text:context.solution.solution.summary});
    }catch(error){if(id!==version)return;state.error=error.message;state.status=error.name==='AbortError'?'已停止':(error.autoRetryCount?'自动修复后仍未完成，原任务已保留。':'')+error.message;if(state.steps[state.index])state.steps[state.index].status='error';}
    finally{if(id===version){state.busy=false;controller=null;publish();}}
}
function openResult(){if(state.result?.id)openSavedSolution(state.result.id).catch(error=>{state.error=error.message;publish();});else if(state.result)window.showSection?.(state.result.section);}
function updateDock(){
    let dock=document.getElementById('agent-task-dock');if(!dock){dock=document.createElement('aside');dock.id='agent-task-dock';dock.className='agent-task-dock';document.body.append(dock);}
    dock.hidden=!state.busy;
    if(state.busy){dock.innerHTML=`<span class="assistant-spinner"></span><span>${esc(state.status)}</span><button data-return>查看任务</button><button data-stop>停止</button>`;dock.querySelector('[data-stop]').onclick=stopAgent;dock.querySelector('[data-return]').onclick=()=>window.showSection?.('agent');}
}
export function prefillAgent(text){state.draft=String(text||'');window.showSection?.('agent');publish();}
export function mountAgent(host){
    try{const pending=sessionStorage.getItem('pending_agent_prompt');if(pending){state.draft=pending;sessionStorage.removeItem('pending_agent_prompt');}}catch{}
    host.innerHTML=`<div class="assistant-shell"><aside class="assistant-sidebar"><span class="assistant-eyebrow">智算视界 / ASSISTANT</span><h2>从想法，到答案。</h2><p>让识别、推导与动画<br>在一次对话中衔接。</p><button data-agent="new"><i class="fa-solid fa-plus"></i> 新对话</button><div class="assistant-capabilities"><span>你可以交给我</span><p><i class="fa-solid fa-square-root-variable"></i> 解题与可视化</p><p><i class="fa-regular fa-image"></i> 图片题目识别</p><p><i class="fa-solid fa-code"></i> 动画代码创作</p><p><i class="fa-regular fa-bookmark"></i> 整理到我的算式</p></div><button data-agent="library">打开我的算式 ↗</button></aside><main class="assistant-main"><header><div><span class="assistant-eyebrow">学习与创作伙伴</span><h2>智算智能体</h2></div><span class="assistant-state">准备就绪</span></header><div class="assistant-thread" aria-label="对话记录"><div class="assistant-math-tasks"></div><div class="assistant-welcome"><div class="assistant-mark">✦</div><h3>今天，想探索什么？</h3><p>输入题目、上传图片，或描述你想实现的动画。</p><div class="assistant-samples">${samples.map(([title,prompt])=>`<button data-prompt="${esc(prompt)}"><span>${title}</span><small>${esc(prompt)}</small><i>↗</i></button>`).join('')}</div></div><div class="assistant-messages"></div><div class="assistant-plan" hidden><div class="assistant-plan-heading">执行进度 <span></span></div><ol></ol></div><div class="assistant-feedback" role="status" aria-live="polite"></div><div class="assistant-result-actions"><button data-agent="result" hidden>查看结果</button><button data-agent="retry" hidden>重试任务</button><button data-agent="template" hidden>存为模板</button></div></div><form class="assistant-composer"><div class="assistant-attachment" hidden><img alt="待识别的题目图片"><button type="button" data-agent="remove-image" aria-label="移除图片">×</button></div><textarea id="agent-prompt" rows="2" maxlength="6000" placeholder="描述你的问题，或粘贴一张题目图片…" aria-label="告诉智能体你的需求"></textarea><label class="agent-task-mode"><input type="checkbox" name="mathTaskMode"> 拆解题目 · 后台任务（可同时安排多道题）</label><div class="assistant-composer-bottom"><label class="assistant-upload" title="上传题目图片"><i class="fa-regular fa-image"></i><input type="file" accept="image/png,image/jpeg,image/webp" hidden></label><span>Enter 发送 · Shift + Enter 换行</span><button type="button" data-agent="stop" hidden>停止任务</button><button type="submit" id="agent-submit-btn">发送 <i class="fa-solid fa-arrow-up"></i></button></div></form></main></div>`;
    const $=s=>host.querySelector(s),input=$('textarea');let draftContext='';let messageCount=-1,lastPlan='',disposed=false;
    const binding=new AbortController(),on=(el,type,fn)=>el.addEventListener(type,fn,{signal:binding.signal});
    const fitViewport=()=>{
        const panel=$('.assistant-main');if(!panel?.getClientRects().length)return;
        const top=panel.getBoundingClientRect().top+window.scrollY;
        panel.style.setProperty('--assistant-viewport-height',`${Math.max(450,Math.min(800,window.innerHeight-top-16))}px`);
    };
    const resizeObserver=new ResizeObserver(fitViewport);
    [host,...document.querySelectorAll('.navbar,.agent-update-banner')].forEach(el=>resizeObserver.observe(el));
    on(window,'resize',fitViewport);
    function update(){
        if(disposed)return;
        $('.assistant-composer-bottom > span').textContent=enterSends()?'Enter 发送 · Shift + Enter 换行':'Enter 换行 · Ctrl / ⌘ + Enter 发送';
        if(document.activeElement!==input)input.value=state.draft;
        $('.assistant-state').textContent=state.busy?'处理中':activeMathTasks()?`${activeMathTasks()} 道题处理中`:state.error?'需要重试':'准备就绪';
        $('.assistant-feedback').textContent=state.messages.length?state.status:'';$('.assistant-feedback').classList.toggle('is-error',!!state.error);
        $('[type=submit]').disabled=state.busy&&!$('[name=mathTaskMode]').checked;$('[data-agent=stop]').hidden=!state.busy;$('[data-agent=new]').disabled=state.busy;
        $('[data-agent=template]').disabled=state.templateSaved||state.templateSaving;$('[data-agent=template]').textContent=state.templateSaved?'已存为模板':state.templateSaving?'保存中…':'存为模板';
        $('[data-agent=retry]').textContent='继续失败步骤 · 不扣额度';$('[data-agent=retry]').title='原失败请求 24 小时内可免费重试两次，已完成步骤不重复执行';$('[data-agent=retry]').hidden=!state.error||state.busy;$('[data-agent=template]').hidden=state.busy||!!state.error||!state.steps.length;$('[data-agent=result]').hidden=!state.result;if(state.result)$('[data-agent=result]').textContent=state.result.label;
        $('.assistant-welcome').hidden=!!state.messages.length||hasMathTasks();$('.assistant-attachment').hidden=!state.image;if(state.image)$('.assistant-attachment img').src=state.image;else $('.assistant-attachment img').removeAttribute('src');
        if(messageCount!==state.messages.length){messageCount=state.messages.length;$('.assistant-messages').innerHTML=state.messages.map((message,i)=>`<article class="assistant-message ${message.role}"><span>${message.role==='user'?'你':'智算'}</span><div data-message="${i}"></div>${message.image?`<img class="assistant-message-image" src="${esc(message.image)}" alt="题目图片">`:''}</article>`).join('');host.querySelectorAll('[data-message]').forEach(el=>textWithMath(el,state.messages[Number(el.dataset.message)].text));if(state.messages.length)$('.assistant-thread').scrollTop=$('.assistant-thread').scrollHeight;}
        const key=JSON.stringify(state.steps);if(key!==lastPlan){lastPlan=key;$('.assistant-plan').hidden=!state.steps.length;$('.assistant-plan-heading span').textContent=`${state.steps.filter(s=>s.status==='done').length} / ${state.steps.length}`;$('.assistant-plan ol').innerHTML=state.steps.map(s=>`<li class="${s.status}"><span class="assistant-step-icon">${s.status==='done'?'✓':s.status==='error'?'!':s.status==='running'?'◌':'○'}</span><div><strong>${esc(names[s.section]||s.section)}</strong><small>${esc(s.detail||({pending:'等待执行',running:'执行中…',done:'已完成',error:'执行未完成',stopped:'已停止'}[s.status]))}</small></div></li>`).join('');}
    }
    async function attach(file){if(!file)return;if(!/^image\/(png|jpeg|webp)$/.test(file.type)||file.size>8*1024*1024){state.error='请选择不超过 8MB 的 PNG、JPG 或 WebP 图片。';state.status=state.error;publish();return;}
        const reader=new FileReader();reader.onload=()=>{state.image=String(reader.result);state.error='';publish();};reader.readAsDataURL(file);
    }
    const submit=async()=>{
        const prompt=input.value.trim();if(!prompt&&!state.image)return;
        if($('[name=mathTaskMode]').checked||(!state.image&&shouldDelegate(prompt))){
            if(state.image){state.error='请先通过图片识题转成完整题面，再提交拆解任务。';state.status=state.error;publish();return;}
            if(await queueMathTask(prompt,draftContext)){input.value='';state.draft='';draftContext='';}
        }else{executeAgent(prompt);input.value='';}
    };
    on($('[name=mathTaskMode]'),'change',update);
    on(window,'agent-new-math-task',event=>{
        $('[name=mathTaskMode]').checked=true;
        state.draft=event.detail?.problem||'';draftContext=event.detail?.context||'';
        input.value=state.draft;input.focus();update();
    });
    on(window,'math-tasks-state',update);
    const disposeTasks=mountTaskBoard($('.assistant-math-tasks'));
    on(input,'input',()=>state.draft=input.value);on(input,'keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&(enterSends()||e.ctrlKey||e.metaKey)){e.preventDefault();if(!state.busy||$('[name=mathTaskMode]').checked)submit();}});
    on(input,'paste',e=>{const file=[...e.clipboardData.items].find(item=>item.type.startsWith('image/'))?.getAsFile();if(file){e.preventDefault();attach(file);}});
    on($('[type=file]'),'change',e=>{attach(e.target.files[0]);e.target.value='';});on($('form'),'submit',e=>{e.preventDefault();submit();});
    on(host,'click',e=>{const button=e.target.closest('button');if(!button)return;if(button.dataset.prompt){state.draft=button.dataset.prompt;input.value=state.draft;input.focus();return;}
        const action=button.dataset.agent;if(action==='stop')stopAgent();if(action==='result')openResult();if(action==='retry'&&state.lastRequest)executeAgent(state.lastRequest.prompt,state.lastRequest.image_base64,{retry:true});if(action==='library')window.showSection?.('my-formulas');
        if(action==='template'){saveTemplate(button);return;}
        if(action==='remove-image'){state.image=null;publish();}if(action==='new'&&!state.busy){executionContext={toolDone:new Set(),failedTutor:new Map()};Object.assign(state,{messages:[],steps:[],error:'',result:null,lastRequest:null,draft:'',image:null,status:'准备就绪'});input.value='';publish();}
    });
    views.add(update);update();window.AgentWorkspace={execute:executeAgent,stop:stopAgent,prefill:prefillAgent,getState:()=>({...state})};
    return()=>{disposed=true;resizeObserver.disconnect();disposeTasks();binding.abort();views.delete(update);};
}

async function saveTemplate(button){
    if(!state.lastRequest||state.templateSaved||state.templateSaving)return;
    const request=state.lastRequest,steps=state.steps;state.templateSaving=true;publish();
    try{const username=await account();const response=await fetch('/api/agent_templates/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,name:request.prompt.slice(0,60),prompt:request.prompt,steps})});const data=await response.json();if(!response.ok||data.status!=='success')throw new Error(data.message||'模板保存失败');if(state.lastRequest===request)state.templateSaved=true;window.dispatchEvent(new CustomEvent('formula-library-updated'));}
    catch(error){if(state.lastRequest===request){state.error=error.message;state.status=error.message;}}
    finally{if(state.lastRequest===request){state.templateSaving=false;publish();}}
}
window.addEventListener('auth-state-change',event=>{if(state.username&&event.detail?.username!==state.username){stopAgent();executionContext={toolDone:new Set(),failedTutor:new Map()};Object.assign(state,{messages:[],steps:[],result:null,lastRequest:null,username:null,error:'',status:'准备就绪',image:null,draft:''});publish();}});
