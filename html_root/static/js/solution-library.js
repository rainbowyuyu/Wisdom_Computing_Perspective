import { textWithMath, normalizeMathText, renderFormula, normalizeSolution } from './math-text.js';
import { escapeText as esc, visualMarkup } from './solution-visual.js';

export function solutionMarkdown(record) {
    const {problem}=record;const solution=normalizeSolution(record.solution);
    return `# ${solution.title}\n\n题目：${normalizeMathText(problem)}\n\n${solution.steps.map((s,i)=>`## ${i+1}. ${s.title}\n\n${normalizeMathText(s.explanation)}\n\n${s.formula?`$$\n${s.formula}\n$$`:''}${s.hint?`\n\n提示：${normalizeMathText(s.hint)}`:''}`).join('\n\n')}\n\n${normalizeMathText(solution.summary)}\n\n${solution.verification}\n${record.video?`\n动画：${new URL(record.video.url,location.origin).href}\n`:''}`;
}

export function exportSolution(record) {
    const url=URL.createObjectURL(new Blob([solutionMarkdown(record)],{type:'text/markdown;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='分步解题笔记.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export async function libraryRequest(path,options={}) {
    const response=await fetch('/api/formulas/solutions'+path,{credentials:'include',...options});
    const result=await response.json();
    if(!response.ok||result.status!=='success') {
        const error=new Error(typeof result.detail==='string'?result.detail:result.message||'暂时无法访问算式库，请稍后重试。');
        error.status=response.status;throw error;
    }
    if(result.data?.solution)result.data.solution=normalizeSolution(result.data.solution);
    return result;
}

export async function openSavedSolution(id) {
    let record;
    try {record=(await libraryRequest('/'+Number(id))).data;}
    catch(error){window.showToast?.(error.message,'error');throw error;}
    return openSolutionRecord(record);
}

export function openSolutionRecord(record) {
    record={...record,solution:normalizeSolution(record.solution)};
    document.querySelector('.solution-reader:not(.auth-account-dialog)')?.close();
    const dialog=document.createElement('dialog');dialog.className='solution-reader';
    dialog.setAttribute('aria-label','阅读已保存题解');
    dialog.innerHTML=`<header class="reader-header"><div><span class="reader-kicker">我的算式 · 分步题解</span><h3>${esc(record.solution.title)}</h3></div><button type="button" data-reader="close" aria-label="关闭题解"><i class="fa-solid fa-xmark"></i></button></header>
      <div class="reader-body"><p class="reader-problem">${esc(record.problem)}</p><nav class="reader-steps" aria-label="选择步骤">${record.solution.steps.map((s,i)=>`<button type="button" data-reader-step="${i}">${i+1}. ${esc(s.title)}</button>`).join('')}</nav><article class="reader-step"></article>
      <div class="reader-conclusion"><span>结论</span><p></p><small>${esc(record.solution.verification)}</small></div>
      ${record.video?'<video class="reader-video" controls playsinline preload="metadata"></video>':''}</div>
      <footer class="reader-footer"><p role="status">${record.id?'已保存至账户，可随时回来阅读':'课包中收录的题解快照'}</p><div><button type="button" data-reader="copy">复制解答</button><button type="button" data-reader="wrongbook">加入错题本</button><button type="button" data-reader="pack">加入课包</button><button type="button" data-reader="export">导出笔记</button><button type="button" class="reader-primary" data-reader="open">继续探索 <i class="fa-solid fa-arrow-up-right-from-square"></i></button></div></footer>`;
    let current=0;
    function select(index,seek=true) {
        current=index;const step=record.solution.steps[index];
        const article=dialog.querySelector('.reader-step');
        article.innerHTML=`<span class="reader-kicker">步骤 ${index+1} / ${record.solution.steps.length}</span><h4>${esc(step.title)}</h4><p>${esc(step.explanation)}</p><div class="tutor-formula"></div><div class="tutor-visual">${visualMarkup(step.visual)}</div><p class="tutor-caption">${esc(step.visual?.caption||'')}</p>${step.hint?`<details><summary>查看提示</summary><p>${esc(step.hint)}</p></details>`:''}`;
        article.querySelectorAll('h4,p').forEach(el=>textWithMath(el,el.textContent));
        renderFormula(article.querySelector('.tutor-formula'),step.formula);
        dialog.querySelectorAll('[data-reader-step]').forEach(b=>{b.classList.toggle('active',Number(b.dataset.readerStep)===index);b.setAttribute('aria-current',Number(b.dataset.readerStep)===index?'step':'false');});
        if(seek&&record.video)dialog.querySelector('video').currentTime=record.video.chapters[index].start;
    }
    textWithMath(dialog.querySelector('.reader-header h3'),record.solution.title);
    textWithMath(dialog.querySelector('.reader-conclusion p'),record.solution.summary);
    textWithMath(dialog.querySelector('.reader-conclusion small'),record.solution.verification);
    textWithMath(dialog.querySelector('.reader-problem'),record.problem);
    dialog.querySelectorAll('[data-reader-step]').forEach((el,i)=>textWithMath(el,`${i+1}. ${record.solution.steps[i].title}`));
    const video=dialog.querySelector('video');
    if(video){video.src=record.video.url;video.addEventListener('timeupdate',()=>{const index=record.video.chapters.findIndex(c=>video.currentTime>=c.start&&video.currentTime<c.end);if(index>=0&&index!==current)select(index,false);});}
    const previousFocus=document.activeElement;
    dialog.addEventListener('close',()=>{video?.pause();dialog.remove();previousFocus?.focus();},{once:true});
    dialog.addEventListener('click',async event=>{
        const button=event.target.closest('button');if(!button)return;
        if(button.dataset.readerStep!=null){select(Number(button.dataset.readerStep));return;}
        const action=button.dataset.reader;
        if(action==='close')dialog.close();
        if(action==='pack'){dialog.close();const C=await import('./course-packs.js');C.chooseCourseMaterial({kind:'solution',source_id:record.id||null,snapshot:{title:record.solution.title,problem:record.problem,answer:record.solution.summary,solution:record}});}
        if(action==='export')exportSolution(record);
        if(action==='wrongbook'){dialog.close();const W=await import('./wrongbook.js');W.editWrongbook({source_type:'solution',formula_id:record.id,snapshot:record,problem:record.problem,title:record.solution.title,answer:record.solution.summary});}
        if(action==='copy'){try{await navigator.clipboard.writeText(solutionMarkdown(record));dialog.querySelector('[role=status]').textContent='解答已复制';}catch{dialog.querySelector('[role=status]').textContent='无法访问剪贴板，可导出笔记。';}}
        if(action==='open'){
            // Vue's dynamic imports may use an ?import URL. Reuse its loader so
            // restoring a record and mounting the page share one tutor instance.
            if(!window.StepTutor)await (window.loadStepTutor?window.loadStepTutor():import('./step-tutor.js'));
            if(window.StepTutor.restore(record)){dialog.close();window.showSection?.('calculate');}
            else dialog.querySelector('[role=status]').textContent='当前有任务正在运行，请先完成或停止任务。';
        }
    });
    document.body.append(dialog);select(0,false);dialog.showModal();
}

window.openSavedSolution=id=>openSavedSolution(id).catch(()=>{});
