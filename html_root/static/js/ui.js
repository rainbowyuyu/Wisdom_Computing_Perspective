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

    document.getElementById(sectionId).classList.add('active-section');

    // 高亮导航按钮
    const navBtns = document.querySelectorAll('.nav-btn');
    navBtns.forEach(btn => {
        if(btn.innerText.includes("首页") && sectionId === 'home') btn.classList.add('active');
        if(btn.innerText.includes("识别") && sectionId === 'detect') btn.classList.add('active');
        if(btn.innerText.includes("计算") && sectionId === 'calculate') btn.classList.add('active');
        if(btn.innerText.includes("案例") && sectionId === 'examples') btn.classList.add('active');
    });
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
}
// ...

// 切换 手写/上传 模式
export function switchInputMode(mode) {
    const drawTools = document.getElementById('draw-tools');
    const uploadTools = document.getElementById('upload-tools');
    const canvasEl = document.getElementById('drawing-board');
    const previewEl = document.getElementById('uploaded-preview');

    if(mode === 'draw') {
        drawTools.style.display = 'block';
        uploadTools.style.display = 'none';
        canvasEl.style.display = 'block';
        previewEl.style.display = 'none';
    } else {
        drawTools.style.display = 'none';
        uploadTools.style.display = 'block';
        canvasEl.style.display = 'none';
        previewEl.style.display = 'block';
    }
}