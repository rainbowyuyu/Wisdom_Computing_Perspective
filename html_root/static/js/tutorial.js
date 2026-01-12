// static/js/tutorial.js
import { showSection, switchInputMode } from './ui.js';

export function startTutorial() {
    const driver = window.driver.js.driver;

    const tour = driver({
        showProgress: true,
        animate: true,
        allowClose: true,
        doneBtnText: "开始探索",
        nextBtnText: "下一步",
        prevBtnText: "上一步",
        progressText: "{{current}} / {{total}}",
        steps: [
            {
                element: '.logo',
                popover: {
                    title: '👋 欢迎来到智算视界',
                    description: '这是一个将数学公式转化为动态可视化视频的智能平台。让我们花 1 分钟了解如何使用它。',
                    side: "bottom",
                    align: 'start'
                }
            },
            {
                element: '.nav-links button:nth-child(2)', // 智能识别按钮
                popover: {
                    title: '第一步：输入公式',
                    description: '点击这里进入识别工作区。支持手写绘制或上传图片。',
                    side: "bottom"
                },
                // 关键：在这一步自动跳转到 Detect 页面
                onHighlightStarted: () => {
                    showSection('detect');
                }
            },
            {
                element: '#draw-tools',
                popover: {
                    title: '✏️ 手写画板',
                    description: '在这里像在纸上一样书写矩阵或公式。左侧是画笔、橡皮和撤销工具。',
                    side: "right"
                }
            },
            {
                element: '.tab-switch button:nth-child(2)', // 上传按钮
                popover: {
                    title: '📷 图片上传',
                    description: '如果是印刷体或已有图片，也可以直接上传识别。',
                    side: "bottom"
                },
                onHighlightStarted: () => {
                    switchInputMode('upload');
                },
                onDeselected: () => {
                    // 离开时切回画板，保持默认状态
                    switchInputMode('draw');
                }
            },
            {
                element: '.result-area',
                popover: {
                    title: '👀 实时预览与修改',
                    description: 'AI 识别的结果会显示在这里。您可以直接点击公式进行修改，或者展开下方查看 LaTeX 源码。',
                    side: "top"
                }
            },
            {
                element: '.btn-calc-go', // 生成动画按钮
                popover: {
                    title: '🚀 生成动画',
                    description: '确认公式无误后，点击这里生成 Manim 视频。',
                    side: "top"
                }
            },
            {
                element: '.nav-links button:nth-child(3)', // 动态计算
                popover: {
                    title: '🧮 更多参数配置',
                    description: '如果需要进行复杂的矩阵运算（如乘法、求逆），可以在“动态计算”页面手动配置两个矩阵。',
                    side: "bottom"
                },
                onHighlightStarted: () => {
                    showSection('calculate');
                }
            },
            {
                element: '.nav-links button:nth-child(6)', // 设置按钮
                popover: {
                    title: '⚙️ 个性化设置',
                    description: '在这里可以自定义快捷键（如 Ctrl+Z 撤销），让操作更顺手。',
                    side: "bottom"
                }
            }
        ],
        onDestroyed: () => {
            // 引导结束或跳过时，回到首页
            showSection('home');
            localStorage.setItem('tutorial_played', 'true');
        }
    });

    tour.drive();
}

// 检查是否需要自动播放
export function checkAutoPlay() {
    if (!localStorage.getItem('tutorial_played')) {
        setTimeout(startTutorial, 1000); // 延迟1秒播放，让页面先加载完
    }
}