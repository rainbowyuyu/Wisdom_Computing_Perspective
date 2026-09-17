import { normalizeLatex } from './math-text.js';
// static/js/detect.js
import { getCanvasBlob } from './canvas.js';
import { showSection } from './ui.js';
import * as DevTools from '/static/js/devtools.js?v=20260917-creator-2';

// 辅助：设置按钮可用状态
function setButtonsState(enabled) {
    const btnSave = document.getElementById('btn-save-check');
    const btnCalc = document.getElementById('btn-copy-calc');
    const btnLatex = document.getElementById('btn-edit-in-latex');

    // 当 enabled 为 true 时，disabled 属性应为 false
    if (btnSave) btnSave.disabled = !enabled;
    if (btnCalc) btnCalc.disabled = !enabled;
    if (btnLatex) btnLatex.disabled = !enabled;
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

    if (mathField && codeArea) {
        // 双向绑定：MathLive -> Textarea
        mathField.addEventListener('input', (e) => {
            const val = e.target.value;
            codeArea.value = val;
            setButtonsState(checkContent(val));
        });

        // 双向绑定：Textarea -> MathLive
        codeArea.addEventListener('input', (e) => {
            const val = e.target.value;
            mathField.setValue(val);
            setButtonsState(checkContent(val));
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
    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    // 1. 开始前：禁用按钮，显示 Loading
    setButtonsState(false);
    mathField.setValue(String.raw`\text{正在识别...}`);

    let blob;

    // 检查当前处于哪个 Tab
    const drawTab = document.querySelector('.tab-btn[onclick*="draw"]');
    const isDrawMode = drawTab && drawTab.classList.contains('active');

    if (isDrawMode) {
        blob = await getCanvasBlob();
    } else {
        const fileInput = document.getElementById('image-upload');
        if (fileInput.files.length > 0) {
            blob = fileInput.files[0];
        }
    }

    if (!blob) {
        if (typeof showAlert === 'function') await showAlert(isDrawMode ? "请先绘制内容" : "请先上传图片", "提示");
        mathField.setValue(String.raw`\text{等待输入...}`);
        setButtonsState(false); // 保持禁用
        return;
    }

    const formData = new FormData();
    formData.append('file', blob);

    try {
        const response = await fetch('/api/detect', { method: 'POST', body: formData });
        const data = await response.json();

        if (data.status === 'success') {
            // 2. 成功：填充内容并激活按钮
            data.latex=normalizeLatex(data.latex);
            if (mathField.setValue) mathField.setValue(data.latex);
            if (codeArea) codeArea.value = data.latex;
            try {
                sessionStorage.setItem('last_detect_latex', String(data.latex));
                sessionStorage.setItem('last_detect_problem', String(data.problem_text || data.latex));
            } catch {}

            setButtonsState(true); // <--- 关键：激活按钮

            // 将识别结果中由后端生成的「视觉描述 Prompt」暂存，供动态计算页复用
            // 这样从 detect → calculate 不仅传 LaTeX，还能携带对几何/结构关系的自然语言描述
            try {
                if (data.vision_prompt && typeof sessionStorage !== 'undefined') {
                    sessionStorage.setItem('last_detect_vision_prompt', String(data.vision_prompt));
                } else if (typeof sessionStorage !== 'undefined') {
                    sessionStorage.removeItem('last_detect_vision_prompt');
                }
            } catch (e) {
                console.warn('persist vision_prompt failed', e);
            }

            // 成功提示效果
            const container = document.querySelector('.result-panel');
            if (container) {
                container.style.boxShadow = "0 0 0 2px var(--primary-color)";
                setTimeout(() => container.style.boxShadow = "", 1000);
            }
        } else {
            // 3. 失败：显示错误信息，保持禁用
            if(mathField.setValue) mathField.setValue(String.raw`\text{Error: }` + data.message);
            setButtonsState(false);
        }
    } catch (e) {
        console.error(e);
        if(mathField.setValue) mathField.setValue(String.raw`\text{网络错误}`);
        setButtonsState(false);
    }
}

// 导出到计算页面
export async function copyToCalc() {
    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    let detected = "";
    if (mathField && mathField.getValue) {
        detected = mathField.getValue();
    } else if (codeArea) {
        detected = codeArea.value;
    }

    // 再次校验（虽然按钮禁用时点不了，但为了健壮性保留）
    if(checkContent(detected)) {
        // 跳转到计算页面
        (window.showSection || showSection)('calculate');
        let problem = detected, context = '';
        try {
            if (sessionStorage.getItem('last_detect_latex') === detected) {
                problem = sessionStorage.getItem('last_detect_problem') || detected;
                context = sessionStorage.getItem('last_detect_vision_prompt') || '';
            }
        } catch {}
        window.StepTutor?.prefill(problem, context);


    } else {
        if (typeof showAlert === 'function') await showAlert("请先进行识别或输入有效公式", "提示");
    }
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
