import { createRecognitionFlow } from './recognition-flow.js';
// static/js/detect.js
import { getCanvasBlob } from './canvas.js';
import { showSection } from './ui.js';
import * as DevTools from '/static/js/devtools.js?v=20260917-creator-2';

let flow;
function getFlow(){
    if(flow)return flow;
    flow=createRecognitionFlow(state=>{
        const math=document.getElementById('latex-output'),code=document.getElementById('latex-code-detect');
        if(math && math.value!==state.latex){if(math.setValue)math.setValue(state.latex);else math.value=state.latex;}
        if(code && code.value!==state.latex)code.value=state.latex;
        const problem=document.getElementById('detect-problem');
        if(problem&&problem.value!==state.problem)problem.value=state.problem;
        const status=document.getElementById('detect-feedback');
        if(status){status.textContent=state.message;status.dataset.error=String(!!state.error);}
        document.getElementById('detect-loading')?.toggleAttribute('hidden',!state.busy);
        document.getElementById('detect-cancel')?.toggleAttribute('hidden',!state.busy);
        const review=document.getElementById('detect-review');
        if(review)review.hidden=!state.needsReview;
        const check=document.getElementById('detect-confirm');if(check)check.checked=state.confirmed;
        document.querySelectorAll('[onclick="processRecognition()"]').forEach(b=>b.disabled=state.busy);
        if(flow)setButtonsState(flow.canContinue());
    });
    return flow;
}

// 辅助：设置按钮可用状态
function setButtonsState(enabled) {
    const btnSave = document.getElementById('btn-save-check');
    const btnCalc = document.getElementById('btn-copy-calc');
    const btnLatex = document.getElementById('btn-edit-in-latex');

    // 当 enabled 为 true 时，disabled 属性应为 false
    const hasFormula = !!flow?.state.latex.trim();
    if (btnSave) btnSave.disabled = !enabled || !hasFormula;
    if (btnCalc) btnCalc.disabled = !enabled;
    if (btnLatex) btnLatex.disabled = !enabled || !hasFormula;
}

// 辅助：检查内容是否为有效公式
function checkContent(text) {
    if (!text) return false;
    const t = text.trim();
    // 排除空值和系统提示文案
    return t.length > 0 &&
           !t.includes("等待识别") &&
           !t.includes("正在识别") &&
           !t.includes("等待输入") &&
           !t.startsWith("\\text{Error");
}

export function initDetectListeners() {
    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');
    if (mathField?.dataset.recognitionBound) return;
    if(mathField)mathField.dataset.recognitionBound='true';
    getFlow();
    document.getElementById('detect-problem')?.addEventListener('input', e=>flow.editProblem(e.target.value));
    document.getElementById('detect-confirm')?.addEventListener('change', e=>flow.confirm(e.target.checked));
    document.getElementById('detect-cancel')?.addEventListener('click', ()=>flow.cancel());
    window.addEventListener('recognition-source-change',()=>flow.reset());
    window.addEventListener('recognition-result',e=>flow.accept(e.detail));
    document.getElementById('image-upload')?.addEventListener('change',()=>flow.reset());
    document.getElementById('drawing-board')?.addEventListener('pointerdown',()=>flow.reset());

    if (mathField && codeArea) {
        // 双向绑定：MathLive -> Textarea
        mathField.addEventListener('input', (e) => {
            const val = e.target.value;
            codeArea.value = val;
            getFlow().editLatex(val);
        });

        // 双向绑定：Textarea -> MathLive
        codeArea.addEventListener('input', (e) => {
            const val = e.target.value;
            mathField.setValue(val);
            getFlow().editLatex(val);
        });
        
        // 调整"查看源码"弹层位置，确保不超出视口
        const details = codeArea.closest('details');
        if (details) {
            const popup = details.querySelector('.code-detail-popup');
            if (popup) {
                const adjustPopupPosition = () => {
                    if (!details.open) return;
                    const detailsRect = details.getBoundingClientRect();
                    const popupRect = popup.getBoundingClientRect();
                    const viewportHeight = window.innerHeight;
                    
                    // 如果弹层会超出视口顶部，则显示在下方
                    if (detailsRect.top - popupRect.height < 0) {
                        popup.style.bottom = 'auto';
                        popup.style.top = 'calc(100% + 0.5rem)';
                    } else {
                        popup.style.bottom = 'calc(100% + 0.5rem)';
                        popup.style.top = 'auto';
                    }
                    
                    // 确保不超出视口右侧
                    if (popupRect.right > window.innerWidth) {
                        popup.style.right = '0';
                        popup.style.left = 'auto';
                    }
                };
                
                details.addEventListener('toggle', adjustPopupPosition);
                window.addEventListener('resize', adjustPopupPosition);
                window.addEventListener('scroll', adjustPopupPosition, true);
            }
        }

        // 手机端：点击编辑公式时，将结果面板固定在视口上方，避免键盘弹出后整页跳到最底部
        const runScrollToPanelTop = () => {
            const panel = document.querySelector('.result-panel');
            if (!panel) return;
            const rect = panel.getBoundingClientRect();
            const scrollTop = window.scrollY ?? document.documentElement.scrollTop;
            const targetY = scrollTop + rect.top - 12;
            window.scrollTo({ top: Math.max(0, targetY), behavior: 'smooth' });
        };
        mathField.addEventListener('focusin', () => {
            if (!window.matchMedia('(max-width: 900px)').matches) return;
            requestAnimationFrame(() => {
                runScrollToPanelTop();
                setTimeout(runScrollToPanelTop, 120);
                setTimeout(runScrollToPanelTop, 350);
            });
        });
        if (typeof window.visualViewport !== 'undefined') {
            window.visualViewport.addEventListener('resize', () => {
                if (!window.matchMedia('(max-width: 900px)').matches) return;
                if (document.activeElement && document.activeElement.closest('#latex-output')) {
                    setTimeout(runScrollToPanelTop, 50);
                }
            });
        }
    }
}

export async function processRecognition() {
    return getFlow().run(async()=>{
        const isDrawMode=document.querySelector('.tab-btn[onclick*="draw"]')?.classList.contains('active');
        return isDrawMode?await getCanvasBlob():document.getElementById('image-upload')?.files?.[0];
    });
}

export async function copyToCalc() {
    try{
        const {problem,context}=getFlow().payload();
        if(!window.StepTutor)await import('./step-tutor.js');
        (window.showSection || showSection)('calculate');
        window.StepTutor.prefill(problem,context);
    }catch(error){window.showAlert?.(error.message,'核对题目');}
}

// 从识别结果跳转到开发者工具中的 LaTeX 编辑器进行进一步编辑
export function editInDevtoolsFromDetect() {
    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    let latex = "";
    if (mathField && mathField.getValue) {
        latex = mathField.getValue();
    } else if (codeArea) {
        latex = codeArea.value;
    }
    if (!checkContent(latex)) {
        if (typeof showAlert === 'function') showAlert("请先识别出有效公式后再编辑", "提示");
        return;
    }

    // 先切到开发者工具，再切换到 LaTeX 标签并填入公式
    showSection('devtools');
    setTimeout(() => {
        if (typeof window.switchDevTool === 'function') window.switchDevTool('latex');
        if (DevTools && typeof DevTools.fillLatexInDevtools === 'function') {
            DevTools.fillLatexInDevtools(latex);
        }
    }, 200);
}
