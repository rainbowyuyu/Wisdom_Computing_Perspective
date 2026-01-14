// static/js/formulas.js
import { showSection, toggleAuthModal, toggleModal } from './ui.js';

// 获取当前登录用户名
function getCurrentUser() {
    const userSpan = document.getElementById('username-span');
    const userDisplay = document.getElementById('user-display');
    if (userDisplay && userDisplay.style.display !== 'none' && userSpan) {
        return userSpan.innerText;
    }
    return null;
}

// --- 核心：保存请求 ---
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

// --- 新增：LaTeX 规范化函数 ---
function normalizeLatex(latex) {
    if (!latex) return "";
    let clean = latex.trim();

    // 去除开头和结尾的 $$
    if (clean.startsWith('$$') && clean.endsWith('$$')) {
        clean = clean.substring(2, clean.length - 2);
    }
    // 去除开头和结尾的 $
    else if (clean.startsWith('$') && clean.endsWith('$')) {
        clean = clean.substring(1, clean.length - 1);
    }

    // 去除 \[ \]
    if (clean.startsWith('\\[') && clean.endsWith('\\]')) {
        clean = clean.substring(2, clean.length - 2);
    }

    return clean.trim();
}

let isEditListenersInit = false;

function initEditListeners() {
    if (isEditListenersInit) return;

    const mathField = document.getElementById('edit-formula-mathlive');
    const codeArea = document.getElementById('edit-formula-latex');

    if (mathField && codeArea) {
        // MathLive -> Textarea
        mathField.addEventListener('input', (e) => {
            codeArea.value = e.target.value;
        });

        // Textarea -> MathLive
        codeArea.addEventListener('input', (e) => {
            mathField.setValue(e.target.value);
        });
    }
    isEditListenersInit = true;
}

// 1. 保存当前公式
export async function saveCurrentFormula() {
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
        alert("没有有效公式");
        return;
    }

    const note = prompt("请输入公式备注：", "我的公式 " + new Date().toLocaleTimeString());
    if (note === null) return;

    const result = await performSave(user, latex, note);
    if (result.status === 'success') {
        alert("保存成功！");
        const section = document.getElementById('my-formulas');
        if (section && section.classList.contains('active-section')) loadMyFormulas();
    } else {
        alert("保存失败: " + result.message);
    }
}

// 2. 保存并跳转
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

    const note = prompt("保存并查看，请输入备注：", "识别结果 " + new Date().toLocaleTimeString());
    if (note === null) return;

    const result = await performSave(user, latex, note);

    if (result.status === 'success') {
        showSection('my-formulas');
        await loadMyFormulas()
    } else {
        alert("保存失败: " + result.message);
    }
}

// 3. 加载列表
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
            container.innerHTML = "加载失败";
        }
    } catch(e) {
        container.innerHTML = "网络错误";
    }
}

function renderList(formulas) {
    const container = document.getElementById('formula-list');

    // --- 新建卡片 HTML ---
    // 点击后跳转到 Detect 页面，即“去识别/添加”
    const addCardHtml = `
        <div class="formula-card add-new-card" onclick="showSection('detect')" style="justify-content: center; align-items: center; border: 2px dashed #cbd5e1; cursor: pointer; min-height: 180px;">
            <div style="font-size: 2.5rem; color: var(--primary-color); margin-bottom: 0.5rem;">
                <i class="fa-solid fa-circle-plus"></i>
            </div>
            <div style="font-size: 1rem; color: var(--text-secondary); font-weight: 600;">
                新建算式
            </div>
        </div>
    `;

    // 如果没有公式，显示新建卡片 + 空状态提示 (或者只显示新建卡片)
    if (!formulas || formulas.length === 0) {
        container.innerHTML = addCardHtml + `
            <div class="empty-state" style="grid-column: 1 / -1; padding-top: 1rem;">
                <p>暂无保存的算式，点击上方卡片去识别添加吧！</p>
            </div>`;
        return;
    }

    // 有公式时，新建卡片放在第一个
    const listHtml = formulas.map(f => {
        const displayLatex = normalizeLatex(f.latex);
        // ... (转义逻辑保持不变)
        const safeLatex = f.latex.replace(/'/g, "\\'").replace(/"/g, '&quot;');
        const safeNote = (f.note || "").replace(/'/g, "\\'").replace(/"/g, '&quot;');

        return `
        <div class="formula-card">
            <div class="formula-preview">
                \\[ ${displayLatex} \\]
            </div>
            <div class="formula-meta">
                <span class="formula-note" title="${f.note}">${f.note || "未命名"}</span>
                <div class="formula-actions">
                    <button class="btn-icon" title="使用" onclick="useFormula('${encodeURIComponent(displayLatex)}')">
                        <i class="fa-solid fa-share-from-square"></i>
                    </button>
                    <button class="btn-icon" title="编辑" onclick="openEditModal(${f.id}, '${encodeURIComponent(f.latex)}', '${encodeURIComponent(f.note || '')}')">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="btn-icon delete" title="删除" onclick="deleteFormula(${f.id})">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `}).join('');

    container.innerHTML = addCardHtml + listHtml;

    if (window.MathJax) MathJax.typesetPromise([container]);
}

// 4. 使用公式
export function useFormula(latexEncoded) {
    const latex = decodeURIComponent(latexEncoded);
    const targetA = document.getElementById('latex-code-a');
    if (targetA) {
        targetA.value = latex;
        showSection('calculate');
    }
}

// 5. 删除公式
export async function deleteFormula(id) {
    if (!confirm("确定删除？")) return;
    const user = getCurrentUser();
    try {
        await fetch(`/api/formulas/delete?id=${id}&username=${user}`, { method: 'DELETE' });
        loadMyFormulas();
    } catch(e) { alert("Error"); }
}

// --- 6. 新增：编辑相关函数 ---

export function openEditModal(id, encodedLatex, encodedNote) {
    const latex = decodeURIComponent(encodedLatex);
    const note = decodeURIComponent(encodedNote);

    // 填充数据
    document.getElementById('edit-formula-id').value = id;
    document.getElementById('edit-formula-note').value = note;

    // 填充代码框
    const codeArea = document.getElementById('edit-formula-latex');
    codeArea.value = latex;

    // 填充 MathLive 组件
    const mathField = document.getElementById('edit-formula-mathlive');
    if (mathField && mathField.setValue) {
        mathField.setValue(latex);
    }

    // 确保监听器已绑定
    initEditListeners();

    toggleModal('edit-formula-modal', true);
}

export function closeEditModal() {
    toggleModal('edit-formula-modal', false);
}

export async function submitFormulaEdit() {
    const id = document.getElementById('edit-formula-id').value;

    // 优先从 MathLive 获取最新值
    const mathField = document.getElementById('edit-formula-mathlive');
    const codeArea = document.getElementById('edit-formula-latex');

    let latex = "";
    if (mathField && mathField.getValue) latex = mathField.getValue();
    else if (codeArea) latex = codeArea.value; // 降级处理

    const note = document.getElementById('edit-formula-note').value;
    const user = getCurrentUser();

    if (!latex || !latex.trim()) {
        alert("公式不能为空");
        return;
    }

    try {
        const res = await fetch('/api/formulas/update', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id: id, username: user, latex: latex, note: note })
        });
        const data = await res.json();

        if (data.status === 'success') {
            closeEditModal();
            loadMyFormulas(); // 刷新列表
        } else {
            alert("更新失败: " + data.message);
        }
    } catch(e) {
        console.error(e);
        alert("网络错误");
    }
}