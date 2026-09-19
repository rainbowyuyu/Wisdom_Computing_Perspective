import { executeNodeAction, getNodeById } from './site-graph.js?v=20260917-ecosystem-6';
import { loadScript } from './lazy-assets.js';
import { showToast } from './ui.js';

let activeTour;
let generation = 0;
const steps = [
    { node: 'home-account', element: '.account-access-card', title: '先了解你的学习账户', description: '在首页查看账户类型与剩余额度。登录后，题解、错题和课包可以保存在你的账户中。' },
    { node: 'examples-curriculum', element: '.curriculum-filters', title: '从一道典型例题开始', description: '按高中、大学和题型筛选，直接阅读已有分步解答，也可以把题目填入计算页。' },
    { node: 'calc-normal', element: '.tutor-composer', title: '输入题目，探索每一步', description: '支持完整题面和 LaTeX；解题后可查看推导、交互图形和动画，并保存、导出或加入课包。' },
    { node: 'agent-tasks', element: '.math-task-board', title: '复杂题交给后台任务', description: '在智能体中选择拆解模式，安排多个任务。切换页面后仍可查看子题进度或继续未完成部分。' },
    { node: 'calc-import', element: '.formulas-sub-nav', title: '把理解积累成学习资料', description: '在我的算式中阅读题解、复用脚本和模板；教学案例中还可以整理错题本与课包。' },
    { node: 'home-nebula', element: '#knowledge-panel', title: '随时从星云继续探索', description: '悬浮球显示任务进度。展开后，沿知识图谱的前后连接跳转，也能查看学习成就。' },
];

export async function startSiteTour() {
    const run = ++generation;
    activeTour?.destroy();
    try {
        const factory = () => window.driver?.js?.driver || window['driver.js']?.driver;
        await loadScript('https://cdn.jsdelivr.net/npm/driver.js@1.0.1/dist/driver.js.iife.js', () => !!factory());
        if (run !== generation) return;
        let index = 0, moving = false, closed = false;
        const tour = factory()({
            animate: !matchMedia('(prefers-reduced-motion: reduce)').matches,
            showProgress: true, progressText: '{{current}} / {{total}}', allowClose: true,
            nextBtnText: '下一步', prevBtnText: '上一步', doneBtnText: '开始探索',
            popoverClass: 'site-guide',
            steps: steps.map(step => ({ element: step.element, popover: { title: step.title, description: step.description } })),
            onNextClick: () => { if (index === steps.length - 1) tour.destroy();else void go(index + 1); },
            onPrevClick: () => { if (index > 0) void go(index - 1); },
            onDestroyed: () => { closed = true;if (activeTour === tour) activeTour = null; },
        });
        activeTour = tour;
        async function go(next) {
            if (moving || closed) return;
            moving = true;
            try {
                if (!await executeNodeAction(getNodeById(steps[next].node))) throw new Error('此步骤暂时无法打开，请稍后重试');
                await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                if (closed || run !== generation) return;
                index = next;tour.drive(index);
            } catch (error) { tour.destroy();showToast(error.message, 'error'); }
            finally { moving = false; }
        }
        await go(0);
    } catch { showToast('入门引导加载失败，请重试；也可从帮助页阅读解题指南。', 'error'); }
}
