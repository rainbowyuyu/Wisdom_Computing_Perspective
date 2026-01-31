import { toggleModal, showSection, toggleAuthModal } from './ui.js';
import { loadMyFormulas, normalizeLatex } from './formulas.js';

// 初始化计算页面的监听器
export function initCalculateListeners() {
    const field = document.getElementById('math-field-main');
    const code = document.getElementById('latex-code-main');

    if (field && code) {
        code.value = field.getValue();
        field.addEventListener('input', (e) => { code.value = e.target.value; });
        code.addEventListener('input', (e) => { field.setValue(e.target.value); });
    }
}

// 核心：开始生成动画 (SSE 流式 - 优化版：分离视频与代码)
export async function startAnimation() {
    // 获取 DOM 元素
    const videoWrapper = document.getElementById('calc-video-wrapper');
    const placeholder = document.getElementById('video-placeholder-content');
    const videoPlayer = document.getElementById('result-video-player');

    const logBox = document.getElementById('gen-log');
    const progBar = document.getElementById('gen-progress');
    const percentText = document.getElementById('gen-percent');

    const method = document.getElementById('calc-method').value;
    const formula = document.getElementById('math-field-main').getValue();

    // 1. 重置 UI 状态
    // 清空日志
    logBox.innerHTML = '';
    addLog("正在初始化生成任务...", "#94a3b8");

    // 重置进度条
    progBar.style.width = '0%';
    progBar.className = ''; // 移除可能的错误颜色类
    percentText.innerText = '0%';

    // 重置视频区域：显示占位符，隐藏播放器
    if(videoPlayer) {
        videoPlayer.pause();
        videoPlayer.style.display = 'none';
        videoPlayer.src = "";
    }
    if(placeholder) placeholder.style.display = 'block';

    // 辅助：添加日志
    function addLog(msg, color = "#cbd5e1") {
        const div = document.createElement('div');
        div.className = 'log-entry';
        div.style.color = color;
        div.style.marginBottom = '6px';
        div.style.lineHeight = '1.5';
        div.innerHTML = `<span style="opacity:0.6; margin-right:5px;">></span> ${msg}`;
        logBox.appendChild(div);
        logBox.scrollTop = logBox.scrollHeight;
    }

    // 辅助：流式打字机显示代码
    async function streamCodeBlock(fullCode) {
        // 创建代码块容器
        const pre = document.createElement('pre');
        pre.style.marginTop = "10px";
        pre.style.marginBottom = "10px";
        pre.style.background = "#00000033";
        pre.style.padding = "10px";
        pre.style.borderRadius = "4px";
        pre.style.border = "1px solid #334155";
        pre.style.overflowX = "auto";

        const codeEl = document.createElement('code');
        codeEl.className = "language-python hljs"; // 使用 highlight.js 类名
        codeEl.style.fontFamily = "'JetBrains Mono', monospace";
        codeEl.style.fontSize = "0.8rem";

        pre.appendChild(codeEl);
        logBox.appendChild(pre);

        const chars = fullCode.split('');
        let currentText = "";

        return new Promise((resolve) => {
            let i = 0;
            const speed = 5; // 打字速度

            function type() {
                if (i < chars.length) {
                    const chunk = chars.slice(i, i + speed).join('');
                    currentText += chunk;
                    codeEl.textContent = currentText;
                    logBox.scrollTop = logBox.scrollHeight;
                    i += speed;
                    requestAnimationFrame(type);
                } else {
                    // 打字完成，应用高亮
                    if (window.hljs) window.hljs.highlightElement(codeEl);
                    resolve();
                }
            }
            requestAnimationFrame(type);
        });
    }

    try {
        const response = await fetch('/api/animate/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                matrixA: formula,
                matrixB: "",
                operation: method
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.replace('data: ', '');
                    try {
                        const data = JSON.parse(jsonStr);

                        // 更新进度
                        if (data.progress) {
                            progBar.style.width = data.progress + '%';
                            percentText.innerText = data.progress + '%';

                            // 根据进度改变颜色
                            if(data.progress < 30) progBar.style.background = "#3b82f6"; // Blue
                            else if(data.progress < 90) progBar.style.background = "#8b5cf6"; // Purple
                            else progBar.style.background = "#10b981"; // Green
                        }

                        // 处理不同阶段
                        if (data.step === 'generating_code') {
                            addLog("正在构思数学可视化脚本...", "#fbbf24");
                        }
                        else if (data.step === 'code_generated') {
                            addLog("脚本生成完毕，代码预览：", "#34d399");
                            if (data.code) {
                                await streamCodeBlock(data.code);
                            }
                        }
                        else if (data.step === 'rendering') {
                            if (data.message && !data.message.includes("渲染帧")) {
                                addLog(data.message, "#e2e8f0");
                            }
                        }
                        else if (data.step === 'complete') {
                            addLog("✨ 渲染完成！视频加载中...", "#a78bfa");

                            // 切换视频显示
                            setTimeout(() => {
                                if (placeholder) placeholder.style.display = 'none';
                                if (videoPlayer) {
                                    // 加上时间戳防止缓存
                                    videoPlayer.src = `${data.video_url}?t=${new Date().getTime()}`;
                                    videoPlayer.style.display = 'block';
                                    videoPlayer.play();
                                }
                            }, 500);
                            return;
                        }
                        else if (data.step === 'error') {
                            addLog("❌ 错误: " + data.message, "#ef4444");
                            progBar.style.background = "#ef4444";
                            return;
                        }

                    } catch (e) {
                        console.warn("JSON Parse Warning", e);
                    }
                }
            }
        }

    } catch (e) {
        console.error(e);
        addLog("网络连接错误，请检查服务器状态。", "#ef4444");
    }
}


// --- 公式选择器逻辑 ---
let currentTargetField = null;

export function openFormulaSelector(target) {
    currentTargetField = target;
    toggleModal('select-formula-modal', true);
    loadFormulaSelectorList();
}

export function closeFormulaSelector() {
    toggleModal('select-formula-modal', false);
    currentTargetField = null;
}

// 加载用于选择的公式列表
async function loadFormulaSelectorList() {
    const container = document.getElementById('selector-list');
    const userSpan = document.getElementById('username-span');
    const userDisplay = document.getElementById('user-display');
    const user = (userDisplay && userDisplay.style.display !== 'none' && userSpan) ? userSpan.innerText : null;

    if (!user) {
        container.innerHTML = `
            <div style="text-align:center; padding: 2rem;">
                <p style="color:var(--text-secondary); margin-bottom: 1rem;">请先登录以查看您的公式库</p>
                <button class="action-btn" onclick="closeFormulaSelector(); toggleAuthModal(true);">
                    立即登录
                </button>
            </div>`;
        return;
    }

    container.innerHTML = '<div style="text-align:center;"><i class="fa-solid fa-spinner fa-spin"></i> 加载中...</div>';

    try {
        const res = await fetch(`/api/formulas/list?username=${user}`);
        const data = await res.json();

        if (data.status === 'success') {
            if (data.data.length === 0) {
                container.innerHTML = `
                    <div style="text-align:center; padding: 2rem; color:#94a3b8;">
                        <p>暂无公式</p>
                        <button class="action-btn secondary" onclick="goToMyFormulas()">去添加</button>
                    </div>`;
            } else {
                const listHtml = data.data.map(f => {
                    const displayLatex = normalizeLatex(f.latex);
                    return `
                    <div class="formula-card" onclick="selectFormula('${encodeURIComponent(f.latex)}')" style="cursor:pointer; margin-bottom:1rem; border:1px solid #e2e8f0; padding:1rem; border-radius:8px; transition:0.2s;">
                        <div style="font-size:1.2rem; margin-bottom:0.5rem; overflow-x:auto; padding:5px;">
                            \\[ ${displayLatex} \\]
                        </div>
                        <div style="font-size:0.85rem; color:#64748b; display:flex; justify-content:space-between;">
                            <span>${f.note || "未命名"}</span>
                            <span style="color:var(--primary-color);"><i class="fa-solid fa-check-circle"></i> 选择</span>
                        </div>
                    </div>
                `}).join('');

                const manageBtnHtml = `
                    <div style="text-align:center; margin-top:2rem; padding-top:1rem; border-top:1px solid #f1f5f9;">
                        <button class="action-btn secondary" onclick="goToMyFormulas()">
                            <i class="fa-solid fa-list-check"></i> 管理我的算式库
                        </button>
                    </div>
                `;
                container.innerHTML = listHtml + manageBtnHtml;
                if (window.MathJax) MathJax.typesetPromise([container]);
            }
        } else {
            container.innerHTML = "加载失败";
        }
    } catch (e) {
        container.innerHTML = "加载失败";
    }
}

window.goToMyFormulas = function() {
    closeFormulaSelector();
    showSection('my-formulas');
}

export function clearCalcInput() {
    const field = document.getElementById('math-field-main');
    const code = document.getElementById('latex-code-main');
    if(field) field.setValue("");
    if(code) code.value = "";
}

window.selectFormula = function(encodedLatex) {
    const latex = decodeURIComponent(encodedLatex);
    const field = document.getElementById('math-field-main');
    if(field) field.setValue(latex);
    closeFormulaSelector();
};