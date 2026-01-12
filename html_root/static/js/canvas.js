// static/js/canvas.js

let canvas, ctx;
let isDrawing = false;
let points = [];
// 历史记录栈
const historyStack = [];
let historyStep = -1;
const MAX_HISTORY = 50;

export function setupCanvas() {
    canvas = document.getElementById('drawing-board');
    if (!canvas) return;

    ctx = canvas.getContext('2d', { willReadFrequently: true });

    // 监听容器变化
    const parent = canvas.parentElement; // 这里是 #canvas-container
    const observer = new ResizeObserver(() => {
        requestAnimationFrame(resizeCanvas);
    });
    observer.observe(parent);

    // 绑定事件
    canvas.addEventListener('mousedown', startDraw);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stopDraw);
    canvas.addEventListener('mouseout', stopDraw);
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', stopDraw);

    // 监听模式切换
    window.addEventListener('mode-change', (e) => {
        const mode = e.detail;
        const dpr = window.devicePixelRatio || 1;
        if (mode === 'draw') {
            // 切回手写：如果画布是空的或透明，填充白色
            // 简单策略：总是重置为白色背景，除非有历史记录
            // 这里为了简单，我们重新填充白色
            ctx.globalCompositeOperation = 'destination-over'; // 在内容后面画
            ctx.fillStyle = "#FFFFFF";
            ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
            ctx.globalCompositeOperation = 'source-over'; // 恢复默认
        } else {
            // 切到上传：清空画布（变透明），露出底下的 img
            ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
        }
    });

    // 图片上传预览
    const uploadInput = document.getElementById('image-upload');
    if (uploadInput) {
        uploadInput.addEventListener('change', function(e) {
            if(e.target.files && e.target.files[0]) {
                const file = e.target.files[0];

                const reader = new FileReader();
                reader.onload = function(evt) {
                    const preview = document.getElementById('uploaded-preview');
                    if(preview) {
                        preview.src = evt.target.result;
                        preview.style.display = 'block'; // 确保显示

                        // 强制 Canvas 变透明
                        const dpr = window.devicePixelRatio || 1;
                        ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
                    }
                }
                reader.readAsDataURL(file);
            }
        });
    }
}

export function resizeCanvas() {
    if (!canvas || !ctx) return;

    const parent = canvas.parentElement;
    const rect = parent.getBoundingClientRect();

    if (rect.width === 0 || rect.height === 0) return;

    const dpr = window.devicePixelRatio || 1;
    const targetWidth = Math.floor(rect.width * dpr);
    const targetHeight = Math.floor(rect.height * dpr);

    // 如果尺寸没变，不重置
    if (canvas.width === targetWidth && canvas.height === targetHeight) return;

    // 保存内容
    let savedContent = null;
    if (canvas.width > 0 && canvas.height > 0) {
        savedContent = document.createElement('canvas');
        savedContent.width = canvas.width;
        savedContent.height = canvas.height;
        savedContent.getContext('2d').drawImage(canvas, 0, 0);
    }

    // 设置新尺寸
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    canvas.style.width = '100%';
    canvas.style.height = '100%';

    // 重置 Context 状态
    ctx.scale(dpr, dpr);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // 恢复背景逻辑：检查当前模式
    const preview = document.getElementById('uploaded-preview');
    // 如果预览图是显示的，说明是上传模式，背景透明
    const isUploadMode = preview && preview.style.display !== 'none' && preview.getAttribute('src');

    if (!isUploadMode) {
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    } else {
        ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    }

    // 恢复内容
    if (savedContent) {
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.drawImage(savedContent, 0, 0);
        ctx.restore();
    } else {
        if (historyStack.length === 0 && !isUploadMode) saveState();
    }
}

// 获取相对于 Canvas 的准确坐标
function getPos(e) {
    const rect = canvas.getBoundingClientRect();
    // dpr 缩放已经在 ctx.scale 处理了，这里直接返回 CSS 像素坐标即可
    // 不需要除以 dpr，因为 scale 会自动放大绘图操作
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

    if (points.length < 3) return;

    const brushSize = getBrushSize();
    ctx.lineWidth = brushSize;
    ctx.strokeStyle = getBrushColor();

    ctx.beginPath();
    const len = points.length;
    // 使用二次贝塞尔曲线平滑绘制
    ctx.moveTo(points[len - 2].x, points[len - 2].y);
    const midX = (points[len - 2].x + points[len - 1].x) / 2;
    const midY = (points[len - 2].y + points[len - 1].y) / 2;
    ctx.quadraticCurveTo(points[len - 2].x, points[len - 2].y, midX, midY); // 这里简化逻辑，直接连线其实也行

    // 修正：简单连线更稳定
    ctx.lineTo(points[len - 1].x, points[len - 1].y);

    ctx.stroke();
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

    // 同理，清空时要判断模式
    const preview = document.getElementById('uploaded-preview');
    const isUploadMode = preview && preview.style.display !== 'none';

    if (!isUploadMode) {
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    } else {
        ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    }
    saveState();
}

export function setTool(tool) {
    window.currentToolType = tool;
}

export function getCanvasBlob() {
    return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
}