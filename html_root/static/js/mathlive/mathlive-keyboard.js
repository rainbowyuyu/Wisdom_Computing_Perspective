// 为 MathLive 虚拟键盘添加右上角关闭按钮，并在键盘显示/几何变化时更新位置

const CLOSE_BTN_ID = 'mathlive-keyboard-close-btn';

const CLOSE_BTN_WIDTH = 36;
const PAD = 10;
let lastRectKey = '';

function positionCloseButton(kbd, btn) {
    if (!kbd || !kbd.visible || !kbd.boundingRect) return;
    const r = kbd.boundingRect;
    if (r.width < 10 || r.height < 10) return;
    const key = `${r.top}|${r.left}|${r.width}|${r.height}`;
    if (key === lastRectKey) return;
    lastRectKey = key;
    const container = kbd.container || document.body;
    const isViewport = container === document.body;
    const vpTop = isViewport ? r.top : (container.getBoundingClientRect().top + r.top);
    const vpRightX = isViewport ? (r.left + r.width) : (container.getBoundingClientRect().left + r.left + r.width);
    btn.style.top = `${vpTop + PAD}px`;
    btn.style.left = `${vpRightX - CLOSE_BTN_WIDTH - PAD}px`;
    btn.style.right = 'auto';
    btn.style.display = 'flex';
}

function initMathLiveKeyboardClose() {
    const kbd = window.mathVirtualKeyboard;
    if (!kbd) return false;

    let btn = document.getElementById(CLOSE_BTN_ID);
    if (!btn) {
        btn = document.createElement('button');
        btn.type = 'button';
        btn.id = CLOSE_BTN_ID;
        btn.className = 'mathlive-keyboard-close';
        btn.setAttribute('aria-label', '关闭虚拟键盘');
        btn.innerHTML = '<i class="fa-solid fa-times"></i>';
        btn.title = '关闭键盘';
        document.body.appendChild(btn);

        btn.addEventListener('click', () => {
            kbd.hide();
            btn.style.display = 'none';
        });
    }

    const updateVisibility = () => {
        if (kbd.visible) positionCloseButton(kbd, btn);
        else btn.style.display = 'none';
    };

    let geometryTimer = 0;
    const schedulePosition = () => {
        if (geometryTimer) cancelAnimationFrame(geometryTimer);
        geometryTimer = requestAnimationFrame(() => {
            geometryTimer = 0;
            positionCloseButton(kbd, btn);
        });
    };
    kbd.addEventListener('virtual-keyboard-toggle', () => {
        if (!kbd.visible) {
            btn.style.display = 'none';
            lastRectKey = '';
            return;
        }
        schedulePosition();
        setTimeout(schedulePosition, 50);
        setTimeout(schedulePosition, 150);
    });
    kbd.addEventListener('geometrychange', () => {
        if (kbd.visible) schedulePosition();
    });

    if (kbd.visible) {
        requestAnimationFrame(() => positionCloseButton(kbd, btn));
        setTimeout(() => positionCloseButton(kbd, btn), 100);
    }
    return true;
}

function tryInit() {
    if (initMathLiveKeyboardClose()) return;
    let attempts = 0;
    const maxAttempts = 50;
    const t = setInterval(() => {
        if (initMathLiveKeyboardClose() || ++attempts >= maxAttempts) clearInterval(t);
    }, 100);
}

export function initMathLiveKeyboard() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', tryInit);
    } else {
        tryInit();
    }
}
