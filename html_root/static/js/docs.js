import { toggleModal } from './ui.js';
import { sanitizeMarkdownHtml } from './sanitize.js';
import { renderMathIn } from './math-text.js';

let requestVersion=0,controller,disposeView=()=>{};
const behavior=()=>matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth';
function ensureModal(){
    let modal=document.getElementById('docs-modal');
    if(!modal){
        modal=document.createElement('div');modal.id='docs-modal';modal.className='modal';
        modal.innerHTML='<div class="modal-content glass-panel"><div class="docs-header"><h3 id="docs-title">文档</h3><button class="close-modal" type="button" aria-label="关闭文档" data-doc-close>×</button></div><div id="docs-content" class="markdown-body"></div><div class="docs-footer"><button class="action-btn" type="button" data-doc-close>关闭</button></div></div>';
        document.body.append(modal);
    }
    modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','docs-title');
    if(!modal.dataset.docsBound){
        modal.dataset.docsBound='true';
        modal.querySelectorAll('[data-doc-close],.close-modal,.docs-footer button').forEach(b=>{b.onclick=closeDocsModal;b.setAttribute('aria-label','关闭文档');});
        modal.addEventListener('click',e=>{if(e.target===modal)closeDocsModal();});
        modal.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();closeDocsModal();}});
    }
    return modal;
}
async function ensureMarked(){
    if(window.marked?.parse)return;
    let script=document.querySelector('script[src*="marked"]');
    if(!script){script=document.createElement('script');script.src='https://cdn.jsdelivr.net/npm/marked/marked.min.js';document.head.append(script);}
    for(let i=0;i<75;i++){if(window.marked?.parse)return;await new Promise(resolve=>setTimeout(resolve,80));}
    throw new Error('文档排版组件加载超时');
}
function highlight(el){
    el.classList.add('docs-highlight');clearTimeout(el.docsHighlightTimer);
    el.docsHighlightTimer=setTimeout(()=>el.classList.remove('docs-highlight'),2200);
}
function scrollWithin(container,target,animated=true){
    const offset=24;
    container.scrollTo({top:container.scrollTop+target.getBoundingClientRect().top-container.getBoundingClientRect().top-offset,behavior:animated?behavior():'instant'});
    highlight(target);
}
const targets={
    'section-formulas':{node:'my-formulas'},'section-my-formulas':{node:'my-formulas'},
    'section-calculate-input':{node:'calc-normal'},
    'section-examples-filter':{node:'examples-filter-all',selector:'#examples-filter'},
    'section-examples-courseware':{node:'examples-courseware',selector:'#examples-filter'},
    'section-examples-wrongbook':{node:'errorbook',selector:'.wrongbook-host'},
    'section-examples-review':{node:'wrongbook-review'},
    'section-examples-create-course':{node:'examples-create-course'},
    'section-devtools-assistant':{node:'devtools-ai-edit'},
    'section-devtools-rainbow':{node:'devtools-rainbow'},
    'section-devtools-manim':{node:'devtools-manim'},
    'section-devtools-latex':{node:'devtools-latex'},
    'section-home-roles':{node:'home',selector:'.role-graph-wrap'},
    'section-search':{node:'search',selector:'#nav-search-input'},
    'section-nebula':{nebula:true},
};
async function waitFor(find){
    for(let i=0;i<100;i++){const el=find();if(el?.checkVisibility())return el;await new Promise(resolve=>setTimeout(resolve,80));}
    throw new Error('目标区域仍在加载，请稍后重试');
}
export async function navigateDocLink(id){
    closeDocsModal();window.closeSettings?.();
    const target=targets[id]||{node:id.slice('section-'.length)};
    if(target.nebula){
        const panel=await waitFor(()=>document.getElementById('knowledge-panel'));
        if(panel.classList.contains('collapsed'))panel.querySelector('#knowledge-panel-bubble')?.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
        highlight(panel);return;
    }
    const G=await import('./site-graph.js?v=20260917-ecosystem-6');
    const node=G.getNodeById(target.node);
    if(!node)throw new Error('此历史入口已调整，请从导航栏进入相应功能');
    if(!await G.executeNodeAction(node))return;
    if(document.querySelector('dialog[open]'))return;
    if(target.node==='search'){
        const wrap=document.getElementById('nav-search-input')?.closest('.nav-search-wrap');
        if(wrap&&!wrap.checkVisibility()){
            const previous=wrap.getAttribute('style');
            wrap.style.setProperty('display','flex','important');Object.assign(wrap.style,{position:'fixed',top:((document.querySelector('.navbar')?.getBoundingClientRect().bottom||72)+8)+'px',left:'16px',right:'16px',width:'auto',zIndex:'2300',background:'var(--bg-surface)',padding:'10px',borderRadius:'12px'});
            const events=new AbortController();const dismiss=()=>{events.abort();if(previous===null)wrap.removeAttribute('style');else wrap.setAttribute('style',previous);};
            document.addEventListener('pointerdown',e=>{if(!wrap.contains(e.target))dismiss();},{signal:events.signal});
            wrap.addEventListener('click',e=>{if(e.target.closest('[data-search-result]'))dismiss();},{signal:events.signal});
            wrap.addEventListener('keydown',e=>{if(e.key==='Escape')dismiss();},{signal:events.signal});
        }
    }
    const el=target.selector?await waitFor(()=>document.querySelector(target.selector)):document.getElementById(node.section);
    if(el&&(target.selector||node.id===node.section)){
        el.style.scrollMarginTop=((document.querySelector('.navbar')?.getBoundingClientRect().height||80)+20)+'px';
        el.scrollIntoView({block:'start',behavior:behavior()});
        const focus=el.matches('input,button,textarea,select')?el:el.querySelector('input,textarea,button');focus?.focus({preventScroll:true});highlight(el);
    }
}
function buildChangelog(content,scrollToId){
    content.classList.add('docs-changelog');
    const headings=[...content.querySelectorAll('h2')];
    const sections=headings.map((h,index)=>{
        const version=h.textContent.match(/v\s*(\d+\.\d+\.\d+)/i)?.[1];
        h.id=version?'update-v-'+version:'update-initial-'+index;h.dataset.updateHeading='true';
        const card=document.createElement('article');card.className='docs-release';
        h.before(card);card.append(h);
        while(card.nextSibling&&!(card.nextSibling.nodeType===1&&card.nextSibling.tagName==='H2'))card.append(card.nextSibling);
        return {h,card,version};
    });
    const versions=sections.filter(x=>x.version),latest=versions.at(-1);
    latest?.card.classList.add('docs-release-latest');
    const bar=document.createElement('nav');bar.className='docs-update-jump';bar.setAttribute('aria-label','更新日志版本导航');
    const label=document.createElement('label');label.textContent='跳转到版本';label.htmlFor='docs-version-select';
    const select=document.createElement('select');select.id='docs-version-select';
    [...sections].reverse().forEach(({h,version})=>{const option=document.createElement('option');option.value=h.id;option.textContent=h.textContent+(version===latest?.version?' · 最新':'');select.append(option);});
    const newest=document.createElement('button');newest.type='button';newest.className='docs-update-jump-btn';newest.textContent='最新版本';
    bar.append(label,select,newest);content.before(bar);
    const find=id=>sections.find(x=>x.h.id===id)?.h;
    const jump=(h,animated=true)=>{if(!h?.isConnected)return;select.value=h.id;newest.classList.toggle('active',h===latest?.h);newest.setAttribute('aria-pressed',String(h===latest?.h));scrollWithin(content,h,animated);};
    select.onchange=()=>jump(find(select.value));newest.onclick=()=>jump(latest?.h);
    let frame=0;
    const onScroll=()=>{if(frame)return;frame=requestAnimationFrame(()=>{frame=0;const line=bar.getBoundingClientRect().bottom+35;let current=sections[0];for(const section of sections){if(section.h.getBoundingClientRect().top<=line)current=section;else break;}if(current){select.value=current.h.id;newest.classList.toggle('active',current===latest);newest.setAttribute('aria-pressed',String(current===latest));}});};
    content.addEventListener('scroll',onScroll,{passive:true});
    content.querySelectorAll('a[href^="#"]').forEach(link=>{
        link.classList.add('docs-internal-link');
        link.onclick=async e=>{e.preventDefault();const id=link.getAttribute('href').slice(1);try{if(id.startsWith('section-'))await navigateDocLink(id);else jump(find(id));}catch(error){window.showToast?.(error.message,'error');}};
    });
    requestAnimationFrame(()=>requestAnimationFrame(()=>{if(content.isConnected&&content.classList.contains('docs-changelog'))jump(find(scrollToId)||latest?.h,false);}));
    return ()=>{content.removeEventListener('scroll',onScroll);cancelAnimationFrame(frame);};
}
export async function openDoc(fileName,title,scrollToId){
    if(!/^[a-zA-Z0-9_-]+\.md$/.test(fileName))return;
    const modal=ensureModal(),content=document.getElementById('docs-content');
    const run=++requestVersion;controller?.abort();controller=new AbortController();disposeView();
    document.getElementById('docs-title').textContent=title;
    modal.querySelector('.docs-update-jump')?.remove();
    content.classList.remove('docs-changelog');content.style.whiteSpace='';content.scrollTop=0;
    content.innerHTML='<div class="docs-loading" role="status">正在加载文档…</div>';toggleModal('docs-modal',true);
    modal.querySelector('.close-modal')?.focus();
    const timer=setTimeout(()=>controller?.abort(),8000);
    try{
        const response=await fetch('/static/docs/'+fileName,{signal:controller.signal,cache:'no-cache'});
        if(!response.ok)throw new Error('文档读取失败，请稍后重试');
        const markdown=await response.text();clearTimeout(timer);
        try{await ensureMarked();}catch{if(run===requestVersion){content.style.whiteSpace='pre-wrap';content.textContent=markdown;}return;}
        if(run!==requestVersion)return;
        content.innerHTML=sanitizeMarkdownHtml(window.marked.parse(markdown,{gfm:true,breaks:true}));
        content.querySelectorAll('pre code').forEach(block=>window.hljs?.highlightElement(block));
        content.querySelectorAll('a:not([href^="#"])').forEach(a=>{a.target='_blank';a.rel='noopener noreferrer';});
        renderMathIn(content);
        if(fileName==='update.md')disposeView=buildChangelog(content,scrollToId);
    }catch(error){if(run!==requestVersion)return;content.replaceChildren();const p=document.createElement('p');p.className='docs-error';p.textContent=error.name==='AbortError'?'文档加载超时，请重新打开':error.message;content.append(p);}
    finally{clearTimeout(timer);}
}
export function closeDocsModal(){requestVersion++;controller?.abort();disposeView();toggleModal('docs-modal',false);}
window.openDoc=openDoc;window.closeDocsModal=closeDocsModal;
