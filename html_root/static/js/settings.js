// static/js/settings.js

import { toggleModal } from './ui.js';

// 画板快捷键（类 Photoshop），均可自定义
const DEFAULT_SHORTCUTS = {
    undo:            { key: 'z', ctrl: true,  shift: false, alt: false, meta: false },
    redo:            { key: 'z', ctrl: true,  shift: true,  alt: false, meta: false },
    clearCanvas:     { key: 'c', ctrl: true,  shift: true,  alt: false, meta: false },
    toolPen:         { key: 'b', ctrl: false, shift: false, alt: false, meta: false },
    toolEraser:      { key: 'e', ctrl: false, shift: false, alt: false, meta: false },
    brushSizeUp:     { key: ']', ctrl: false, shift: false, alt: false, meta: false },
    brushSizeDown:   { key: '[', ctrl: false, shift: false, alt: false, meta: false },
};
const SHORTCUT_LABELS = {
    undo: '撤销',
    redo: '重做',
    clearCanvas: '清空画布',
    toolPen: '画笔',
    toolEraser: '橡皮擦',
    brushSizeUp: '笔刷加粗',
    brushSizeDown: '笔刷变细',
};
function loadShortcuts() {
    const out = JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));
    try {
        const saved = JSON.parse(localStorage.getItem('app_shortcuts') || '{}');
        Object.keys(out).forEach(k => { if (saved[k] && typeof saved[k] === 'object') out[k] = saved[k]; });
    } catch (_) {}
    return out;
}
let shortcuts = loadShortcuts();
let recordingAction = null;

export function initSettings() {
    renderShortcutsList();
    updateShortcutDisplay();
    loadVersionFromUpdate();
}

function renderShortcutsList() {
    const list = document.getElementById('shortcuts-list');
    if (!list || list.dataset.rendered) return;
    list.dataset.rendered = '1';
    Object.keys(SHORTCUT_LABELS).forEach(action => {
        const row = document.createElement('div');
        row.className = 'shortcut-row';
        row.style.cssText = 'display: flex; align-items: center; margin-bottom: 1rem; gap: 10px;';
        const label = document.createElement('label');
        label.textContent = SHORTCUT_LABELS[action];
        label.style.cssText = 'width: 100px; font-weight: 600; color: var(--text-main); flex-shrink: 0;';
        const input = document.createElement('input');
        input.type = 'text';
        input.id = `shortcut-${action}-display`;
        input.setAttribute('readonly', '');
        input.className = 'tech-input';
        input.style.cssText = 'margin:0; text-align: center; flex: 1; max-width: 200px;';
        const btn = document.createElement('button');
        btn.className = 'action-btn secondary';
        btn.style.padding = '0.5rem 1rem';
        btn.textContent = '修改';
        btn.id = `btn-record-${action}`;
        btn.onclick = () => startRecording(action);
        row.appendChild(label);
        row.appendChild(input);
        row.appendChild(btn);
        list.appendChild(row);
    });
}

// ... (getShortcuts, openSettings, startRecording, handleRecordKey, formatShortcut, updateShortcutDisplay, resetDefaults 保持不变) ...
export function getShortcuts() { return shortcuts; }
export function openSettings(anchor) {
    updateShortcutDisplay();
    toggleModal('settings-modal', true);
    if (anchor === 'shortcuts') {
        requestAnimationFrame(() => {
            const el = document.getElementById('settings-shortcuts');
            const body = document.querySelector('#settings-modal .settings-modal-body');
            if (el && body) el.scrollIntoView({ block: 'start', behavior: 'smooth' });
        });
    }
}
export function startRecording(action) {
    recordingAction = action;
    const btn = document.getElementById(`btn-record-${action}`);
    if (btn) { btn.innerText = '按下键盘...'; btn.classList.add('recording'); }
    document.addEventListener('keydown', handleRecordKey, { once: true, capture: true });
}
function handleRecordKey(e) {
    e.preventDefault();
    e.stopPropagation();
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
        document.addEventListener('keydown', handleRecordKey, { once: true, capture: true });
        return;
    }
    const newConfig = { key: e.key.toLowerCase(), ctrl: e.ctrlKey, shift: e.shiftKey, alt: e.altKey, meta: e.metaKey };
    if (recordingAction) {
        const doneAction = recordingAction;
        shortcuts[doneAction] = newConfig;
        localStorage.setItem('app_shortcuts', JSON.stringify(shortcuts));
        updateShortcutDisplay();
        const btn = document.getElementById(`btn-record-${doneAction}`);
        if (btn) { btn.classList.remove('recording'); btn.innerText = '修改'; }
        recordingAction = null;
    }
}
function formatShortcut(config) {
    const parts = [];
    if (config.ctrl) parts.push('Ctrl');
    if (config.meta) parts.push('Cmd');
    if (config.alt) parts.push('Alt');
    if (config.shift) parts.push('Shift');
    parts.push(config.key.toUpperCase());
    return parts.join(' + ');
}
function updateShortcutDisplay() {
    Object.keys(DEFAULT_SHORTCUTS).forEach(action => {
        const el = document.getElementById(`shortcut-${action}-display`);
        const cfg = shortcuts[action] || DEFAULT_SHORTCUTS[action];
        if (el && cfg) el.value = formatShortcut(cfg);
    });
}
export function resetDefaults() {
    shortcuts = JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));
    localStorage.setItem('app_shortcuts', JSON.stringify(shortcuts));
    updateShortcutDisplay();
}
export function getShortcutLabels() {
    return SHORTCUT_LABELS;
}

// --- 修复版：加载版本号 ---
async function loadVersionFromUpdate() {
  const displayEl = document.getElementById('version-display');
  if (!displayEl) return;

  try {
    // 1. 请求路径改为当前目录下的 update.md (假设已移动到 static 目录)
    // 加上时间戳防止缓存
    const res = await fetch('update.md?t=' + new Date().getTime());

    if (!res.ok) {
        console.warn('update.md not found in static folder.');
        displayEl.textContent = "Unknown";
        return;
    }

    const text = await res.text();

    // 2. 增强正则匹配
    // 匹配 v 0.1.0 或 v0.1.0，忽略大小写，允许v和数字间有空格
    const regex = /v\s*([\d.]+\.[\d]+)/gi;

    // 找到所有匹配项
    const matches = [...text.matchAll(regex)];

    if (matches.length > 0) {
        // 通常最后一个匹配的是最新版本（假设 update.md 是追加写入的）
        // 如果 update.md 是倒序（最新在最上），则取 matches[0]
        // 这里假设 update.md 是追加模式，取最后一个
        const latestVersion = 'v' + matches[matches.length - 1][1];
        displayEl.textContent = latestVersion;
    } else {
        displayEl.textContent = "v0.0.0";
    }

  } catch (err) {
    console.error('Version load failed:', err);
    displayEl.textContent = "Error";
  }
}