// static/js/detect.js
import { getCanvasBlob } from './canvas.js';
import { showSection } from './ui.js';

// 辅助：设置按钮可用状态
function setButtonsState(enabled) {
    const btnSave = document.getElementById('btn-save-check');
    const btnCalc = document.getElementById('btn-copy-calc');

    // 当 enabled 为 true 时，disabled 属性应为 false
    if (btnSave) btnSave.disabled = !enabled;
    if (btnCalc) btnCalc.disabled = !enabled;
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
            // 实时检查内容，决定是否激活按钮
            setButtonsState(checkContent(val));
        });

        // 双向绑定：Textarea -> MathLive
        codeArea.addEventListener('input', (e) => {
            const val = e.target.value;
            mathField.setValue(val);
            // 实时检查内容，决定是否激活按钮
            setButtonsState(checkContent(val));
        });
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
        alert(isDrawMode ? "请先绘制内容" : "请先上传图片");
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
            if(mathField.setValue) mathField.setValue(data.latex);
            if(codeArea) codeArea.value = data.latex;

            setButtonsState(true); // <--- 关键：激活按钮

            // 成功提示效果
            const container = document.querySelector('.result-panel');
            if(container) {
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
export function copyToCalc() {
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
        showSection('calculate');

        // 延时一点点以确保 DOM 可见，然后填充
        setTimeout(() => {
            // 填充到计算页面的矩阵(MathLive 组件)
            const targetField = document.getElementById('math-field-main');
            if (targetField && targetField.setValue) {
                targetField.setValue(detected);
            }

            // 同时更新隐藏的 textarea，保持数据同步
            const targetCode = document.getElementById('latex-code-main');
            if(targetCode) {
                targetCode.value = detected;
            }
        }, 100);

    } else {
        alert("请先进行识别或输入有效公式");
    }
}