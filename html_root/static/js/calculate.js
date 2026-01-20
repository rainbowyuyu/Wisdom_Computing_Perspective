// static/js/calculate.js

import { toggleModal, showSection, toggleAuthModal } from './ui.js';
import { loadMyFormulas, normalizeLatex } from './formulas.js';

// 初始化计算页面的监听器
export function initCalculateListeners() {
    const field = document.getElementById('math-field-main');
    const code = document.getElementById('latex-code-main');

    if (field && code) {
        // 双向绑定
        code.value = field.getValue();
        field.addEventListener('input', (e) => { code.value = e.target.value; });
        code.addEventListener('input', (e) => { field.setValue(e.target.value); });
    }
}

// 核心：开始生成动画 (SSE 流式 - 增强版)
export async function startAnimation() {
    const container = document.getElementById('video-container');
    const method = document.getElementById('calc-method').value;
    const formula = document.getElementById('math-field-main').getValue();

    // 1. 初始化 UI：显示进度条和日志
    container.innerHTML = `
        <div style="width: 100%; height: 100%; display: flex; flex-direction: column; padding: 20px; background: #0f172a; color: #cbd5e1; font-family: 'JetBrains Mono', monospace;">
            <!-- 进度条区域 -->
            <div style="margin-bottom: 15px;">
                <div style="display: flex; justify-content: space-between; font-size: 0.9rem; margin-bottom: 5px; color: #60a5fa;">
                    <span id="gen-status">准备就绪...</span>
                    <span id="gen-percent">0%</span>
                </div>
                <div style="height: 6px; background: #334155; border-radius: 3px; overflow: hidden;">
                    <div id="gen-progress" style="width: 0%; height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6); transition: width 0.3s;"></div>
                </div>
            </div>

            <!-- 日志与代码输出区域 -->
            <div id="gen-log" style="flex: 1; overflow-y: auto; font-size: 0.85rem; background: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #334155;">
                <div class="log-entry" style="color: #94a3b8;">> 系统初始化...</div>
            </div>
        </div>
    `;

    const logBox = document.getElementById('gen-log');
    const progBar = document.getElementById('gen-progress');
    const statusText = document.getElementById('gen-status');
    const percentText = document.getElementById('gen-percent');

    // 辅助：解析 Markdown 并高亮
    function renderMarkdown(text) {
        if (!text) return "";
        if (window.marked) {
            return window.marked.parse(text);
        }
        return text;
    }

    function addLog(msg, color = "#cbd5e1") {
        const div = document.createElement('div');
        div.className = 'log-entry';
        div.style.color = color;
        div.style.marginBottom = '6px';
        div.style.lineHeight = '1.5';

        const html = renderMarkdown(msg);
        div.innerHTML = `<span style="opacity:0.6; margin-right:5px;">></span> ${html}`;

        const p = div.querySelector('p');
        if(p) p.style.margin = '0';

        logBox.appendChild(div);
        logBox.scrollTop = logBox.scrollHeight;
    }

    // --- 核心修改：流式打字机效果显示代码 ---
    async function streamCodeBlock(fullCode) {
        // 创建 pre code 结构
        const pre = document.createElement('pre');
        pre.style.margin = "10px 0";
        pre.style.borderRadius = "8px";
        pre.style.background = "#282c34";
        pre.style.padding = "10px";
        pre.style.overflowX = "auto";
        pre.style.border = "1px solid #475569";

        const codeEl = document.createElement('code');
        pre.className = "hljs"; // 添加 hljs 类
        codeEl.textContent = ""; // 初始为空

        pre.appendChild(codeEl);
        logBox.appendChild(pre);

        // 模拟打字机
        const chars = fullCode.split('');
        let currentText = "";

        // 使用 Promise 包装，以便可以使用 await 等待打字完成
        return new Promise((resolve) => {
            let i = 0;
            // 速度：每帧打多少个字。代码通常比较长，需要快一点
            // 假设 60fps，每帧打 5 个字，每秒就是 300 字
            const speed = 3;

            function type() {
                if (i < chars.length) {
                    // 每次追加一小段
                    const chunk = chars.slice(i, i + speed).join('');
                    currentText += chunk;
                    codeEl.textContent = currentText;

                    // 实时高亮 (Highlight.js 的 highlightElement 会重置 DOM，所以我们需要 carefully)
                    // highlight.js 直接操作 innerHTML，这在流式追加时可能会有冲突。
                    // 更好的做法是：只在最后高亮，或者使用 highlight.js 的 highlightAuto 返回 HTML

                    // 只有当打字完成或者每隔一定字符数才高亮一次，避免闪烁
                    // 这里为了性能，我们只在最后高亮。中间过程保持纯文本。

                    logBox.scrollTop = logBox.scrollHeight;
                    i += speed;
                    requestAnimationFrame(type);
                } else {
                    // 打字完成，执行最终高亮
                    if (window.hljs) {
                        window.hljs.highlightElement(codeEl);
                    }
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
                matrixA: formula, // 将公式传给 A
                matrixB: "",      // B 为空
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
                        }

                        // 处理消息
                        if (data.step === 'generating_code') {
                            statusText.innerText = "匹配代码中...";
                            addLog("正在请求 Manim 代码...", "#fbbf24");
                        }
                        else if (data.step === 'code_generated') {
                            addLog("代码重写完毕，正在准备渲染环境...", "#34d399");
                            if (data.code) {
                                addLog("Python 脚本预览 (实时重写中)：", "#94a3b8");
                                // 关键：使用 await 等待打字机效果完成，再处理后续消息
                                // 注意：这里会阻塞后续日志的显示，这正是我们想要的（先看完代码再看渲染日志）
                                await streamCodeBlock(data.code);
                            }
                        }
                        else if (data.step === 'rendering') {
                            statusText.innerText = "渲染视频中...";
                            if (data.message && !data.message.includes("渲染帧")) {
                                addLog(data.message);
                            }
                        }
                        else if (data.step === 'complete') {
                            statusText.innerText = "任务完成";
                            addLog("渲染成功！正在加载视频播放器...", "#a78bfa");
                            progBar.style.background = "#34d399";

                            setTimeout(() => {
                                const videoSrc = `${data.video_url}?t=${new Date().getTime()}`;
                                container.innerHTML = `
                                    <video controls autoplay style="width: 100%; height: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
                                        <source src="${videoSrc}" type="video/mp4">
                                        您的浏览器不支持视频标签。
                                    </video>
                                `;
                            }, 1500);
                            return;
                        }
                        else if (data.step === 'error') {
                            statusText.innerText = "发生错误";
                            statusText.style.color = "#ef4444";
                            progBar.style.background = "#ef4444";
                            addLog("❌ 错误: " + data.message, "#ef4444");
                            return;
                        }

                    } catch (e) {
                        console.warn("Skipping incomplete JSON chunk");
                    }
                }
            }
        }

    } catch (e) {
        console.error(e);
        addLog("网络连接中断", "#ef4444");
    }
}


// --- 公式选择器逻辑 ---
let currentTargetField = null; // 'A' or 'B'

export function openFormulaSelector(target) {
    currentTargetField = target;
    toggleModal('select-formula-modal', true);
    loadFormulaSelectorList();
}

export function closeFormulaSelector() {
    toggleModal('select-formula-modal', false);
    currentTargetField = null;
}

// 加载用于选择的公式列表 (优化版)
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
                // 渲染列表
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

                // 在列表底部添加管理按钮
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

// 辅助跳转函数 (需要挂载到 window)
window.goToMyFormulas = function() {
    closeFormulaSelector();
    showSection('my-formulas');
}

// 清空输入
export function clearCalcInput() {
    const field = document.getElementById('math-field-main');
    const code = document.getElementById('latex-code-main');
    if(field) field.setValue("");
    if(code) code.value = "";
}

// 选中公式 (回调)
window.selectFormula = function(encodedLatex) {
    const latex = decodeURIComponent(encodedLatex);
    const field = document.getElementById('math-field-main');
    if(field) field.setValue(latex);
    closeFormulaSelector();
};
