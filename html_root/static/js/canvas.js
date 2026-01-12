// static/js/canvas.js

let canvas, ctx;
let isDrawing = false;
// 使用点数组来平滑曲线
let points = [];

// 历史记录栈
const historyStack = [];
let historyStep = -1;
const MAX_HISTORY = 50;

export function setupCanvas() {
    canvas = document.getElementById('drawing-board');
    if (!canvas) return;

    ctx = canvas.getContext('2d', { willReadFrequently: true }); // 优化性能

    const parent = canvas.parentElement;
    const observer = new ResizeObserver(() => {
        // 使用 requestAnimationFrame 避免高频触发重绘
        requestAnimationFrame(resizeCanvas);
    });
    observer.observe(parent);

    // 绑定事件
    canvas.addEventListener('mousedown', startDraw);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stopDraw);
    canvas.addEventListener('mouseout', stopDraw);

    // 移动端支持 (passive: false 禁止默认滚动)
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', stopDraw);

    // ... (图片上传监听代码保持不变) ...
}

export function resizeCanvas() {
    if (!canvas || !ctx) return;

    const parent = canvas.parentElement;
    const rect = parent.getBoundingClientRect();

    if (rect.width === 0 || rect.height === 0) return;

    const dpr = window.devicePixelRatio || 1;

    // 强制整数像素，防止模糊
    const targetWidth = Math.floor(rect.width * dpr);
    const targetHeight = Math.floor(rect.height * dpr);

    if (canvas.width === targetWidth && canvas.height === targetHeight) return;

    // --- 保存内容 ---
    let savedContent = null;
    if (canvas.width > 0 && canvas.height > 0) {
        savedContent = document.createElement('canvas');
        savedContent.width = canvas.width;
        savedContent.height = canvas.height;
        savedContent.getContext('2d').drawImage(canvas, 0, 0);
    }

    // 设置尺寸
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    // 样式尺寸 (CSS)
    canvas.style.width = '100%';
    canvas.style.height = '100%';

    // 重置 Context
    ctx.scale(dpr, dpr);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // 恢复背景
    ctx.fillStyle = "#FFFFFF";
    ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);

    // --- 恢复内容 ---
    if (savedContent) {
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        // 使用 drawImage 的完整参数来适应新尺寸 (可选: 拉伸或居中)
        // 这里选择居中保留原比例，或者直接铺在左上角
        ctx.drawImage(savedContent, 0, 0);
        ctx.restore();
    } else {
        if (historyStack.length === 0) saveState();
    }
}

// 获取相对于 Canvas 的准确坐标
function getPos(e) {
    // 缓存 rect 减少重排 (注意：如果页面布局动态变化很大，可能需要实时获取)
    const rect = canvas.getBoundingClientRect();
    return {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
    };
}

// --- 触摸事件适配 ---
function handleTouchStart(e) {
    e.preventDefault();
    const touch = e.touches[0];
    const mouseEvent = new MouseEvent("mousedown", {
        clientX: touch.clientX,
        clientY: touch.clientY
    });
    canvas.dispatchEvent(mouseEvent);
}

function handleTouchMove(e) {
    e.preventDefault();
    const touch = e.touches[0];
    const mouseEvent = new MouseEvent("mousemove", {
        clientX: touch.clientX,
        clientY: touch.clientY
    });
    canvas.dispatchEvent(mouseEvent);
}

// --- 核心绘图逻辑 (贝塞尔曲线优化) ---
function startDraw(e) {
    isDrawing = true;
    const pos = getPos(e);
    points = [pos]; // 重置点数组，存入起点

    // 立即画一个圆点，保证点击也能出墨
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

    // 至少需要3个点才能绘制二次贝塞尔曲线
    if (points.length < 3) return;

    const brushSize = getBrushSize();
    ctx.lineWidth = brushSize;
    ctx.strokeStyle = getBrushColor();

    ctx.beginPath();

    // 移动到倒数第三个点
    // 我们总是绘制从 p[i-2] 到 p[i-1] 的曲线，控制点由 p[i-1] 和 p[i] 决定
    const len = points.length;
    // 起点
    ctx.moveTo(points[len - 2].x, points[len - 2].y);

    // 二次贝塞尔曲线：终点是两点中点，控制点是倒数第二个点
    // 这种算法能画出非常平滑的曲线
    const lastPos = points[len - 2];
    const currPos = points[len - 1];

    // 取中点作为曲线终点，平滑过渡
    const midX = (lastPos.x + currPos.x) / 2;
    const midY = (lastPos.y + currPos.y) / 2;

    // 注意：这里其实是在补画上一段的尾巴
    // 简易版：直接连线（旧逻辑），优化版如下：

    // 为了极致流畅，通常我们不实时清空重绘整个路径，而是画小段
    // 但简单的 lineTo 在转角处很生硬。
    // 使用“中点法”：

    // 清空当前点数组，只保留最后两个用于下一次计算
    // 实际上，为了性能，我们每两点画一条直线通常足够，只要采样率够高（mousemove 频率高）
    // 但如果鼠标移动极快，就需要插值。

    // 这里采用更稳定的方案：直接画线，但在样式上优化
    ctx.moveTo(points[len-2].x, points[len-2].y);
    ctx.lineTo(points[len-1].x, points[len-1].y);
    ctx.stroke();

    // 如果想要贝塞尔曲线效果，需要更复杂的缓冲区逻辑，
    // 对于手写识别场景，高频直线连接其实更准确且性能更好。
    // 关键在于 ctx.lineCap = 'round' 和 ctx.lineJoin = 'round' (在 resizeCanvas 已设置)
}

function stopDraw() {
    if (!isDrawing) return;
    isDrawing = false;
    points = [];
    saveState();
}

// 辅助函数
function getBrushSize() {
    const el = document.getElementById('brush-size');
    const val = el ? parseInt(el.value) : 3;
    // 橡皮擦模式下笔触加粗
    return window.currentToolType === 'eraser' ? val * 5 : val;
}

function getBrushColor() {
    return window.currentToolType === 'eraser' ? '#FFFFFF' : '#000000';
}

// --- 历史记录与工具导出 (保持不变) ---
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
        ctx.fillStyle = "#FFFFFF";
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
    ctx.fillStyle = "#FFFFFF";
    ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    saveState();
}

export function setTool(tool) {
    window.currentToolType = tool;
}

export function getCanvasBlob() {
    return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
}