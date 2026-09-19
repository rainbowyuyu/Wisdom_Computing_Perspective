import { escapeText as esc } from './solution-visual.js?v=20260918-adaptive-1';
import { textWithMath } from './math-text.js';

/** The catalog reuses the tutor and its existing storage/export/render actions. */
export function mountCurriculum(host, {prefill, read, busy}) {
    host.innerHTML=`<summary><span><i class="fa-solid fa-book-open"></i> 典型例题 <small>高中 · 大学</small></span><span>选一道，慢慢学 <i class="fa-solid fa-chevron-down"></i></span></summary>
      <div class="curriculum-body"><p>本站整理的分步题解，可直接阅读、生成动画或存入学习库。改动题目后会重新计算。</p>
      <div class="curriculum-filters"><label>学段<select data-filter="level"><option value="">全部学段</option><option>高中</option><option>大学</option></select></label><label>题型<select data-filter="topic"><option value="">全部题型</option></select></label><label class="curriculum-search">查找<input type="search" placeholder="极限、概率、圆…" maxlength="100" aria-label="查找典型例题"></label></div>
      <p class="curriculum-status" role="status"></p><div class="curriculum-grid"></div><button type="button" data-catalog-retry hidden>重新加载</button></div>`;
    const $ = s => host.querySelector(s);
    let items = [], loading = false, loaded = false, controller = null;
    const bindings = new AbortController();
    const on = (el, type, fn) => el.addEventListener(type, fn, {signal:bindings.signal});
    function draw() {
        const level=$('[data-filter=level]').value, topic=$('[data-filter=topic]').value;
        const query=$('input').value.trim().toLowerCase();
        const matches=items.filter(e=>(!level||e.level===level)&&(!topic||e.topic===topic)&&`${e.title} ${e.problem} ${e.method}`.toLowerCase().includes(query));
        $('.curriculum-status').textContent=matches.length?`共 ${matches.length} 道 · 阅读典型题解不调用 AI`:'没有找到匹配例题，可切换筛选或直接输入你的题目。';
        $('.curriculum-grid').innerHTML=matches.map(e=>`<article class="curriculum-card"><small>${esc(e.level)} · ${esc(e.topic)}</small><h5>${esc(e.title)}</h5><p class="curriculum-problem"></p><p class="curriculum-method">${esc(e.method)}</p><div><button type="button" data-fill="${esc(e.id)}">填入题目</button><button type="button" data-read="${esc(e.id)}">阅读分步解答 <span aria-hidden="true">→</span></button></div></article>`).join('');
        host.querySelectorAll('.curriculum-problem').forEach((el,i)=>textWithMath(el,matches[i].problem));
    }
    async function load() {
        if (loading||loaded) return;
        loading=true;$('.curriculum-status').textContent='正在加载例题…';$('[data-catalog-retry]').hidden=true;
        controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),10000);
        try {
            const response=await fetch('/api/solve/examples',{signal:controller.signal});
            if(!response.ok)throw new Error('例题暂时无法加载，请稍后重试。');
            const result=await response.json();items=result.items;loaded=true;
            $('[data-filter=topic]').innerHTML='<option value="">全部题型</option>'+[...new Set(items.map(e=>e.topic))].map(t=>`<option>${esc(t)}</option>`).join('');
            draw();
        } catch(error) {
            if(!bindings.signal.aborted){$('.curriculum-status').textContent=error.name==='AbortError'?'加载超时，请重试。':error.message;$('[data-catalog-retry]').hidden=false;}
        } finally { clearTimeout(timeout); loading=false; }
    }
    on(host,'toggle',()=>{if(host.open)load();});
    if(host.open)load();
    on($('input'),'input',draw);
    host.querySelectorAll('select').forEach(el=>on(el,'change',draw));
    on(host,'click',async event=>{
        const button=event.target.closest('button');if(!button)return;
        if(button.hasAttribute('data-catalog-retry'))return load();
        const item=items.find(e=>e.id===(button.dataset.fill||button.dataset.read));if(!item)return;
        if(button.dataset.fill){
            if(busy()){$('.curriculum-status').textContent='请先完成或停止当前任务，再切换例题。';return;}
            button.disabled=true;
            try{await prefill(item.problem);}catch(error){if(!bindings.signal.aborted)$('.curriculum-status').textContent=error.message;}
            finally{button.disabled=false;}
            return;
        }
        button.disabled=true;$('.curriculum-status').textContent='正在打开分步解答…';
        const aborter=new AbortController();
        const abort=()=>aborter.abort();bindings.signal.addEventListener('abort',abort,{once:true});
        const timeout=setTimeout(abort,10000);
        try {
            const response=await fetch(`/api/solve/examples/${encodeURIComponent(item.id)}`,{signal:aborter.signal});
            if(!response.ok)throw new Error('题解暂时无法打开，请重试。');
            const record=await response.json();
            if(bindings.signal.aborted)return;
            await read(record);
            $('.curriculum-status').textContent='已打开典型题解；选择「继续探索」可进入数学运算生成动画或保存。';
        }catch(error){if(!bindings.signal.aborted)$('.curriculum-status').textContent=error.name==='AbortError'?'加载超时，请重试。':error.message;}
        finally{clearTimeout(timeout);bindings.signal.removeEventListener('abort',abort);button.disabled=false;}
    });
    return ()=>{bindings.abort();controller?.abort();};
}
