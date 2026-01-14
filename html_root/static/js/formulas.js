// static/js/formulas.js
import { showSection, toggleAuthModal } from './ui.js';

// 获取当前登录用户名
function getCurrentUser() {
    const userSpan = document.getElementById('username-span');
    const userDisplay = document.getElementById('user-display');
    if (userDisplay && userDisplay.style.display !== 'none' && userSpan) {
        return userSpan.innerText;
    }
    return null;
}

// 核心保存请求 (复用逻辑)
async function performSave(user, latex, note) {
    try {
        const res = await fetch('/api/formulas/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ username: user, latex: latex, note: note })
        });
        const data = await res.json();
        return data;
    } catch (e) {
        console.error(e);
        return { status: 'error', message: '网络请求失败' };
    }
}

// --- 功能 1: 仅保存 (用于手动触发) ---
export async function saveCurrentFormula() {
    const user = getCurrentUser();
    if (!user) {
        alert("请先登录！");
        toggleAuthModal(true);
        return;
    }

    // 获取公式
    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    let latex = "";
    if (mathField && mathField.getValue) latex = mathField.getValue();
    else if (codeArea) latex = codeArea.value;

    if (!latex || latex.includes("等待")) {
        alert("没有有效公式");
        return;
    }

    const note = prompt("请输入公式备注：", "我的公式 " + new Date().toLocaleTimeString());
    if (note === null) return;

    const result = await performSave(user, latex, note);
    if (result.status === 'success') {
        alert("保存成功！");
        // 如果当前就在列表页，刷新它
        const section = document.getElementById('my-formulas');
        if (section && section.classList.contains('active-section')) loadMyFormulas();
    } else {
        alert("保存失败: " + result.message);
    }
}

// --- 功能 2: 保存并跳转 (用于识别结果页按钮) ---
export async function saveAndShowFormula() {
    const user = getCurrentUser();
    if (!user) {
        alert("请先登录！");
        toggleAuthModal(true);
        return;
    }

    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    let latex = "";
    if (mathField && mathField.getValue) latex = mathField.getValue();
    else if (codeArea) latex = codeArea.value;

    if (!latex || latex.includes("等待")) {
        alert("请先识别一个有效公式");
        return;
    }

    // 自动生成备注或简单询问
    const note = prompt("保存并查看，请输入备注：", "识别结果 " + new Date().toLocaleTimeString());
    if (note === null) return;

    const result = await performSave(user, latex, note);

    if (result.status === 'success') {
        // 保存成功，直接跳转到列表页
        showSection('my-formulas');
        // showSection 在 main.js 中被修改过，会自动触发 loadMyFormulas
    } else {
        alert("保存失败: " + result.message);
    }
}

// --- 功能 3: 加载列表 ---
export async function loadMyFormulas() {
    const user = getCurrentUser();
    const container = document.getElementById('formula-list');

    if (!container) return;

    if (!user) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-lock"></i>
                <p>请先登录以查看您的云端算式库</p>
                <button class="action-btn" onclick="toggleAuthModal(true)">立即登录</button>
            </div>`;
        return;
    }

    container.innerHTML = `
        <div class="empty-state">
            <i class="fa-solid fa-spinner fa-spin"></i>
            <p>正在同步云端数据...</p>
        </div>`;

    try {
        const res = await fetch(`/api/formulas/list?username=${user}`);
        const data = await res.json();

        if (data.status === 'success') {
            renderList(data.data);
        } else {
            container.innerHTML = `<div class="empty-state"><p>加载失败: ${data.message}</p></div>`;
        }
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><p>网络连接错误</p></div>`;
    }
}

// 渲染列表 HTML
function renderList(formulas) {
    const container = document.getElementById('formula-list');

    if (!formulas || formulas.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-regular fa-folder-open"></i>
                <p>暂无保存的算式，快去识别一个吧！</p>
                <button class="action-btn secondary" onclick="showSection('detect')">去识别</button>
            </div>`;
        return;
    }

    container.innerHTML = formulas.map(f => `
        <div class="formula-card">
            <div class="formula-preview">
                \\[ ${f.latex} \\]
            </div>
            <div class="formula-meta">
                <div class="formula-info">
                    <span class="formula-note" title="${f.note}">${f.note || "未命名"}</span>
                    <span class="formula-date" style="font-size:0.7rem; color:#94a3b8;">${f.created_at || ''}</span>
                </div>
                <div class="formula-actions">
                    <button class="btn-icon" title="使用此公式" onclick="useFormula('${encodeURIComponent(f.latex)}')">
                        <i class="fa-solid fa-share-from-square"></i>
                    </button>
                    <button class="btn-icon delete" title="删除" onclick="deleteFormula(${f.id})">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');

    // 重新渲染 MathJax
    if (window.MathJax) {
        MathJax.typesetPromise([container]).catch(err => console.log(err));
    }
}

// --- 功能 4: 使用公式 ---
export function useFormula(latexEncoded) {
    const latex = decodeURIComponent(latexEncoded);
    const targetA = document.getElementById('latex-code-a');
    if (targetA) {
        targetA.value = latex;
        showSection('calculate');
    }
}

// --- 功能 5: 删除公式 ---
export async function deleteFormula(id) {
    if (!confirm("确定要永久删除这条算式吗？")) return;

    const user = getCurrentUser();
    try {
        const res = await fetch(`/api/formulas/delete?id=${id}&username=${user}`, { method: 'DELETE' });
        const data = await res.json();

        if (data.status === 'success') {
            loadMyFormulas(); // 重新加载列表
        } else {
            alert("删除失败: " + data.message);
        }
    } catch(e) {
        alert("网络错误");
    }
}