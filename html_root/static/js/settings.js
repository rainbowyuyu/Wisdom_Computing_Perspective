// static/js/settings.js

import { toggleModal, showToast } from './ui.js';
import * as Profile from './profile.js';
import { canUseAccountFeatures } from './account-session.js';

const SETTINGS_STORAGE_KEY = 'app_settings';
let saveToServerTimer = null;
const SAVE_DEBOUNCE_MS = 800;

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

const AGENT_ENTER_SEND_KEY = 'agent_enter_send';
const DETECT_DEFAULT_INPUT_KEY = 'detect_default_input';
const CALC_DEFAULT_MODE_KEY = 'calc_default_mode';
/** 数学表达式字号（rem），默认 1.1（小字号便于看全长题） */
const CALC_MATH_FONT_SIZE_KEY = 'calc_math_font_size';
const CALC_MATH_FONT_SIZE_MIN = 0.8;
const CALC_MATH_FONT_SIZE_MAX = 2.2;
const CALC_MATH_FONT_SIZE_DEFAULT = 1.1;
const DEVTOOLS_DEFAULT_TAB_KEY = 'devtools_default_tab';
/** 手机版锁定画板：开启后画板区域仅可滑动不可书写 */
export const CANVAS_LOCK_MOBILE_KEY = 'canvas_lock_mobile';
/** 主页Hero文字效果模式：'gradient' 动态渐变，'interaction' 抖动交互 */
export const HERO_EFFECT_MODE_KEY = 'hero_effect_mode';

export function getAgentEnterSend() {
    try {
        const v = localStorage.getItem(AGENT_ENTER_SEND_KEY);
        return v === null || v === 'true';
    } catch (_) { return true; }
}

export function setAgentEnterSend(value) {
    try {
        localStorage.setItem(AGENT_ENTER_SEND_KEY, value ? 'true' : 'false');
        persistAfterChange();
    } catch (_) {}
}

export function getDetectDefaultInput() {
    const v = localStorage.getItem(DETECT_DEFAULT_INPUT_KEY);
    return v === 'upload' ? 'upload' : 'draw';
}
export function setDetectDefaultInput(value) {
    localStorage.setItem(DETECT_DEFAULT_INPUT_KEY, value === 'upload' ? 'upload' : 'draw');
    persistAfterChange();
}

export function getCalcDefaultMode() {
    const v = localStorage.getItem(CALC_DEFAULT_MODE_KEY);
    return v || 'normal';
}
export function setCalcDefaultMode(value) {
    const allowed = ['normal', 'formular', 'visualization', 'solution'];
    localStorage.setItem(CALC_DEFAULT_MODE_KEY, allowed.includes(value) ? value : 'normal');
    persistAfterChange();
}

export function getCalcMathFontSize() {
    const v = parseFloat(localStorage.getItem(CALC_MATH_FONT_SIZE_KEY), 10);
    if (Number.isFinite(v) && v >= CALC_MATH_FONT_SIZE_MIN && v <= CALC_MATH_FONT_SIZE_MAX) return v;
    return CALC_MATH_FONT_SIZE_DEFAULT;
}
export function setCalcMathFontSize(value) {
    const n = Number(value);
    const clamped = Number.isFinite(n)
        ? Math.max(CALC_MATH_FONT_SIZE_MIN, Math.min(CALC_MATH_FONT_SIZE_MAX, n))
        : CALC_MATH_FONT_SIZE_DEFAULT;
    localStorage.setItem(CALC_MATH_FONT_SIZE_KEY, String(clamped));
    persistAfterChange();
}

/** 将数学表达式字号应用到页面 #math-field-main（若存在） */
export function applyCalcMathFontSizeToPage() {
    document.documentElement.style.setProperty('--math-reading-size',getCalcMathFontSize()+'rem');
}

export function getDevtoolsDefaultTab() {
    const v = localStorage.getItem(DEVTOOLS_DEFAULT_TAB_KEY);
    return v === 'latex' || v === 'manim' || v === 'rainbow' ? v : 'manim';
}
export function setDevtoolsDefaultTab(value) {
    const allowed = ['latex', 'manim', 'rainbow'];
    localStorage.setItem(DEVTOOLS_DEFAULT_TAB_KEY, allowed.includes(value) ? value : 'manim');
    persistAfterChange();
}

export function getCanvasLockMobile() {
    try {
        return localStorage.getItem(CANVAS_LOCK_MOBILE_KEY) === 'true';
    } catch (_) { return false; }
}
export function setCanvasLockMobile(value) {
    try {
        localStorage.setItem(CANVAS_LOCK_MOBILE_KEY, value ? 'true' : 'false');
        persistAfterChange();
    } catch (_) {}
}

/** 教学案例弹幕设置 */
const DANMAKU_ENABLED_KEY = 'danmaku_enabled';
const DANMAKU_OPACITY_KEY = 'danmaku_opacity';
const DANMAKU_FONT_SIZE_KEY = 'danmaku_font_size';
const DANMAKU_SCREEN_KEY = 'danmaku_screen';

export function getDanmakuEnabled() {
    try {
        return localStorage.getItem(DANMAKU_ENABLED_KEY) !== 'false';
    } catch (_) { return true; }
}
export function setDanmakuEnabled(value) {
    try {
        localStorage.setItem(DANMAKU_ENABLED_KEY, value ? 'true' : 'false');
        persistAfterChange();
    } catch (_) {}
}

export function getDanmakuOpacity() {
    const v = parseInt(localStorage.getItem(DANMAKU_OPACITY_KEY), 10);
    return (Number.isFinite(v) && v >= 30 && v <= 100) ? v / 100 : 0.9;
}
export function setDanmakuOpacity(value) {
    const n = Math.min(100, Math.max(30, parseInt(value, 10) || 90));
    localStorage.setItem(DANMAKU_OPACITY_KEY, String(n));
    const el = document.getElementById('settings-danmaku-opacity');
    if (el) el.value = n;
    const label = document.getElementById('settings-danmaku-opacity-value');
    if (label) label.textContent = n;
    persistAfterChange();
}

export function getDanmakuFontSize() {
    const v = localStorage.getItem(DANMAKU_FONT_SIZE_KEY);
    return (v === 'small' || v === 'large') ? v : 'medium';
}
export function setDanmakuFontSize(value) {
    const v = (value === 'small' || value === 'large') ? value : 'medium';
    localStorage.setItem(DANMAKU_FONT_SIZE_KEY, v);
    ['small', 'medium', 'large'].forEach(s => {
        const el = document.getElementById('danmaku-size-' + s);
        if (el) el.checked = (s === v);
    });
    persistAfterChange();
}

const DANMAKU_SCREEN_VALUES = ['full', 'half', 'quarter'];
export function getDanmakuScreen() {
    const v = localStorage.getItem(DANMAKU_SCREEN_KEY);
    return DANMAKU_SCREEN_VALUES.includes(v) ? v : 'full';
}
export function setDanmakuScreen(value) {
    const v = DANMAKU_SCREEN_VALUES.includes(value) ? value : 'full';
    localStorage.setItem(DANMAKU_SCREEN_KEY, v);
    DANMAKU_SCREEN_VALUES.forEach(mode => {
        const el = document.getElementById('danmaku-screen-' + mode);
        if (el) el.checked = (mode === v);
    });
    persistAfterChange();
}

export function getHeroEffectMode() {
    const v = localStorage.getItem(HERO_EFFECT_MODE_KEY);
    return v === 'gradient' ? 'gradient' : 'interaction'; // 默认为抖动交互
}
export function setHeroEffectMode(value) {
    const allowed = ['gradient', 'interaction'];
    const mode = allowed.includes(value) ? value : 'interaction';
    localStorage.setItem(HERO_EFFECT_MODE_KEY, mode);
    persistAfterChange();
    
    // 更新UI选择状态
    syncHeroEffectMode();
    
    // 触发重新初始化Hero效果
    if (window.initHeroTextGlow) {
        setTimeout(() => {
            window.initHeroTextGlow();
        }, 100);
    }
}

/** 从本地组装完整设置（供保存到云端与恢复用） */
export function getFullSettings() {
    const theme = localStorage.getItem('theme') || 'light';
    const agentEnterSend = getAgentEnterSend();
    const appShortcuts = localStorage.getItem('app_shortcuts');
    let shortcuts = JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));
    try {
        if (appShortcuts) Object.assign(shortcuts, JSON.parse(appShortcuts));
    } catch (_) {}
    const payload = {
        theme,
        agent_enter_send: agentEnterSend,
        shortcuts,
        detect_default_input: getDetectDefaultInput(),
        calc_default_mode: getCalcDefaultMode(),
        calc_math_font_size: getCalcMathFontSize(),
        devtools_default_tab: getDevtoolsDefaultTab(),
        canvas_lock_mobile: getCanvasLockMobile(),
        hero_effect_mode: getHeroEffectMode(),
        danmaku_enabled: getDanmakuEnabled(),
        danmaku_opacity: getDanmakuOpacity(),
        danmaku_font_size: getDanmakuFontSize(),
        danmaku_screen: getDanmakuScreen()
    };
    try {
        const extra = JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY) || '{}');
        Object.assign(payload, extra);
    } catch (_) {}
    return payload;
}

/** 应用一批设置到页面并写入本地（登录后加载云端用） */
export function applySettings(obj) {
    if (!obj || typeof obj !== 'object') return;
    try {
        if (obj.theme === 'dark' || obj.theme === 'light') {
            localStorage.setItem('theme', obj.theme);
            document.documentElement.setAttribute('data-theme', obj.theme);
            const icon = document.getElementById('theme-toggle-icon');
            if (icon) icon.className = obj.theme === 'dark' ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
            window.dispatchEvent(new CustomEvent('theme-change', { detail: obj.theme }));
        }
        if (typeof obj.agent_enter_send === 'boolean') {
            localStorage.setItem(AGENT_ENTER_SEND_KEY, obj.agent_enter_send ? 'true' : 'false');
            const cb = document.getElementById('agent-enter-send');
            if (cb) cb.checked = obj.agent_enter_send;
        }
        if (obj.shortcuts && typeof obj.shortcuts === 'object') {
            Object.keys(DEFAULT_SHORTCUTS).forEach(k => {
                if (obj.shortcuts[k] && typeof obj.shortcuts[k] === 'object') shortcuts[k] = obj.shortcuts[k];
            });
            localStorage.setItem('app_shortcuts', JSON.stringify(shortcuts));
            updateShortcutDisplay();
        }
        if (obj.detect_default_input === 'draw' || obj.detect_default_input === 'upload') {
            localStorage.setItem(DETECT_DEFAULT_INPUT_KEY, obj.detect_default_input);
            const sel = document.getElementById('settings-detect-default-input');
            if (sel) sel.value = obj.detect_default_input;
        }
        if (['normal', 'formular', 'visualization', 'solution'].includes(obj.calc_default_mode)) {
            localStorage.setItem(CALC_DEFAULT_MODE_KEY, obj.calc_default_mode);
            syncCalcDefaultMode();
        }
        if (typeof obj.calc_math_font_size === 'number' && obj.calc_math_font_size >= CALC_MATH_FONT_SIZE_MIN && obj.calc_math_font_size <= CALC_MATH_FONT_SIZE_MAX) {
            localStorage.setItem(CALC_MATH_FONT_SIZE_KEY, String(obj.calc_math_font_size));
            syncCalcMathFontSize();
        }
        if (['latex', 'manim', 'rainbow'].includes(obj.devtools_default_tab)) {
            localStorage.setItem(DEVTOOLS_DEFAULT_TAB_KEY, obj.devtools_default_tab);
            const sel = document.getElementById('settings-devtools-default-tab');
            if (sel) sel.value = obj.devtools_default_tab;
        }
        if (obj.hero_gradient_mode === 'static' || obj.hero_gradient_mode === 'dynamic') {
            localStorage.setItem(HERO_GRADIENT_MODE_KEY, obj.hero_gradient_mode);
            const sel = document.getElementById('settings-hero-gradient-mode');
            if (sel) sel.value = obj.hero_gradient_mode;
        }
        if (typeof obj.hero_interaction_enabled === 'boolean') {
            localStorage.setItem(HERO_INTERACTION_ENABLED_KEY, obj.hero_interaction_enabled ? 'true' : 'false');
            const cb = document.getElementById('settings-hero-interaction-enabled');
            if (cb) cb.checked = obj.hero_interaction_enabled;
        }
        if (typeof obj.canvas_lock_mobile === 'boolean') {
            localStorage.setItem(CANVAS_LOCK_MOBILE_KEY, obj.canvas_lock_mobile ? 'true' : 'false');
            const cb = document.getElementById('settings-canvas-lock-mobile');
            if (cb) cb.checked = obj.canvas_lock_mobile;
        }
        if (obj.hero_effect_mode === 'gradient' || obj.hero_effect_mode === 'interaction') {
            localStorage.setItem(HERO_EFFECT_MODE_KEY, obj.hero_effect_mode);
            const sel = document.getElementById('settings-hero-effect-mode');
            if (sel) sel.value = obj.hero_effect_mode;
            if (window.initHeroTextGlow) setTimeout(() => window.initHeroTextGlow(), 100);
        }
        if (typeof obj.danmaku_enabled === 'boolean') {
            localStorage.setItem(DANMAKU_ENABLED_KEY, obj.danmaku_enabled ? 'true' : 'false');
            const cb = document.getElementById('settings-danmaku-enabled');
            if (cb) cb.checked = obj.danmaku_enabled;
        }
        if (typeof obj.danmaku_opacity === 'number' && obj.danmaku_opacity >= 0 && obj.danmaku_opacity <= 1) {
            const n = Math.round(obj.danmaku_opacity * 100);
            localStorage.setItem(DANMAKU_OPACITY_KEY, String(n));
            const el = document.getElementById('settings-danmaku-opacity');
            if (el) el.value = n;
            const label = document.getElementById('settings-danmaku-opacity-value');
            if (label) label.textContent = n;
        }
        if (obj.danmaku_font_size === 'small' || obj.danmaku_font_size === 'medium' || obj.danmaku_font_size === 'large') {
            localStorage.setItem(DANMAKU_FONT_SIZE_KEY, obj.danmaku_font_size);
            ['small', 'medium', 'large'].forEach(s => {
                const el = document.getElementById('danmaku-size-' + s);
                if (el) el.checked = (s === obj.danmaku_font_size);
            });
        }
        if (DANMAKU_SCREEN_VALUES.includes(obj.danmaku_screen)) {
            localStorage.setItem(DANMAKU_SCREEN_KEY, obj.danmaku_screen);
            setDanmakuScreen(obj.danmaku_screen);
        }
        const { theme, agent_enter_send, shortcuts: _, detect_default_input, calc_default_mode, calc_math_font_size: _cf, devtools_default_tab, canvas_lock_mobile, hero_effect_mode, danmaku_enabled, danmaku_opacity, danmaku_font_size, danmaku_screen, ...rest } = obj;
        if (Object.keys(rest).length > 0) {
            const extra = JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY) || '{}');
            Object.assign(extra, rest);
            localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(extra));
        }
    } catch (e) {
        console.warn('applySettings', e);
    }
}

/**
 * 应用单条设置（供智能体调用）
 * @param {string} key - 设置键，见 SETTINGS_AGENT_KEYS
 * @param {string|number|boolean} value - 设置值（会做类型转换）
 * @returns {boolean} 是否成功应用
 */
export function applySingleSetting(key, value) {
    if (!key || typeof key !== 'string') return false;
    const k = key.trim();
    let v = value;
    const boolKeys = ['agent_enter_send', 'canvas_lock_mobile', 'danmaku_enabled'];
    if (boolKeys.includes(k)) {
        v = v === true || v === 'true' || v === 1 || v === '1';
    }
    if (k === 'calc_math_font_size' || k === 'danmaku_opacity') {
        const n = typeof v === 'number' ? v : parseFloat(v);
        if (k === 'danmaku_opacity' && Number.isFinite(n)) v = n <= 1 ? n : n / 100;
        else if (k === 'calc_math_font_size') v = n;
    }
    try {
        applySettings({ [k]: v });
        return true;
    } catch (_) {
        return false;
    }
}

/** 延迟上报到云端（已登录时） */
export function persistAfterChange() {
    if (saveToServerTimer) clearTimeout(saveToServerTimer);
    saveToServerTimer = setTimeout(saveSettingsToServer, SAVE_DEBOUNCE_MS);
}

/** 仅内部/防抖用：上报到云端，返回是否成功 */
async function saveSettingsToServer() {
    try {
        const res = await fetch('/api/user/me', { credentials: 'include' });
        // 401 是未登录的正常状态，静默处理
        if (res.status === 401 || !res.ok) return false;
        const me = await res.json();
        if (me.status !== 'success' || !me.username) return false;
        const settings = getFullSettings();
        const settingsRes = await fetch('/api/user/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ settings }),
            credentials: 'include'
        });
        const data = await settingsRes.json();
        return data.status === 'success';
    } catch (_) {
        return false;
    }
}

/** 用户点击「保存」：未登录则引导登录，已登录则立即同步到账号 */
export async function saveSettingsToAccount() {
    try {
        const res = await fetch('/api/user/me', { credentials: 'include' });
        // 401 是未登录的正常状态
        if (res.status === 401 || !res.ok) {
            if (typeof showToast === 'function') showToast('请登录后再保存到账号', 'info');
            if (typeof window.toggleAuthModal === 'function') window.toggleAuthModal(true);
            return;
        }
        const me = await res.json();
        if (me.status !== 'success' || !me.username) {
            if (typeof showToast === 'function') showToast('请登录后再保存到账号', 'info');
            if (typeof window.toggleAuthModal === 'function') window.toggleAuthModal(true);
            return;
        }
        const ok = await saveSettingsToServer();
        if (typeof showToast === 'function') {
            showToast(ok ? '已保存到账号' : '保存失败，请重试', ok ? 'success' : 'error');
        }
    } catch (_) {
        if (typeof showToast === 'function') showToast('网络错误', 'error');
    }
}

/** 登录后调用：拉取云端设置并应用到页面与本地 */
export async function loadUserSettings() {
    try {
        if (!await canUseAccountFeatures()) return;
        const res = await fetch('/api/user/settings', { credentials: 'include' });
        const data = await res.json();
        if (data.status === 'success' && data.settings && typeof data.settings === 'object') {
            applySettings(data.settings);
            updateShortcutDisplay();
            syncAgentEnterSendCheckbox();
            syncHeroEffectMode();
        }
    } catch (e) {
        console.warn('loadUserSettings', e);
    }
}

function syncDetectDefaultInput() {
    const value = getDetectDefaultInput();
    const drawRadio = document.getElementById('detect-input-draw');
    const uploadRadio = document.getElementById('detect-input-upload');
    
    if (drawRadio) drawRadio.checked = (value === 'draw');
    if (uploadRadio) uploadRadio.checked = (value === 'upload');
    
    // 更新卡片选中状态
    const drawCard = drawRadio?.closest('.settings-select-card');
    const uploadCard = uploadRadio?.closest('.settings-select-card');
    if (drawCard) drawCard.classList.toggle('selected', value === 'draw');
    if (uploadCard) uploadCard.classList.toggle('selected', value === 'upload');
}

function syncHeroEffectMode() {
    const mode = getHeroEffectMode();
    // 更新卡片式选择器
    const gradientCard = document.getElementById('hero-effect-gradient');
    const interactionCard = document.getElementById('hero-effect-interaction');
    const gradientCardEl = document.getElementById('hero-effect-gradient-card');
    const interactionCardEl = document.getElementById('hero-effect-interaction-card');
    
    if (gradientCard) gradientCard.checked = (mode === 'gradient');
    if (interactionCard) interactionCard.checked = (mode === 'interaction');
    
    // 更新卡片选中状态
    if (gradientCardEl) {
        gradientCardEl.classList.toggle('selected', mode === 'gradient');
    }
    if (interactionCardEl) {
        interactionCardEl.classList.toggle('selected', mode === 'interaction');
    }
    
    // 更新预览
    updateHeroEffectPreview(mode);
}

function updateHeroEffectPreview(mode) {
    const preview = document.getElementById('hero-effect-preview');
    if (!preview) return;
    
    preview.className = 'settings-preview-box preview-hero-text';
    
    if (mode === 'gradient') {
        preview.classList.add('gradient-preview');
        // 恢复原始文本（移除字符拆分）
        const text = '让数学计算 看得见、摸得着';
        preview.innerHTML = `<span>${text}</span>`;
    } else if (mode === 'interaction') {
        preview.classList.add('interaction-preview');
        // 拆分文字为字符，用于抖动效果预览
        const text = '让数学计算 看得见、摸得着';
        const chars = text.split('');
        preview.innerHTML = chars.map((char, index) => {
            if (char === ' ') {
                return '<span class="preview-char" style="display: inline-block; width: 0.3em;">&nbsp;</span>';
            }
            return `<span class="preview-char">${char}</span>`;
        }).join('');
    }
}

// 为卡片式选择器添加点击事件处理
function initSelectCards() {
    // 主页文字效果卡片
    const heroCards = document.querySelectorAll('#hero-effect-gradient-card, #hero-effect-interaction-card');
    heroCards.forEach(card => {
        card.addEventListener('click', function(e) {
            const radio = this.querySelector('input[type="radio"]');
            if (radio && !radio.checked) {
                radio.checked = true;
                radio.dispatchEvent(new Event('change'));
            }
        });
    });
    
    // 识别页默认输入卡片
    const detectCards = document.querySelectorAll('[name="detect-default-input"]');
    detectCards.forEach(radio => {
        radio.addEventListener('change', function() {
            const card = this.closest('.settings-select-card');
            document.querySelectorAll('[name="detect-default-input"]').forEach(r => {
                const c = r.closest('.settings-select-card');
                if (c) c.classList.remove('selected');
            });
            if (card) card.classList.add('selected');
        });
    });
    
    // 动态计算模式卡片
    const calcCards = document.querySelectorAll('[name="calc-default-mode"]');
    calcCards.forEach(radio => {
        radio.addEventListener('change', function() {
            const card = this.closest('.settings-select-card');
            document.querySelectorAll('[name="calc-default-mode"]').forEach(r => {
                const c = r.closest('.settings-select-card');
                if (c) c.classList.remove('selected');
            });
            if (card) card.classList.add('selected');
        });
    });
    
    // 开发者工具标签卡片
    const devtoolsCards = document.querySelectorAll('[name="devtools-default-tab"]');
    devtoolsCards.forEach(radio => {
        radio.addEventListener('change', function() {
            const card = this.closest('.settings-select-card');
            document.querySelectorAll('[name="devtools-default-tab"]').forEach(r => {
                const c = r.closest('.settings-select-card');
                if (c) c.classList.remove('selected');
            });
            if (card) card.classList.add('selected');
        });
    });
}
function syncCalcDefaultMode() {
    const value = getCalcDefaultMode();
    const normalRadio = document.getElementById('calc-mode-normal');
    const formularRadio = document.getElementById('calc-mode-formular');
    const visualizationRadio = document.getElementById('calc-mode-visualization');
    const solutionRadio = document.getElementById('calc-mode-solution');

    if (normalRadio) normalRadio.checked = (value === 'normal');
    if (formularRadio) formularRadio.checked = (value === 'formular');
    if (visualizationRadio) visualizationRadio.checked = (value === 'visualization');
    if (solutionRadio) solutionRadio.checked = (value === 'solution');

    // 同步计算页下拉框（状态栏）
    const calcMethodSelect = document.getElementById('calc-method');
    if (calcMethodSelect && ['normal', 'formular', 'visualization', 'solution'].includes(value)) {
        calcMethodSelect.value = value;
    }

    // 更新卡片选中状态
    [normalRadio, formularRadio, visualizationRadio, solutionRadio].forEach(radio => {
        if (radio) {
            const card = radio.closest('.settings-select-card');
            if (card) card.classList.toggle('selected', radio.checked);
        }
    });
}

function syncCalcMathFontSize() {
    const value = getCalcMathFontSize();
    const slider = document.getElementById('settings-calc-math-font-size');
    const valueEl = document.getElementById('settings-calc-math-font-size-value');
    if (slider) slider.value = value;
    if (valueEl) valueEl.textContent = String(value);
    applyCalcMathFontSizeToPage();
}

/** 设置页「数学表达式字号」滑块变更时调用 */
export function onCalcMathFontSizeChange(sliderEl) {
    const v = parseFloat(sliderEl?.value, 10);
    if (!Number.isFinite(v)) return;
    setCalcMathFontSize(v);
    const valueEl = document.getElementById('settings-calc-math-font-size-value');
    if (valueEl) valueEl.textContent = String(getCalcMathFontSize());
    applyCalcMathFontSizeToPage();
}

function syncDevtoolsDefaultTab() {
    const value = getDevtoolsDefaultTab();
    const latexRadio = document.getElementById('devtools-tab-latex');
    const manimRadio = document.getElementById('devtools-tab-manim');
    const rainbowRadio = document.getElementById('devtools-tab-rainbow');
    
    if (latexRadio) latexRadio.checked = (value === 'latex');
    if (manimRadio) manimRadio.checked = (value === 'manim');
    if (rainbowRadio) rainbowRadio.checked = (value === 'rainbow');
    
    // 更新卡片选中状态
    [latexRadio, manimRadio, rainbowRadio].forEach(radio => {
        if (radio) {
            const card = radio.closest('.settings-select-card');
            if (card) card.classList.toggle('selected', radio.checked);
        }
    });
}
function syncCanvasLockMobileCheckbox() {
    const cb = document.getElementById('settings-canvas-lock-mobile');
    if (cb) cb.checked = getCanvasLockMobile();
}

const SETTINGS_SECTION_IDS = ['settings-appearance', 'settings-profile', 'settings-agent', 'settings-detect', 'settings-shortcuts', 'settings-calc', 'settings-devtools', 'settings-examples'];

function syncDanmakuSettings() {
    const cb = document.getElementById('settings-danmaku-enabled');
    if (cb) cb.checked = getDanmakuEnabled();
    const opacityVal = Math.round(getDanmakuOpacity() * 100);
    const opacityEl = document.getElementById('settings-danmaku-opacity');
    if (opacityEl) opacityEl.value = opacityVal;
    const opacityLabel = document.getElementById('settings-danmaku-opacity-value');
    if (opacityLabel) opacityLabel.textContent = opacityVal;
    const size = getDanmakuFontSize();
    ['small', 'medium', 'large'].forEach(s => {
        const el = document.getElementById('danmaku-size-' + s);
        if (el) el.checked = (s === size);
    });
    const screen = getDanmakuScreen();
    DANMAKU_SCREEN_VALUES.forEach(mode => {
        const el = document.getElementById('danmaku-screen-' + mode);
        if (el) el.checked = (screen === mode);
    });
}

function initSettingsNav() {
    const container = document.getElementById('settings-scroll-container');
    const nav = document.getElementById('settings-nav');
    if (!container || !nav) return;

    nav.querySelectorAll('.settings-nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const id = item.getAttribute('data-section');
            const el = document.getElementById(id);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                setSettingsNavActive(id);
            }
        });
    });

    let ticking = false;
    container.addEventListener('scroll', () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            const sections = SETTINGS_SECTION_IDS.map(id => document.getElementById(id)).filter(Boolean);
            const top = container.scrollTop;
            const viewMid = top + container.clientHeight / 3;
            let activeId = SETTINGS_SECTION_IDS[0];
            for (const el of sections) {
                if (el.offsetTop <= viewMid) activeId = el.id;
            }
            setSettingsNavActive(activeId);
            ticking = false;
        });
    });
}

function setSettingsNavActive(sectionId) {
    const nav = document.getElementById('settings-nav');
    if (!nav) return;
    nav.querySelectorAll('.settings-nav-item').forEach(item => {
        item.classList.toggle('active', item.getAttribute('data-section') === sectionId);
    });
}

function updateSettingsFooterHint() {
    const hint = document.getElementById('settings-footer-hint');
    const welcome = document.getElementById('settings-welcome');
    if (!hint) return;
    fetch('/api/user/me', { credentials: 'include' })
        .then(r => {
            // 401 是未登录的正常状态，静默处理
            if (r.status === 401 || !r.ok) {
                hint.textContent = '当前仅本地生效，登录后可保存到账号';
                if (welcome) welcome.style.display = 'none';
                return null;
            }
            return r.json();
        })
        .then(data => {
            if (data && data.status === 'success' && data.username) {
                hint.textContent = '设置已自动保存并同步到账号';
                if (welcome) {
                    welcome.textContent = '欢迎，' + data.username;
                    welcome.style.display = '';
                }
            } else {
                hint.textContent = '当前仅本地生效，登录后可保存到账号';
                if (welcome) welcome.style.display = 'none';
            }
        })
        .catch(() => {
            hint.textContent = '当前仅本地生效，登录后可保存到账号';
            if (welcome) welcome.style.display = 'none';
        });
}

export function initSettings() {
    renderShortcutsList();
    updateShortcutDisplay();
    syncAgentEnterSendCheckbox();
    syncDetectDefaultInput();
    syncCalcDefaultMode();
    syncCalcMathFontSize();
    syncDevtoolsDefaultTab();
    syncHeroEffectMode();
    syncDetectDefaultInput();
    syncCalcDefaultMode();
    syncDevtoolsDefaultTab();
    syncCanvasLockMobileCheckbox();
    loadVersionFromUpdate();
    initSettingsNav();
    initSelectCards();
    window.addEventListener('settings-changed', persistAfterChange);
}

export function onOpenSettings() {
    updateSettingsFooterHint();
    if (typeof Profile.loadProfile === 'function') Profile.loadProfile();
}

function syncAgentEnterSendCheckbox() {
    const cb = document.getElementById('agent-enter-send');
    if (cb) cb.checked = getAgentEnterSend();
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
    syncAgentEnterSendCheckbox();
    syncDetectDefaultInput();
    syncCalcDefaultMode();
    syncCalcMathFontSize();
    syncDevtoolsDefaultTab();
    syncHeroEffectMode();
    syncDanmakuSettings();
    syncCanvasLockMobileCheckbox();
    onOpenSettings();
    toggleModal('settings-modal', true);
    const scrollMap = { appearance: 'settings-appearance', shortcuts: 'settings-shortcuts', agent: 'settings-agent', detect: 'settings-detect', calc: 'settings-calc', devtools: 'settings-devtools', profile: 'settings-profile', examples: 'settings-examples' };
    if (scrollMap[anchor]) {
        requestAnimationFrame(() => {
            const sectionId = scrollMap[anchor];
            const el = document.getElementById(sectionId);
            if (el) {
                el.scrollIntoView({ block: 'start', behavior: 'smooth' });
                setSettingsNavActive(sectionId);
            }
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
        persistAfterChange();
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
    updatePageShortcutHints();
}

/** 更新页面中带 data-shortcut 的按钮的 title（小括号内显示当前快捷键） */
function updatePageShortcutHints() {
    document.querySelectorAll('[data-shortcut]').forEach(el => {
        const action = el.getAttribute('data-shortcut');
        const label = SHORTCUT_LABELS[action];
        const cfg = shortcuts[action] || DEFAULT_SHORTCUTS[action];
        if (label && cfg) {
            el.setAttribute('title', label + ' (' + formatShortcut(cfg) + ')');
        }
    });
}
export function resetDefaults() {
    shortcuts = JSON.parse(JSON.stringify(DEFAULT_SHORTCUTS));
    localStorage.setItem('app_shortcuts', JSON.stringify(shortcuts));
    setAgentEnterSend(true);
    localStorage.setItem(DETECT_DEFAULT_INPUT_KEY, 'draw');
    localStorage.setItem(CALC_DEFAULT_MODE_KEY, 'normal');
    localStorage.setItem(CALC_MATH_FONT_SIZE_KEY, String(CALC_MATH_FONT_SIZE_DEFAULT));
    localStorage.setItem(DEVTOOLS_DEFAULT_TAB_KEY, 'manim');
    setCanvasLockMobile(false);
    updateShortcutDisplay();
    syncAgentEnterSendCheckbox();
    syncDetectDefaultInput();
    syncCalcDefaultMode();
    syncCalcMathFontSize();
    syncDevtoolsDefaultTab();
    syncHeroEffectMode();
    syncDetectDefaultInput();
    syncCalcDefaultMode();
    syncDevtoolsDefaultTab();
    syncCanvasLockMobileCheckbox();
    persistAfterChange();
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
