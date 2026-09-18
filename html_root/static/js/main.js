import { initNavSearch } from './site-search.js';
// static/js/main.js
import * as UI from './ui.js';
import * as Canvas from './canvas.js';
import * as Detect from './detect.js?v=20260917-creator-2';
import * as Calculate from './calculate.js';
import * as Auth from './auth.js';
import * as Settings from './settings.js';
import * as Tutorial from './tutorial.js';
import * as Formulas from './formulas.js?v=20260917-creator-2';
import * as Examples from './examples.js';
import * as Docs from './docs.js?v=20260918-doc-math-1';
import * as Theme from './theme.js';
import * as DevTools from '/static/js/devtools.js?v=20260917-creator-2';
import * as Agent from './agent.js';
import * as Profile from './profile.js';
import * as ImageEditor from './image-editor.js';
import * as KnowledgePanel from './knowledge-panel.js?v=20260917-ecosystem-6';
import * as ContextMenu from './context-menu.js';
import * as RoleGraph from './role-graph.js?v=20260917-ecosystem-6';
import * as Tooltip from './tooltip.js';
import * as SectionHistory from './section-history.js';
import * as MathLiveKeyboard from './mathlive/mathlive-keyboard.js';
import * as MathLiveMenu from './mathlive/mathlive-menu.js';
import * as MathLiveLocale from './mathlive/mathlive-locale.js';
import { initStepTutor } from './step-tutor.js?v=20260918-progress-1';
import { initFloatingPanel } from './floating-panel.js?v=20260917-nebula-math-7';

// 将常用 UI 能力挂到 window，便于各处统一使用（如 Toast）
window.showToast = UI.showToast;

window._initPhase = true;  // 初始化阶段（URL 直接进入某 section）结束后置为 false

// 0. 子页面 URL 与 History API 同步（使浏览器原生前进/后退在子页面间切换）
function buildSectionUrl(sectionId, extraParams = {}) {
  const params = { section: sectionId, ...extraParams };
  const qs = Object.entries(params)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => k + '=' + encodeURIComponent(String(v)))
    .join('&');
  return (window.location.pathname || '/') + (qs ? '?' + qs : '');
}

function pushStateForSection(sectionId) {
  const url = buildSectionUrl(sectionId);
  try {
    history.pushState({ sectionId }, '', url);
  } catch (_) {}
}

function replaceStateForSection(sectionId) {
  const url = buildSectionUrl(sectionId);
  try {
    history.replaceState({ sectionId }, '', url);
  } catch (_) {}
}

// 1. 解析URL参数的工具函数（通用可复用）
function getUrlParams() {
  const params = {};
  // 获取URL中?后的参数部分，若无则返回空对象
  const search = window.location.search.slice(1);
  if (!search) return params;
  // 分割参数并解析为键值对（支持 decodeURIComponent）
  search.split('&').forEach(item => {
    const [key, value] = item.split('=');
    try {
      params[key] = value ? decodeURIComponent(value.replace(/\+/g, ' ')) : '';
    } catch (_) {
      params[key] = value || '';
    }
  });
  return params;
}

// 帮助页面内搜索：在当前页面内过滤/展开问答
function initHelpSearch() {
  const input = document.getElementById('help-search-input');
  const helpSection = document.getElementById('help');
  if (!input || !helpSection) return;
  const entries = Array.from(helpSection.querySelectorAll('details'));
  if (!entries.length) return;

  input.addEventListener('input', () => {
    const q = (input.value || '').trim().toLowerCase();
    if (!q) {
      entries.forEach(d => {
        d.style.display = '';
        // 恢复默认展开状态：只保留页面原有的 open 属性
        // 不强制关闭，避免干扰用户手动展开的结果
      });
      return;
    }
    entries.forEach(d => {
      const text = (d.textContent || '').toLowerCase();
      if (text.includes(q)) {
        d.style.display = '';
        d.open = true;
      } else {
        d.style.display = 'none';
      }
    });
  });
}

function initCanvasLockButton() {
    const btn = document.getElementById('canvas-lock-btn');
    const icon = document.getElementById('canvas-lock-icon');
    const label = document.getElementById('canvas-lock-label');
    if (!btn || !icon || !label) return;
    
    // 更新按钮显示状态（仅在移动端显示）
    function updateButtonVisibility() {
        if (isMobileDevice()) {
            btn.style.display = 'inline-flex';
        } else {
            btn.style.display = 'none';
        }
    }
    
    function updateButtonState() {
        const locked = Settings.getCanvasLockMobile();
        btn.classList.toggle('is-locked', locked);
        btn.title = locked ? '已锁定：画板区域仅可滑动' : '锁定画板（仅滑动不书写）';
        icon.className = locked ? 'fa-solid fa-lock canvas-lock-icon' : 'fa-solid fa-lock-open canvas-lock-icon';
        label.textContent = locked ? '已锁定' : '锁定画板';
        const wrapper = document.querySelector('.canvas-wrapper');
        if (wrapper) wrapper.classList.toggle('canvas-locked', locked);
    }
    
    // 初始化显示状态
    updateButtonVisibility();
    updateButtonState();
    
    // 监听窗口大小变化
    window.addEventListener('resize', () => {
        updateButtonVisibility();
    });
    
    btn.addEventListener('click', () => {
        const next = !Settings.getCanvasLockMobile();
        Settings.setCanvasLockMobile(next);
        updateButtonState();
        if (window.showToast) window.showToast(next ? '画板已锁定，仅可滑动' : '画板已解锁，可书写', 'success');
    });
    window.addEventListener('settings-changed', updateButtonState);
}

// 顶层设备判断：在多个初始化逻辑中复用
function isMobileDevice() {
  return window.innerWidth <= 768 ||
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

document.addEventListener('DOMContentLoaded', async () => {
    Canvas.setupCanvas();
    if (typeof window.currentToolType === 'undefined') window.currentToolType = 'pen';
    initStepTutor();
    DevTools.initDevTools();
    window.showSection(getUrlParams().section || 'home');
    await Auth.initAuth();  // 等待鉴权完成，确保首屏时已登录用户的信息已写入 DOM
    Settings.initSettings();
    initCanvasLockButton();
    Detect.initDetectListeners();
    // The tutorial remains available on demand; never interrupt a user entering a problem.
    // Examples and their video metadata load on first entry.
    Theme.initTheme();

    // 全设备初始化开发者工具工作台（含手机端）
    DevTools.initDevTools();

    Agent.initAgent();
    Profile.initProfile();
    window.Profile = Profile;
    MathLiveKeyboard.initMathLiveKeyboard();
    MathLiveMenu.initMathLiveMenuOnce();
    MathLiveLocale.initMathLiveLocale();
    
    // 初始化Hero文字效果（根据设置选择渐变模式和交互效果）
    initHeroTextGlow();
    RoleGraph.initRoleGraph();

    // 画板快捷键（类 Photoshop），仅在非输入框时生效
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        const s = Settings.getShortcuts();
        if (isMatch(e, s.undo)) { e.preventDefault(); Canvas.undo(); }
        else if (isMatch(e, s.redo)) { e.preventDefault(); Canvas.redo(); }
        else if (isMatch(e, s.clearCanvas)) { e.preventDefault(); Canvas.clearCanvas(); }
        else if (isMatch(e, s.toolPen) || (e.key.toLowerCase() === 'p' && !e.ctrlKey && !e.shiftKey && !e.altKey && !e.metaKey)) { e.preventDefault(); window.setTool('pen'); }
        else if (isMatch(e, s.toolEraser)) { e.preventDefault(); window.setTool('eraser'); }
        else if (isMatch(e, s.brushSizeUp)) { e.preventDefault(); Canvas.setBrushSizeDelta(1); }
        else if (isMatch(e, s.brushSizeDown)) { e.preventDefault(); Canvas.setBrushSizeDelta(-1); }
    });

    const params = getUrlParams(); // 获取所有URL参数
      // 若存在section参数，执行showSection
      if (params.section) {
        showSection(params.section);
        if (params.section === 'examples' && params.video) {
          setTimeout(() => Examples.playExampleByVideoId(params.video, params.t), 400);
        }
      }
      KnowledgePanel.refreshKnowledgePanel(params.section || 'home');  // 智算星云：首屏即现，按当前 section 展示
      // 若存在devtool参数，执行switchDevTool
      if (params.devtool) {
        switchDevTool(params.devtool);
      }
      // 将当前 section 写入浏览器历史（replace），使后续 pushState 与原生前进/后退一致
      const initSection = params.section || 'home';
      replaceStateForSection(initSection, (initSection === 'examples' && params.video) ? { video: params.video, t: params.t } : {});
    initNavSearch();
    initHelpSearch();
    window.appSectionBack = () => history.back();
    window.appSectionForward = () => history.forward();
    window.appSectionCanBack = SectionHistory.canGoBack;
    window.appSectionCanForward = SectionHistory.canGoForward;
    window.addEventListener('popstate', (e) => {
      const sid = e.state?.sectionId;
      if (sid) {
        SectionHistory.syncIndexToSection(sid);
        window.showSection(sid, { fromHistory: true });
      }
    });
    ContextMenu.initContextMenu();
    Tooltip.initTooltip();
    UI.initModalEscHandler?.();

    // 初始化阶段结束，之后跳转到「我的算式」时将允许显示知识星云
    setTimeout(() => { window._initPhase = false; }, 0);


    // 新增功能条：若用户曾关闭则不再显示
    if (localStorage.getItem('wisdom.release.dismissed')==='0.4.5') {
      const el = document.getElementById('agent-update-banner');
      if (el) el.style.display = 'none';
    }

    // 用户登录后刷新智算星云
    window.addEventListener('auth-state-change', () => {
      const active = document.querySelector('.section.active-section');
      KnowledgePanel.refreshKnowledgePanel(active ? active.id : 'home');
    });

    // 星云内渲染进度：展开态进度条，折叠态水面填满小球
    KnowledgePanel.initRenderProgressInNebula?.();

    initStepTutor();
    initFloatingPanel();
});

// 按版本记住公告关闭状态，新版本仍会展示。
window.closeAgentBanner = function () {
  const el = document.getElementById('agent-update-banner');
  if (el) {
    el.style.display = 'none';
    localStorage.setItem('wisdom.release.dismissed', '0.4.5');
  }
};

function isMatch(e, config) {
    return e.key.toLowerCase() === config.key &&
           e.ctrlKey === config.ctrl &&
           e.shiftKey === config.shift &&
           e.altKey === config.alt &&
           e.metaKey === config.meta;
}

/** Hero文字创意交互效果（仅桌面端）- 根据设置选择渐变模式或交互效果（互斥） */
window.initHeroTextGlow = function initHeroTextGlow() {
    // 读取设置
    const effectMode = Settings.getHeroEffectMode(); // 'gradient' 或 'interaction'
    
    const heroText = document.querySelector('.hero .animate-text');
    if (!heroText) return;
    
    // 移除所有字符拆分（如果存在），恢复原始文本结构
    const chars = heroText.querySelectorAll('.char');
    if (chars.length > 0) {
        // 恢复原始文本结构：将每个 .char 替换为文本节点
        chars.forEach(char => {
            const parent = char.parentNode;
            if (parent) {
                const text = document.createTextNode(char.textContent);
                parent.replaceChild(text, char);
            }
        });
        // 清理可能的空文本节点
        const walker = document.createTreeWalker(
            heroText,
            NodeFilter.SHOW_TEXT,
            null
        );
        const textNodes = [];
        let node;
        while (node = walker.nextNode()) {
            if (node.textContent.trim() === '') {
                textNodes.push(node);
            }
        }
        textNodes.forEach(n => n.parentNode?.removeChild(n));
    }
    
    // 应用效果模式到CSS
    heroText.classList.remove('hero-gradient-dynamic', 'hero-gradient-static', 'hero-interaction-only');
    
    if (effectMode === 'gradient') {
        // 动态渐变模式：只有渐变，没有交互
        heroText.classList.add('hero-gradient-dynamic');
        return; // 不拆分字符，不启用交互
    } else if (effectMode === 'interaction') {
        // 抖动交互模式：只有交互，没有渐变
        heroText.classList.add('hero-interaction-only');
        // 继续执行下面的交互逻辑
    }
    
    // 仅在桌面端且支持hover的设备上启用交互
    if (window.innerWidth < 769 || !window.matchMedia('(hover: hover)').matches) {
        return;
    }
    
    // heroText 已经在上面获取过了
    if (!heroText) return;
    
    const hero = document.querySelector('.hero');
    if (!hero) return;
    
    // 抖动交互模式：不需要渐变同步
    
    // 初始化交互效果
    function initInteraction() {
        const charElements = heroText.querySelectorAll('.char');
        if (charElements.length === 0) {
            // 如果还没有字符，等待一下再试
            setTimeout(initInteraction, 100);
            return;
        }
        
        
        let rafId = null;
        let targetX = 50;
        let targetY = 50;
        let currentX = 50;
        let currentY = 50;
        
        // 平滑插值函数
        function lerp(start, end, factor) {
            return start + (end - start) * factor;
        }
        
        // 计算两点之间的距离
        function distance(x1, y1, x2, y2) {
            return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
        }
        
        // 缓存字符位置，避免频繁getBoundingClientRect
        let charPositions = [];
        let heroRect = null;
        let lastUpdateTime = 0;
        const UPDATE_INTERVAL = 16; // 约60fps
        
        function cacheCharPositions() {
            heroRect = heroText.getBoundingClientRect();
            charPositions = Array.from(charElements).map(char => {
                const rect = char.getBoundingClientRect();
                return {
                    element: char,
                    x: rect.left + rect.width / 2 - heroRect.left,
                    y: rect.top + rect.height / 2 - heroRect.top,
                    width: rect.width,
                    height: rect.height
                };
            });
        }
        
        // 初始化时缓存位置
        cacheCharPositions();
        
        // 窗口resize时重新缓存
        window.addEventListener('resize', () => {
            setTimeout(cacheCharPositions, 100);
        });
        
        function updatePosition() {
            // 安全检查：确保 heroRect 存在
            if (!heroRect || charPositions.length === 0) {
                rafId = null;
                return;
            }
            
            const now = performance.now();
            const timeSinceLastUpdate = now - lastUpdateTime;
            
            // 限制更新频率，避免卡顿
            if (timeSinceLastUpdate < UPDATE_INTERVAL) {
                // 如果还需要继续更新，继续请求下一帧
                if (Math.abs(currentX - targetX) > 0.1 || Math.abs(currentY - targetY) > 0.1) {
                    rafId = requestAnimationFrame(updatePosition);
                } else {
                    rafId = null;
                }
                return;
            }
            
            lastUpdateTime = now;
            
            const factor = 0.16; // 折中跟手度，手感顺滑
            currentX = lerp(currentX, targetX, factor);
            currentY = lerp(currentY, targetY, factor);
            
            // 字符磁性吸引效果 - 使用缓存的位置，性能优化
            const mouseX = heroRect.width * currentX / 100;
            const mouseY = heroRect.height * currentY / 100;
            
            // 抖动交互模式：只应用交互效果，不使用渐变
            charPositions.forEach(({element, x, y}) => {
                const dist = distance(x, y, mouseX, mouseY);
                const maxDist = 140; // 影响距离折中，手感舒适
                const maxOffset = 5; // 偏移折中，既有反馈又不晃眼
                
                if (dist < maxDist && dist > 0) {
                    const strength = 1 - (dist / maxDist);
                    const offsetX = ((mouseX - x) / dist) * maxOffset * strength;
                    const offsetY = ((mouseY - y) / dist) * maxOffset * strength;
                    const rotation = strength * 2.5; // 旋转幅度折中
                    
                    element.style.transform = `translate(${offsetX}px, ${offsetY}px) rotate(${rotation}deg)`;
                } else {
                    element.style.transform = 'translate(0, 0) rotate(0deg)';
                }
            });
            
            // 检查是否需要继续更新
            const needsUpdate = Math.abs(currentX - targetX) > 0.1 || Math.abs(currentY - targetY) > 0.1;
            
            if (needsUpdate) {
                rafId = requestAnimationFrame(updatePosition);
            } else {
                // 重置所有字符
                charPositions.forEach(({element}) => {
                    element.style.transform = 'translate(0, 0) rotate(0deg)';
                });
                rafId = null;
            }
        }
        
        // 绑定鼠标移动事件（确保只绑定一次）
        const mouseMoveHandler = (e) => {
            // 确保 heroRect 存在
            if (!heroRect) {
                cacheCharPositions();
            }
            
            // 重新缓存位置（鼠标移动时可能布局变化）
            if (Math.random() < 0.05) { // 5%概率更新缓存，减少计算
                cacheCharPositions();
            }
            
            const rect = heroText.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width) * 100;
            const y = ((e.clientY - rect.top) / rect.height) * 100;
            
            targetX = Math.max(0, Math.min(100, x));
            targetY = Math.max(0, Math.min(100, y));
            
            if (!rafId) {
                rafId = requestAnimationFrame(updatePosition);
            }
        };
        
        hero.addEventListener('mousemove', mouseMoveHandler);
        
        // 鼠标离开时平滑重置
        const mouseLeaveHandler = () => {
            targetX = 50;
            targetY = 50;
            // 重置所有字符
            charPositions.forEach(({element}) => {
                element.style.transform = 'translate(0, 0) rotate(0deg)';
            });
            if (!rafId) {
                rafId = requestAnimationFrame(updatePosition);
            }
        };
        
        hero.addEventListener('mouseleave', mouseLeaveHandler);
        
        // 页面可见性变化时停止动画，避免后台运行
        document.addEventListener('visibilitychange', () => {
            if (document.hidden && rafId) {
                cancelAnimationFrame(rafId);
                rafId = null;
            }
        });
    }
    
    // 检查是否已经拆分过（避免重复拆分）
    if (heroText.querySelector('.char')) {
        // 已经拆分过，直接初始化交互
        setTimeout(() => {
            initInteraction();
        }, 50);
    } else {
        // 将文字拆分为字符，用于磁性吸引效果
        function splitTextIntoChars() {
            // 递归处理所有文本节点
            function processNode(node) {
                if (node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent;
                    // 保留空白和换行
                    if (!text.trim()) {
                        return;
                    }
                    
                    const parent = node.parentNode;
                    const chars = text.split('');
                    const fragments = [];
                    
                    chars.forEach(char => {
                        if (char === ' ') {
                            fragments.push(document.createTextNode(' '));
                        } else if (char === '\n' || char === '\r') {
                            // 跳过换行符，因为HTML中已经有<br>
                            return;
                        } else {
                            const span = document.createElement('span');
                            span.className = 'char';
                            span.textContent = char;
                            fragments.push(span);
                        }
                    });
                    
                    // 替换原文本节点
                    if (fragments.length > 0) {
                        fragments.forEach(frag => {
                            parent.insertBefore(frag, node);
                        });
                        parent.removeChild(node);
                    }
                } else if (node.nodeType === Node.ELEMENT_NODE) {
                    // 跳过br标签，递归处理其他子节点
                    if (node.tagName !== 'BR') {
                        const children = Array.from(node.childNodes);
                        children.forEach(child => processNode(child));
                    }
                }
            }
            
            // 处理所有子节点
            const children = Array.from(heroText.childNodes);
            children.forEach(child => processNode(child));
        }
        
        splitTextIntoChars();
        // 字符拆分后，等待DOM更新完成再初始化交互
        setTimeout(() => {
            initInteraction();
        }, 50);
    }
}

// --- 核心挂载：将 Formulas 中的函数暴露给 HTML ---
window.saveCurrentFormula = Formulas.saveCurrentFormula;
window.saveAndShowFormula = Formulas.saveAndShowFormula; // 关键修复：这就是报错的那个函数
window.loadMyFormulas = Formulas.loadMyFormulas;         // 关键修复
window.useFormula = Formulas.useFormula;
window.deleteFormula = Formulas.deleteFormula;

// --- 其他挂载 ---
window.showSection = (sectionId, opts = {}) => {
    if (!opts.fromHistory) {
        SectionHistory.pushSection(sectionId);
        if (!window._initPhase) pushStateForSection(sectionId);
    }

    UI.closeAllModals?.();
    UI.showSection(sectionId);
    if (sectionId === 'examples' && !document.getElementById('examples')?.dataset.loadedOnce) {
        document.getElementById('examples').dataset.loadedOnce = '1';
        Examples.loadExamples();
    }
    document.querySelectorAll('video').forEach(video => { if (!video.closest('.section')?.classList.contains('active-section')) video.pause(); });
    if (sectionId === 'detect') {
        setTimeout(() => Canvas.resizeCanvas(), 50);
        const inputMode = Settings.getDetectDefaultInput();
        setTimeout(() => window.switchInputMode(inputMode), 60);
    }
    if (sectionId === 'my-formulas') {
        Formulas.loadMyFormulas();
        Formulas.switchFormulasSubTab('formulas');
    }
    if (sectionId === 'devtools') {
        const tab = Settings.getDevtoolsDefaultTab();
        if (window.switchDevTool) window.switchDevTool(tab);
    }
    if (sectionId === 'agent' && Agent.refreshAgentGate) Agent.refreshAgentGate();
    // A section switch reuses the document: do not carry the previous page's
    // scroll offset into the assistant and hide its header behind the navbar.
    // The conversation keeps its own independent scroll position.
    if (sectionId === 'agent' && !opts.fromHistory) {
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    }

    // 智算星云：全局浮动，按页面切换内容
    KnowledgePanel.refreshKnowledgePanel(sectionId);
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
window.openInDevLatexFromDetect = Detect.editInDevtoolsFromDetect;
window.startAnimation = () => window.StepTutor?.solve(window.StepTutor.getState().draftProblem);
window.handleLogin = Auth.handleLogin;
window.handleRegister = Auth.handleRegister;
window.refreshCaptcha = Auth.refreshCaptcha;
window.logout = Auth.logout;
window.Settings = Settings;
window.openSettings = Settings.openSettings;
window.closeSettings = () => UI.toggleModal('settings-modal', false);
window.startRecording = Settings.startRecording;
window.resetDefaults = Settings.resetDefaults;
    window.startTutorial = Tutorial.startTutorial;
    window.startRoleGuide = Tutorial.startRoleGuide;

// 新增挂载
window.openEditModal = Formulas.openEditModal;
window.closeEditModal = Formulas.closeEditModal;
window.submitFormulaEdit = Formulas.submitFormulaEdit;
window.Formulas = Formulas;
window.Calculate = window.Calculate || {};
window.Calculate.saveLastCodeToScripts = Calculate.saveLastCodeToScripts;
window.submitCalcScriptNote = (note) => Calculate.submitSaveScriptNote(note);


document.addEventListener('DOMContentLoaded', () => {
    // ... (其他初始化)
    Calculate.initCalculateListeners(); // 初始化 MathLive 监听
});

// ... (其他挂载)

// 挂载 Calculate 新增函数
window.startAnimation = () => window.StepTutor?.solve(window.StepTutor.getState().draftProblem);
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
    window.StepTutor?.prefill(latex);
};


// 挂载 Examples 函数
window.playExample = Examples.playExample;
window.closeVideoModal = Examples.closeVideoModal;
window.loadExamples = Examples.loadExamples;
window.Examples = Examples;

// --- Docs 挂载 ---
window.openDoc = Docs.openDoc;
window.closeDocsModal = Docs.closeDocsModal;

// 挂载移动端函数
window.toggleMobileMenu = UI.toggleMobileMenu;
window.mobileNavClick = UI.mobileNavClick;

// 挂载自定义对话框（替换原生 alert/confirm/prompt）
window.showAlert = UI.showAlert;
window.showConfirm = UI.showConfirm;
window.showPrompt = UI.showPrompt;

// 挂载切换函数给 HTML 按钮使用
window.toggleTheme = Theme.toggleTheme;
window.toggleModal = UI.toggleModal;

// 挂载全局 开发者工具（inline onclick 需用 DevTools.xxx）
window.DevTools = DevTools;
// 不覆盖 window.Agent：agent.js 已自行挂载可扩展的 window.Agent 及 openTemplatesModal 等（若写 window.Agent = Agent 会变成只读的模块命名空间，无法添加方法）
window.switchDevTool = DevTools.switchDevTool;
window.runDevManim = DevTools.runDevManim;
window.copyDevLatex = DevTools.copyDevLatex;
window.openManimWorkbenchWithCode = DevTools.openManimWorkbenchWithCode;
