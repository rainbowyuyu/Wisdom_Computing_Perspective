// static/js/main.js
import * as UI from './ui.js';
import * as Canvas from './canvas.js';
import * as Detect from './detect.js';
import * as Calculate from './calculate.js';
import * as Auth from './auth.js';
import * as Settings from './settings.js'; // 引入设置
import * as Tutorial from './tutorial.js';

document.addEventListener('DOMContentLoaded', () => {
    Canvas.setupCanvas();
    UI.showSection('home');
    Auth.initAuth();
    Settings.initSettings(); // 初始化设置
    Detect.initDetectListeners();

    // --- 全局热键监听 ---
    document.addEventListener('keydown', (e) => {
        // 如果焦点在输入框内，不触发快捷键
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        const shortcuts = Settings.getShortcuts();

        // 检查是否匹配 Undo
        if (isMatch(e, shortcuts.undo)) {
            e.preventDefault();
            Canvas.undo();
        }
        // 检查是否匹配 Redo
        else if (isMatch(e, shortcuts.redo)) {
            e.preventDefault();
            Canvas.redo();
        }
    });
});

// 辅助函数：判断事件是否匹配配置
function isMatch(e, config) {
    return e.key.toLowerCase() === config.key &&
           e.ctrlKey === config.ctrl &&
           e.shiftKey === config.shift &&
           e.altKey === config.alt &&
           e.metaKey === config.meta;
}

// --- 挂载 Settings 相关函数 ---
window.openSettings = Settings.openSettings;
window.closeSettings = () => UI.toggleModal('settings-modal', false);
window.startRecording = Settings.startRecording;
window.resetDefaults = Settings.resetDefaults;

// ... (其他原有挂载代码保持不变) ...
window.showSection = (sectionId) => {
    UI.showSection(sectionId);
    if (sectionId === 'detect') setTimeout(() => Canvas.resizeCanvas(), 50);
};
window.toggleAuthModal = UI.toggleAuthModal;
window.switchInputMode = UI.switchInputMode;
window.switchAuthMode = (mode) => {
    UI.switchAuthMode(mode);
    Auth.refreshCaptcha(mode);
};
window.clearCanvas = Canvas.clearCanvas;
window.undo = Canvas.undo;
window.redo = Canvas.redo;
window.setTool = (tool) => {
    Canvas.setTool(tool);
    document.querySelectorAll('.tool-btn').forEach(btn => {
        const val = btn.getAttribute('onclick');
        if(val && val.includes(`'${tool}'`)) btn.classList.add('active');
        else if(val && (val.includes('pen') || val.includes('eraser'))) btn.classList.remove('active');
    });
};
window.processRecognition = Detect.processRecognition;
window.copyToCalc = Detect.copyToCalc;
window.startAnimation = Calculate.startAnimation;
window.handleLogin = Auth.handleLogin;
window.handleRegister = Auth.handleRegister;
window.refreshCaptcha = Auth.refreshCaptcha;
window.logout = () => location.reload();

document.addEventListener('DOMContentLoaded', () => {
    // ... 原有初始化 ...
    Canvas.setupCanvas();
    UI.showSection('home');

    // 检查并自动播放教程
    Tutorial.checkAutoPlay();
});

// 挂载到 window，以便手动触发
window.startTutorial = Tutorial.startTutorial;