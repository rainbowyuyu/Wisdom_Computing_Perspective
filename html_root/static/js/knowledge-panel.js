import { mountTaskProgress } from '/static/js/task-progress.js';
/**
 * 智算星云 - 全局浮动面板
 * 统计性与功能性并存，每页展示相关用户统计与快捷入口
 */
// showSection / openDoc / switchDevTool 由 window 全局提供

import { getMetroPathForSection, getNodeById, executeNodeAction } from './site-graph.js?v=20260917-ecosystem-6';
import {
    loadAchievementCardManifest,
    getCardMeta,
    renderHoloCardHtml,
    renderAchievementHoloGrid,
    bindHoloCardTilt,
} from './achievement-cards.js?v=20260917-artwork-3';

const WRONGBOOK_STORAGE_KEY = 'wcp_examples_wrongbook_v1';

function getCurrentUser() {
    const userSpan = document.getElementById('username-span');
    const userDisplay = document.getElementById('user-display');
    if (userDisplay && userDisplay.style.display !== 'none' && userSpan) {
        return userSpan.innerText;
    }
    return null;
}

/** 获取用户相关统计数据（供各页星云展示） */
let statsCache=null,statsPending=null,statsEpoch=0;
function invalidateStats(){statsEpoch++;statsCache=null;statsPending=null;}
window.addEventListener('auth-state-change',invalidateStats);
for(const type of ['wrongbook-updated','course-packs-updated','formula-library-updated','formula-library-deleted'])window.addEventListener(type,invalidateStats);
async function fetchUserStats() {
    const user=getCurrentUser();
    const stats={formulas:0,scripts:0,templates:0,wrongbook:0,tutorialDone:!!localStorage.getItem('tutorial_played')};
    if(!user){try{const rows=JSON.parse(localStorage.getItem(WRONGBOOK_STORAGE_KEY)||'[]');stats.wrongbook=Array.isArray(rows)?rows.length:0;}catch{}return stats;}
    if(statsCache?.user===user&&Date.now()-statsCache.at<30000)return {...stats,...statsCache.data};
    if(statsPending?.user===user)return statsPending.promise;
    const version=statsEpoch;
    const promise=(async()=>{
        try{
            const response=await fetch('/api/user/stats',{credentials:'include',signal:AbortSignal.timeout(10000)});
            const data=await response.json();
            if(!response.ok||data.status!=='success')throw new Error('统计暂不可用');
            if(version===statsEpoch)statsCache={user,at:Date.now(),data:data.data};
            return {...stats,...data.data};
        }catch{return stats;}
        finally{if(version===statsEpoch)statsPending=null;}
    })();
    statsPending={user,promise};return promise;
}

/** 成就式进度条（条状图） */
function renderAchievementBar(label, value, max, icon = '') {
    const cap = Math.max(1, max || 20);
    const pct = Math.min(100, Math.round((Number(value) || 0) / cap * 100));
    const ico = icon ? `<i class="fa-solid ${icon}"></i>` : '';
    return `
        <div class="knowledge-achievement-item">
            <div class="knowledge-achievement-header">
                <span class="knowledge-achievement-label">${ico} ${escapeHtml(label)}</span>
                <span class="knowledge-achievement-meta">${value} / ${cap}</span>
            </div>
            <div class="knowledge-achievement-bar">
                <div class="knowledge-achievement-bar-inner" style="width:${pct}%;"></div>
            </div>
        </div>
    `;
}

/** 环形进度图 */
function renderRingChart(label, value, max) {
    const cap = Math.max(1, max || 100);
    const pct = Math.min(100, Math.round((Number(value) || 0) / cap * 100));
    const r = 18;
    const circ = 2 * Math.PI * r;
    const dash = (pct / 100) * circ;
    return `
        <div class="knowledge-ring-item">
            <svg class="knowledge-ring-svg" viewBox="0 0 44 44">
                <circle class="knowledge-ring-bg" cx="22" cy="22" r="${r}"/>
                <circle class="knowledge-ring-fill" cx="22" cy="22" r="${r}" stroke-dasharray="${dash} ${circ}"/>
            </svg>
            <span class="knowledge-ring-label">${escapeHtml(label)}<br>${value}</span>
        </div>
    `;
}

/** 多栏并排条状图 */
function renderMultiBar(items, maxEach = 20) {
    const cap = Math.max(1, maxEach);
    return `
        <div class="knowledge-multibar">
            ${items.filter(it => it && it.label != null).map(it => {
                const v = Number(it.value) || 0;
                const pct = Math.min(100, Math.round(v / cap * 100));
                return `
                <div class="knowledge-multibar-row">
                    <span class="knowledge-multibar-label">${escapeHtml(it.label)}</span>
                    <div class="knowledge-multibar-track">
                        <div class="knowledge-multibar-fill" style="width:${pct}%;"></div>
                    </div>
                    <span class="knowledge-multibar-value">${v}</span>
                </div>
            `}).join('')}
        </div>
    `;
}

/** 成就徽章（单枚） */
function renderBadge(label, value, icon, unlocked) {
    const cls = unlocked ? 'knowledge-badge unlocked' : 'knowledge-badge';
    const ico = icon || 'fa-star';
    return `<div class="${cls}"><i class="fa-solid ${ico}"></i><span>${escapeHtml(label)} ${value}</span></div>`;
}

/** 获取成就列表（含 DB 读写，仅登录用户参与成就系统） */
async function fetchAchievements(stats) {
    const user = getCurrentUser();
    // 未登录：不参与成就系统，不请求后端
    if (!user) return [];
    const params = new URLSearchParams({
        formulas: String(stats.formulas || 0),
        scripts: String(stats.scripts || 0),
        templates: String(stats.templates || 0),
        wrongbook: String(stats.wrongbook || 0),
        tutorial_done: stats.tutorialDone ? 'true' : 'false',
        username: user,
    });
    try {
        const res = await fetch(`/api/achievements/list?${params}`);
        const d = await res.json();
        if (d.status === 'success' && Array.isArray(d.data)) return d.data;
    } catch (_) {}
    return [];
}

/** 同步成就到数据库 */
async function syncAchievementToDb(achievementId, progress, unlocked) {
    const user = getCurrentUser();
    if (!user) return;
    try {
        await fetch('/api/achievements/upsert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: user, achievement_id: achievementId, progress, unlocked }),
        });
    } catch (_) {}
}

let _lastAllAchievements = [];

/** 根据成就 ID 跳转到对应功能区域（在统计面板与解锁弹窗中复用） */
function navigateToAchievement(achievement) {
    if (!achievement || !achievement.id) return;
    const id = String(achievement.id);
    // 新手教程：跳到帮助 Section
    if (id === 'tutorial') {
        if (typeof window.showSection === 'function') window.showSection('help');
        const helpSection = document.getElementById('help');
        if (helpSection && helpSection.scrollIntoView) {
            setTimeout(() => helpSection.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
        }
        return;
    }
    // 公式相关成就：跳转到「我的算式」
    if (id.startsWith('formulas_')) {
        if (typeof window.showSection === 'function') window.showSection('my-formulas');
        return;
    }
    // 脚本 / 模板成就：跳转到开发者工具 Manim 工作台
    if (id.startsWith('scripts_') || id.startsWith('templates_')) {
        if (typeof window.showSection === 'function') window.showSection('devtools');
        if (typeof window.switchDevTool === 'function') {
            setTimeout(() => window.switchDevTool('manim'), 120);
        }
        return;
    }
    // 错题本成就：跳转到教学案例页
    if (id.startsWith('wrongbook_')) {import('./wrongbook.js').then(W=>W.openWrongbook());}
}

/** 解锁成就弹窗：展示闪卡与跳转按钮，仅在首次解锁时出现 */
async function showAchievementUnlockModal(achievement) {
    const modal = document.getElementById('achievement-unlock-modal');
    if (!modal || !achievement) return;
    await loadAchievementCardManifest();
    // Native editors/readers own the top layer; do not interrupt a save with
    // an achievement overlay that the user cannot dismiss until the dialog closes.
    if(document.querySelector('dialog[open]')){
        window.showToast?.('已解锁：'+(achievement.label||'学习成就')+'，可在成就面板查看','success');
        return;
    }

    const cardHost = document.getElementById('achievement-unlock-holo');
    const meta = getCardMeta(achievement.id);
    if (cardHost) {
        if (meta) {
            cardHost.innerHTML = renderHoloCardHtml(
                {
                    ...meta,
                    label: achievement.label || meta.label,
                    condition: achievement.condition || meta.condition,
                },
                { size: 'lg', locked: false, showMeta: false },
            );
            bindHoloCardTilt(cardHost);
        } else {
            cardHost.innerHTML = `<p class="achievement-unlock-fallback">${escapeHtml(achievement.label || '已解锁成就')}</p>`;
        }
    }

    const closeAll = () => {
        if (typeof window.toggleModal === 'function') {
            window.toggleModal('achievement-unlock-modal', false);
        } else {
            modal.classList.remove('show');
            modal.style.display = 'none';
        }
    };

    const closeBtn = document.getElementById('achievement-unlock-close-btn');
    const xBtn = document.getElementById('achievement-unlock-close-x');
    const openPanelBtn = document.getElementById('achievement-unlock-open-panel-btn');
    if (closeBtn) closeBtn.onclick = (e) => { e.stopPropagation(); closeAll(); };
    if (xBtn) xBtn.onclick = (e) => { e.stopPropagation(); closeAll(); };
    if (openPanelBtn) {
        openPanelBtn.onclick = (e) => {
            e.stopPropagation();
            openAchievementPanel(_lastAllAchievements);
            closeAll();
        };
    }

    if (typeof window.toggleModal === 'function') {
        window.toggleModal('achievement-unlock-modal', true);
    } else {
        modal.style.display = 'flex';
        requestAnimationFrame(() => modal.classList.add('show'));
    }
}

/** 保存新成就并轻提示，完整闪卡由用户从成就面板主动打开。 */
function handleNewlyUnlockedAchievements(achievements) {
    if (!Array.isArray(achievements) || !achievements.length) return;
    // 后端返回的 db_unlocked 表示历史是否已解锁；仅在 db_unlocked 为 false 且当前 unlocked 为 true 时视为首次解锁
    const newly = achievements.filter(a => a && a.unlocked && !a.db_unlocked);
    if (!newly.length) return;
    // 先将这些成就写入数据库，标记为已解锁，避免下次再弹
    newly.forEach(a => {
        const progress = a.target || a.progress || 0;
        syncAchievementToDb(a.id, progress, true);
    });
    // Learning navigation and saves must never be interrupted by an automatic modal.
    newly.sort((a, b) => (b.target || 0) - (a.target || 0));
    window.showToast?.('已解锁：'+newly[0].label+'，可在成就面板查看闪卡','success');
}

/** 选取 5 个最接近完成的成就（未达成优先，按进度从高到低） */
function getTop5ClosestAchievements(achievements) {
    const list = Array.isArray(achievements) ? achievements : [];
    const incomplete = list.filter(a => !a.unlocked);
    const complete = list.filter(a => a.unlocked);
    incomplete.sort((a, b) => {
        const pa = a.target > 0 ? a.progress / a.target : 0;
        const pb = b.target > 0 ? b.progress / b.target : 0;
        return pb - pa;
    });
    const top = incomplete.slice(0, 5);
    const need = 5 - top.length;
    if (need > 0 && complete.length) top.push(...complete.slice(0, need));
    return top;
}

/** 成就轮播：横线段形式（5 个最接近完成），点击打开成就统计面板 */
function renderAchievementCarousel(achievements, allAchievements = []) {
    const list = getTop5ClosestAchievements(achievements);
    if (list.length === 0) return '';

    const items = list.map(a => {
        const pct = a.target > 0 ? Math.min(100, Math.round(a.progress / a.target * 100)) : 0;
        const segClass = a.unlocked ? 'achievement-seg unlocked' : 'achievement-seg';
        const ico = a.icon || 'fa-star';
        return `<div class="knowledge-achievement-seg-item" title="${escapeHtml(a.label)} ${a.progress}/${a.target}" data-achievement-id="${escapeHtml(a.id)}"><i class="fa-solid ${ico} achievement-seg-icon"></i><div class="${segClass}" style="--pct:${pct}%;"></div></div>`;
    }).join('');

    const wrapClass = 'knowledge-achievement-carousel knowledge-achievement-seg-carousel';
    const wrapId = 'knowledge-achievement-carousel-el';
    return `<div class="${wrapClass}" id="${wrapId}" data-count="${list.length}">${items}</div>`;
}

/** 星云气泡（创意展示：不同大小圆点代表数据，类似词云但更有空间感） */
function renderCloudBubbles(items, maxEach = 20) {
    const cap = Math.max(1, maxEach);
    return `
        <div class="knowledge-cloud-bubbles">
            ${items.filter(it => it && it.label != null).map((it, i) => {
                const v = Number(it.value) || 0;
                const pct = Math.min(100, Math.round(v / cap * 100));
                const size = 8 + Math.min(14, Math.max(0, pct / 100 * 12));  /* 8–20px */
                const hue = 220 + (i * 35) % 80;
                return `<span class="knowledge-bubble" data-label="${escapeHtml(it.label)}" data-value="${v}" style="--size:${size}px; --hue:${hue};"></span>`;
            }).join('')}
            <span class="knowledge-cloud-hint">悬停查看</span>
        </div>
    `;
}

/** 里程碑提示（达成或接近时显示鼓励文案） */
function renderMilestoneHint(stats, milestones = { formulas: 10, scripts: 5, templates: 3 }) {
    const hints = [];
    if (stats.formulas >= milestones.formulas) hints.push({ icon: 'fa-calculator', text: '算式积累破 10，继续深耕数学可视化！' });
    else if (stats.formulas >= milestones.formulas - 2) hints.push({ icon: 'fa-fire', text: '还差一点，算式数量即将突破 10！' });
    if (stats.scripts >= milestones.scripts) hints.push({ icon: 'fa-video', text: '脚本创作达人，Manim 动画玩得溜～' });
    if (stats.templates >= milestones.templates) hints.push({ icon: 'fa-wand-magic-sparkles', text: '模板已就绪，智能体效率拉满' });
    if (!hints.length) hints.push({ icon: 'fa-seedling', text: '点滴积累，汇成星云。' });
    const h = hints[Math.floor(Math.random() * hints.length)];
    return `<div class="knowledge-milestone-hint"><i class="fa-solid ${h.icon}"></i> ${escapeHtml(h.text)}</div>`;
}

function escapeHtml(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
}

/** 获取当前 devtools 子标签 */
function getActiveDevtool() {
    const btn = document.querySelector('#devtools .tab-btn.active');
    if (!btn) return null;
    if (btn.dataset.tool) return btn.dataset.tool;
    const m = String(btn.getAttribute('onclick') || '').match(/switchDevTool\s*\(\s*['"](\w+)['"]\s*\)/);
    return m ? m[1] : null;
}

/** 用视口坐标定位；收起、展开及窗口缩放后仍能正确居中。 */
function centerMetroCurrent(metroWrap) {
    requestAnimationFrame(() => {
        const line = metroWrap.querySelector('.knowledge-metro-line');
        const current = line?.querySelector('.knowledge-metro-station.current');
        if (!line?.isConnected || !line.clientWidth || !current) return;
        const target = line.scrollLeft + current.getBoundingClientRect().left
            + current.offsetWidth / 2 - line.getBoundingClientRect().left - line.clientWidth / 2;
        line.scrollTo({ left: Math.max(0, target), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    });
}

let selectedMetroNode = null;
let metroResizeObserver;
window.addEventListener('nebula-panel-toggle', ({ detail }) => {
    if (detail?.collapsed !== false) return;
    const wrap = document.getElementById('knowledge-panel-metro');
    if (wrap) centerMetroCurrent(wrap);
});
window.addEventListener('graph-station-selected', ({ detail }) => {
    const node = getNodeById(detail?.nodeId);
    // Ignore missing nodes and late navigation results from another page/tab.
    if (!node || node.section !== currentPanelSection) return;
    if (node.section === 'devtools' && node.devtool && node.devtool !== getActiveDevtool()) return;
    selectedMetroNode = node;
    refreshMetroNav(currentPanelSection);
});

function renderMetroNav(sectionId) {
    const devtool = sectionId === 'devtools' ? getActiveDevtool() : null;
    if (selectedMetroNode?.section !== sectionId || (devtool && selectedMetroNode?.devtool !== devtool)) selectedMetroNode = null;
    const path = getMetroPathForSection(sectionId, devtool, selectedMetroNode?.id);
    const current = path.find(n => n.current);
    if (!current) return { html: '', hasNav: false };
    const station = n => `<button type="button" class="knowledge-metro-station ${n.current ? 'current' : ''}"
        ${n.current ? 'aria-current="step"' : ''} data-node-id="${escapeHtml(n.id)}" data-relation="${n.relation}">
        <span class="knowledge-metro-dot" aria-hidden="true"></span><span class="knowledge-metro-label">${escapeHtml(n.name)}</span></button>`;
    const group = (relation, label) => {
        const nodes = path.filter(n => n.relation === relation);
        return `<div class="knowledge-metro-branch" role="group" aria-label="${label}">
            <span class="knowledge-metro-caption">${label}${nodes.length ? ' · ' + nodes.length : ''}</span>
            <div class="knowledge-metro-options">${nodes.length ? nodes.map(station).join('') : '<span class="knowledge-metro-empty">暂无连接</span>'}</div></div>`;
    };
    const connector = '<span class="knowledge-metro-connector" aria-hidden="true">→</span>';
    return { hasNav: true, html: `
        <div class="knowledge-metro-current"><span class="knowledge-metro-current-pill">
            <i class="fa-solid fa-location-dot" aria-hidden="true"></i> 当前站：${escapeHtml(current.name)}</span></div>
        <div class="knowledge-metro-line" aria-label="知识图谱连接导航">
            <div class="knowledge-metro-track">${group('incoming', '前序入口')}${connector}${station(current)}${connector}${group('outgoing', '后续去向')}</div>
        </div>` };
}

function refreshMetroNav(sectionId) {
    const wrap = document.getElementById('knowledge-panel-metro');
    if (!wrap) return;
    const result = renderMetroNav(sectionId);
    metroResizeObserver?.disconnect();
    const hadFocus = wrap.contains(document.activeElement);
    wrap.innerHTML = result.html;
    wrap.style.display = result.hasNav ? '' : 'none';
    wrap.onclick = e => {
        const btn = e.target.closest('.knowledge-metro-station');
        if (!btn || !wrap.contains(btn)) return;
        e.stopPropagation();
        const node = getNodeById(btn.dataset.nodeId);
        if (node) void executeNodeAction(node, { skipFocus: true });
    };
    const line = wrap.querySelector('.knowledge-metro-line');
    if (!line) return;
    // Wheel scrolling is scoped to the rail; touch/trackpad and keyboard remain native.
    line.addEventListener('wheel', e => {
        if (e.ctrlKey || e.shiftKey || Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return;
        const delta = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? line.clientWidth : 1);
        const next = Math.max(0, Math.min(line.scrollWidth - line.clientWidth, line.scrollLeft + delta));
        if (Math.abs(next - line.scrollLeft) < 1) return;
        e.preventDefault();
        line.scrollLeft = next;
    }, { passive: false });
    if (hadFocus) line.querySelector('[aria-current="step"]')?.focus({ preventScroll: true });
    metroResizeObserver = new ResizeObserver(() => centerMetroCurrent(wrap));
    metroResizeObserver.observe(line);
    centerMetroCurrent(wrap);
}

/** 旧版简单统计行（兼容） */
function renderStatsRow(items) {
    if (!items || items.length === 0) return '';
    const filtered = items.filter(it => it != null && (it.value !== undefined && it.value !== null && it.label));
    if (filtered.length === 0) return '';
    return `
        <div class="knowledge-stats-row">
            ${filtered.map(it => `
                <div class="knowledge-stat-item">
                    <span class="knowledge-stat-value">${it.value}</span>
                    <span class="knowledge-stat-label">${it.label}</span>
                </div>
            `).join('')}
        </div>
    `;
}

const MILESTONE = 20;

const SECTION_CONFIG = {
    admin: {
        title: '账户管理',
        subtitle: '用户权限与使用额度',
        body: `<div class="knowledge-panel-tips"><p>在管理页搜索用户，调整 VIP、每日额度或账户状态。保存后，新的权限会用于后续请求。</p><p>个人额度留空时跟随默认值，管理记录可追溯最近的调整。</p><button type="button" class="knowledge-shortcut-btn full" onclick="showSection('home'); event.stopPropagation();"><i class="fa-solid fa-house"></i> 返回首页</button></div>`
    },
    home: {
        title: '智算星云',
        subtitle: '成就与快捷入口',
        renderCharts: (s, achievements = []) => {
            let html = '<div class="knowledge-ring-wrap">';
            html += renderRingChart('算式', s.formulas, MILESTONE);
            html += renderRingChart('脚本', s.scripts, MILESTONE);
            html += renderRingChart('模板', s.templates, MILESTONE);
            html += '</div>';
            html += renderCloudBubbles([
                { label: '算式', value: s.formulas },
                { label: '脚本', value: s.scripts },
                { label: '模板', value: s.templates },
                { label: '错题', value: s.wrongbook }
            ], MILESTONE);
            html += renderAchievementCarousel(achievements, achievements);
            return html;
        },
        body: `
            <div class="knowledge-panel-shortcuts">
                <button type="button" class="knowledge-shortcut-btn" onclick="showSection('agent'); event.stopPropagation();"><i class="fa-solid fa-robot"></i> 智能体</button>
                <button type="button" class="knowledge-shortcut-btn" onclick="showSection('detect'); event.stopPropagation();"><i class="fa-solid fa-camera"></i> 识别</button>
                <button type="button" class="knowledge-shortcut-btn" onclick="showSection('calculate'); event.stopPropagation();"><i class="fa-solid fa-calculator"></i> 计算</button>
                <button type="button" class="knowledge-shortcut-btn" onclick="showSection('examples'); event.stopPropagation();"><i class="fa-solid fa-play"></i> 案例</button>
            </div>
        `
    },
    agent: {
        title: '智能体助手',
        subtitle: '用自然语言完成任务',
        renderCharts: s => renderMultiBar([
            { label: '已存模板', value: s.templates },
            { label: '算式数', value: s.formulas }
        ], MILESTONE),
        body: `
            <div class="knowledge-panel-tips">
                <p>可对我说：</p>
                <ul>
                    <li>「识别这张图片中的公式」</li>
                    <li>「帮我推演 ∫x²dx」</li>
                    <li>「生成矩阵乘法的 Manim 动画」</li>
                </ul>
                <button type="button" class="knowledge-shortcut-btn full" onclick="showSection('my-formulas'); event.stopPropagation();"><i class="fa-solid fa-book"></i> 我的算式库</button>
            </div>
        `
    },
    detect: {
        title: '智能识别',
        subtitle: '手写 / 图片转公式',
        renderCharts: s => renderAchievementBar('已保存算式', s.formulas, MILESTONE, 'fa-camera'),
        body: `
            <div class="knowledge-panel-tips">
                <p>支持手写、拍照、上传图片识别公式，一键复制到动态计算或保存至算式库。</p>
                <button type="button" class="knowledge-shortcut-btn full" onclick="showSection('calculate'); event.stopPropagation();"><i class="fa-solid fa-calculator"></i> 去动态计算</button>
            </div>
        `
    },
    'my-formulas': {
        title: '知识星云',
        subtitle: '基于你的算式统计掌握度',
        body: 'dynamic'
    },
    calculate: {
        title: '动态计算',
        subtitle: '分步解题与动画',
        renderCharts: s => renderMultiBar([
            { label: '已存公式与题解', value: s.formulas },
            { label: '已存脚本', value: s.scripts }
        ], MILESTONE),
        body: `
            <div class="knowledge-panel-tips">
                <p>输入题目查看分步推导与交互图形。题解和动画可一并保存到我的算式，随时继续阅读。</p>
                <button type="button" class="knowledge-shortcut-btn full" onclick="showSection('my-formulas'); event.stopPropagation();"><i class="fa-solid fa-book"></i> 我的算式</button>
            </div>
        `
    },
    examples: {
        title: '教学案例',
        subtitle: '精选数学动画',
        renderCharts: s => renderAchievementBar('错题本收录', s.wrongbook, 15, 'fa-bookmark'),
        body: `
            <div class="knowledge-panel-tips">
                <p>浏览微积分、线性代数、几何等分类的 Manim 动画，可加入课件包或复用到工作台。</p><button type="button" class="knowledge-shortcut-btn full" onclick="window.openWrongbook?.(); event.stopPropagation();">打开错题本与复习</button>
                <button type="button" class="knowledge-shortcut-btn full" onclick="showSection('agent'); event.stopPropagation();"><i class="fa-solid fa-robot"></i> 打开智能体</button>
            </div>
        `
    },
    devtools: {
        title: '开发者工具',
        subtitle: 'Manim 工作台',
        renderCharts: s => renderMultiBar([
            { label: '脚本', value: s.scripts },
            { label: '算式', value: s.formulas }
        ], MILESTONE),
        body: `
            <div class="knowledge-panel-shortcuts">
                <button type="button" class="knowledge-shortcut-btn" onclick="showSection('devtools'); switchDevTool('manim'); event.stopPropagation();"><i class="fa-solid fa-code"></i> Manim</button>
                <button type="button" class="knowledge-shortcut-btn" onclick="showSection('devtools'); switchDevTool('latex'); event.stopPropagation();"><i class="fa-solid fa-square-root-variable"></i> LaTeX</button>
                <button type="button" class="knowledge-shortcut-btn full" onclick="showSection('my-formulas'); event.stopPropagation();"><i class="fa-solid fa-book"></i> 从算式库导入</button>
            </div>
        `
    },
    help: {
        title: '帮助中心',
        subtitle: '使用文档',
        renderCharts: (s, achievements = []) => {
            const tutorial = achievements.find(a => a.id === 'tutorial');
            if (tutorial) return renderAchievementCarousel([tutorial], achievements);
            return s.tutorialDone
                ? '<div class="knowledge-badge-wrap">' + renderBadge('新手教程', '已完成', 'fa-circle-check', true) + '</div>'
                : renderAchievementBar('完成新手教程', 0, 1, 'fa-graduation-cap');
        },
        body: `
            <div class="knowledge-panel-tips">
                <p>查看使用说明、隐私政策、更新日志等。</p>
                <button type="button" class="knowledge-shortcut-btn full" onclick="openDoc('update.md','更新日志'); event.stopPropagation();"><i class="fa-solid fa-file-lines"></i> 更新日志</button>
            </div>
        `
    }
};

function ensureCollapsedOnMobile(panel) {
    if (typeof window.matchMedia !== 'undefined' && window.matchMedia('(max-width: 768px)').matches && panel && !panel.classList.contains('collapsed')) {
        panel.classList.add('collapsed');
        panel.style.width = '56px';
        panel.style.height = '56px';
        const cnt = document.getElementById('knowledge-panel-content');
        const bbl = document.getElementById('knowledge-panel-bubble');
        if (cnt) cnt.style.display = 'none';
        if (bbl) bbl.style.display = 'flex';
        if (panel) panel.title = '点击打开智算星云';
    }
}

let refreshVersion = 0;
let currentPanelSection = 'home';
let dataRefreshTimer;
for(const event of ['wrongbook-updated','course-packs-updated','formula-library-updated','formula-library-deleted'])window.addEventListener(event,()=>{clearTimeout(dataRefreshTimer);dataRefreshTimer=setTimeout(()=>refreshKnowledgePanel(currentPanelSection),250);});
export async function refreshKnowledgePanel(sectionId) {
    currentPanelSection = sectionId;
    const version = ++refreshVersion;
    if (_carouselInterval) clearInterval(_carouselInterval);
    const panel = document.getElementById('knowledge-panel');
    const titleEl = document.getElementById('knowledge-panel-title');
    const subtitleEl = document.getElementById('knowledge-panel-subtitle');
    const dynamicEl = document.getElementById('knowledge-panel-dynamic');
    const staticEl = document.getElementById('knowledge-panel-static');

    if (!panel || !titleEl || !subtitleEl || !dynamicEl || !staticEl) return;

    // 预热闪卡清单，打开成就面板时无需等待
    loadAchievementCardManifest();

    const config = SECTION_CONFIG[sectionId] || SECTION_CONFIG.home;

    titleEl.textContent = config.title;
    subtitleEl.textContent = config.subtitle;

    refreshMetroNav(sectionId);

    if (config.body === 'dynamic') {
        dynamicEl.style.display = '';
        staticEl.style.display = 'none';
        staticEl.innerHTML = '';
        const statsEl = document.getElementById('knowledge-panel-dynamic-stats');
        if (statsEl) {
            fetchUserStats().then(stats => {
                if (version !== refreshVersion) return;
                statsEl.innerHTML = renderMultiBar([
                    { label: '算式', value: stats.formulas },
                    { label: '脚本', value: stats.scripts }
                ], MILESTONE);
                statsEl.style.display = '';
                const bodyEl = document.getElementById('knowledge-panel-body');
                if (bodyEl) bodyEl.scrollTop = 0;
            });
        }
        return;
    }

    dynamicEl.style.display = 'none';
    staticEl.style.display = '';

    const stats = await fetchUserStats();
    const achievements = await fetchAchievements(stats);
    if (version !== refreshVersion) return;
    if (stats.tutorialDone) syncAchievementToDb('tutorial', 1, true);
    handleNewlyUnlockedAchievements(achievements);
    _lastAllAchievements = achievements;
    const chartsHtml = config.renderCharts ? config.renderCharts(stats, achievements) : '';
    staticEl.innerHTML = (chartsHtml ? chartsHtml + '<div class="knowledge-panel-divider"></div>' : '') + config.body;

    // 成就点击：打开成就统计面板
    staticEl.querySelectorAll('.knowledge-achievement-seg-item').forEach(el => {
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            openAchievementPanel(_lastAllAchievements);
        });
    });

    startAchievementCarousel();
    const bodyEl = document.getElementById('knowledge-panel-body');
    if (bodyEl) bodyEl.scrollTop = 0;
    // Collapsed state is controlled by the floating panel and persisted by the user.
}

/** 星云内渲染进度：展开态显示进度条，折叠态小球水面填满 + 「渲染中」 */
export function initRenderProgressInNebula() {
    mountTaskProgress();
}

/** 成就轮播：多成就时定时横向滚动 */
let _carouselInterval = null;
function startAchievementCarousel() {
    if (_carouselInterval) clearInterval(_carouselInterval);
    _carouselInterval = null;
    const carousel = document.getElementById('knowledge-achievement-carousel-el');
    if (!carousel || parseInt(carousel.dataset.count || '0', 10) <= 1) return;
    let step = 0;
    _carouselInterval = setInterval(() => {
        if (!carousel.isConnected) { clearInterval(_carouselInterval); return; }
        if (document.hidden || document.getElementById("knowledge-panel")?.classList.contains("collapsed") || matchMedia("(prefers-reduced-motion: reduce)").matches || carousel.matches(":hover, :focus-within")) return;
        const maxScroll = carousel.scrollWidth - carousel.clientWidth;
        if (maxScroll <= 0) return;
        step = (step + 1) % 4;
        const target = (step / 3) * maxScroll;
        carousel.scrollTo({ left: target, behavior: 'smooth' });
    }, 3500);
}

/** 打开成就统计面板（独立窗口，闪卡展台） */
async function openAchievementPanel(achievements) {
    const modal = document.getElementById('achievement-panel-modal');
    if (!modal) return;
    const listEl = modal.querySelector('.achievement-panel-list');
    if (!listEl) return;
    await loadAchievementCardManifest();

    const list = Array.isArray(achievements) ? achievements : [];
    const unlocked = list.filter((a) => a && a.unlocked);
    const locked = list.filter((a) => a && !a.unlocked);

    const summaryHtml = `
        <div class="achievement-holo-summary">
            <div class="achievement-holo-summary-text">
                <strong>智算星云 · 成就闪卡</strong>
                <span>已解锁 ${unlocked.length} / ${list.length} · 拖动卡面可感受镭射光泽</span>
            </div>
            ${locked.length ? `<div class="achievement-badge-hint">继续使用站内功能，点亮更多闪卡～</div>` : ''}
        </div>
    `;

    const gridHtml = `
        <div class="achievement-holo-grid">
            ${renderAchievementHoloGrid(list, { size: 'sm' })}
        </div>
    `;

    listEl.innerHTML = summaryHtml + gridHtml;
    bindHoloCardTilt(listEl);

    listEl.querySelectorAll('.ach-holo-card').forEach((el) => {
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            const aid = el.getAttribute('data-achievement-id') || '';
            const ach = list.find((a) => a && String(a.id) === aid);
            if (!ach) return;
            if (ach.unlocked) {
                showAchievementUnlockModal(ach);
                if (typeof window.toggleModal === 'function') {
                    window.toggleModal('achievement-panel-modal', false);
                }
            } else {
                navigateToAchievement(ach);
                if (typeof window.toggleModal === 'function') {
                    window.toggleModal('achievement-panel-modal', false);
                }
            }
        });
    });

    if (typeof window.toggleModal === 'function') {
        window.toggleModal('achievement-panel-modal', true);
    } else {
        modal.style.display = 'flex';
        modal.classList.add('show');
    }
}
