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

    // 1. 检查当前处于哪个 Tab
    const drawTab = document.querySelector('.tab-btn[onclick*="draw"]');
    const isDrawMode = drawTab && drawTab.classList.contains('active');

    if (isDrawMode) {
        // 画板模式：获取 Canvas 数据
        blob = await getCanvasBlob();
    } else {
        // 上传模式：获取文件输入框的文件
        const fileInput = document.getElementById('image-upload');
        if (fileInput.files.length > 0) {
            blob = fileInput.files[0];
        }
    }

    if (!blob) {
        alert(isDrawMode ? "请先绘制内容" : "请先上传图片");
        mathField.setValue(String.raw`\text{等待输入...}`);
        return;
    }

    const formData = new FormData();
    formData.append('file', blob);

    try {
        const response = await fetch('/api/detect', { method: 'POST', body: formData });
        const data = await response.json();

        if (data.status === 'success') {
            // 双向更新
            if(mathField.setValue) mathField.setValue(data.latex);
            if(codeArea) codeArea.value = data.latex;

            // 成功提示效果
            const container = document.querySelector('.result-panel');
            if(container) {
                container.style.boxShadow = "0 0 0 2px var(--primary-color)";
                setTimeout(() => container.style.boxShadow = "", 1000);
            }
        } else {
            if(mathField.setValue) mathField.setValue(String.raw`\text{Error: }` + data.message);
        }
    } catch (e) {
        console.error(e);
        if(mathField.setValue) mathField.setValue(String.raw`\text{网络错误}`);
    }
}

// 导出到计算页面
export function copyToCalc() {
    // 从 MathLive 组件获取值
    const mathField = document.getElementById('latex-output');
    // 兼容普通 Textarea (如果降级)
    const codeArea = document.getElementById('latex-code-detect');

    let detected = "";
    if (mathField && mathField.getValue) {
        detected = mathField.getValue();
    } else if (codeArea) {
        detected = codeArea.value;
    }

    if(detected && !detected.includes("等待") && !detected.includes("Error")) {
        // 跳转到计算页面
        showSection('calculate');

        // 延时一点点以确保 DOM 可见，然后填充
        setTimeout(() => {
            // 填充到计算页面的矩阵 A (MathLive 组件)
            const targetField = document.getElementById('math-field-a');
            if (targetField && targetField.setValue) {
                targetField.setValue(detected);
            }

            // 同时更新隐藏的 textarea，保持数据同步
            const targetCode = document.getElementById('latex-code-a');
            if(targetCode) {
                targetCode.value = detected;
            }
        }, 100);

    } else {
        alert("请先进行识别或输入有效公式");
    }
}