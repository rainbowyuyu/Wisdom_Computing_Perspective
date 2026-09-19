export function mountCodeAssistant(panel, getEditor, run, ensureEditor) {
    if (!panel) return;
    if (panel.codeAssistant && panel.querySelector('.code-assistant-form')) return;
    panel.codeAssistant?.dispose();
    delete panel.dataset.assistantMounted;
    panel.innerHTML=`<header class="code-assistant-header"><div><span class="assistant-eyebrow">创作助手</span><h3>把想法写成动画</h3></div><button type="button" data-code="close" aria-label="关闭代码助手">×</button></header>
      <p class="code-assistant-intro">结合当前脚本与运行日志，生成可检查、可撤销的代码建议。</p>
      <div class="code-assistant-shortcuts"><button data-prompt="请根据最近的运行日志修复代码，保留动画意图。">修复报错</button><button data-prompt="让当前动画使用连续变换，改善节奏并保留数学含义。">优化动画</button><button data-prompt="从零创建一段正方形平滑变成圆的动画。">从零创作</button></div>
      <form class="code-assistant-form"><textarea id="manim-ai-edit-input" maxlength="3000" rows="3" placeholder="描述想添加或修改的内容…" aria-label="代码修改需求"></textarea><div><span>Ctrl / ⌘ + Enter 发送</span><button type="button" data-code="stop" hidden>停止</button><button id="manim-ai-edit-btn" type="submit">生成建议 ↗</button></div></form>
      <p class="code-assistant-status" role="status" aria-live="polite">准备就绪，应用前可以查看完整代码差异。</p>
      <div class="code-assistant-proposal" hidden><p class="code-assistant-summary"></p><div class="code-assistant-diff"></div><details class="code-assistant-source"><summary>查看完整建议代码</summary><pre></pre></details><div class="code-assistant-preview" hidden><img alt="建议代码的实际渲染预览"></div><div class="code-assistant-actions"><button data-code="preview">预览效果</button><button data-code="apply">应用修改</button><button data-code="apply-run">应用并运行</button><button data-code="discard">放弃</button></div></div><button class="code-assistant-undo" data-code="undo" hidden>撤销上次应用</button>`;
    const $=selector=>panel.querySelector(selector), input=$('textarea'), status=$('[role=status]');
    let controller=null, version=0, proposal=null, diff=null, undo=null;
    function disposeDiff(){if(diff){const model=diff.getModel();diff.dispose();model?.original.dispose();model?.modified.dispose();diff=null;}}
    function busy(value){const submit=$('button[type=submit]'),stop=$('[data-code=stop]');if(submit)submit.disabled=value;if(stop)stop.hidden=!value;$('.code-assistant-actions')?.querySelectorAll('button').forEach(b=>b.disabled=value);panel.setAttribute('aria-busy',String(value));}
    function reset(){disposeDiff();proposal=null;$('.code-assistant-proposal').hidden=true;$('.code-assistant-preview').hidden=true;$('.code-assistant-preview img').removeAttribute('src');}
    async function request(path,body,signal){const response=await fetch('/api/devtools/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});const data=await response.json();if(!response.ok||data.status!=='success')throw new Error(data.message||'请求未完成，请重试。');return data;}
    async function generate(){
        if(controller)return;
        const instruction=input.value.trim();
        if(!instruction){input.focus();return;}
        const aborter=new AbortController(), id=++version;controller=aborter;busy(true);reset();
        status.textContent='正在准备代码编辑器…';
        try{
            const editor=getEditor()||await ensureEditor?.();
            if(id!==version)return;
            if(!editor)throw new Error('请打开动画工作台后重试。');
            const base=editor.getValue();
            status.textContent='正在读取当前脚本并生成代码建议…';
            const data=await request('edit_code',{code:base,instruction,render_log:(document.getElementById('dev-manim-log')?.textContent||'').slice(-12000)},aborter.signal);
            if(id!==version)return;
            proposal={base,code:data.code,applied:false};
            $('.code-assistant-summary').textContent=data.summary||'已生成代码建议';$('.code-assistant-source pre').textContent=data.code;
            $('.code-assistant-proposal').hidden=false;
            if(window.monaco){diff=window.monaco.editor.createDiffEditor($('.code-assistant-diff'),{automaticLayout:true,readOnly:true,renderSideBySide:false,minimap:{enabled:false},fontSize:12,theme:document.documentElement.dataset.theme==='dark'?'vs-dark':'vs'});diff.setModel({original:window.monaco.editor.createModel(base,'python'),modified:window.monaco.editor.createModel(data.code,'python')});}
            else $('.code-assistant-source').open=true;
            status.textContent=data.code===base?'未发现需要修改的代码，可补充具体要求。':'语法检查通过。可预览实际效果，再应用修改。';
        }catch(error){if(id===version)status.textContent=error.name==='AbortError'?'已停止生成。':error.message;}
        finally{if(id===version){controller=null;busy(false);}}
    }
    async function preview(){
        if(!proposal||controller)return;const aborter=new AbortController(),id=++version;controller=aborter;busy(true);status.textContent='正在实际渲染建议代码的最终画面…';
        try{const result=await request('render_keyframe',{code:proposal.code},aborter.signal);if(id!==version)return;
            if(!/^\/videos\/[a-f0-9-]+_preview\.png$/.test(result.preview_url))throw new Error('预览地址无效');
            if(result.repaired&&result.code){proposal.code=result.code;$('.code-assistant-source pre').textContent=result.code;diff?.getModel()?.modified.setValue(result.code);$('.code-assistant-summary').textContent='预览错误已自动修复，应用时将使用修复后的脚本。';}
            $('.code-assistant-preview img').src=result.preview_url;$('.code-assistant-preview').hidden=false;status.textContent='预览渲染成功。代码尚未应用，可检查效果。';
        }catch(error){if(id===version){status.textContent=error.name==='AbortError'?'已停止等待预览。':'预览失败：'+error.message+'。可补充修复要求重新生成。';
            if(error.name!=='AbortError'){const log=document.getElementById('dev-manim-log');if(log)log.textContent=('建议代码预览失败：\n'+error.message).slice(-12000);}}}
        finally{if(id===version){controller=null;busy(false);}}
    }
    function apply(){const editor=getEditor();if(!proposal||!editor)return false;if(editor.getValue()!==proposal.base){status.textContent='当前脚本已发生变化。请重新生成建议，避免覆盖你的编辑。';return false;}
        undo={before:proposal.base,after:proposal.code};editor.pushUndoStop();editor.executeEdits('code-assistant',[{range:editor.getModel().getFullModelRange(),text:proposal.code}]);editor.pushUndoStop();
        reset();$('[data-code=undo]').hidden=false;status.textContent='修改已应用到工作台，可继续编辑或运行。';return true;
    }
    function stop(){version++;controller?.abort();controller=null;busy(false);status.textContent='已停止，当前工作台代码保留。';}
    $('form').addEventListener('submit',event=>{event.preventDefault();generate();});
    input.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();generate();}});
    const events=new AbortController();
    panel.addEventListener('click',async event=>{const button=event.target.closest('button');if(!button)return;
        if(button.dataset.prompt){input.value=button.dataset.prompt;input.focus();return;}
        const action=button.dataset.code;
        if(action==='close')panel.style.display='none';if(action==='stop')stop();if(action==='preview')preview();
        if(action==='discard'){reset();status.textContent='已放弃建议，工作台代码保留。';}
        if(action==='apply')apply();if(action==='apply-run'&&apply()){
            const aborter=new AbortController(),id=++version;controller=aborter;busy(true);status.textContent='正在运行已应用的脚本…';
            try{const ok=await run({signal:aborter.signal});if(id===version)status.textContent=ok?'视频已生成，可在工作台播放。':'运行未完成，请查看日志并使用“修复报错”。';}
            catch(error){if(id===version)status.textContent=error.message;}
            finally{if(id===version){controller=null;busy(false);}}
        }
        if(action==='undo'&&undo){const editor=getEditor();if(editor?.getValue()!==undo.after){status.textContent='应用后又有新编辑，请使用编辑器撤销以保留编辑顺序。';return;}editor.trigger('code-assistant','undo');undo=null;button.hidden=true;status.textContent='已撤销助手的修改。';}
    },{signal:events.signal});
    panel.codeAssistant={generate,stop,prefill(text){input.value=text;input.focus();},dispose(){stop();disposeDiff();events.abort();delete panel.codeAssistant;delete panel.dataset.assistantMounted;}};
    panel.dataset.assistantMounted='true';
}
