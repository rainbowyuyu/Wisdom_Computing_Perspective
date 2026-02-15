// static/js/main.js
import * as UI from './ui.js';
import * as Canvas from './canvas.js';
import * as Detect from './detect.js';
import * as Calculate from './calculate.js';
import * as Auth from './auth.js';
import * as Settings from './settings.js';
import * as Tutorial from './tutorial.js';
import * as Formulas from './formulas.js';
import * as Examples from './examples.js';
import * as Docs from './docs.js';
import * as Theme from './theme.js';
import * as DevTools from './devtools.js';
import * as Agent from './agent.js';
import * as MathLiveKeyboard from './mathlive/mathlive-keyboard.js';
import * as MathLiveMenu from './mathlive/mathlive-menu.js';
import * as MathLiveLocale from './mathlive/mathlive-locale.js';

// 1. 解析URL参数的工具函数（通用可复用）
function getUrlParams() {
  const params = {};
  // 获取URL中?后的参数部分，若无则返回空对象
  const search = window.location.search.slice(1);
  if (!search) return params;
  // 分割参数并解析为键值对
  search.split('&').forEach(item => {
    const [key, value] = item.split('=');
    params[key] = value || '';
  });
  return params;
}

document.addEventListener('DOMContentLoaded', () => {
    Canvas.setupCanvas();
    if (typeof window.currentToolType === 'undefined') window.currentToolType = 'pen';
    UI.showSection('home');
    Auth.initAuth();
    Settings.initSettings();
    Detect.initDetectListeners();
    Tutorial.checkAutoPlay();
    Examples.loadExamples(); // 加载案例
    Theme.initTheme();
    DevTools.initDevTools();
    Agent.initAgent();
    MathLiveKeyboard.initMathLiveKeyboard();
    MathLiveMenu.initMathLiveMenuOnce();
    MathLiveLocale.initMathLiveLocale();

    // 画板快捷键（类 Photoshop），仅在非输入框时生效
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        const s = Settings.getShortcuts();
        if (isMatch(e, s.undo)) { e.preventDefault(); Canvas.undo(); }
        else if (isMatch(e, s.redo)) { e.preventDefault(); Canvas.redo(); }
        else if (isMatch(e, s.clearCanvas)) { e.preventDefault(); Canvas.clearCanvas(); }
        else if (isMatch(e, s.toolPen)) { e.preventDefault(); window.setTool(window.currentToolType === 'pen' ? 'eraser' : 'pen'); }
        else if (isMatch(e, s.toolEraser)) { e.preventDefault(); window.setTool(window.currentToolType === 'eraser' ? 'pen' : 'eraser'); }
        else if (isMatch(e, s.brushSizeUp)) { e.preventDefault(); Canvas.setBrushSizeDelta(1); }
        else if (isMatch(e, s.brushSizeDown)) { e.preventDefault(); Canvas.setBrushSizeDelta(-1); }
    });

    const params = getUrlParams(); // 获取所有URL参数
      // 若存在section参数，执行showSection
      if (params.section) {
        showSection(params.section);
      }
      // 若存在devtool参数，执行switchDevTool
      if (params.devtool) {
        switchDevTool(params.devtool);
      }

    // 新增功能条：若用户曾关闭则不再显示
    if (localStorage.getItem('agent_banner_closed')) {
      const el = document.getElementById('agent-update-banner');
      if (el) el.style.display = 'none';
    }
});

// 关闭顶部“新功能：智能体”条，并记住选择
window.closeAgentBanner = function () {
  const el = document.getElementById('agent-update-banner');
  if (el) {
    el.style.display = 'none';
    localStorage.setItem('agent_banner_closed', '1');
  }
};

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
    if (sectionId === 'my-formulas') {
        Formulas.loadMyFormulas();
        Formulas.switchFormulasSubTab('formulas');
    }
    if (sectionId === 'agent' && Agent.refreshAgentGate) Agent.refreshAgentGate();
};

window.toggleAuthModal = UI.toggleAuthModal;
window.switchInputMode = UI.switchInputMode;
window.switchAuthMode = (mode) => {
    UI.switchAuthMode(mode);
    Auth.refreshCaptcha(mode);
    if (mode === 'register') Auth.clearUsernameHint?.();
};
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
window.logout = Auth.logout;
window.openSettings = Settings.openSettings;
window.closeSettings = () => UI.toggleModal('settings-modal', false);
window.startRecording = Settings.startRecording;
window.resetDefaults = Settings.resetDefaults;
window.startTutorial = Tutorial.startTutorial;

// 新增挂载
window.openEditModal = Formulas.openEditModal;
window.closeEditModal = Formulas.closeEditModal;
window.submitFormulaEdit = Formulas.submitFormulaEdit;
window.Formulas = Formulas;
window.Calculate = window.Calculate || {};
window.Calculate.saveLastCodeToScripts = Calculate.saveLastCodeToScripts;


document.addEventListener('DOMContentLoaded', () => {
    // ... (其他初始化)
    Calculate.initCalculateListeners(); // 初始化 MathLive 监听
});

// ... (其他挂载)

// 挂载 Calculate 新增函数
window.startAnimation = Calculate.startAnimation;
window.openFormulaSelector = Calculate.openFormulaSelector;
window.closeFormulaSelector = Calculate.closeFormulaSelector;
window.clearCalcInput = Calculate.clearCalcInput; // 新增

// 更新 useFormula (从 formulas.js 跳转过来的逻辑)
// 我们需要它填充 MathLive 组件而不是 textarea
// 在 main.js 中重写或更新 formulas.js 中的 useFormula
window.useFormula = (latexEncoded) => {
    const latex = decodeURIComponent(latexEncoded);
    // 切换到计算页
    window.showSection('calculate');
    // 延时填充，确保页面可见
    setTimeout(() => {
        // 改为填充新的主输入框
        const field = document.getElementById('math-field-main');
        if(field) field.setValue(latex);
    }, 100);
};


// 挂载 Examples 函数
window.playExample = Examples.playExample;
window.closeVideoModal = Examples.closeVideoModal;

// --- Docs 挂载 ---
window.openDoc = Docs.openDoc;
window.closeDocsModal = Docs.closeDocsModal;

// 挂载移动端函数
window.toggleMobileMenu = UI.toggleMobileMenu;
window.mobileNavClick = UI.mobileNavClick;

// 挂载切换函数给 HTML 按钮使用
window.toggleTheme = Theme.toggleTheme;

// 挂载全局 开发者工具（inline onclick 需用 DevTools.xxx）
window.DevTools = DevTools;
window.Agent = Agent;
window.switchDevTool = DevTools.switchDevTool;
window.runDevManim = DevTools.runDevManim;
window.copyDevLatex = DevTools.copyDevLatex;