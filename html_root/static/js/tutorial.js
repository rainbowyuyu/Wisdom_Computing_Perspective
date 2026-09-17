// static/js/tutorial.js
import { showSection, switchInputMode } from './ui.js';

// 兼容 CDN 暴露：官方为 window.driver.js.driver，部分 IIFE 为 window['driver.js'].driver
function getDriver() {
    if (typeof window === 'undefined') return null;
    if (window.driver?.js?.driver) return window.driver.js.driver;
    if (window['driver.js']?.driver) return window['driver.js'].driver;
    return null;
}
let tutorialInterval = null;

// 模拟数据
const MOCK_MATRIX = String.raw`\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}`;

// 辅助：延时
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// 辅助：先切换区块，等布局完成后再滚动，确保 Driver.js 能正确高亮
function goToAndScroll(sectionId, element) {
    showSection(sectionId);
    if (element) {
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                element.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'nearest' });
            });
        });
    }
}

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

// 仅当【智能识别】区块可见时执行（避免教程切到其他页时误触）
function isDetectSectionVisible() {
    const section = document.getElementById('detect');
    return section && section.classList.contains('active-section');
}

// 1. 模拟画板绘制 (适配深色模式)
async function simulateDrawing() {
    if (!isDetectSectionVisible()) return;
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
    if (!isDetectSectionVisible()) return;
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

// 动态加载 driver.js（CDN），加载完成后执行 callback
function loadDriverScript(callback) {
    const scriptId = 'driver-js-script';
    const existing = document.getElementById(scriptId);
    if (existing) {
        const fn = getDriver();
        if (fn) callback(fn);
        else callback(null);
        return;
    }
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdn.jsdelivr.net/npm/driver.js@1.0.1/dist/driver.css';
    document.head.appendChild(link);
    const script = document.createElement('script');
    script.id = scriptId;
    script.src = 'https://cdn.jsdelivr.net/npm/driver.js@1.0.1/dist/driver.js.iife.js';
    script.onload = () => callback(getDriver());
    script.onerror = () => callback(null);
    document.head.appendChild(script);
}

// --- 教程主逻辑 ---

export function startTutorial() {
    function runTutorial(driverFn) {
        if (!driverFn) {
            if (typeof showToast === 'function') showToast('引导库未加载，请刷新后重试', 'error');
            else if (typeof showAlert === 'function') showAlert('引导库未加载，请刷新后重试', "提示");
            return;
        }
        injectDriverStyles();
        runDriverTour(driverFn);
    }

    const driverFn = getDriver();
    if (driverFn) {
        runTutorial(driverFn);
        return;
    }
    // 未检测到引导库时尝试动态加载
    loadDriverScript(runTutorial);
}

// --- 按角色快速开始：仅观看操作流程（不强制使用智能体） ---

export function startRoleGuide(role) {
    function run(driverFn) {
        if (!driverFn) {
            if (typeof showToast === 'function') showToast('引导库未加载，请刷新后重试', 'error');
            else if (typeof showAlert === 'function') showAlert('引导库未加载，请刷新后重试', "提示");
            return;
        }
        injectDriverStyles();
        runRoleTour(driverFn, role);
    }
    const driverFn = getDriver();
    if (driverFn) {
        run(driverFn);
        return;
    }
    loadDriverScript(run);
}

function runDriverTour(driverFn) {

    const tour = driverFn({
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
                    description: '本站是<b>数学公式识别 + 动态可视化</b>一体化平台：可<b>手写或上传</b>公式 → 【智能识别】 → 存入【我的算式】 → 在【动态计算】中生成 Manim 动画；也可用【智能体】一句话完成上述流程。所有功能都汇聚在右侧的<b>全站知识图谱</b>中，节点即工具，一图总览全站能力。下面用约 30 秒带您走一遍经典路径。',
                    side: "bottom",
                    align: 'start'
                },
                onHighlightStarted: (el) => goToAndScroll('home', el)
            },
            // --- 智能体（跳转到智能体页并高亮侧栏入口）---
            {
                element: '#agent #agent-features-examples-btn',
                popover: {
                    title: '推荐：智能体',
                    description: '用<b>自然语言</b>说出需求（或<b>上传公式图片</b>），系统会自动跳转并执行：识别、保存、生成动画、打开 LaTeX/Manim 工作台等。支持多步指令，如【识别这张图并保存到我的算式】。可点击此处【功能与示例】查看可用的说法与示例。',
                    side: "right"
                },
                onHighlightStarted: (el) => goToAndScroll('agent', el)
            },
            // --- 全站知识图谱 ---
            {
                element: '#role-graph-3d',
                popover: {
                    title: '0. 全站知识图谱（可选）',
                    description: '这一块是<b>全站知识图谱</b>：每个发光的圆球代表一个功能（如「智能识别」「动态计算」「开发者工具」「课件包」等），连线表示常用路径。你可以拖动旋转 3D 图谱，点击任意节点跳转到对应页面；右侧「推荐路径」会根据学生 / 教师 / 创作者 / 开发者给出 3 步最佳上手路线。',
                    side: 'top',
                    align: 'center'
                },
                onHighlightStarted: (el) => goToAndScroll('home', el)
            },
            // --- 阶段一：识别（先切区块再滚动，保证 Driver.js 高亮位置正确）---
            {
                element: '.nav-links .desktop-nav button:nth-child(3)', // 智能识别 tab
                popover: {
                    title: '1. 进入识别工作台',
                    description: '第一步：点击这里进入【智能识别】页面。',
                    side: "bottom"
                },
                onHighlightStarted: (el) => goToAndScroll('detect', el)
            },
            {
                element: '#detect #draw-tools',
                popover: {
                    title: '2. 书写数学公式',
                    description: '请在中间的画板区域写下您的公式。支持矩阵、微积分等复杂符号。<br><i>(👀 请看屏幕上的自动书写演示)</i>',
                    side: "right"
                },
                onHighlightStarted: async (el) => {
                    goToAndScroll('detect', el);
                    switchInputMode('draw');
                    await sleep(500);
                    simulateDrawing();
                }
            },
            {
                element: '#detect .tools-panel .action-btn',
                popover: {
                    title: '3. 点击识别',
                    description: '写好后，点击【立即识别】按钮，将把笔迹转换为标准数学公式。',
                    side: "right"
                },
                onHighlightStarted: (el) => goToAndScroll('detect', el)
            },
            {
                element: '#detect .result-panel',
                popover: {
                    title: '4. 检查与编辑结果',
                    description: '识别结果会显示在这里。<br>👉 <b>技巧：</b>如果个别数字识别有误，直接点击公式即可像在 Word 中一样修改。',
                    side: "top"
                },
                onHighlightStarted: (el) => {
                    goToAndScroll('detect', el);
                    simulateRecognitionResult();
                }
            },
            // --- 阶段二：保存 ---
            {
                element: '#detect .result-actions .btn-calc-go',
                popover: {
                    title: '5. 保存公式',
                    description: '确认无误后，点击【保存并查看】。公式将存入您的云端笔记本，无需重复书写。',
                    side: "top"
                },
                onHighlightStarted: (el) => goToAndScroll('detect', el)
            },
            {
                element: '#my-formulas #formula-list',
                popover: {
                    title: '6. 我的算式',
                    description: '保存的公式会出现在这里，可随时调用。本页还有【子页】：渲染出的动画可【保存为脚本】，在【我的脚本】中编辑，或到【开发者工具】中继续编辑与渲染。',
                    side: "top"
                },
                onHighlightStarted: (el) => goToAndScroll('my-formulas', el)
            },
            // --- 阶段三：计算 ---
            {
                element: '.nav-links .desktop-nav button:nth-child(5)', // 动态计算 tab
                popover: {
                    title: '7. 前往计算引擎',
                    description: '现在，让我们把静态公式变成动画。点击进入【动态计算】页面。',
                    side: "bottom"
                },
                onHighlightStarted: (el) => goToAndScroll('calculate', el)
            },
            {
                element: '#calculate [data-action=library]',
                popover: {
                    title: '8. 从算式库继续',
                    description: '在【我的算式】选择已保存的公式或题解，可继续计算或阅读之前的完整解答。',
                    side: "left"
                },
                onHighlightStarted: (el) => goToAndScroll('calculate', el)
            },
            {
                element: '#calculate .tutor-composer',
                popover: {
                    title: '9. 输入题目',
                    description: '输入完整题目或 LaTeX，系统会自动组织分步推导与交互图形。无需手动选择计算模式。',
                    side: "left"
                },
                onHighlightStarted: (el) => goToAndScroll('calculate', el)
            },
            {
                element: '#calculate .tutor-compose-actions',
                popover: {
                    title: '10. 生成视频',
                    description: '勾选【同步生成动画】后开始解题。完成后可切换步骤与视频章节，并将题解、图形和动画保存到【我的算式】。',
                    side: "right"
                },
                onHighlightStarted: (el) => goToAndScroll('calculate', el)
            },
            // --- 开发者工具（跳转到工作台并高亮工具箱）---
            {
                element: '#devtools .tools-list',
                popover: {
                    title: '11. 进阶：开发者工具',
                    description: '【LaTeX 编辑器】写公式；【Manim 工作台】写 Manim 代码并云端渲染，可导入已保存脚本或 Rainbow 拓展库示例；【Rainbow 拓展库】免安装使用拓展案例。开发者工具中出现的所有子功能（如 AI 编辑、导入脚本、关键帧预览）也都在知识图谱中有对应节点，方便用智能体或图谱一键直达。',
                    side: "right"
                },
                onHighlightStarted: (el) => goToAndScroll('devtools', el)
            },
            // --- 开发者工具功能 1：LaTeX 可视化编辑器 ---
            {
                element: '#dev-latex-mathfield',
                popover: {
                    title: '12. LaTeX 可视化编辑器',
                    description: '这里是可视化公式输入区：像在 Word 里一样点击输入数学公式。下方会用 KaTeX 实时渲染，右侧同步维护对应的 LaTeX 源码。<br><br>上方工具栏支持：从「我的算式」<b>导入算式</b>、将当前公式<b>保存回算式库</b>、一键<b>复制 LaTeX</b>，以及通过 Temml 把公式导出为<b>适合粘贴到 Word 的 MathML</b>。',
                    side: 'bottom'
                },
                onHighlightStarted: (el) => {
                    goToAndScroll('devtools', el);
                    if (typeof window.switchDevTool === 'function') window.switchDevTool('latex');
                }
            },
            // --- 开发者工具功能 2：Manim 工作台 + AI 编辑 ---
            {
                element: '#btn-manim-ai-edit',
                popover: {
                    title: '13. Manim 云端工作台 + AI 编辑',
                    description: '切换到「Manim 工作台」后，可以在上方的 Monaco 编辑器里写 Python Manim 代码。点击这里的 <b>AI</b> 按钮，会在左侧弹出一块<b>AI 编辑助手</b>浮窗：你只需用自然语言描述修改（例如「把圆改成红色并在右下角加标题」），系统会自动生成<b>代码变更对比 + 效果关键帧预览</b>，确认后点击「接受」即可把改动应用到脚本中。',
                    side: 'left'
                },
                onHighlightStarted: (el) => {
                    goToAndScroll('devtools', el);
                    // 确保切到 manim 标签，方便用户理解
                    if (typeof window.switchDevTool === 'function') window.switchDevTool('manim');
                }
            },
            // --- 开发者工具功能 3：关键帧预览 + 运行渲染 ---
            {
                element: '#btn-manim-keyframe',
                popover: {
                    title: '14. 关键帧预览与完整渲染',
                    description: '写好脚本后，推荐先点击<b>关键帧</b>渲染一张预览图，快速检查画面构图与元素位置；确认无误后再点击旁边的<b>运行</b>按钮，在右下角浮动的视频窗口中查看完整动画。下方「渲染日志」会实时打印 Manim 输出，出现错误时可直接在这里排查问题。',
                    side: 'left'
                },
                onHighlightStarted: (el) => {
                    goToAndScroll('devtools', el);
                    if (typeof window.switchDevTool === 'function') window.switchDevTool('manim');
                }
            },
            // --- 教学案例（跳转到案例页并高亮内容区）---
            {
                element: '#examples .section-title',
                popover: {
                    title: '15. 教学案例',
                    description: '最后，到「教学案例」中查看现成的动画示例与你的渲染结果，配合时间戳笔记、错题本和课件包，形成完整的学习闭环。',
                    side: "bottom"
                },
                onHighlightStarted: (el) => goToAndScroll('examples', el)
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

function runRoleTour(driverFn, role) {
    const stepsByRole = {
        student: [
            {
                element: '.role-start-section',
                popover: {
                    title: '👩‍🎓 我是学生：从这里开始',
                    description: '这一行是「按角色快速开始」。你可以根据自己的身份选择不同路线：学生适合从【教学案例】+【动态计算】开始，先看例题再做可视化推演。',
                    side: 'bottom',
                    align: 'start'
                },
                onHighlightStarted: (el) => goToAndScroll('home', el)
            },
            {
                element: '#examples .section-title',
                popover: {
                    title: '1. 先看教学案例',
                    description: '在「教学案例」中选一个你关心的知识点，点击卡片即可全屏播放，并支持时间戳笔记与弹幕互动。',
                    side: 'bottom'
                },
                onHighlightStarted: (el) => goToAndScroll('examples', el)
            },
            {
                element: '#examples-grid',
                popover: {
                    title: '2. 在例题里做笔记',
                    description: '播放时可以添加「时间戳笔记」，系统会记住你看到的关键步骤，后续还能一键把笔记转成练习题。',
                    side: 'top'
                },
                onHighlightStarted: (el) => goToAndScroll('examples', el)
            },
            {
                element: '#calculate .section-title',
                popover: {
                    title: '3. 用动态计算复盘',
                    description: '看完例题后，切到「动态计算」，输入题目或已有公式，逐步探索图形并生成自己的动画讲解。',
                    side: 'bottom'
                },
                onHighlightStarted: (el) => goToAndScroll('calculate', el)
            }
        ],
        teacher: [
            {
                element: '.role-start-section',
                popover: {
                    title: '👨‍🏫 我是老师：课包路线',
                    description: '你可以把一节课拆成多个「教学案例」，再通过【我的课件】分组形成课包，反复使用。',
                    side: 'bottom',
                    align: 'start'
                },
                onHighlightStarted: (el) => goToAndScroll('home', el)
            },
            {
                element: '#detect .section-title',
                popover: {
                    title: '1. 从板书/讲义识别公式',
                    description: '在「智能识别」中上传板书或讲义截图，把公式快速转成 LaTeX，检查后保存到「我的算式」。',
                    side: 'bottom'
                },
                onHighlightStarted: (el) => goToAndScroll('detect', el)
            },
            {
                element: '#devtools .tools-list',
                popover: {
                    title: '2. 在 Manim 工作台生成课堂动画',
                    description: '进入「开发者工具」，选择 Manim 工作台，从算式库或 Rainbow 拓展里导入脚本，生成课堂用动画视频。',
                    side: 'right'
                },
                onHighlightStarted: (el) => goToAndScroll('devtools', el)
            },
            {
                element: '#examples .examples-filter-tabs',
                popover: {
                    title: '3. 把视频加入课件包',
                    description: '在「教学案例」中播放刚才生成的视频，点击播放页里的「加入课件包」。之后在筛选栏选择「我的课件」即可看到整套课包。',
                    side: 'bottom'
                },
                onHighlightStarted: (el) => goToAndScroll('examples', el)
            }
        ],
        creator: [
            {
                element: '.role-start-section',
                popover: {
                    title: '🎬 内容创作者：短视频流水线',
                    description: '适合做数学/科普短视频：一边写脚本，一边预览效果，并可导出弹幕发布包。',
                    side: 'bottom',
                    align: 'start'
                },
                onHighlightStarted: (el) => goToAndScroll('home', el)
            },
            {
                element: '#devtools .tools-list',
                popover: {
                    title: '1. 进入 Manim 工作台 / Rainbow 组件',
                    description: '在「开发者工具」中选择 Manim 工作台或 Rainbow 拓展组件，快速加载现成脚本再做改动。',
                    side: 'right'
                },
                onHighlightStarted: (el) => goToAndScroll('devtools', el)
            },
            {
                element: '#devtools #dev-manim',
                popover: {
                    title: '2. 编写或调整脚本并渲染',
                    description: '在编辑器里调整脚本细节，使用快捷键 Ctrl+Enter 预览动画，直到画面满足你的讲解需求。',
                    side: 'left'
                },
                onHighlightStarted: (el) => goToAndScroll('devtools', el)
            },
            {
                element: '#examples .section-title',
                popover: {
                    title: '3. 在教学案例中预览成片',
                    description: '将脚本生成的视频保存为教学案例，使用自定义播放器查看弹幕、进度和关键帧，再导出「发布包」上传至 B 站等平台。',
                    side: 'bottom'
                },
                onHighlightStarted: (el) => goToAndScroll('examples', el)
            }
        ],
        developer: [
            {
                element: '.role-start-section',
                popover: {
                    title: '👨‍💻 开发者：组件化你的 Manim 代码',
                    description: '如果你更习惯写代码，可以把常用的 Manim 脚本整理成可复用组件，在站内一键载入与改编。',
                    side: 'bottom',
                    align: 'start'
                },
                onHighlightStarted: (el) => goToAndScroll('home', el)
            },
            {
                element: '#devtools .tools-list',
                popover: {
                    title: '1. 在开发者工具管理脚本',
                    description: '使用「Manim 工作台」编写和调试脚本，保存到动画脚本库后，可在多处一键导入使用。',
                    side: 'right'
                },
                onHighlightStarted: (el) => goToAndScroll('devtools', el)
            },
            {
                element: '#devtools .tools-list button[onclick*=\"rainbow\"]',
                popover: {
                    title: '2. 参考 Rainbow 扩展组件',
                    description: '在 Rainbow 拓展区浏览示例组件，学习推荐的脚本结构与参数设计，然后按同样方式整理自己的组件。',
                    side: 'right'
                },
                onHighlightStarted: (el) => goToAndScroll('devtools', el)
            },
            {
                element: '#my-formulas',
                popover: {
                    title: '3. 与算式/课件联动',
                    description: '将脚本与「我的算式」及「课件包」联动：算式 → 动画脚本 → 教学案例，形成完整的开发-教学闭环。',
                    side: 'top'
                },
                onHighlightStarted: (el) => goToAndScroll('my-formulas', el)
            }
        ]
    };

    const steps = stepsByRole[role] || stepsByRole.student;
    const tour = driverFn({
        showProgress: true,
        animate: true,
        allowClose: true,
        doneBtnText: "我知道了",
        nextBtnText: "下一步",
        prevBtnText: "上一步",
        progressText: "步骤 {{current}} / {{total}}",
        popoverClass: 'driverjs-theme',
        steps
    });
    tour.drive();
}

// 检查自动播放
export function checkAutoPlay() {
    if (!localStorage.getItem('tutorial_played')) {
        setTimeout(startTutorial, 1500);
    }
}