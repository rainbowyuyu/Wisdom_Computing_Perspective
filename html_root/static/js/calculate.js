import { toggleModal, showSection, toggleAuthModal, showToast } from './ui.js';
import { loadMyFormulas, normalizeLatex } from './formulas.js';
import * as Formulas from './formulas.js';

let lastGeneratedCode = '';

function getCurrentUser() {
    const userDisplay = document.getElementById('user-display');
    const usernameSpan = document.getElementById('username-span');
    if (userDisplay && userDisplay.style.display !== 'none' && usernameSpan) return usernameSpan.innerText;
    return null;
}

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

// 辅助：冷却逻辑 (独立并行)
function startCooldown(duration = 10) {
    const btn = document.querySelector('.calc-sidebar .action-btn.full-width');
    if (!btn) return;

    // 如果已经在冷却中，不再重复触发（双重保险）
    if (btn.classList.contains('is-cooldown')) return;

    // 1. 保存原始按钮内容 (如果还没保存过)
    if (!btn.dataset.originalHtml) {
        btn.dataset.originalHtml = btn.innerHTML;
    }

    // 2. 设置冷却状态
    btn.disabled = true;
    btn.classList.add('is-cooldown'); // 添加标记
    btn.style.opacity = '0.7';
    btn.style.cursor = 'not-allowed';

    let timeLeft = duration;
    btn.innerHTML = `<i class="fa-regular fa-clock"></i> 冷却中 (${timeLeft}s)`;

    // 3. 启动倒计时 (不等待 Promise，独立运行)
    const timer = setInterval(() => {
        timeLeft--;
        if (timeLeft <= 0) {
            clearInterval(timer);
            // 4. 恢复原始状态
            btn.disabled = false;
            btn.classList.remove('is-cooldown');
            btn.innerHTML = btn.dataset.originalHtml;
            btn.style.opacity = '';
            btn.style.cursor = '';
        } else {
            btn.innerHTML = `<i class="fa-regular fa-clock"></i> 冷却中 (${timeLeft}s)`;
        }
    }, 1000);
}

// 核心：开始生成动画
export async function startAnimation() {
    const btn = document.querySelector('.calc-sidebar .action-btn.full-width');

    // 检查是否正在冷却
    if (btn && btn.disabled) return;

    const formulaField = document.getElementById('math-field-main');
    const formula = formulaField ? formulaField.getValue() : "";

    if (!formula.trim()) {
        alert("请输入公式");
        return;
    }

    // --- 核心修改：点击后立即启动冷却 (并行执行) ---
    startCooldown(30);

    // 获取 DOM 元素
    const videoWrapper = document.getElementById('calc-video-wrapper');
    const placeholder = document.getElementById('video-placeholder-content');
    const videoPlayer = document.getElementById('result-video-player');

    const logBox = document.getElementById('gen-log');
    const progBar = document.getElementById('gen-progress');
    const percentText = document.getElementById('gen-percent');
    const method = document.getElementById('calc-method').value;

    // 1. 重置 UI 状态
    if(logBox) logBox.innerHTML = '';
    addLog("正在初始化生成任务...", "#94a3b8");

    if(progBar) {
        progBar.style.width = '0%';
        progBar.className = '';
        progBar.style.background = "#3b82f6";
    }
    if(percentText) percentText.innerText = '0%';

    if(videoPlayer) {
        videoPlayer.pause();
        videoPlayer.style.display = 'none';
        videoPlayer.src = "";
    }
    if(placeholder) placeholder.style.display = 'block';
    const saveScriptWrap = document.getElementById('calc-save-script-wrap');
    if(saveScriptWrap) saveScriptWrap.style.display = 'none';
    const renderLoading = document.getElementById('calc-render-loading');
    if(renderLoading) renderLoading.style.display = 'flex';

    // 辅助：添加日志
    function addLog(msg, color = "#cbd5e1") {
        if (!logBox) return;
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
        if (!logBox) return;
        const pre = document.createElement('pre');
        pre.style.marginTop = "10px";
        pre.style.marginBottom = "10px";
        pre.style.background = "#00000033";
        pre.style.padding = "10px";
        pre.style.borderRadius = "4px";
        pre.style.border = "1px solid #334155";
        pre.style.overflowX = "auto";

        const codeEl = document.createElement('code');
        codeEl.className = "language-python hljs";
        codeEl.style.fontFamily = "'JetBrains Mono', monospace";
        codeEl.style.fontSize = "0.8rem";

        pre.appendChild(codeEl);
        logBox.appendChild(pre);

        const chars = fullCode.split('');
        let currentText = "";

        return new Promise((resolve) => {
            let i = 0;
            const speed = 5;

            function type() {
                if (i < chars.length) {
                    const chunk = chars.slice(i, i + speed).join('');
                    currentText += chunk;
                    codeEl.textContent = currentText;
                    logBox.scrollTop = logBox.scrollHeight;
                    i += speed;
                    requestAnimationFrame(type);
                } else {
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

                        if (data.progress) {
                            if(progBar) progBar.style.width = data.progress + '%';
                            if(percentText) percentText.innerText = data.progress + '%';

                            if(data.progress < 30 && progBar) progBar.style.background = "#3b82f6";
                            else if(data.progress < 90 && progBar) progBar.style.background = "#8b5cf6";
                            else if(progBar) progBar.style.background = "#10b981";
                        }

                        if (data.step === 'generating_code') {
                            addLog("正在构思数学可视化脚本...", "#fbbf24");
                        }
                        else if (data.step === 'code_generated') {
                            if (data.code) lastGeneratedCode = data.code;
                            addLog("脚本生成完毕，代码预览：", "#34d399");
                            if (data.code) {
                                await streamCodeBlock(data.code);
                            }
                        }
                        else if (data.step === 'fixing_code') {
                            addLog(data.message || "渲染报错，正在根据错误信息修正代码并重试...", "#fbbf24");
                        }
                        else if (data.step === 'rendering') {
                            if (data.message) {
                                addLog(data.message, "#e2e8f0");
                            }
                        }
                        else if (data.step === 'complete') {
                            if (renderLoading) renderLoading.style.display = 'none';
                            addLog("✨ 渲染完成！视频加载中...", "#a78bfa");
                            setTimeout(() => {
                                if (placeholder) placeholder.style.display = 'none';
                                if (videoPlayer) {
                                    videoPlayer.src = `${data.video_url}?t=${new Date().getTime()}`;
                                    videoPlayer.style.display = 'block';
                                    videoPlayer.play();
                                }
                                const saveScriptWrap = document.getElementById('calc-save-script-wrap');
                                if (saveScriptWrap && lastGeneratedCode) saveScriptWrap.style.display = 'block';
                            }, 500);
                            return;
                        }
                        else if (data.step === 'error') {
                            if (renderLoading) renderLoading.style.display = 'none';
                            addLog("❌ 错误: " + data.message, "#ef4444");
                            if(progBar) progBar.style.background = "#ef4444";
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
        const loadingEl = document.getElementById('calc-render-loading');
        if (loadingEl) loadingEl.style.display = 'none';
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

export async function saveLastCodeToScripts() {
    const user = getCurrentUser();
    if (!user) {
        showToast('请先登录', 'error');
        toggleAuthModal(true);
        return;
    }
    if (!lastGeneratedCode.trim()) {
        showToast('暂无可保存的代码', 'error');
        return;
    }
    const note = prompt('请输入脚本备注（用于在动画脚本库中识别）：', '动态计算 ' + new Date().toLocaleString());
    if (note === null) return;
    try {
        const res = await fetch('/api/animation_scripts/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: user, note: note.trim() || '未命名', code: lastGeneratedCode })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('已保存到动画脚本库', 'success');
            showSection('my-formulas');
            Formulas.switchFormulasSubTab('scripts');
        } else {
            showToast(data.message || '保存失败', 'error');
        }
    } catch (e) {
        showToast('网络错误', 'error');
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