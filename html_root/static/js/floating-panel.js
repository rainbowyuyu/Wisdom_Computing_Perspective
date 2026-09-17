import { textWithMath } from './math-text.js';

/** Pointer capture, viewport constraints and task controls shared by both frontends. */
export function initFloatingPanel() {
    const panel=document.getElementById('knowledge-panel');
    if(!panel||panel.dataset.floatingReady)return;
    panel.dataset.floatingReady='true';
    const header=panel.querySelector('#knowledge-panel-header'),bubble=panel.querySelector('#knowledge-panel-bubble'),content=panel.querySelector('#knowledge-panel-content'),close=panel.querySelector('#knowledge-panel-close-btn');
    if(!header||!bubble||!content||!close)return;
    const key='wisdom.nebula.layout.v2';
    let drag=null,frame=0,moved=false,position=null,lastFocus=null;
    let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}');}catch{}
    panel.style.cursor='auto';panel.style.maxHeight='calc(100dvh - 32px)';
    panel.style.transition='box-shadow .2s ease, border-color .2s ease';
    bubble.setAttribute('role','button');bubble.tabIndex=0;bubble.setAttribute('aria-label','打开智算星云');bubble.setAttribute('aria-controls','knowledge-panel-content');
    header.tabIndex=0;header.setAttribute('aria-label','智算星云，可拖动标题移动窗口');
    close.setAttribute('aria-label','收起智算星云');
    function persist() {
        const r=panel.getBoundingClientRect();
        try{localStorage.setItem(key,JSON.stringify({collapsed:panel.classList.contains('collapsed'),left:r.left,top:r.top}));}catch{}
    }
    function clamp(left,top) {
        const r=panel.getBoundingClientRect();
        return {left:Math.max(12,Math.min(left,window.innerWidth-r.width-12)),top:Math.max(12,Math.min(top,window.innerHeight-r.height-12))};
    }
    function place(left,top) {
        const p=clamp(left,top);panel.style.left=p.left+'px';panel.style.top=p.top+'px';panel.style.right='auto';panel.style.bottom='auto';panel.style.transform='';position=p;
    }
    function setCollapsed(value,focus=true) {
        const r=panel.getBoundingClientRect();
        panel.classList.toggle('collapsed',value);panel.classList.add('has-bubble-pos');
        panel.style.width=value?'64px':'min(340px, calc(100vw - 32px))';panel.style.height=value?'64px':'';
        content.style.display=value?'none':'flex';bubble.style.display=value?'flex':'none';
        bubble.setAttribute('aria-expanded',String(!value));
        panel.title=value?'打开智算星云；拖动可移动位置':'';
        place(r.left,r.top);persist();
        if(focus){if(value){bubble.focus();}else{lastFocus=document.activeElement;close.focus();}}
    }
    function down(e) {
        if(e.button!==0||e.target.closest('button,a,input,select,textarea'))return;
        const handle=e.currentTarget;
        const r=panel.getBoundingClientRect();
        drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:r.left,top:r.top,handle};moved=false;
        handle.setPointerCapture(e.pointerId);panel.classList.add('is-dragging');
    }
    function move(e) {
        if(!drag||drag.id!==e.pointerId)return;
        const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
        if(dx*dx+dy*dy>36)moved=true;
        position=clamp(drag.left+dx,drag.top+dy);
        if(!frame)frame=requestAnimationFrame(()=>{frame=0;if(drag)panel.style.transform=`translate3d(${position.left-drag.left}px,${position.top-drag.top}px,0)`;});
    }
    function up(e) {
        if(!drag||drag.id!==e.pointerId)return;
        const current=drag;drag=null;cancelAnimationFrame(frame);frame=0;panel.classList.remove('is-dragging');
        if(current.handle.hasPointerCapture(e.pointerId))current.handle.releasePointerCapture(e.pointerId);
        panel.style.transform='';
        if(moved&&position){place(position.left,position.top);persist();}
        else if(e.type==='pointerup'&&current.handle===bubble)setCollapsed(false);
    }
    [bubble,header].forEach(el=>{el.style.touchAction='none';el.addEventListener('pointerdown',down);el.addEventListener('pointermove',move);el.addEventListener('pointerup',up);el.addEventListener('pointercancel',up);el.addEventListener('lostpointercapture',up);});
    bubble.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();setCollapsed(false);}});
    header.addEventListener('keydown',e=>{const delta={ArrowLeft:[-20,0],ArrowRight:[20,0],ArrowUp:[0,-20],ArrowDown:[0,20]}[e.key];if(delta){e.preventDefault();const r=panel.getBoundingClientRect();place(r.left+delta[0],r.top+delta[1]);persist();}});
    close.addEventListener('click',e=>{e.stopPropagation();setCollapsed(true);});
    panel.addEventListener('keydown',e=>{if(e.key==='Escape'&&!panel.classList.contains('collapsed')){e.stopPropagation();setCollapsed(true);if(lastFocus?.isConnected&&!panel.contains(lastFocus))lastFocus.focus();}});
    const fit=()=>{if(drag)return;const r=panel.getBoundingClientRect();place(r.left,r.top);};
    window.addEventListener('resize',fit,{passive:true});window.visualViewport?.addEventListener('resize',fit,{passive:true});
    new ResizeObserver(fit).observe(panel);
    setCollapsed(typeof saved.collapsed==='boolean'?saved.collapsed:true,false);
    if(Number.isFinite(saved.left)&&Number.isFinite(saved.top))place(saved.left,saved.top);
    const task=document.createElement('section');task.className='tutor-task-card';task.hidden=true;
    task.innerHTML='<strong style="font-size:.8rem">分步解题任务</strong><p class="tutor-task-problem"></p><p class="tutor-task-status" role="status" aria-live="polite"></p><button type="button" data-task="open">继续查看</button><button type="button" data-task="stop">停止</button><button type="button" data-task="render">生成动画</button>';
    header.after(task);
    const update=({detail})=>{
        task.hidden=!detail.problem;
        textWithMath(task.querySelector('.tutor-task-problem'),detail.problem||'');
        textWithMath(task.querySelector('.tutor-task-status'),detail.status||'');
        task.querySelector('[data-task=stop]').hidden=!detail.busy;
        task.querySelector('[data-task=render]').hidden=detail.busy||!window.StepTutor?.getState().solution;
        bubble.setAttribute('aria-label',detail.busy?'解题任务进行中，打开智算星云查看进度':'打开智算星云');
        panel.classList.toggle('has-tutor-task',detail.busy);
    };
    window.addEventListener('tutor-state',update);
    const tutor=window.StepTutor?.getState();if(tutor)update({detail:{...tutor,busy:tutor.busy||tutor.rendering}});
    task.addEventListener('click',e=>{const action=e.target.closest('button')?.dataset.task;if(action==='stop')window.StepTutor?.cancel();if(action==='render')window.StepTutor?.render();if(action==='open'){window.showSection?.('calculate');if(matchMedia('(max-width:768px)').matches)setCollapsed(true);}});
}
