// static/js/calculate.js

import { toggleModal, showSection, toggleAuthModal } from './ui.js'; // 引入更多 UI 函数
import { loadMyFormulas, normalizeLatex } from './formulas.js'; // 我们需要复用加载逻辑，但渲染逻辑不同

// 初始化计算页面的监听器
export function initCalculateListeners() {
    const fieldA = document.getElementById('math-field-a');
    const codeA = document.getElementById('latex-code-a');
    const fieldB = document.getElementById('math-field-b');
    const codeB = document.getElementById('latex-code-b');

    // 双向绑定 A
    if (fieldA && codeA) {
        // 初始化值
        codeA.value = fieldA.getValue();
        fieldA.addEventListener('input', (e) => { codeA.value = e.target.value; });
    }
    // 双向绑定 B
    if (fieldB && codeB) {
        codeB.value = fieldB.getValue();
        fieldB.addEventListener('input', (e) => { codeB.value = e.target.value; });
    }
}

// 开始动画 (修改为从 math-field 获取值)
export async function startAnimation() {
    const container = document.getElementById('video-container');
    const method = document.getElementById('calc-method').value;

    // 直接从 MathLive 组件获取值，更准确
    const matA = document.getElementById('math-field-a').getValue();
    const matB = document.getElementById('math-field-b').getValue();

    container.innerHTML = `
        <div class="placeholder-content" style="color:var(--secondary-color)">
            <i class="fa-solid fa-circle-notch fa-spin" style="font-size: 3rem;"></i>
            <p style="margin-top:1rem;">Manim 渲染中 (约需5-10秒)...</p>
        </div>
    `;

    try {
        const response = await fetch('/api/animate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                matrixA: matA,
                matrixB: matB,
                operation: method
            })
        });
        const data = await response.json();

        if (data.status === 'success') {
            const videoSrc = `${data.video_url}?t=${new Date().getTime()}`;
            container.innerHTML = `
                <video controls autoplay style="width: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
                    <source src="${videoSrc}" type="video/mp4">
                    您的浏览器不支持视频标签。
                </video>
            `;
        } else {
            container.innerHTML = `<p style="color:red; text-align:center;">生成失败: ${data.message || 'Unknown error'}</p>`;
        }
    } catch (e) {
        console.error(e);
        container.innerHTML = `<p style="color:red; text-align:center;">服务器连接错误</p>`;
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

    // 检查登录状态
    const user = (userDisplay && userDisplay.style.display !== 'none' && userSpan) ? userSpan.innerText : null;

    if (!user) {
        container.innerHTML = `
            <div style="text-align:center; padding: 2rem;">
                <p style="color:var(--text-secondary); margin-bottom: 1rem;">请先登录以查看您的公式库</p>
                <!-- 核心修改：先调用 closeFormulaSelector() 关闭当前模态框，再打开登录模态框 -->
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
                        <!-- 未有公式时，跳转到公式库也会先关闭模态框 -->
                        <button class="action-btn secondary" onclick="goToMyFormulas()">去添加</button>
                    </div>`;
            } else {
                // 渲染列表
                const listHtml = data.data.map(f => {
                    // 核心修改：使用 normalizeLatex 处理显示的公式
                    const displayLatex = normalizeLatex(f.latex);

                    return `
                    <div class="formula-card" onclick="selectFormula('${encodeURIComponent(f.latex)}')" style="cursor:pointer; margin-bottom:1rem; border:1px solid #e2e8f0; padding:1rem; border-radius:8px; transition:0.2s;">
                        <div style="font-size:1.2rem; margin-bottom:0.5rem; overflow-x:auto; padding:5px;">
                            \\[ ${displayLatex} \\] <!-- 这里使用处理过的公式 -->
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
    closeFormulaSelector(); // 关闭模态框
    showSection('my-formulas'); // 跳转页面
}

// 选中公式
window.selectFormula = function(encodedLatex) {
    const latex = decodeURIComponent(encodedLatex);
    if (currentTargetField === 'A') {
        const field = document.getElementById('math-field-a');
        if(field) field.setValue(latex);
    } else if (currentTargetField === 'B') {
        const field = document.getElementById('math-field-b');
        if(field) field.setValue(latex);
    }
    closeFormulaSelector();
};