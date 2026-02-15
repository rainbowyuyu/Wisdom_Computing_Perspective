// static/js/tutorial.js
import { showSection, switchInputMode } from './ui.js';

const driver = window.driver.js.driver;
let tutorialInterval = null;

// 模拟数据
const MOCK_MATRIX = String.raw`\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}`;

// 辅助：延时
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// 辅助：检测深色模式
const isDarkMode = () => document.documentElement.getAttribute('data-theme') === 'dark';

// --- 样式注入：适配 Driver.js 的深色模式 ---
function injectDriverStyles() {
    const styleId = 'driver-custom-styles';
    if (document.getElementById(styleId)) return;

    const style = document.createElement('style');
    style.id = styleId;
    style.innerHTML = `
        /* 覆盖 Driver.js 默认样式以适配深色模式和品牌色 */
        .driver-popover.driverjs-theme {
            background-color: var(--bg-surface);
            color: var(--text-main);
            border: 1px solid var(--border-color);
            box-shadow: var(--shadow-lg);
            border-radius: var(--radius-md);
        }
        .driver-popover.driverjs-theme .driver-popover-title {
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--primary-color);
        }
        .driver-popover.driverjs-theme .driver-popover-description {
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-size: 0.95rem;
            color: var(--text-main);
            line-height: 1.6;
        }
        .driver-popover.driverjs-theme button {
            background-color: var(--bg-body);
            color: var(--text-main);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            text-shadow: none;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }
        .driver-popover.driverjs-theme button:hover {
            background-color: var(--primary-color);
            color: white;
        }
        .driver-popover.driverjs-theme .driver-popover-navigation-btns {
            gap: 8px;
        }
        /* 遮罩层颜色 */
        .driver-overlay path {
            fill: var(--bg-body);
            opacity: 0.75;
        }
    `;
    document.head.appendChild(style);
}

// --- 动画效果函数 ---

// 1. 模拟画板绘制 (适配深色模式)
async function simulateDrawing() {
    const canvas = document.getElementById('drawing-board');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // 获取当前主题颜色配置
    const dark = isDarkMode();
    // 深色模式背景色对应 --bg-surface (#1e293b), 亮色对应 #FFFFFF
    const bgColor = dark ? '#1e293b' : '#FFFFFF';
    // 深色模式笔触用亮青色，亮色模式用品牌蓝
    const strokeColor = dark ? '#22d3ee' : '#2563eb';

    // 重置画布
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // 坐标转换辅助
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;

    ctx.lineWidth = 3 * scaleX;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = strokeColor;

    // 定义一个 "1" 的轨迹 (简化版)
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;

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
    mathField.setValue(String.raw`\text{正在识别中...}`);
    await sleep(800);
    // 模拟结果
    mathField.setValue(MOCK_MATRIX);
    // 高亮反馈 (使用 primary color 的 glow)
    const container = document.querySelector('.result-panel');
    if(container) {
        container.style.transition = "box-shadow 0.3s";
        container.style.boxShadow = "0 0 0 4px var(--shadow-glow)"; // 使用 CSS 变量
        setTimeout(() => container.style.boxShadow = "", 1000);
    }
}

// --- 教程主逻辑 ---

export function startTutorial() {
    // 注入样式
    injectDriverStyles();

    const tour = driver({
        showProgress: true,
        animate: true,
        allowClose: true,
        doneBtnText: "开始探索",
        nextBtnText: "下一步",
        prevBtnText: "上一步",
        progressText: "步骤 {{current}} / {{total}}",
        // 关键：给引导框添加自定义类名，以便应用样式
        popoverClass: 'driverjs-theme',
        steps: [
            {
                element: '.logo',
                popover: {
                    title: '👋 欢迎使用智算视界',
                    description: '30秒带您上手：从<b>手写公式</b>到生成<b>动态视频</b>的完整流程。',
                    side: "bottom",
                    align: 'start'
                }
            },
            // --- 小贴士：智能体 ---
            {
                element: '.nav-links .desktop-nav button:nth-child(2)', // 智能体
                popover: {
                    title: '小贴士：智能体',
                    description: '除了按步骤操作，你也可以使用【智能体】用自然语言一句话完成识别、生成动画等。例如："把 sin(x) = 1/2 做成动画"、"识别这张图并去计算"。',
                    side: "bottom"
                },
                onHighlightStarted: () => showSection('home')
            },
            // --- 阶段一：识别 ---
            {
                element: '.nav-links .desktop-nav button:nth-child(3)', // 智能识别 tab
                popover: {
                    title: '1. 进入识别工作台',
                    description: '第一步：点击这里进入【智能识别】页面。',
                    side: "bottom"
                },
                onHighlightStarted: () => showSection('detect')
            },
            {
                element: '#draw-tools',
                popover: {
                    title: '2. 书写数学公式',
                    description: '请在中间的画板区域写下您的公式。支持矩阵、微积分等复杂符号。<br><i>(👀 请看屏幕上的自动书写演示)</i>',
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
                    description: '写好后，点击【立即识别】按钮，将把笔迹转换为标准数学公式。',
                    side: "right"
                }
            },
            {
                element: '.result-panel',
                popover: {
                    title: '4. 检查与编辑结果',
                    description: '识别结果会显示在这里。<br>👉 <b>技巧：</b>如果个别数字识别有误，直接点击公式即可像在 Word 中一样修改。',
                    side: "top"
                },
                onHighlightStarted: () => simulateRecognitionResult()
            },
            // --- 阶段二：保存 ---
            {
                element: '.result-actions .btn-calc-go', // 保存按钮
                popover: {
                    title: '5. 保存公式',
                    description: '确认无误后，点击【保存并查看】。公式将存入您的云端笔记本，无需重复书写。',
                    side: "top"
                }
            },
            {
                element: '#formula-list',
                popover: {
                    title: '6. 您的算式库',
                    description: '刚才保存的公式已经出现在这里了。以后您可以随时调用它。',
                    side: "top"
                },
                onHighlightStarted: () => showSection('my-formulas')
            },
            // --- 阶段三：计算 ---
            {
                element: '.nav-links .desktop-nav button:nth-child(5)', // 动态计算 tab
                popover: {
                    title: '7. 前往计算引擎',
                    description: '现在，让我们把静态公式变成动画。点击进入【动态计算】页面。',
                    side: "bottom"
                },
                onHighlightStarted: () => showSection('calculate')
            },
            {
                element: '.header-actions .btn-import:first-child', // 导入按钮
                popover: {
                    title: '8. 一键导入',
                    description: '不需要重新输入。点击这个【导入图标】，直接选择刚才保存的公式。',
                    side: "left"
                }
            },
            {
                element: '#calc-method',
                popover: {
                    title: '9. 选择可视化模式',
                    description: '根据需要选择模式。例如“公式推演”或“可视化演示”，系统会生成不同的解题动画。',
                    side: "left"
                }
            },
            {
                element: '.calc-sidebar .action-btn.full-width', // 生成按钮
                popover: {
                    title: '10. 生成视频',
                    description: '最后，点击生成按钮。稍等片刻，右侧就会播放 Manim 渲染的高清数学动画！',
                    side: "right"
                }
            }
        ],
        onDestroyed: () => {
            // 清理
            if (tutorialInterval) clearInterval(tutorialInterval);

            // 清空画板并重置颜色
            const canvas = document.getElementById('drawing-board');
            if (canvas) {
                const ctx = canvas.getContext('2d');
                const dark = isDarkMode();
                const bgColor = dark ? '#1e293b' : '#FFFFFF';
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = bgColor;
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