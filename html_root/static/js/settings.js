// static/js/settings.js

import { toggleModal } from './ui.js';

// ... (DEFAULT_SHORTCUTS 和 shortcuts 定义保持不变) ...
const DEFAULT_SHORTCUTS = {
    undo: { key: 'z', ctrl: true, shift: false, alt: false, meta: false },
    redo: { key: 'z', ctrl: true, shift: true, alt: false, meta: false }
};
let shortcuts = JSON.parse(localStorage.getItem('app_shortcuts')) || JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));
let recordingAction = null;

export function initSettings() {
    updateShortcutDisplay();
    loadVersionFromUpdate();
}

// ... (getShortcuts, openSettings, startRecording, handleRecordKey, formatShortcut, updateShortcutDisplay, resetDefaults 保持不变) ...
export function getShortcuts() { return shortcuts; }
export function openSettings() { toggleModal('settings-modal', true); }
export function startRecording(action) {
    recordingAction = action;
    const btn = document.getElementById(`btn-record-${action}`);
    if (btn) { btn.innerText = "按下键盘..."; btn.classList.add('recording'); }
    document.addEventListener('keydown', handleRecordKey, { once: true, capture: true });
}
function handleRecordKey(e) {
    e.preventDefault(); e.stopPropagation();
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
        document.addEventListener('keydown', handleRecordKey, { once: true, capture: true });
        return;
    }
    const newConfig = { key: e.key.toLowerCase(), ctrl: e.ctrlKey, shift: e.shiftKey, alt: e.altKey, meta: e.metaKey };
    if (recordingAction) {
        shortcuts[recordingAction] = newConfig;
        localStorage.setItem('app_shortcuts', JSON.stringify(shortcuts));
        updateShortcutDisplay();
        const btn = document.getElementById(`btn-record-${recordingAction}`);
        if(btn) btn.classList.remove('recording');
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
    const undoDisplay = document.getElementById('shortcut-undo-display');
    const redoDisplay = document.getElementById('shortcut-redo-display');
    if (undoDisplay) undoDisplay.value = formatShortcut(shortcuts.undo);
    if (redoDisplay) redoDisplay.value = formatShortcut(shortcuts.redo);
}
export function resetDefaults() {
    shortcuts = JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));
    localStorage.setItem('app_shortcuts', JSON.stringify(shortcuts));
    updateShortcutDisplay();
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