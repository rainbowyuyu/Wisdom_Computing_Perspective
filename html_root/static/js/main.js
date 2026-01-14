// static/js/main.js
import * as UI from './ui.js';
import * as Canvas from './canvas.js';
import * as Detect from './detect.js';
import * as Calculate from './calculate.js';
import * as Auth from './auth.js';
import * as Settings from './settings.js';
import * as Tutorial from './tutorial.js';
import * as Formulas from './formulas.js'; // 确保引入

document.addEventListener('DOMContentLoaded', () => {
    Canvas.setupCanvas();
    UI.showSection('home');
    Auth.initAuth();
    Settings.initSettings();
    Detect.initDetectListeners();
    Tutorial.checkAutoPlay();

    // 全局快捷键
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        const shortcuts = Settings.getShortcuts();
        if (isMatch(e, shortcuts.undo)) { e.preventDefault(); Canvas.undo(); }
        else if (isMatch(e, shortcuts.redo)) { e.preventDefault(); Canvas.redo(); }
    });
});

function isMatch(e, config) {
    return e.key.toLowerCase() === config.key &&
           e.ctrlKey === config.ctrl &&
           e.shiftKey === config.shift &&
           e.altKey === config.alt &&
           e.metaKey === config.meta;
}

// --- 核心挂载：将 Formulas 中的函数暴露给 HTML ---
window.saveCurrentFormula = Formulas.saveCurrentFormula;
window.saveAndShowFormula = Formulas.saveAndShowFormula; // 关键修复：这就是报错的那个函数
window.loadMyFormulas = Formulas.loadMyFormulas;         // 关键修复
window.useFormula = Formulas.useFormula;
window.deleteFormula = Formulas.deleteFormula;

// --- 其他挂载 ---
window.showSection = (sectionId) => {
    UI.showSection(sectionId);
    if (sectionId === 'detect') setTimeout(() => Canvas.resizeCanvas(), 50);
    // 切换到我的算式页时自动加载
    if (sectionId === 'my-formulas') Formulas.loadMyFormulas();
};

window.toggleAuthModal = UI.toggleAuthModal;
window.switchInputMode = UI.switchInputMode;
window.switchAuthMode = (mode) => { UI.switchAuthMode(mode); Auth.refreshCaptcha(mode); };
window.clearCanvas = Canvas.clearCanvas;
window.undo = Canvas.undo;
window.redo = Canvas.redo;
window.setTool = (tool) => {
    Canvas.setTool(tool);
    document.querySelectorAll('.tool-btn').forEach(btn => {
        const val = btn.getAttribute('onclick');
        if (val && val.includes(`'${tool}'`)) btn.classList.add('active');
        else if (val && (val.includes('pen') || val.includes('eraser'))) btn.classList.remove('active');
    });
};
window.processRecognition = Detect.processRecognition;
window.copyToCalc = Detect.copyToCalc;
window.startAnimation = Calculate.startAnimation;
window.handleLogin = Auth.handleLogin;
window.handleRegister = Auth.handleRegister;
window.refreshCaptcha = Auth.refreshCaptcha;
window.logout = () => location.reload();
window.openSettings = Settings.openSettings;
window.closeSettings = () => UI.toggleModal('settings-modal', false);
window.startRecording = Settings.startRecording;
window.resetDefaults = Settings.resetDefaults;
window.startTutorial = Tutorial.startTutorial;