// static/js/formulas.js
import { showSection, toggleAuthModal, toggleModal } from './ui.js';
import * as DevTools from './devtools.js';

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
export function normalizeLatex(latex) {
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

// --- 7. 动画脚本库（子页：算式库 | 动画脚本库）---

let formulasMonacoEditor = null;
let currentScriptId = null; // 编辑中的脚本 id，null 表示新建

export function switchFormulasSubTab(tab) {
    document.querySelectorAll('.formulas-sub-tab').forEach(btn => btn.classList.remove('active'));
    const btn = document.querySelector(`.formulas-sub-tab[data-tab="${tab}"]`);
    if (btn) btn.classList.add('active');

    const formulasPanel = document.getElementById('formulas-panel');
    const scriptsPanel = document.getElementById('scripts-panel');
    if (tab === 'formulas') {
        if (formulasPanel) formulasPanel.style.display = 'block';
        if (scriptsPanel) scriptsPanel.style.display = 'none';
    } else {
        if (formulasPanel) formulasPanel.style.display = 'none';
        if (scriptsPanel) scriptsPanel.style.display = 'block';
        loadAnimationScripts();
    }
}

export async function loadAnimationScripts() {
    const user = getCurrentUser();
    const listEl = document.getElementById('animation-scripts-list');
    if (!listEl) return;

    if (!user) {
        listEl.innerHTML = `
            <div class="empty-state" style="grid-column:1/-1;">
                <i class="fa-solid fa-lock"></i>
                <p>请先登录以查看动画脚本库</p>
                <button class="action-btn" onclick="toggleAuthModal(true)">立即登录</button>
            </div>`;
        return;
    }

    listEl.innerHTML = '<div style="text-align:center; padding:2rem; color:var(--text-secondary);"><i class="fa-solid fa-spinner fa-spin"></i> 加载中...</div>';
    try {
        const res = await fetch(`/api/animation_scripts/list?username=${encodeURIComponent(user)}`);
        const data = await res.json();
        if (data.status === 'success') renderScriptsList(data.data);
        else listEl.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">加载失败</div>';
    } catch (e) {
        listEl.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">网络错误</div>';
    }
}

function renderScriptsList(scripts) {
    const listEl = document.getElementById('animation-scripts-list');
    if (!listEl) return;

    const addCard = `
        <div class="formula-card add-new-card" onclick="showSection('calculate')" style="justify-content:center; align-items:center; border:2px dashed var(--border-color); cursor:pointer; min-height:180px;">
            <div style="font-size:2.5rem; color:var(--primary-color); margin-bottom:0.5rem;"><i class="fa-solid fa-circle-plus"></i></div>
            <div style="font-size:1rem; color:var(--text-secondary); font-weight:600;">去动态计算页生成并保存</div>
        </div>`;

    if (!scripts || scripts.length === 0) {
        listEl.innerHTML = addCard + `
            <div class="empty-state" style="grid-column:1/-1; padding-top:1rem;">
                <p>暂无保存的脚本。在「动态计算」中渲染出想要的内容后，可保存代码到此库，并在此用 Monaco 编辑、重新运行。</p>
            </div>`;
        return;
    }

    const cards = scripts.map(s => {
        const note = (s.note || '未命名').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const preview = (s.code_preview || s.code || '').replace(/</g, '&lt;').replace(/>/g, '&gt;').substring(0, 120) + (s.code_preview && s.code_preview.length > 120 ? '...' : '');
        return `
        <div class="formula-card">
            <div class="formula-preview" style="font-size:0.8rem; font-family:monospace; white-space:pre-wrap; text-align:left; justify-content:flex-start;">
                ${preview}
            </div>
            <div class="formula-meta">
                <span class="formula-note" title="${note}">${note}</span>
                <div class="formula-actions">
                    <button class="btn-icon" title="在云端工作台编辑" onclick="Formulas.editScriptInWorkbench(${s.id})"><i class="fa-solid fa-pen-to-square"></i></button>
                    <button class="btn-icon" title="在云端工作台运行" onclick="Formulas.runScriptInWorkbench(${s.id})"><i class="fa-solid fa-play"></i></button>
                    <button class="btn-icon delete" title="删除" onclick="Formulas.deleteScript(${s.id})"><i class="fa-solid fa-trash"></i></button>
                </div>
            </div>
        </div>`;
    }).join('');
    listEl.innerHTML = addCard + cards;
}

export async function openScriptDetail(id) {
    const user = getCurrentUser();
    if (!user) { toggleAuthModal(true); return; }

    currentScriptId = id;
    const listView = document.getElementById('scripts-list-view');
    const detailView = document.getElementById('scripts-detail-view');
    if (listView) listView.style.display = 'none';
    if (detailView) detailView.style.display = 'block';

    const noteInput = document.getElementById('script-detail-note');
    if (noteInput) noteInput.value = '';

    if (id === 'new') {
        initFormulasMonacoIfNeeded('');
        if (formulasMonacoEditor) formulasMonacoEditor.setValue(`from manim import *

class GenScene(Scene):
    def construct(self):
        circle = Circle(radius=2, color=BLUE)
        self.play(Create(circle))
        self.wait(1)`);
        return;
    }

    try {
        const res = await fetch(`/api/animation_scripts/get?id=${id}&username=${encodeURIComponent(user)}`);
        const data = await res.json();
        if (data.status === 'success' && data.data) {
            if (noteInput) noteInput.value = data.data.note || '';
            initFormulasMonacoIfNeeded(data.data.code || '');
        } else {
            if (detailView) detailView.style.display = 'none';
            if (listView) listView.style.display = 'block';
            alert('加载脚本失败');
        }
    } catch (e) {
        if (detailView) detailView.style.display = 'none';
        if (listView) listView.style.display = 'block';
        alert('网络错误');
    }
}

export function closeScriptDetail() {
    currentScriptId = null;
    const listView = document.getElementById('scripts-list-view');
    const detailView = document.getElementById('scripts-detail-view');
    if (listView) listView.style.display = 'block';
    if (detailView) detailView.style.display = 'none';
}

function initFormulasMonacoIfNeeded(initialCode) {
    const container = document.getElementById('formulas-monaco-container');
    if (!container) return;

    if (window.monaco && !formulasMonacoEditor) {
        formulasMonacoEditor = window.monaco.editor.create(container, {
            value: initialCode,
            language: 'python',
            theme: 'vs-dark',
            automaticLayout: true,
            fontSize: 14,
            fontFamily: "'JetBrains Mono', monospace",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            padding: { top: 15, bottom: 15 },
            lineNumbersMinChars: 3,
        });
        return;
    }
    if (formulasMonacoEditor) {
        formulasMonacoEditor.setValue(initialCode);
        return;
    }

    if (document.getElementById('monaco-loader-script')) {
        setTimeout(() => initFormulasMonacoIfNeeded(initialCode), 200);
        return;
    }
    const script = document.createElement('script');
    script.id = 'monaco-loader-script';
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/loader.min.js';
    script.onload = () => {
        window.require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' } });
        window.require(['vs/editor/editor.main'], () => {
            initFormulasMonacoIfNeeded(initialCode);
        });
    };
    document.body.appendChild(script);
}

export async function saveScriptFromDetail() {
    const user = getCurrentUser();
    if (!user) { toggleAuthModal(true); return; }
    const note = document.getElementById('script-detail-note')?.value?.trim() || '';
    const code = formulasMonacoEditor ? formulasMonacoEditor.getValue() : '';
    if (!code.trim()) { alert('代码不能为空'); return; }

    if (currentScriptId === null || currentScriptId === 'new') {
        try {
            const res = await fetch('/api/animation_scripts/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, note, code })
            });
            const data = await res.json();
            if (data.status === 'success') {
                if (typeof showToast === 'function') showToast('保存成功', 'success');
                else alert('保存成功');
                currentScriptId = data.id;
                loadAnimationScripts();
            } else {
                alert('保存失败: ' + (data.message || ''));
            }
        } catch (e) {
            alert('网络错误');
        }
        return;
    }

    try {
        const res = await fetch('/api/animation_scripts/update', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: currentScriptId, username: user, note, code })
        });
        const data = await res.json();
        if (data.status === 'success') {
            if (typeof showToast === 'function') showToast('更新成功', 'success');
            else alert('更新成功');
        } else {
            alert('更新失败: ' + (data.message || ''));
        }
    } catch (e) {
        alert('网络错误');
    }
}

export async function runScriptFromDetail() {
    const code = formulasMonacoEditor ? formulasMonacoEditor.getValue() : '';
    if (!code.trim()) { alert('请先输入或加载代码'); return; }
    const btn = document.getElementById('btn-run-script');
    const modal = document.getElementById('script-run-modal');
    const video = document.getElementById('script-run-video');
    const errEl = document.getElementById('script-run-error');
    const logEl = document.getElementById('script-run-log');
    if (btn) btn.disabled = true;
    if (video) video.style.display = 'none';
    if (errEl) errEl.style.display = 'none';
    if (logEl) { logEl.textContent = ''; }
    toggleModal('script-run-modal', true);
    try {
        const res = await fetch('/api/devtools/run_manim_stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        if (!res.ok || !res.body) {
            if (errEl) { errEl.textContent = '请求失败'; errEl.style.display = 'block'; }
            return;
        }
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop() || '';
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'log' && data.message && logEl) {
                        logEl.textContent += data.message + '\n';
                        logEl.scrollTop = logEl.scrollHeight;
                    } else if (data.type === 'start' && logEl) {
                        logEl.textContent += (data.message || '') + '\n';
                    } else if (data.type === 'complete' && data.video_url && video) {
                        video.src = data.video_url + '?t=' + Date.now();
                        video.style.display = 'block';
                        if (logEl) logEl.textContent += '渲染完成。\n';
                    } else if (data.type === 'error' && errEl) {
                        errEl.textContent = data.message || '渲染失败';
                        errEl.style.display = 'block';
                        if (logEl) logEl.textContent += '错误: ' + (data.message || '') + '\n';
                    }
                } catch (_) {}
            }
        }
    } catch (e) {
        if (errEl) { errEl.textContent = '网络错误: ' + e.message; errEl.style.display = 'block'; }
    } finally {
        if (btn) btn.disabled = false;
    }
}

export async function deleteScript(id) {
    if (!confirm('确定删除该脚本？')) return;
    const user = getCurrentUser();
    try {
        await fetch(`/api/animation_scripts/delete?id=${id}&username=${encodeURIComponent(user)}`, { method: 'DELETE' });
        loadAnimationScripts();
        if (currentScriptId === id) closeScriptDetail();
    } catch (e) {
        alert('删除失败');
    }
}

/** 在开发者工具-云端渲染工作台中编辑该脚本 */
export async function editScriptInWorkbench(scriptId) {
    const user = getCurrentUser();
    if (!user) { toggleAuthModal(true); return; }
    try {
        const res = await fetch(`/api/animation_scripts/get?id=${scriptId}&username=${encodeURIComponent(user)}`);
        const data = await res.json();
        if (data.status !== 'success' || !data.data || !data.data.code) {
            if (typeof showToast === 'function') showToast('加载脚本失败', 'error');
            else alert('加载脚本失败');
            return;
        }
        showSection('devtools');
        DevTools.openManimWorkbenchWithCode(data.data.code, { autoRun: false });
    } catch (e) {
        if (typeof showToast === 'function') showToast('网络错误', 'error');
        else alert('网络错误');
    }
}

/** 在开发者工具-云端渲染工作台中运行该脚本 */
export async function runScriptInWorkbench(scriptId) {
    const user = getCurrentUser();
    if (!user) { toggleAuthModal(true); return; }
    try {
        const res = await fetch(`/api/animation_scripts/get?id=${scriptId}&username=${encodeURIComponent(user)}`);
        const data = await res.json();
        if (data.status !== 'success' || !data.data || !data.data.code) {
            if (typeof showToast === 'function') showToast('加载脚本失败', 'error');
            else alert('加载脚本失败');
            return;
        }
        showSection('devtools');
        DevTools.openManimWorkbenchWithCode(data.data.code, { autoRun: true });
    } catch (e) {
        if (typeof showToast === 'function') showToast('网络错误', 'error');
        else alert('网络错误');
    }
}