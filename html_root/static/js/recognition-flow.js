import { normalizeLatex } from './math-text.js';

export const singleProblemMessage='每次请只提交一道完整题目，保留题干、图形和该题的小问。';
export function multipleProblems(text){
    return (String(text).match(/第[一二三四五六七八九十\d]+题/g)||[]).length>=2 ||
        (String(text).match(/^\s*\d{1,3}[.．、]\s*(?=[^\d\s])/gm)||[]).length>=2;
}
function clearStored(){
    try{['last_detect_latex','last_detect_problem','last_detect_vision_prompt'].forEach(k=>sessionStorage.removeItem(k));}catch{}
}

export function createRecognitionFlow(onChange){
    const state={latex:'',problem:'',context:'',busy:false,message:singleProblemMessage,error:'',needsReview:false,confirmed:false};
    let controller=null,revision=0;
    const publish=()=>onChange(state);
    const canContinue=()=>!!(state.problem.trim()||state.latex.trim()) && !state.busy && !state.error &&
        (!state.needsReview||state.confirmed) && !multipleProblems(state.problem) && !state.latex.includes('?');
    function cancel(){revision++;controller?.abort();controller=null;state.busy=false;state.message='识别已停止，图片保留，可以裁剪或手动输入题面。';publish();}
    function reset(){cancel();Object.assign(state,{latex:'',problem:'',context:'',error:'',needsReview:false,confirmed:false,message:singleProblemMessage});clearStored();publish();}
    function accept(data,external=true){
        if(external&&state.busy)cancel();
        const latex=normalizeLatex(data.latex||'');
        Object.assign(state,{latex,problem:String(data.problem_text||latex),context:String(data.vision_prompt||''),
            needsReview:!!data.needs_review,confirmed:false,error:'',message:String(data.message||'请核对完整题面后送入计算。')});
        if(data.uncertainties?.length)state.message+=' '+data.uncertainties.map(x=>String(x).slice(0,240)).join('；');
        clearStored();publish();
    }
    function editLatex(value){
        if(state.busy)cancel();
        value=String(value);const previous=state.latex;
        if(!state.problem||state.problem===previous)state.problem=value;
        else if(previous&&state.problem.includes(previous))state.problem=state.problem.replace(previous,value);
        else {state.needsReview=true;state.message='公式已修改，请在下方同步核对完整题面，以完整题面送入计算。';}
        state.latex=value;state.confirmed=false;state.error='';clearStored();publish();
    }
    function editProblem(value){if(state.busy)cancel();state.problem=String(value);state.confirmed=false;state.error='';clearStored();publish();}
    function confirm(value){state.confirmed=!!value;publish();}
    async function run(getBlob){
        if(state.busy)return;
        const run=++revision;controller=new AbortController();const aborter=controller;
        Object.assign(state,{busy:true,error:'',confirmed:false,message:'正在准备图片…'});clearStored();publish();
        let timeout,notice;
        try{
            const blob=await getBlob();if(run!==revision)return;
            if(!blob)throw new Error('请先书写或上传一道题，也可以直接在下方输入完整题面。');
            if(blob.size>5000000)throw new Error('图片请控制在 5 MB 以内，先裁剪到一道题再识别。');
            state.message='正在识别题面与公式…';publish();
            timeout=setTimeout(()=>aborter.abort(),100000);
            notice=setTimeout(()=>{if(run===revision){state.message='仍在识别，请稍候。也可以取消后调整图片。';publish();}},18000);
            const form=new FormData();form.append('file',blob,'question.png');
            const response=await fetch('/api/detect',{method:'POST',body:form,signal:aborter.signal});
            const data=await response.json().catch(()=>({}));if(run!==revision)return;
            if(!response.ok||data.status!=='success')throw new Error(data.message||'识别暂未完成，请稍后再试或手动输入题面。');
            if(!String(data.problem_text||data.latex||'').trim())throw new Error('没有读到题目，请裁剪或手动补充题面。');
            accept(data,false);
        }catch(error){
            if(run!==revision)return;
            state.error=error.name==='AbortError'?'识别等待超时，图片已保留。请裁剪到一道题后重试，或手动输入题面。':error.message;
            state.message=state.error;state.needsReview=true;publish();
        }finally{
            clearTimeout(timeout);clearTimeout(notice);
            if(run===revision){state.busy=false;controller=null;publish();}
        }
    }
    function payload(){
        if(!canContinue())throw new Error(multipleProblems(state.problem)?singleProblemMessage:'请先核对并补全题面与公式，再确认送入计算。');
        return {problem:state.problem.trim()||state.latex.trim(),context:state.context};
    }
    return {state,run,cancel,reset,accept,editLatex,editProblem,confirm,canContinue,payload};
}
