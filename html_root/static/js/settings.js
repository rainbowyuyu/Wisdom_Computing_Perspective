// static/js/settings.js

import { toggleModal } from './ui.js';

// 默认热键配置
const DEFAULT_SHORTCUTS = {
    undo: { key: 'z', ctrl: true, shift: false, alt: false, meta: false },
    redo: { key: 'z', ctrl: true, shift: true, alt: false, meta: false } // 或者 Ctrl+Y
};

// 当前配置（从 localStorage 读取或使用默认）
let shortcuts = JSON.parse(localStorage.getItem('app_shortcuts')) || JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));

// 正在录制的动作 (null, 'undo', 'redo')
let recordingAction = null;

export function initSettings() {
    // 初始化设置面板的值
    updateShortcutDisplay();
}

export function getShortcuts() {
    return shortcuts;
}

// 打开设置模态框
export function openSettings() {
    toggleModal('settings-modal', true);
}

// 开始录制热键
export function startRecording(action) {
    recordingAction = action;
    const btn = document.getElementById(`btn-record-${action}`);
    if (btn) {
        btn.innerText = "按下键盘...";
        btn.classList.add('recording');
    }

    // 添加一次性键盘监听
    document.addEventListener('keydown', handleRecordKey, { once: true, capture: true });
}

function handleRecordKey(e) {
    e.preventDefault();
    e.stopPropagation();

    // 忽略单纯的修饰键按下
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
        // 如果只按了修饰键，重新监听
        document.addEventListener('keydown', handleRecordKey, { once: true, capture: true });
        return;
    }

    // 保存配置
    const newConfig = {
        key: e.key.toLowerCase(),
        ctrl: e.ctrlKey,
        shift: e.shiftKey,
        alt: e.altKey,
        meta: e.metaKey
    };

    if (recordingAction) {
        shortcuts[recordingAction] = newConfig;
        localStorage.setItem('app_shortcuts', JSON.stringify(shortcuts));

        // 更新 UI
        updateShortcutDisplay();

        const btn = document.getElementById(`btn-record-${recordingAction}`);
        if(btn) btn.classList.remove('recording');

        recordingAction = null;
    }
}

// 将配置对象转为可读字符串 (e.g., "Ctrl + Shift + Z")
function formatShortcut(config) {
    const parts = [];
    if (config.ctrl) parts.push('Ctrl');
    if (config.meta) parts.push('Cmd'); // Mac
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

// 恢复默认
export function resetDefaults() {
    shortcuts = JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));
    localStorage.setItem('app_shortcuts', JSON.stringify(shortcuts));
    updateShortcutDisplay();
}