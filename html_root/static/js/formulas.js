import { normalizeLatex, renderMathIn } from './math-text.js';
export { normalizeLatex } from './math-text.js';
// static/js/formulas.js
import { showSection, toggleAuthModal, toggleModal } from './ui.js';
import * as DevTools from '/static/js/devtools.js?v=20260917-creator-2';
import { sanitizeMarkdownHtml } from './sanitize.js';
import { escapeText as escapeHtml } from './solution-visual.js';
import { openSavedSolution } from './solution-library.js';
window.addEventListener('formula-library-updated',()=>{if(document.getElementById('my-formulas')?.classList.contains('active-section'))loadMyFormulas();});

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
        if (typeof showAlert === 'function') await showAlert("请先登录！", "提示");
        toggleAuthModal(true);
        return;
    }

    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    let latex = "";
    if (mathField && mathField.getValue) latex = mathField.getValue();
    else if (codeArea) latex = codeArea.value;

    if (!latex || latex.includes("等待")) {
        if (typeof showAlert === 'function') await showAlert("没有有效公式", "提示");
        return;
    }

    const note = typeof showPrompt === 'function' ? await showPrompt("请输入公式备注：", "我的公式 " + new Date().toLocaleTimeString(), "保存公式") : null;
    if (note === null) return;

    const result = await performSave(user, latex, note);
    if (result.status === 'success') {
        if (typeof showToast === 'function') showToast("保存成功！", "success");
        const section = document.getElementById('my-formulas');
        if (section && section.classList.contains('active-section')) loadMyFormulas();
    } else {
        if (typeof showAlert === 'function') await showAlert("保存失败: " + result.message, "错误");
    }
}

// 2. 保存并跳转
export async function saveAndShowFormula() {
    const user = getCurrentUser();
    if (!user) {
        if (typeof showAlert === 'function') await showAlert("请先登录！", "提示");
        toggleAuthModal(true);
        return;
    }

    const mathField = document.getElementById('latex-output');
    const codeArea = document.getElementById('latex-code-detect');

    let latex = "";
    if (mathField && mathField.getValue) latex = mathField.getValue();
    else if (codeArea) latex = codeArea.value;

    if (!latex || latex.includes("等待")) {
        if (typeof showAlert === 'function') await showAlert("请先识别一个有效公式", "提示");
        return;
    }

    const note = typeof showPrompt === 'function' ? await showPrompt("保存并查看，请输入备注：", "识别结果 " + new Date().toLocaleTimeString(), "保存并查看") : null;
    if (note === null) return;

    const result = await performSave(user, latex, note);

    if (result.status === 'success') {
        showSection('my-formulas');
        await loadMyFormulas()
    } else {
        if (typeof showAlert === 'function') await showAlert("保存失败: " + result.message, "错误");
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
            // 同步刷新右侧「知识星云」，基于已保存算式的主题标签统计
            refreshKnowledgeSummary();
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
        if(f.solution_title) return `<div class="formula-card solution-card">
            <div class="solution-card-body"><span class="solution-card-kind"><i class="fa-solid fa-layer-group"></i> 分步题解 ${f.video_url?'<i class="fa-solid fa-film" title="含动画"></i>':''}</span><h3>${escapeHtml(f.solution_title)}</h3><p>${escapeHtml(f.latex)}</p><span class="solution-card-detail">${Number(f.step_count)} 个步骤${f.video_url?' · 含动画':''}</span></div>
            <div class="formula-meta"><button class="solution-card-open" data-solution-read="${Number(f.id)}">阅读题解 <i class="fa-solid fa-arrow-right"></i></button><button class="btn-icon delete" title="删除题解" data-solution-delete="${Number(f.id)}"><i class="fa-regular fa-trash-can"></i></button></div></div>`;
        const displayLatex = normalizeLatex(f.latex);
        // ... (转义逻辑保持不变)
        const safeLatex = f.latex.replace(/'/g, "\\'").replace(/"/g, '&quot;');
        const safeNote = (f.note || "").replace(/'/g, "\\'").replace(/"/g, '&quot;');

        return `
        <div class="formula-card">
            <div class="formula-preview">
                \\[ ${escapeHtml(displayLatex)} \\]
            </div>
            <div class="formula-meta">
                <span class="formula-note" title="${escapeHtml(f.note)}">${escapeHtml(f.note || "未命名")}</span>
                <div class="formula-actions">
                    <button class="btn-icon" title="使用" onclick="useFormula('${encodeURIComponent(displayLatex).replace(/'/g,'%27')}')">
                        <i class="fa-solid fa-share-from-square"></i>
                    </button>
                    <button class="btn-icon" title="编辑" onclick="openEditModal(${f.id}, '${encodeURIComponent(f.latex).replace(/'/g,'%27')}', '${encodeURIComponent(f.note || '').replace(/'/g,'%27')}')">
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
    container.querySelectorAll('[data-solution-read]').forEach(button=>button.addEventListener('click',()=>openSavedSolution(button.dataset.solutionRead).catch(()=>{})));
    container.querySelectorAll('[data-solution-delete]').forEach(button=>button.addEventListener('click',()=>deleteFormula(Number(button.dataset.solutionDelete))));

    renderMathIn(container);
}

// 4. 使用公式
export function useFormula(latexEncoded) {
    const latex = decodeURIComponent(latexEncoded);
    window.showSection?.('calculate');window.StepTutor?.prefill(latex);
}

// 5. 删除公式
export async function deleteFormula(id) {
    const confirmed = typeof showConfirm === 'function' ? await showConfirm("确定删除？", "确认删除") : false;
    if (!confirmed) return;
    const user = getCurrentUser();
    try {
        const response=await fetch(`/api/formulas/delete?id=${id}&username=${encodeURIComponent(user)}`, { method: 'DELETE' });
        if(!response.ok)throw new Error('删除失败');
        window.dispatchEvent(new CustomEvent('formula-library-deleted',{detail:{id}}));
        loadMyFormulas();
    } catch(e) {
        if (typeof showAlert === 'function') await showAlert("删除失败", "错误");
    }
}

// 6. 「知识星云」与掌握度进度条
async function refreshKnowledgeSummary() {
    const user = getCurrentUser();
    const listEl = document.getElementById('knowledge-progress-list');
    const cloudEl = document.getElementById('knowledge-cloud');
    const panelEl = document.getElementById('knowledge-panel');
    if (!listEl || !cloudEl || !panelEl) return;

    if (!user) {
        listEl.innerHTML = '<p style="font-size:0.85rem; color:var(--text-secondary);">登录后可查看基于你算式的知识掌握情况。</p>';
        cloudEl.innerHTML = '';
        return;
    }
    listEl.innerHTML = '<div style="font-size:0.85rem; color:var(--text-secondary);"><i class="fa-solid fa-spinner fa-spin"></i> 计算知识星云中…</div>';
    cloudEl.innerHTML = '';

    try {
        const res = await fetch(`/api/formulas/knowledge?username=${encodeURIComponent(user)}`);
        const data = await res.json();
        if (data.status !== 'success') {
            listEl.innerHTML = '<p style="font-size:0.85rem; color:var(--error-color,#ef4444);">暂时无法获取知识统计</p>';
            cloudEl.innerHTML = '';
            return;
        }
        const topics = Array.isArray(data.topics) ? data.topics : [];
        const total = data.total || 0;
        // 若完全没有标签数据，则提示用户多做几道题再来
        if (!topics.length || !total) {
            listEl.innerHTML = '<p style="font-size:0.85rem; color:var(--text-secondary);">还没有足够的算式，先去识别或计算几道题，点亮你的第一颗知识星吧。</p>';
            cloudEl.innerHTML = '';
            return;
        }

        // 进度条列表
        listEl.innerHTML = topics
            .slice(0, 8)
            .map(t => {
                const tag = t.tag || '';
                const mastery = Math.max(0, Math.min(100, parseInt(t.mastery, 10) || 0));
                const count = t.count || 0;
                return `
                    <div class="knowledge-progress-item">
                        <div class="knowledge-progress-header">
                            <span class="knowledge-tag-label">#${tag}</span>
                            <span class="knowledge-tag-meta">${mastery}% · ${count} 条算式</span>
                        </div>
                        <div class="knowledge-progress-bar">
                            <div class="knowledge-progress-inner" style="width:${mastery}%;"></div>
                        </div>
                    </div>
                `;
            })
            .join('');

        // 星云/标签云：按掌握度控制大小与透明度，简单随机分布
        const maxFont = 1.6; // rem
        const minFont = 0.85;
        const tagsHtml = topics
            .map((t, idx) => {
                const tag = t.tag || '';
                const mastery = Math.max(0, Math.min(100, parseInt(t.mastery, 10) || 0));
                const ratio = mastery / 100;
                const size = (minFont + (maxFont - minFont) * ratio).toFixed(2);
                const opacity = (0.4 + 0.6 * ratio).toFixed(2);
                const hue = 200 + Math.round(60 * ratio) + (idx * 17) % 40;
                return `<span class="knowledge-cloud-tag" style="font-size:${size}rem; opacity:${opacity}; color:hsl(${hue},80%,70%);">#${tag}</span>`;
            })
            .join('');
        cloudEl.innerHTML = tagsHtml;
        // 手机端：默认折叠为小球
        if (typeof window.matchMedia !== 'undefined' && window.matchMedia('(max-width: 768px)').matches && panelEl) {
            panelEl.classList.add('collapsed');
            panelEl.style.width = '56px';
            panelEl.style.height = '56px';
            const cnt = document.getElementById('knowledge-panel-content');
            const bbl = document.getElementById('knowledge-panel-bubble');
            if (cnt) cnt.style.display = 'none';
            if (bbl) bbl.style.display = 'flex';
            panelEl.title = '点击打开知识星云';
        }
    } catch (e) {
        console.warn('refreshKnowledgeSummary failed', e);
        listEl.innerHTML = '<p style="font-size:0.85rem; color:var(--error-color,#ef4444);">知识统计加载失败</p>';
        cloudEl.innerHTML = '';
    }
}

// --- 6. 新增：编辑相关函数 ---

export function openEditModal(id, encodedLatex, encodedNote) {
    const latex = normalizeLatex(decodeURIComponent(encodedLatex));
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
        if (typeof showAlert === 'function') await showAlert("公式不能为空", "提示");
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
            if (typeof showAlert === 'function') await showAlert("更新失败: " + data.message, "错误");
        }
    } catch(e) {
        console.error(e);
        if (typeof showAlert === 'function') await showAlert("网络错误", "错误");
    }
}

// 从「我的算式」编辑弹窗跳转到开发者工具的 LaTeX 编辑器继续编辑
export function openInDevLatexFromEdit() {
    const mathField = document.getElementById('edit-formula-mathlive');
    const codeArea = document.getElementById('edit-formula-latex');
    let latex = "";
    if (mathField && mathField.getValue) latex = mathField.getValue();
    else if (codeArea) latex = codeArea.value;
    latex = (latex || "").trim();
    if (!latex) {
        if (typeof showAlert === 'function') showAlert("公式为空，无法跳转编辑", "提示");
        return;
    }
    // 先关闭编辑弹窗，再跳转到 LaTeX 编辑器
    closeEditModal();
    showSection('devtools');
    setTimeout(() => {
        if (typeof window.switchDevTool === 'function') window.switchDevTool('latex');
        if (DevTools && typeof DevTools.fillLatexInDevtools === 'function') {
            DevTools.fillLatexInDevtools(latex);
        }
    }, 200);
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
    const templatesPanel = document.getElementById('templates-panel');
    if (tab === 'formulas') {
        if (formulasPanel) formulasPanel.style.display = 'block';
        if (scriptsPanel) scriptsPanel.style.display = 'none';
        if (templatesPanel) templatesPanel.style.display = 'none';
    } else if (tab === 'scripts') {
        if (formulasPanel) formulasPanel.style.display = 'none';
        if (scriptsPanel) scriptsPanel.style.display = 'block';
        if (templatesPanel) templatesPanel.style.display = 'none';
        loadAnimationScripts();
    } else if (tab === 'templates') {
        if (formulasPanel) formulasPanel.style.display = 'none';
        if (scriptsPanel) scriptsPanel.style.display = 'none';
        if (templatesPanel) templatesPanel.style.display = 'block';
        loadAgentTemplates();
    }
}

async function loadAgentTemplates() {
    const listEl = document.getElementById('formulas-agent-templates-list');
    if (!listEl) return;
    const user = getCurrentUser();
    if (!user) {
        listEl.innerHTML = `
            <div class="empty-state" style="grid-column:1/-1;">
                <i class="fa-solid fa-lock"></i>
                <p>请先登录以使用智能体模板</p>
                <button class="action-btn" onclick="toggleAuthModal(true)">立即登录</button>
            </div>`;
        return;
    }
    listEl.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><i class="fa-solid fa-spinner fa-spin"></i><p>正在同步云端数据...</p></div>';
    let list = [];
    try {
        const res = await fetch(`/api/agent_templates/list?username=${encodeURIComponent(user)}`);
        const data = await res.json();
        if (data.status === 'success' && Array.isArray(data.data)) list = data.data;
    } catch (e) {
        listEl.innerHTML = '<div class="empty-state" style="grid-column:1/-1;">读取模板失败</div>';
        return;
    }
    const addCard = `<div class="formula-card add-new-card" onclick="showSection('agent')">
        <div style="font-size:2.5rem; color:var(--primary-color); margin-bottom:0.5rem;"><i class="fa-solid fa-circle-plus"></i></div>
        <div style="font-size:1rem; color:var(--text-secondary); font-weight:600;">去智能体生成并保存</div>
    </div>`;
    if (list.length === 0) {
        listEl.innerHTML = addCard + `
            <div class="empty-state" style="grid-column:1/-1; padding-top:1rem;">
                <p>暂无保存的模板。在「智能体」对话中执行任务后，点击回复中的「存为模板」，即可在此一键复用。</p>
            </div>`;
        return;
    }
    const marked = window.marked && typeof window.marked.parse === 'function' ? window.marked : null;
    const typesetMath = typeof window.typesetAgentMath === 'function' ? window.typesetAgentMath : null;
    function toPreviewLine(text, maxLen) {
        if (!text || !text.trim()) return '';
        const line = text.replace(/\s+/g, ' ').trim();
        return line.length > maxLen ? line.slice(0, maxLen) + '…' : line;
    }
    const cardFrag = document.createDocumentFragment();
    list.slice().reverse().forEach(t => {
        const name = (t.name || '未命名').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const promptText = (t.prompt || '').trim();
        const ts = t.createdAt != null ? (typeof t.createdAt === 'number' ? t.createdAt : new Date(t.createdAt).getTime()) : null;
        const createdAt = ts ? new Date(ts).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : '';
        const id = (t.id || '').toString();
        const card = document.createElement('div');
        card.className = 'formula-card';
        const previewDiv = document.createElement('div');
        if (promptText && marked) {
            previewDiv.className = 'formula-preview formula-preview-copy markdown-body';
            previewDiv.style.cssText = 'font-size:0.8rem; text-align:left; justify-content:flex-start; max-height:140px; overflow:hidden;';
            const safeCopy = promptText.slice(0, 1500);
            previewDiv.innerHTML = sanitizeMarkdownHtml(marked.parse(safeCopy));
            if (typesetMath) typesetMath(previewDiv);
        } else if (promptText) {
            previewDiv.className = 'formula-preview formula-preview-copy';
            previewDiv.style.cssText = 'font-size:0.8rem; text-align:left; justify-content:flex-start; overflow:hidden; white-space:nowrap; text-overflow:ellipsis;';
            previewDiv.textContent = toPreviewLine(promptText, 200) || '（无提示词）';
        } else {
            previewDiv.className = 'formula-preview';
            previewDiv.style.cssText = 'font-size:0.8rem; text-align:left; justify-content:flex-start; overflow:hidden; white-space:pre-wrap;';
            previewDiv.textContent = '（无提示词）';
        }
        const meta = document.createElement('div');
        meta.className = 'formula-meta';
        meta.innerHTML = `
            <div class="formula-info">
                <span class="formula-note" title="${name}">${name}</span>
                ${createdAt ? `<small class="formula-date">${createdAt}</small>` : ''}
            </div>
            <div class="formula-actions">
                <button class="btn-icon agent-template-use-btn" title="使用" type="button" data-template-id="${id}"><i class="fa-solid fa-play"></i></button>
            </div>`;
        card.appendChild(previewDiv);
        card.appendChild(meta);
        card.dataset.templateId = id;
        cardFrag.appendChild(card);
    });
    listEl.innerHTML = addCard;
    listEl.appendChild(cardFrag);
    listEl.querySelectorAll('.agent-template-use-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.getAttribute('data-template-id');
            if (typeof showSection === 'function') showSection('agent');
            if (window.Agent && typeof window.Agent.runTemplateById === 'function') window.Agent.runTemplateById(id);
        });
    });
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

    listEl.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><i class="fa-solid fa-spinner fa-spin"></i><p>正在同步云端数据...</p></div>';
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

    const getVideoCopy = (typeof window !== 'undefined' && window.DevTools && typeof window.DevTools.getVideoCopyForScript === 'function')
        ? window.DevTools.getVideoCopyForScript.bind(window.DevTools) : () => '';
    const marked = window.marked && typeof window.marked.parse === 'function' ? window.marked : null;
    const typesetMath = typeof window.typesetAgentMath === 'function' ? window.typesetAgentMath : null;

    /** 将总结文案压成简短文本（仅在没有 marked 时使用） */
    function toPreviewLine(text, maxLen) {
        if (!text || !text.trim()) return '';
        const line = text.replace(/\s+/g, ' ').trim();
        return line.length > maxLen ? line.slice(0, maxLen) + '…' : line;
    }

    const cardFrag = document.createDocumentFragment();
    scripts.forEach(s => {
        const note = (s.note || '未命名').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const videoCopy = getVideoCopy(s.id);
        const card = document.createElement('div');
        card.className = 'formula-card';
        const previewDiv = document.createElement('div');
        if (videoCopy && marked) {
            // 与「导入 → 我的脚本」保持一致：正常 Markdown 多行渲染，但卡片内限制高度
            previewDiv.className = 'formula-preview formula-preview-copy markdown-body';
            previewDiv.style.cssText = 'font-size:0.8rem; text-align:left; justify-content:flex-start; max-height:140px; overflow:hidden;';
            const safeCopy = videoCopy.slice(0, 1500);
            previewDiv.innerHTML = sanitizeMarkdownHtml(marked.parse(safeCopy));
            if (typesetMath) typesetMath(previewDiv);
        } else if (videoCopy) {
            // 无 marked 时的降级：仍然单行截断，但不做富文本渲染
            previewDiv.className = 'formula-preview formula-preview-copy';
            previewDiv.style.cssText = 'font-size:0.8rem; text-align:left; justify-content:flex-start; overflow:hidden; white-space:nowrap; text-overflow:ellipsis;';
            previewDiv.textContent = toPreviewLine(videoCopy, 200) || '（无摘要）';
        } else {
            previewDiv.className = 'formula-preview';
            previewDiv.style.cssText = 'font-size:0.8rem; text-align:left; justify-content:flex-start; overflow:hidden; white-space:pre-wrap;';
            const codePreview = (s.code_preview || s.code || '').replace(/</g, '&lt;').replace(/>/g, '&gt;').substring(0, 120) + (s.code_preview && s.code_preview.length > 120 ? '...' : '');
            previewDiv.textContent = codePreview || '（无预览）';
        }
        const meta = document.createElement('div');
        meta.className = 'formula-meta';
        meta.innerHTML = `
            <span class="formula-note" title="${note}">${note}</span>
            <div class="formula-actions">
                <button class="btn-icon" title="在云端工作台编辑" onclick="Formulas.editScriptInWorkbench(${s.id})"><i class="fa-solid fa-pen-to-square"></i></button>
                <button class="btn-icon" title="在云端工作台运行" onclick="Formulas.runScriptInWorkbench(${s.id})"><i class="fa-solid fa-play"></i></button>
                <button class="btn-icon delete" title="删除" onclick="Formulas.deleteScript(${s.id})"><i class="fa-solid fa-trash"></i></button>
            </div>`;
        card.appendChild(previewDiv);
        card.appendChild(meta);
        cardFrag.appendChild(card);
    });
    listEl.innerHTML = addCard;
    listEl.appendChild(cardFrag);
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
            if (typeof showAlert === 'function') await showAlert('加载脚本失败', "错误");
        }
    } catch (e) {
        if (detailView) detailView.style.display = 'none';
        if (listView) listView.style.display = 'block';
        if (typeof showAlert === 'function') await showAlert('网络错误', "错误");
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
    if (!code.trim()) {
        if (typeof showAlert === 'function') await showAlert('代码不能为空', "提示");
        return;
    }

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
                if (typeof showAlert === 'function') await showAlert('保存失败: ' + (data.message || ''), "错误");
            }
        } catch (e) {
            if (typeof showAlert === 'function') await showAlert('网络错误', "错误");
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
            if (typeof showAlert === 'function') await showAlert('更新失败: ' + (data.message || ''), "错误");
        }
    } catch (e) {
        if (typeof showAlert === 'function') await showAlert('网络错误', "错误");
    }
}

export async function runScriptFromDetail() {
    const code = formulasMonacoEditor ? formulasMonacoEditor.getValue() : '';
    if (!code.trim()) {
        if (typeof showAlert === 'function') await showAlert('请先输入或加载代码', "提示");
        return;
    }
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
    const confirmed = typeof showConfirm === 'function' ? await showConfirm('确定删除该脚本？', "确认删除") : false;
    if (!confirmed) return;
    const user = getCurrentUser();
    try {
        await fetch(`/api/animation_scripts/delete?id=${id}&username=${encodeURIComponent(user)}`, { method: 'DELETE' });
        loadAnimationScripts();
        if (currentScriptId === id) closeScriptDetail();
    } catch (e) {
        if (typeof showAlert === 'function') await showAlert('删除失败', "错误");
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
            else { if (typeof showAlert === 'function') await showAlert('加载脚本失败', "错误"); }
            return;
        }
        showSection('devtools');
        DevTools.openManimWorkbenchWithCode(data.data.code, {
            autoRun: false,
            scriptId: scriptId,
            note: data.data.note || ''
        });
    } catch (e) {
        if (typeof showToast === 'function') showToast('网络错误', 'error');
        else { if (typeof showAlert === 'function') await showAlert('网络错误', "错误"); }
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
            else { if (typeof showAlert === 'function') await showAlert('加载脚本失败', "错误"); }
            return;
        }
        showSection('devtools');
        DevTools.openManimWorkbenchWithCode(data.data.code, {
            autoRun: true,
            scriptId: scriptId,
            note: data.data.note || ''
        });
    } catch (e) {
        if (typeof showToast === 'function') showToast('网络错误', 'error');
        else { if (typeof showAlert === 'function') await showAlert('网络错误', "错误"); }
    }
}

/** 算式库「新建空白脚本」：进入云端渲染工作台并填入框架脚本 */
export function createNewScriptInWorkbench() {
    const user = getCurrentUser();
    if (!user) { toggleAuthModal(true); return; }
    showSection('devtools');
    DevTools.openNewBlankScriptInWorkbench();
}
