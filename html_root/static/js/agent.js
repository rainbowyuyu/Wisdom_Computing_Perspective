// static/js/agent.js — 智能体：理解意图后跳转到对应页面并执行对应任务（需登录）

import { showSection, toggleAuthModal } from './ui.js';
import { getCurrentUser } from './auth.js';

const SECTION_NAMES = {
    detect: '智能识别',
    calculate: '动态计算',
    devtools: '开发者工具',
    'my-formulas': '我的算式',
    examples: '教学案例',
    help: '帮助'
};

function getPromptEl() {
    return document.getElementById('agent-prompt');
}
function getFileInput() {
    return document.getElementById('agent-image-upload');
}
function getFileNameEl() {
    return document.getElementById('agent-file-name');
}
function getSubmitBtn() {
    return document.getElementById('agent-submit-btn');
}
function getStatusEl() {
    return document.getElementById('agent-status');
}
function getResultArea() {
    return document.getElementById('agent-result-area');
}
function getResultMessage() {
    return document.getElementById('agent-result-message');
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

/** 根据后端返回的 section/formula/operation/trigger 跳转并执行 */
function applyAgentResult(data) {
    const section = data.section || 'calculate';
    showSection(section);

    if (section === 'devtools' && data.devtool && window.switchDevTool) {
        setTimeout(() => switchDevTool(data.devtool), 100);
    }

    if (section === 'calculate' && data.formula) {
        setTimeout(() => {
            const mf = document.getElementById('math-field-main');
            const code = document.getElementById('latex-code-main');
            const method = document.getElementById('calc-method');
            if (mf && mf.setValue) mf.setValue(data.formula);
            if (code) code.value = data.formula;
            if (method && data.operation) method.value = data.operation || 'normal';
            if (data.trigger === 'generate' && typeof window.startAnimation === 'function') {
                setTimeout(() => window.startAnimation(), 400);
            }
        }, 200);
    }

    if (section === 'detect' && data.formula) {
        setTimeout(() => {
            const mathField = document.getElementById('latex-output');
            const codeArea = document.getElementById('latex-code-detect');
            const btnSave = document.getElementById('btn-save-check');
            const btnCalc = document.getElementById('btn-copy-calc');
            if (mathField && mathField.setValue) mathField.setValue(data.formula);
            if (codeArea) codeArea.value = data.formula;
            if (btnSave) btnSave.disabled = false;
            if (btnCalc) btnCalc.disabled = false;
        }, 200);
    }
}

/** 根据登录状态切换「引导登录」与「工作区」的显示 */
export function refreshAgentGate() {
    const gate = document.getElementById('agent-gate');
    const wrap = document.getElementById('agent-workspace-wrap');
    if (!gate || !wrap) return;
    const loggedIn = !!getCurrentUser();
    gate.style.display = loggedIn ? 'none' : 'block';
    wrap.style.display = loggedIn ? 'block' : 'none';
}

export function initAgent() {
    const input = getFileInput();
    const nameEl = getFileNameEl();
    if (input && nameEl) {
        input.addEventListener('change', () => {
            nameEl.textContent = (input.files && input.files[0]) ? input.files[0].name : '';
        });
    }
    refreshAgentGate();
    window.addEventListener('auth-state-change', refreshAgentGate);
}

export async function execute() {
    if (!getCurrentUser()) {
        toggleAuthModal(true);
        return;
    }
    const promptEl = getPromptEl();
    const fileInput = getFileInput();
    const btn = getSubmitBtn();
    const statusEl = getStatusEl();
    const resultArea = getResultArea();
    const resultMessage = getResultMessage();

    const prompt = (promptEl && promptEl.value) ? promptEl.value.trim() : '';
    if (!prompt) {
        statusEl.textContent = '请先输入需求描述。';
        statusEl.className = 'agent-status agent-status-error';
        return;
    }

    btn.disabled = true;
    statusEl.textContent = '正在理解您的需求…';
    statusEl.className = 'agent-status agent-status-loading';
    if (resultArea) resultArea.style.display = 'none';

    let image_base64 = null;
    if (fileInput && fileInput.files && fileInput.files[0]) {
        try {
            image_base64 = await fileToBase64(fileInput.files[0]);
        } catch (e) {
            statusEl.textContent = '图片读取失败';
            statusEl.className = 'agent-status agent-status-error';
            btn.disabled = false;
            return;
        }
    }

    try {
        const res = await fetch('/api/agent/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, image_base64 })
        });
        const data = await res.json();

        if (data.status === 'success') {
            statusEl.textContent = '已为您跳转到对应步骤';
            statusEl.className = 'agent-status agent-status-success';
            if (resultArea) resultArea.style.display = 'block';
            const name = SECTION_NAMES[data.section] || data.section;
            if (resultMessage) resultMessage.textContent = `已打开“${name}”并完成预填${data.trigger === 'generate' ? '，已自动开始生成动画' : data.trigger === 'recognize' ? '，识别结果已填入' : ''}。`;
            applyAgentResult(data);
        } else {
            statusEl.textContent = data.message || '执行失败';
            statusEl.className = 'agent-status agent-status-error';
        }
    } catch (e) {
        statusEl.textContent = '网络错误：' + (e.message || '请稍后重试');
        statusEl.className = 'agent-status agent-status-error';
    } finally {
        btn.disabled = false;
    }
}
