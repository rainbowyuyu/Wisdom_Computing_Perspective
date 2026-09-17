import { escapeText as esc } from './solution-visual.js';

// Both frontends share the same result routing and request cancellation.
export function initNavSearch(){
    const input=document.getElementById('nav-search-input'),dropdown=document.getElementById('nav-search-dropdown');
    if(!input||!dropdown)return ()=>{};
    let timer,request,version=0,items=[];
    const events=new AbortController(),on=(el,type,fn)=>el.addEventListener(type,fn,{signal:events.signal});
    const hide=()=>{dropdown.style.display='none';input.setAttribute('aria-expanded','false');};
    const show=()=>{dropdown.style.display='block';input.setAttribute('aria-expanded','true');};
    const wrap=input.closest('.nav-search-wrap');if(wrap)wrap.style.position='relative';
    input.setAttribute('aria-controls','nav-search-dropdown');input.setAttribute('aria-expanded','false');
    on(input,'input',()=>{
        clearTimeout(timer);request?.abort();const run=++version,q=input.value.trim();hide();items=[];
        if(!q)return;
        timer=setTimeout(async()=>{
            request=new AbortController();
            try{
                const response=await fetch('/api/search?q='+encodeURIComponent(q),{credentials:'include',signal:request.signal});
                const data=await response.json();if(run!==version)return;if(!response.ok||data.status!=='success')throw new Error('搜索暂时不可用，请重试');
                dropdown.innerHTML=[['formulas','我的算式与题解'],['course_packs','我的课包'],['wrongbook','错题本'],['scripts','动画脚本'],['examples','教学案例']].map(([key,title])=>{
                    const rows=data[key]||[];if(!rows.length)return '';
                    return '<div class="nav-search-group"><span class="nav-search-group-title">'+title+'</span>'+rows.slice(0,5).map(row=>{const i=items.push({key,row})-1;return `<button type="button" class="nav-search-item" data-search-result="${i}">${esc((row.name||row.title||row.note||row.latex||'动画脚本').slice(0,80))}</button>`;}).join('')+'</div>';
                }).join('')||'<div class="nav-search-empty">未找到相关结果</div>';show();
            }catch(error){if(error.name!=='AbortError'&&run===version){dropdown.textContent=error.message;show();}}
        },280);
    });
    on(dropdown,'click',async event=>{
        const b=event.target.closest('[data-search-result]');if(!b)return;
        const item=items[Number(b.dataset.searchResult)];if(!item)return;hide();
        try{await openResult(item);input.value='';}catch(error){window.showToast?.(error.message,'error');}
    });
    on(input,'keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();dropdown.querySelector('button')?.focus();}if(e.key==='Escape')hide();});
    on(dropdown,'keydown',e=>{const buttons=[...dropdown.querySelectorAll('button')],i=buttons.indexOf(document.activeElement);if(e.key==='Escape'){hide();input.focus();}if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();buttons[(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}});
    on(document,'click',e=>{if(!dropdown.contains(e.target)&&e.target!==input)hide();});
    on(window,'auth-state-change',()=>{version++;request?.abort();clearTimeout(timer);items=[];dropdown.replaceChildren();hide();});
    return ()=>{clearTimeout(timer);request?.abort();events.abort();};
}
async function openResult({key,row}){
    if(key==='course_packs'){const C=await import('./course-packs.js');return C.openCoursePack(row.id);}
    if(key==='wrongbook'){const W=await import('./wrongbook.js');return W.openWrongbookEntry(row.id);}
    if(key==='formulas'){
        if(row.is_solution){const S=await import('./solution-library.js');return S.openSavedSolution(row.id);}
        if(!window.StepTutor)await(window.loadStepTutor?window.loadStepTutor():import('./step-tutor.js'));
        const st=window.StepTutor.getState();if(st.busy||st.rendering||st.saving)throw new Error('请先完成或停止当前解题任务');
        window.StepTutor.prefill(row.latex);window.showSection?.('calculate');return;
    }
    if(key==='scripts'){
        const me=await (await fetch('/api/user/me',{credentials:'include'})).json();
        if(!me.username)throw new Error('请先登录后阅读脚本');
        const response=await fetch('/api/animation_scripts/get?id='+row.id+'&username='+encodeURIComponent(me.username),{credentials:'include'}),result=await response.json();
        if(!response.ok||result.status!=='success')throw new Error(result.detail||result.message||'脚本读取失败');
        window.showSection?.('devtools');
        for(let i=0;i<100;i++){
            if(document.getElementById('devtools')?.dataset.devInitialized&&window.DevTools){window.DevTools.switchDevTool('manim');await window.DevTools.openManimWorkbenchWithCode(result.data.code,{scriptId:row.id,note:result.data.note});return;}
            await new Promise(resolve=>setTimeout(resolve,100));
        }
        throw new Error('开发者工具仍在加载，请稍后重试');
    }
    window.showSection?.('examples');
    for(let i=0;i<80;i++){if(window.Examples&&document.querySelector('#examples-filter')){window.Examples.playExampleByVideoId(row.video_id);return;}await new Promise(resolve=>setTimeout(resolve,100));}
    throw new Error('案例页面仍在加载，请稍后重试');
}
