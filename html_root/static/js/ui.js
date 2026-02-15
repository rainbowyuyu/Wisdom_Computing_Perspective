// static/js/ui.js

export function toggleModal(modalId, show) {
    const modal = document.getElementById(modalId);
    if (!modal) return;

    if (show) {
        modal.style.display = 'flex';
        requestAnimationFrame(() => {
            modal.classList.add('show');
        });
    } else {
        modal.classList.remove('show');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }
}

export function showSection(sectionId) {
    document.querySelectorAll('.section').forEach(sec => sec.classList.remove('active-section'));
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));

    const target = document.getElementById(sectionId);
    if(target) target.classList.add('active-section');

    // 高亮导航按钮
    const navBtns = document.querySelectorAll('.nav-btn');
    navBtns.forEach(btn => {
        const onclickVal = btn.getAttribute('onclick');
        if(onclickVal && onclickVal.includes(`'${sectionId}'`)) {
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

    if (show) {
        modal.style.display = 'flex';
        // 强制重绘，确保 transition 生效
        // requestAnimationFrame 可以保证在下一帧添加 class，从而触发 CSS transition
        requestAnimationFrame(() => {
            modal.classList.add('show');
        });

        // 尝试自动聚焦用户名输入框，提升体验
        setTimeout(() => {
            const userParams = document.getElementById('login-user');
            if(userParams) userParams.focus();
        }, 100);

    } else {
        modal.classList.remove('show');
        // 等待 CSS transition (0.3s) 结束后再隐藏 display
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }

    toggleModal('auth-modal', show);
}

// ... 其他函数保持不变 ...
export function switchAuthMode(mode) {
    const loginForm = document.getElementById('login-form');
    const regForm = document.getElementById('register-form');
    const tabs = document.querySelectorAll('.auth-tab');

    tabs.forEach(t => t.classList.remove('active'));

    if(mode === 'login') {
        loginForm.style.display = 'block';
        regForm.style.display = 'none';
        tabs[0].classList.add('active'); // 假设第一个是登录
    } else {
        loginForm.style.display = 'none';
        regForm.style.display = 'block';
        tabs[1].classList.add('active'); // 假设第二个是注册
    }
    if (window.refreshCaptcha) {
        window.refreshCaptcha(mode);
    }
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
    if(mode === 'draw') {
        if(drawTools) drawTools.style.display = 'block';
        if(uploadTools) uploadTools.style.display = 'none';

        // 隐藏预览图，显示 Canvas 并恢复背景
        if(preview) preview.style.display = 'none';
        if(canvas) {
            canvas.style.display = 'block';
            window.dispatchEvent(new CustomEvent('mode-change', { detail: 'draw' }));
        }
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
    showSection(sectionId);
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