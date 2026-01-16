// static/js/tutorial.js
import { showSection, switchInputMode } from './ui.js';

const driver = window.driver.js.driver;
let tutorialInterval = null;

// 模拟数据
const MOCK_MATRIX = String.raw`\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}`;

// 辅助：延时
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// --- 动画效果函数 ---

// 1. 模拟画板绘制 (更复杂的轨迹)
async function simulateDrawing() {
    const canvas = document.getElementById('drawing-board');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // 重置画布
    const dpr = window.devicePixelRatio || 1;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#FFFFFF";
    ctx.fillRect(0, 0, canvas.width, canvas.height); // 这里的 width/height 已经是物理像素

    // 坐标转换辅助
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    ctx.lineWidth = 3 * scaleX;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = '#2563eb';

    // 定义一个 "1" 的轨迹 (简化版)
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;

    // 画左括号 [
    const paths = [
        // [
        [{x: centerX-60, y: centerY-50}, {x: centerX-80, y: centerY-50}, {x: centerX-80, y: centerY+50}, {x: centerX-60, y: centerY+50}],
        // 1
        [{x: centerX-40, y: centerY-20}, {x: centerX-40, y: centerY+20}],
        // 2
        [{x: centerX+40, y: centerY-20}, {x: centerX+40, y: centerY+20}],
        // ]
        [{x: centerX+60, y: centerY-50}, {x: centerX+80, y: centerY-50}, {x: centerX+80, y: centerY+50}, {x: centerX+60, y: centerY+50}]
    ];

    let pathIdx = 0;
    let pointIdx = 0;

    if (tutorialInterval) clearInterval(tutorialInterval);

    tutorialInterval = setInterval(() => {
        if (pathIdx >= paths.length) {
            clearInterval(tutorialInterval);
            return;
        }

        const currentPath = paths[pathIdx];

        if (pointIdx === 0) {
            ctx.beginPath();
            ctx.moveTo(currentPath[0].x, currentPath[0].y);
        }

        if (pointIdx < currentPath.length) {
            const p = currentPath[pointIdx];
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
            pointIdx++;
        } else {
            ctx.closePath();
            pathIdx++;
            pointIdx = 0;
        }
    }, 50);
}

// 2. 模拟识别结果填充
async function simulateRecognitionResult() {
    const mathField = document.getElementById('latex-output');
    if (!mathField) return;

    // 模拟 Loading
    mathField.setValue(String.raw`\text{识别中...}`);
    await sleep(800);
    // 模拟结果
    mathField.setValue(MOCK_MATRIX);
    // 高亮反馈
    const container = document.querySelector('.result-panel');
    if(container) {
        container.style.boxShadow = "0 0 0 4px rgba(37, 99, 235, 0.3)";
        setTimeout(() => container.style.boxShadow = "", 1000);
    }
}

// --- 教程主逻辑 ---

export function startTutorial() {
    const tour = driver({
        showProgress: true,
        animate: true,
        allowClose: true,
        doneBtnText: "开始使用",
        nextBtnText: "下一步",
        prevBtnText: "上一步",
        progressText: "步骤 {{current}} / {{total}}",
        steps: [
            {
                element: '.logo',
                popover: {
                    title: '👋 欢迎来到智算视界',
                    description: '这是一个全流程的数学可视化平台。接下来我们将演示从<b>识别</b>到<b>计算</b>的完整工作流。',
                    side: "bottom",
                    align: 'start'
                }
            },
            // --- 阶段一：识别 ---
            {
                element: '.nav-links button:nth-child(2)', // 智能识别 tab
                popover: {
                    title: '1. 进入识别工作区',
                    description: '首先，我们需要输入一个数学公式。',
                    side: "bottom"
                },
                onHighlightStarted: () => showSection('detect')
            },
            {
                element: '#draw-tools',
                popover: {
                    title: '2. 手写输入',
                    description: '在画板上书写公式。系统支持复杂的矩阵和微积分符号。<br><i>(正在演示自动绘制...)</i>',
                    side: "right"
                },
                onHighlightStarted: async () => {
                    switchInputMode('draw');
                    await sleep(500);
                    simulateDrawing();
                }
            },
            {
                element: '.tools-panel .action-btn', // 识别按钮
                popover: {
                    title: '3. 点击识别',
                    description: '绘制完成后，点击此按钮，将识别 LaTeX 代码。',
                    side: "right"
                }
            },
            {
                element: '.result-panel',
                popover: {
                    title: '4. 结果预览与编辑',
                    description: '识别结果会显示在这里。您可以直接点击公式进行修改，所见即所得。',
                    side: "top"
                },
                onHighlightStarted: () => simulateRecognitionResult()
            },
            // --- 阶段二：保存与管理 ---
            {
                element: '.result-actions .btn-calc-go', // 保存按钮
                popover: {
                    title: '5. 保存并查看',
                    description: '确认无误后，点击保存。公式将存入您的云端库，方便后续复用。',
                    side: "top"
                }
            },
            {
                element: '.nav-links button:nth-child(3)', // 我的算式 tab
                popover: {
                    title: '6. 管理算式库',
                    description: '所有保存的公式都在这里。您可以点击卡片上的<b>跳转图标</b>，直接将公式带入计算页面。',
                    side: "bottom"
                },
                onHighlightStarted: () => showSection('my-formulas')
            },
            // --- 阶段三：计算与动画 ---
            {
                element: '.nav-links button:nth-child(4)', // 动态计算 tab
                popover: {
                    title: '7. 动态计算',
                    description: '这里是核心工作台。您可以组合多个公式，选择算法（如矩阵乘法）。',
                    side: "bottom"
                },
                onHighlightStarted: () => showSection('calculate')
            },
            {
                element: '.matrix-input-group:first-child .btn-icon', // 导入按钮
                popover: {
                    title: '8. 快速导入',
                    description: '无需重复输入，点击“导入”即可从您的算式库中选择公式填入。',
                    side: "left"
                }
            },
            {
                element: '.calc-sidebar .action-btn.full-width', // 生成动画按钮
                popover: {
                    title: '9. 生成可视化动画',
                    description: '最后，点击生成。系统将调用 Manim 引擎，为您呈现数学推演的动态过程！',
                    side: "right"
                }
            }
        ],
        onDestroyed: () => {
            // 清理
            if (tutorialInterval) clearInterval(tutorialInterval);

            // 清空画板
            const canvas = document.getElementById('drawing-board');
            if (canvas) {
                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = "#FFFFFF";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
            }

            // 重置输入框
            const mathField = document.getElementById('latex-output');
            if(mathField) mathField.setValue(String.raw`\text{等待输入...}`);

            // 回到首页
            showSection('home');
            localStorage.setItem('tutorial_played', 'true');
        }
    });

    tour.drive();
}

// 检查自动播放
export function checkAutoPlay() {
    if (!localStorage.getItem('tutorial_played')) {
        setTimeout(startTutorial, 1500);
    }
}