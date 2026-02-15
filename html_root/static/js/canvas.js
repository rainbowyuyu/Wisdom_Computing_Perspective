// static/js/canvas.js

import { switchInputMode } from './ui.js'; // 引入 switchInputMode 用于自动切换

let canvas, ctx;
let isDrawing = false;
let points = [];
const historyStack = [];
let historyStep = -1;
const MAX_HISTORY = 50;

// 手机端防误触：仅当判定为「书写」时才占住触摸，否则允许页面上下滑动
const TOUCH_COMMIT_DIST = 10;       // 移动超过此像素才做意图判断
const TOUCH_SCROLL_VERTICAL_RATIO = 1.3; // 垂直位移 / 水平位移 > 此值视为滚动
let touchStartX = 0;
let touchStartY = 0;
let touchCommittedToDraw = false;

// 深色模式下画板与笔/橡皮颜色与主题一致，避免颜色错误
function isDarkTheme() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
}
function getCanvasBgColor() {
    return isDarkTheme() ? '#1e293b' : '#FFFFFF';
}
function getPenColor() {
    return isDarkTheme() ? '#e2e8f0' : '#000000';
}

export function setupCanvas() {
    canvas = document.getElementById('drawing-board');
    if (!canvas) return;

    ctx = canvas.getContext('2d', { willReadFrequently: true });

    // 1. ResizeObserver
    const parent = canvas.parentElement;
    const observer = new ResizeObserver(() => {
        requestAnimationFrame(resizeCanvas);
    });
    observer.observe(parent);

    // 2. 鼠标/触摸事件
    canvas.addEventListener('mousedown', startDraw);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stopDraw);
    canvas.addEventListener('mouseout', stopDraw);
    canvas.addEventListener('touchstart', handleTouchStart, { passive: true });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', handleTouchEnd);

    // 3. 监听模式切换 (自定义事件)
    window.addEventListener('mode-change', (e) => {
        const mode = e.detail;
        const dpr = window.devicePixelRatio || 1;
        if (mode === 'draw') {
            ctx.globalCompositeOperation = 'destination-over';
            ctx.fillStyle = getCanvasBgColor();
            ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
            ctx.globalCompositeOperation = 'source-over';
        } else {
            ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
        }
    });

    // 4. 主题切换时重绘画布背景，使手写面板与深浅色模式一致
    window.addEventListener('theme-change', () => {
        if (!canvas || !ctx) return;
        const preview = document.getElementById('uploaded-preview');
        const isUploadMode = preview && preview.style.display !== 'none' && preview.getAttribute('src');
        const dpr = window.devicePixelRatio || 1;
        if (!isUploadMode) {
            ctx.fillStyle = getCanvasBgColor();
            ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
            historyStack.length = 0;
            historyStep = -1;
            saveState();
        }
    });

    // 5. 文件上传 Input 监听
    const uploadInput = document.getElementById('image-upload');
    if (uploadInput) {
        uploadInput.addEventListener('change', function(e) {
            if(e.target.files && e.target.files[0]) {
                handleImageFile(e.target.files[0]);
            }
        });
    }

    // --- 新增：全局粘贴监听 ---
    document.addEventListener('paste', handlePaste);
}

// 处理粘贴事件
function handlePaste(e) {
    // 只有在 detect 页面可见时才处理粘贴
    const detectSection = document.getElementById('detect');
    if (!detectSection || !detectSection.classList.contains('active-section')) return;

    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    for (let index in items) {
        const item = items[index];
        if (item.kind === 'file' && item.type.startsWith('image/')) {
            const blob = item.getAsFile();

            // 1. 自动切换到上传模式
            if(window.switchInputMode) window.switchInputMode('upload');
            // 或者使用 import 的 switchInputMode
            // switchInputMode('upload');

            // 2. 将文件赋值给 input (为了兼容 detect.js 的逻辑)
            const fileInput = document.getElementById('image-upload');
            if (fileInput) {
                // 创建一个新的 FileList (Hack)
                const container = new DataTransfer();
                container.items.add(blob);
                fileInput.files = container.files;
            }

            // 3. 显示预览
            handleImageFile(blob);

            e.preventDefault(); // 阻止默认粘贴行为
            return;
        }
    }
}

// 统一处理图片加载与预览
function handleImageFile(file) {
    const fileNameDisplay = document.getElementById('file-name-display');
    if(fileNameDisplay) fileNameDisplay.innerText = file.name || "Pasted Image";

    const reader = new FileReader();
    reader.onload = function(evt) {
        const preview = document.getElementById('uploaded-preview');
        if(preview) {
            preview.src = evt.target.result;
            preview.style.display = 'block';

            // 强制 Canvas 变透明
            const dpr = window.devicePixelRatio || 1;
            if (ctx && canvas) {
                ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
            }
        }
    }
    reader.readAsDataURL(file);
}


export function resizeCanvas() {
    if (!canvas || !ctx) return;

    const parent = canvas.parentElement;
    const rect = parent.getBoundingClientRect();

    if (rect.width === 0 || rect.height === 0) return;

    const dpr = window.devicePixelRatio || 1;
    const targetWidth = Math.floor(rect.width * dpr);
    const targetHeight = Math.floor(rect.height * dpr);

    if (canvas.width === targetWidth && canvas.height === targetHeight) return;

    let savedContent = null;
    if (canvas.width > 0 && canvas.height > 0) {
        savedContent = document.createElement('canvas');
        savedContent.width = canvas.width;
        savedContent.height = canvas.height;
        savedContent.getContext('2d').drawImage(canvas, 0, 0);
    }

    canvas.width = targetWidth;
    canvas.height = targetHeight;
    canvas.style.width = '100%';
    canvas.style.height = '100%';

    ctx.scale(dpr, dpr);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    const preview = document.getElementById('uploaded-preview');
    // 如果预览图是显示的，说明是上传模式，背景透明
    const isUploadMode = preview && preview.style.display !== 'none' && preview.getAttribute('src');

    if (!isUploadMode) {
        ctx.fillStyle = getCanvasBgColor();
        ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    } else {
        ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    }

    if (savedContent) {
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(savedContent, 0, 0);
        ctx.restore();
    } else {
        if (historyStack.length === 0 && !isUploadMode) saveState();
    }
}

// ... (getPos, Touch Events, Draw Logic 保持不变) ...

function getPos(e) {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

function handleTouchStart(e) {
    if (!e.touches.length) return;
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    touchCommittedToDraw = false;
    // 不 preventDefault，先让浏览器可以滚动；在 touchmove 里再根据移动方向决定是画还是滚
}

function handleTouchMove(e) {
    if (!e.touches.length) return;
    const touch = e.touches[0];
    const x = touch.clientX;
    const y = touch.clientY;

    if (touchCommittedToDraw) {
        e.preventDefault();
        canvas.dispatchEvent(new MouseEvent("mousemove", { clientX: x, clientY: y }));
        return;
    }

    const dx = x - touchStartX;
    const dy = y - touchStartY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < TOUCH_COMMIT_DIST) return;

    // 以移动方向区分：明显偏垂直视为滚动，否则视为书写
    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);
    if (absDy > absDx * TOUCH_SCROLL_VERTICAL_RATIO) {
        return;
    }

    touchCommittedToDraw = true;
    e.preventDefault();
    canvas.dispatchEvent(new MouseEvent("mousedown", { clientX: touchStartX, clientY: touchStartY }));
    canvas.dispatchEvent(new MouseEvent("mousemove", { clientX: x, clientY: y }));
}

function handleTouchEnd(e) {
    if (touchCommittedToDraw) stopDraw();
    touchCommittedToDraw = false;
}

function startDraw(e) {
    isDrawing = true;
    const pos = getPos(e);
    points = [pos];
    const brushSize = getBrushSize();
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, brushSize / 2, 0, Math.PI * 2);
    ctx.fillStyle = getBrushColor();
    ctx.fill();
}

function draw(e) {
    if (!isDrawing) return;
    const pos = getPos(e);
    points.push(pos);
    if (points.length < 3) return;

    const brushSize = getBrushSize();
    ctx.lineWidth = brushSize;
    ctx.strokeStyle = getBrushColor();

    ctx.beginPath();
    const len = points.length;
    ctx.moveTo(points[len - 2].x, points[len - 2].y);
    const midX = (points[len - 2].x + points[len - 1].x) / 2;
    const midY = (points[len - 2].y + points[len - 1].y) / 2;
    ctx.quadraticCurveTo(points[len - 2].x, points[len - 2].y, midX, midY);
    ctx.lineTo(points[len - 1].x, points[len - 1].y);
    ctx.stroke();
}

function stopDraw() {
    if (!isDrawing) return;
    isDrawing = false;
    points = [];
    saveState();
}

function getBrushSize() {
    const el = document.getElementById('brush-size');
    const val = el ? parseInt(el.value) : 3;
    return window.currentToolType === 'eraser' ? val * 5 : val;
}

function getBrushColor() {
    return window.currentToolType === 'eraser' ? getCanvasBgColor() : getPenColor();
}

function saveState() {
    if (historyStep < historyStack.length - 1) {
        historyStack.length = historyStep + 1;
    }
    historyStack.push(canvas.toDataURL());
    historyStep++;
    if (historyStack.length > MAX_HISTORY) {
        historyStack.shift();
        historyStep--;
    }
}

export function undo() {
    if (historyStep > 0) {
        historyStep--;
        restoreState();
    }
}

export function redo() {
    if (historyStep < historyStack.length - 1) {
        historyStep++;
        restoreState();
    }
}

function restoreState() {
    const img = new Image();
    img.src = historyStack[historyStep];
    img.onload = () => {
        const dpr = window.devicePixelRatio || 1;
        ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
        ctx.fillStyle = getCanvasBgColor();
        ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(img, 0, 0);
        ctx.restore();
    };
}

export function clearCanvas() {
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;

    const preview = document.getElementById('uploaded-preview');
    const isUploadMode = preview && preview.style.display !== 'none';

    if (!isUploadMode) {
        ctx.fillStyle = getCanvasBgColor();
        ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    } else {
        ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    }
    saveState();
}

export function setTool(tool) {
    window.currentToolType = tool;
}

/** 笔刷粗细增减（供快捷键调用），delta 为 +1 或 -1 */
export function setBrushSizeDelta(delta) {
    const el = document.getElementById('brush-size');
    if (!el) return;
    const v = Math.max(1, Math.min(20, parseInt(el.value, 10) + delta));
    el.value = String(v);
}

export function getCanvasBlob() {
    return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
}