// static/js/detect.js
import { getCanvasBlob } from './canvas.js';
import { showSection } from './ui.js';

export function initDetectListeners() {
    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    if (mathField && codeArea) {
        // 双向绑定：MathLive -> Textarea
        mathField.addEventListener('input', (e) => {
            codeArea.value = e.target.value;
        });

        // 双向绑定：Textarea -> MathLive
        codeArea.addEventListener('input', (e) => {
            mathField.setValue(e.target.value);
        });
    }
}

export async function processRecognition() {
    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    // UI 反馈
    mathField.setValue(String.raw`\text{正在识别...}`);

    let blob;
    const canvasEl = document.getElementById('drawing-board');
    // 判断当前是否在画板模式（检查可见性）
    if (canvasEl && canvasEl.offsetParent !== null) {
        blob = await getCanvasBlob();
    } else {
        const fileInput = document.getElementById('image-upload');
        if (fileInput.files.length > 0) blob = fileInput.files[0];
    }

    if (!blob) {
        alert("请先绘制或上传图片");
        mathField.setValue(String.raw`\text{等待输入...}`);
        return;
    }

    const formData = new FormData();
    formData.append('file', blob);

    try {
        const response = await fetch('/api/detect', { method: 'POST', body: formData });
        const data = await response.json();

        if (data.status === 'success') {
            mathField.setValue(data.latex);
            codeArea.value = data.latex; // 同步到底层代码框

            // 成功提示效果
            const container = document.querySelector('.result-panel');
            if(container) {
                container.style.boxShadow = "0 0 0 2px var(--primary-color)";
                setTimeout(() => container.style.boxShadow = "", 1000);
            }
        } else {
            mathField.setValue(String.raw`\text{Error: }` + data.message);
        }
    } catch (e) {
        console.error(e);
        mathField.setValue(String.raw`\text{网络错误}`);
    }
}

export function copyToCalc() {
    const mathField = document.getElementById('latex-output');
    // 获取当前公式
    const detected = mathField ? mathField.getValue() : "";

    if(detected && !detected.includes("等待") && !detected.includes("Error")) {
        const target = document.getElementById('latex-code-a');
        if(target) target.value = detected;
        showSection('calculate');
    } else {
        alert("请先进行识别或输入有效公式");
    }
}