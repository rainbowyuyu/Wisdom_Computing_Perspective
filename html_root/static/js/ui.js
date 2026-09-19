// static/js/ui.js

const MODAL_IDS = [
    'auth-modal', 'settings-modal', 'change-username-modal', 'change-password-modal',
    'agent-templates-modal', 'agent-examples-modal', 'edit-formula-modal', 'video-copy-modal',
    'script-note-modal', 'select-formula-modal', 'custom-dialog-modal',
    'script-run-modal', 'docs-modal', 'video-modal', 'image-editor-modal', 'achievement-panel-modal'
];

const modalTimers = new WeakMap();
export function toggleModal(modalId, show) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    clearTimeout(modalTimers.get(modal));

    if (show) {
        modal.style.display = 'flex';
        requestAnimationFrame(() => {
            modal.classList.add('show');
        });
    } else {
        modal.classList.remove('show');
        modalTimers.set(modal, setTimeout(() => {
            modal.style.display = 'none';
            if(modalId==='auth-modal')window.dispatchEvent(new Event('auth-dialog-closed'));
        }, 300));
    }
}

/** 关闭所有已打开的弹窗 */
export function closeAllModals() {
    MODAL_IDS.forEach(id => toggleModal(id, false));
}

/** 按 ESC 关闭最顶层弹窗（若有多层则逐个关闭） */
export function initModalEscHandler() {
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || document.querySelector('dialog[open]')) return;
        const visible = MODAL_IDS.map(id => document.getElementById(id)).filter(m => m && m.classList.contains('show'));
        if (visible.length) {
            e.preventDefault();
            const top = visible[visible.length - 1];
            toggleModal(top.id, false);
        }
    });
}

export function showSection(sectionId) {
    if(sectionId!=='examples'&&document.getElementById('video-modal')?.classList.contains('show'))window.closeVideoModal?.();
    document.querySelectorAll('.section').forEach(sec => sec.classList.remove('active-section'));
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));

    // 若传入的 sectionId 无法在页面中找到，对应 section 将找不到，导致整页空白。
    // 为了增强容错，这里增加「兜底到首页」的逻辑：当找不到目标 section 时，退回到 home。
    let effectiveId = sectionId;
    let target = document.getElementById(sectionId);
    if (!target) {
        const homeSection = document.getElementById('home');
        if (homeSection) {
            target = homeSection;
            effectiveId = 'home';
        }
    }
    if (target) target.classList.add('active-section');

    // 高亮导航按钮（使用有效的 section id）
    const navBtns = document.querySelectorAll('.nav-btn');
    navBtns.forEach(btn => {
        const onclickVal = btn.getAttribute('onclick');
        if (onclickVal && onclickVal.includes(`'${effectiveId}'`)) {
            btn.classList.add('active');
        }
    });

    // --- 新增：切换页面时强制关闭 MathLive 虚拟键盘 ---
    if (window.mathVirtualKeyboard) {
        window.mathVirtualKeyboard.hide();
    }
}

// static/js/ui.js

export function toggleAuthModal(show) {
    const modal = document.getElementById('auth-modal');
    if (!modal) return;
    if(show && modal.dataset.requiresVerify==='true')switchAuthMode('verify');
    toggleModal('auth-modal', show);
}

// ... 其他函数保持不变 ...
export function switchAuthMode(mode) {
    if(document.getElementById('auth-modal')?.dataset.requiresVerify==='true')mode='verify';
    const loginForm = document.getElementById('login-form');
    const regForm = document.getElementById('register-form');
    const forgotForm = document.getElementById('forgot-form');
    const verifyForm = document.getElementById('email-verify-form');
    const tabs = document.querySelectorAll('.auth-tab');

    tabs.forEach(t => t.classList.remove('active'));
    [loginForm, regForm, forgotForm, verifyForm].forEach(form => { if (form) form.style.display = 'none'; });
    if(mode === 'register') { regForm.style.display = 'block'; tabs[1]?.classList.add('active'); }
    else if(mode === 'forgot') { forgotForm.style.display = 'block'; }
    else if(mode === 'verify') { verifyForm.style.display = 'block'; }
    else { loginForm.style.display = 'block'; tabs[0]?.classList.add('active'); }
    if (window.refreshCaptcha && ['login','register','forgot'].includes(mode)) window.refreshCaptcha(mode);
}
// ...

// 切换 手写/上传 模式
export function switchInputMode(mode) {
    const drawTools = document.getElementById('draw-tools');
    const uploadTools = document.getElementById('upload-tools');
    const canvas = document.getElementById('drawing-board');
    const preview = document.getElementById('uploaded-preview');

    // 1. 切换 Tab 按钮高亮 (关键修复)
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(t => {
        const onclickVal = t.getAttribute('onclick');
        if(onclickVal && onclickVal.includes(`'${mode}'`)) {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });

    // 2. 切换显示区域
    const canvasHint = document.getElementById('canvas-hint');
    
    if(mode === 'draw') {
        if(drawTools) drawTools.style.display = 'block';
        if(uploadTools) uploadTools.style.display = 'none';

        // 隐藏预览图，显示 Canvas 并恢复背景
        if(preview) preview.style.display = 'none';
        if(canvas) {
            canvas.style.display = 'block';
            window.dispatchEvent(new CustomEvent('mode-change', { detail: 'draw' }));
        }
        
        // 显示提示（仅在手写模式）
        if (canvasHint) {
            canvasHint.style.display = 'flex';
            canvasHint.style.visibility = 'visible';
            canvasHint.style.opacity = '0.95';
        }
        
        // 隐藏编辑按钮
        const editBtn = document.getElementById('canvas-edit-btn');
        if (editBtn) editBtn.style.display = 'none';
    } else {
        if(drawTools) drawTools.style.display = 'none';
        // 使用 flex 以保持样式 (关键修复)
        if(uploadTools) uploadTools.style.display = 'flex';

        // 显示预览图，Canvas 保持显示但变透明（用于获取位置或作为遮罩）
        if(preview && preview.src) preview.style.display = 'block';

        if(canvas) {
            canvas.style.display = 'block';
            window.dispatchEvent(new CustomEvent('mode-change', { detail: 'upload' }));
        }
        
        // 隐藏提示（上传模式不显示）
        if (canvasHint) {
            canvasHint.style.display = 'none';
            canvasHint.style.visibility = 'hidden';
        }
        
        // 如果有图片，显示编辑按钮（使用已定义的 preview 变量）
        if (preview && preview.src) {
            const editBtn = document.getElementById('canvas-edit-btn');
            if (editBtn) editBtn.style.display = 'flex';
        }
    }
}

// --- 移动端菜单控制 ---
export function toggleMobileMenu() {
    const overlay = document.getElementById('mobile-menu-overlay');
    if (!overlay) return;

    if (overlay.style.display === 'flex') {
        overlay.classList.remove('show');
        setTimeout(() => {
            overlay.style.display = 'none';
        }, 300);
    } else {
        overlay.style.display = 'flex';
        // 强制重绘
        requestAnimationFrame(() => {
            overlay.classList.add('show');
        });
    }
}

export function mobileNavClick(sectionId) {
    // 手机版导航：优先走全局 window.showSection，这样会自动联动智算星云等全局浮动组件
    if (typeof window.showSection === 'function') {
        window.showSection(sectionId);
    } else {
        showSection(sectionId);
    }
    toggleMobileMenu(); // 点击后自动关闭菜单
}

/** 轻提示 Toast：type = 'success' | 'error' | 'info'，自动消失 */
export function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container') || (() => {
        const el = document.createElement('div');
        el.id = 'toast-container';
        document.body.appendChild(el);
        return el;
    })();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icons = {
        success: 'fa-circle-check',
        error: 'fa-circle-xmark',
        info: 'fa-circle-info'
    };
    toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info} toast-icon"></i><span class="toast-text">${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('toast-show'));

    const duration = type === 'error' ? 4500 : 3000;
    const t = setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
    toast.addEventListener('click', () => {
        clearTimeout(t);
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    });
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/** 自定义 Alert 对话框（替换原生 alert） */
export function showAlert(message, title = '提示') {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-dialog-modal');
        if (!modal) {
            console.warn('custom-dialog-modal not found, falling back to native alert');
            alert(message);
            resolve();
            return;
        }
        const titleEl = document.getElementById('custom-dialog-title');
        const messageEl = document.getElementById('custom-dialog-message');
        const inputWrap = document.getElementById('custom-dialog-input-wrap');
        const inputEl = document.getElementById('custom-dialog-input');
        const confirmBtn = document.getElementById('custom-dialog-confirm');
        const cancelBtn = document.getElementById('custom-dialog-cancel');
        const closeBtn = document.getElementById('custom-dialog-close');
        const handleClose = () => {
            toggleModal('custom-dialog-modal', false);
            resolve();
        };
        if (titleEl) titleEl.textContent = title;
        if (messageEl) {
            messageEl.textContent = message;
            messageEl.style.display = 'block';
        }
        if (inputWrap) inputWrap.style.display = 'none';
        if (confirmBtn) {
            confirmBtn.textContent = '确定';
            confirmBtn.onclick = handleClose;
        }
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (closeBtn) {
            closeBtn.onclick = handleClose;
            closeBtn.style.display = 'block';
        }
        toggleModal('custom-dialog-modal', true);
    });
}

/** 自定义 Confirm 对话框（替换原生 confirm） */
export function showConfirm(message, title = '确认') {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-dialog-modal');
        if (!modal) {
            const result = confirm(message);
            resolve(result);
            return;
        }
        const titleEl = document.getElementById('custom-dialog-title');
        const messageEl = document.getElementById('custom-dialog-message');
        const inputWrap = document.getElementById('custom-dialog-input-wrap');
        const inputEl = document.getElementById('custom-dialog-input');
        const confirmBtn = document.getElementById('custom-dialog-confirm');
        const cancelBtn = document.getElementById('custom-dialog-cancel');
        const closeBtn = document.getElementById('custom-dialog-close');
        const handleCancel = () => {
            toggleModal('custom-dialog-modal', false);
            resolve(false);
        };
        if (titleEl) titleEl.textContent = title;
        if (messageEl) {
            messageEl.textContent = message;
            messageEl.style.display = 'block';
        }
        if (inputWrap) inputWrap.style.display = 'none';
        if (confirmBtn) {
            confirmBtn.textContent = '确定';
            confirmBtn.onclick = () => {
                toggleModal('custom-dialog-modal', false);
                resolve(true);
            };
        }
        if (cancelBtn) {
            cancelBtn.style.display = 'inline-block';
            cancelBtn.onclick = handleCancel;
        }
        if (closeBtn) {
            closeBtn.onclick = handleCancel;
            closeBtn.style.display = 'block';
        }
        toggleModal('custom-dialog-modal', true);
    });
}

/** 自定义 Prompt 对话框（替换原生 prompt） */
export function showPrompt(message, defaultValue = '', title = '输入') {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-dialog-modal');
        if (!modal) {
            const result = prompt(message, defaultValue);
            resolve(result);
            return;
        }
        const titleEl = document.getElementById('custom-dialog-title');
        const messageEl = document.getElementById('custom-dialog-message');
        const inputWrap = document.getElementById('custom-dialog-input-wrap');
        const inputEl = document.getElementById('custom-dialog-input');
        const confirmBtn = document.getElementById('custom-dialog-confirm');
        const cancelBtn = document.getElementById('custom-dialog-cancel');
        const closeBtn = document.getElementById('custom-dialog-close');
        const handleCancel = () => {
            toggleModal('custom-dialog-modal', false);
            resolve(null);
        };
        if (titleEl) titleEl.textContent = title;
        if (messageEl) {
            messageEl.textContent = message;
            messageEl.style.display = 'block';
        }
        if (inputWrap) inputWrap.style.display = 'block';
        if (inputEl) {
            inputEl.value = defaultValue;
            setTimeout(() => {
                inputEl.focus();
                inputEl.select();
            }, 100);
            const handleEnter = (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    confirmBtn.click();
                }
            };
            inputEl.addEventListener('keydown', handleEnter, { once: true });
        }
        if (confirmBtn) {
            confirmBtn.textContent = '确定';
            confirmBtn.onclick = () => {
                const value = inputEl ? inputEl.value : '';
                toggleModal('custom-dialog-modal', false);
                resolve(value);
            };
        }
        if (cancelBtn) {
            cancelBtn.style.display = 'inline-block';
            cancelBtn.onclick = handleCancel;
        }
        if (closeBtn) {
            closeBtn.onclick = handleCancel;
            closeBtn.style.display = 'block';
        }
        toggleModal('custom-dialog-modal', true);
    });
}
