import { renderWrongbook, editWrongbook, openWrongbook } from './wrongbook.js';
import { textWithMath } from './math-text.js';
import { createTeachingDanmaku } from './teaching-danmaku.js';
// static/js/examples.js — 教学案例：B 站风预览、点赞、评论与弹幕（登录后可发）
import { toggleModal, toggleAuthModal as staticAuthModal, showToast } from './ui.js';
import * as Settings from './settings.js';
import { editCoursePack, openCoursePack, renderCoursePacks, chooseCoursePack, importCoursePack, disposeCourseDialogs } from './course-packs.js';
function toggleAuthModal(show){if(window.toggleAuthModal&&window.toggleAuthModal!==toggleAuthModal)window.toggleAuthModal(show);else staticAuthModal(show);}

let examplesFilterMode = 'all';
let examplesTag = '';
let allTagsSet = new Set();
let examplesFilterTabsInited = false;
let examplesPage = 1;
const EXAMPLES_PAGE_SIZE_DESKTOP = 9;
const EXAMPLES_PAGE_SIZE_MOBILE = 4;
let examplesLastVideos = [];
let teachingCatalog = [];
let loadGeneration=0;
export async function ensurePlayer(){
    if(document.getElementById('video-modal'))return;
    const response=await fetch('/static/templates/teaching-player.html');if(!response.ok)throw new Error('播放器加载失败');
    const html=await response.text();if(document.getElementById('video-modal'))return;
    const container=document.createElement('div');container.id='teaching-player-host';container.innerHTML=html;document.body.append(container);
}
export async function mountExamples(host){
    await ensurePlayer();if(!host.isConnected)return()=>{};
    host.innerHTML='<h2 class="section-title">教学案例与课包</h2><p class="section-subtitle">观看、记录、备课，让每一次理解成为下一堂课的起点。</p><div id="examples-filter" class="examples-toolbar"><div class="examples-filter-tabs"><button class="examples-filter-tab active" data-filter="all">全部案例</button><button class="examples-filter-tab" data-filter="favorites">收藏</button><button class="examples-filter-tab" data-filter="watch_later">稍后看</button><button class="examples-filter-tab" data-filter="courseware">我的课件</button></div><button id="examples-create-course-btn" class="action-btn secondary">创建课包与教案</button><div class="examples-tag-filter"><label for="examples-tag-select">标签</label><select id="examples-tag-select" class="examples-tag-select"><option value="">全部</option></select></div></div><div id="examples-grid" class="video-grid"></div>';
    window.Examples={loadExamples,switchExamplesFilter,playExample,playExampleByVideoId,playCoursePack,closeVideoModal,openCoursePackModal,ensurePlayer,focusPlayerFeature};
    window.playExample=playExample;window.closeVideoModal=closeVideoModal;
    await loadExamples();
    const params=new URLSearchParams(location.search);if(host.isConnected&&params.get('video'))playExampleByVideoId(params.get('video'),Number(params.get('t')||0));
    return()=>{loadGeneration++;closeVideoModal();disposeCourseDialogs();};
}
window.addEventListener('course-packs-updated',()=>{if(document.querySelector('.examples-filter-tab.active')?.dataset.filter==='courseware')loadExamples();});
window.addEventListener('auth-state-change',()=>{closeVideoModal();document.querySelectorAll('.course-dialog').forEach(d=>{if(!d.querySelector('.course-editor'))d.close();});if(document.getElementById('examples-grid'))loadExamples();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!document.querySelector('dialog[open]')&&document.getElementById('video-modal')?.classList.contains('show')){e.preventDefault();e.stopImmediatePropagation();closeVideoModal();}},true);

function escapeAttr(str) { if (!str) return ''; return String(str).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

/** 安全播放：捕获 AbortError（被 load/pause 打断时）和 NotAllowedError，避免未处理的 Promise 拒绝 */
function safePlay(el) { if (el && typeof el.play === 'function') el.play().catch(() => {}); }

export async function loadExamples() {
    const generation=++loadGeneration;
    const grid = document.getElementById('examples-grid');
    if (!grid) return;
    initExamplesFilterTabs();

    const filterTab = document.querySelector('.examples-filter-tab.active');
    const filterMode = (filterTab && filterTab.dataset.filter) || 'all';
    const tagSelect = document.getElementById('examples-tag-select');
    const tag = (tagSelect && tagSelect.value) || '';
    grid.classList.toggle('course-pack-grid',filterMode==='courseware');
    grid.classList.toggle('wrongbook-host',filterMode==='wrongbook');
    for(const control of document.querySelectorAll('#examples-create-course-btn,.course-import'))control.hidden=filterMode==='wrongbook';
    if(tagSelect)tagSelect.closest('.examples-tag-filter').hidden=['courseware','wrongbook'].includes(filterMode);
    if(filterMode==='wrongbook'){const options=window.pendingWrongbookOptions||{};window.pendingWrongbookOptions=null;return renderWrongbook(grid,()=>generation===loadGeneration,options);}
    if(filterMode==='courseware'){document.querySelector('.examples-pagination')?.remove();return renderCoursePacks(grid,()=>generation===loadGeneration);}

    grid.innerHTML = '<div class="video-grid-loading"><i class="fa-solid fa-spinner"></i>加载案例中...</div>';

    const params = new URLSearchParams();
    if (filterMode !== 'all') params.set('filter_mode', filterMode);
    if (tag) params.set('tag', tag);
    const qs = params.toString();
    const url = '/api/examples' + (qs ? '?' + qs : '');

    try {
        const res = await fetch(url, { credentials: 'include' });
        const text = await res.text();
        if(generation!==loadGeneration||!grid.isConnected)return;
        let data;
        try {
            data = JSON.parse(text);
        } catch (_) {
            data = { status: 'error', message: res.ok ? '响应格式错误' : (text && text.length < 200 ? text : '服务异常(500)，请查看控制台或访问 /api/examples/health 排查') };
        }
        if (data.status === 'success') {
            const videos = data.data || [];
            teachingCatalog = videos;
            if (filterMode === 'all' && !tag && Array.isArray(videos)) {
                videos.forEach(v => { (v.tags || []).forEach(t => allTagsSet.add(String(t))); });
                if (tagSelect) {
                    const cur = tagSelect.value;
                    tagSelect.innerHTML = '<option value="">全部</option>' + Array.from(allTagsSet).sort().map(t => '<option value="' + escapeAttr(t) + '">' + escapeHtml(t) + '</option>').join('');
                    if (cur) tagSelect.value = cur;
                }
            }
            examplesPage = 1; // 每次重新加载重置到第一页
            renderExampleCards(videos);
            if (data.error) {
                grid.innerHTML = grid.innerHTML + '<div class="video-grid-error" style="margin-top:0.5rem;"><i class="fa-solid fa-info-circle"></i> ' + escapeHtml(data.error) + '</div>';
            }
        } else {
            const msg = data.message || '加载失败，请稍后再试';
            grid.innerHTML = '<div class="video-grid-error"><i class="fa-solid fa-circle-exclamation"></i>' + escapeHtml(msg) + '</div>';
        }
    } catch (e) {
        console.error(e);
        grid.innerHTML = '<div class="video-grid-error"><i class="fa-solid fa-wifi"></i>网络错误，请检查网络后重试</div>';
    }
}

/**
 * 切换教学案例筛选（供知识图谱、智能体调用）
 * @param {string} mode - 'all' | 'favorites' | 'watch_later' | 'courseware'
 * @returns {Promise<boolean>} 是否成功切换（登录校验失败时返回 false）
 */
export async function switchExamplesFilter(mode) {
    const valid = ['all', 'favorites', 'watch_later', 'courseware', 'wrongbook'].includes(mode);
    const filterMode = valid ? mode : 'all';
    if (filterMode === 'favorites' || filterMode === 'watch_later' || filterMode === 'courseware') {
        try {
            const res = await fetch('/api/user/me', { credentials: 'include' });
            const me = await res.json();
            if (!me || me.status !== 'success' || !me.username) {
                window.toggleAuthModal?.(true);
                if (typeof showToast === 'function') showToast('登录后可查看我的收藏、稍后看和课件包', 'info');
                return false;
            }
        } catch (_) {
            if (typeof showToast === 'function') showToast('网络错误，请稍后重试', 'error');
            return false;
        }
    }
    const tab = document.querySelector(`.examples-filter-tab[data-filter="${filterMode}"]`);
    if (tab) {
        document.querySelectorAll('.examples-filter-tab').forEach(b => b.classList.remove('active'));
        tab.classList.add('active');
    }
    initExamplesFilterTabs();
    await loadExamples();
    return true;
}

function initExamplesFilterTabs() {
    const toolbar=document.getElementById('examples-filter');
    if(!toolbar||toolbar.dataset.bound)return;
    toolbar.dataset.bound='true';
    if(!toolbar.querySelector('[data-filter=wrongbook]'))toolbar.querySelector('.examples-filter-tabs').insertAdjacentHTML('beforeend','<button class="examples-filter-tab" data-filter="wrongbook">错题本</button>');
    document.querySelectorAll('.examples-filter-tab').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const mode = (btn.dataset && btn.dataset.filter) || 'all';
            await switchExamplesFilter(mode);
        });
    });
    const tagSelect = document.getElementById('examples-tag-select');
    if (tagSelect) tagSelect.addEventListener('change', () => loadExamples());

    const createCourseBtn = document.getElementById('examples-create-course-btn');
    if (createCourseBtn) {
        createCourseBtn.disabled=false;createCourseBtn.title='创建教案、选择视频并保存课包';
        createCourseBtn.addEventListener('click', () => openCoursePackModal());
    }
    const importButton=document.createElement('label');importButton.className='action-btn tertiary course-import';importButton.innerHTML='导入课包<input type="file" accept="application/json,.json" hidden>';
    toolbar.append(importButton);importButton.querySelector('input').onchange=async e=>{try{await importCoursePack(e.target.files[0]);}catch(error){showToast(error.message,'error');}finally{e.target.value='';}};

}

/** 教师：打开教案与课包编辑器（入口统一在教学案例页） */
export function openCoursePackModal() { return editCoursePack(); }
window.openCoursePackModal=openCoursePackModal;


function formatDuration(sec) {
    if (sec == null || !Number.isFinite(sec) || sec < 0) return '';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    if (m >= 60) {
        const h = Math.floor(m / 60);
        return h + ':' + String(m % 60).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }
    return m + ':' + String(s).padStart(2, '0');
}

function renderExampleCards(videos) {
    const grid = document.getElementById('examples-grid');
    if (!grid) return;

    if (!Array.isArray(videos) || videos.length === 0) {
        const filterTab = document.querySelector('.examples-filter-tab.active');
        const isCourseware = filterTab && (filterTab.dataset.filter === 'courseware');
        grid.innerHTML = isCourseware
            ? '<div class="video-grid-empty video-grid-empty-courseware"><i class="fa-solid fa-chalkboard-user"></i>暂无课件包<p class="video-grid-empty-hint">点击「创建课包」将公式→动画打包成课堂案例，并生成课堂链接</p><button type="button" class="action-btn secondary" id="examples-create-course-btn-inline">创建课包</button></div>'
            : '<div class="video-grid-empty"><i class="fa-solid fa-film"></i>暂无视频案例</div>';
        const inlineBtn = document.getElementById('examples-create-course-btn-inline');
        if (inlineBtn) inlineBtn.onclick = () => document.getElementById('examples-create-course-btn')?.click();
        examplesLastVideos = videos;
        return;
    }

    examplesLastVideos = videos;

    const escapeHtml = (str) => {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    };
    const escapeAttr = (str) => {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    };

    const isMobile = window.innerWidth <= 768;
    const pageSize = isMobile ? EXAMPLES_PAGE_SIZE_MOBILE : EXAMPLES_PAGE_SIZE_DESKTOP;
    const total = videos.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (examplesPage > totalPages) examplesPage = totalPages;
    if (examplesPage < 1) examplesPage = 1;
    const start = (examplesPage - 1) * pageSize;
    const pageVideos = videos.slice(start, start + pageSize);

    const cardsHtml = pageVideos.map(v => {
        const url = escapeHtml(v.url || '');
        const title = escapeHtml(v.title || '');
        const description = escapeHtml(v.description || '');
        const videoId = escapeAttr(v.video_id || (v.filename ? v.filename.replace(/\.mp4$/i, '') : ''));
        const urlAttr = escapeAttr(v.url || '');
        const titleAttr = escapeAttr(v.title || '');
        const descAttr = escapeAttr(v.description || '');
        const spriteAttr = escapeAttr(v.sprite_url || '');
        const hlsAttr = escapeAttr(v.hls_url || '');
        const maskAttr = escapeAttr(v.mask_url || '');
        const highEnergyAttr = escapeAttr(Array.isArray(v.high_energy) ? JSON.stringify(v.high_energy) : '');
        const durationSec = v.duration_sec != null && Number.isFinite(v.duration_sec) ? String(v.duration_sec) : '';
        const spriteCols = v.sprite_cols != null ? String(v.sprite_cols) : '10';
        const spriteRows = v.sprite_rows != null ? String(v.sprite_rows) : '10';
        const durationLabel = v.duration_sec != null ? formatDuration(v.duration_sec) : '';
        const likeCount = Math.max(0, parseInt(v.like_count, 10) || 0);
        const durationBadge = durationLabel ? ('<span class="video-duration-badge">' + escapeHtml(durationLabel) + '</span>') : '';
        const fav = v.user_favorited ? ' fa-solid' : ' fa-regular';
        const watch = v.user_watch_later ? ' fa-solid' : ' fa-regular';
        const tagsList = Array.isArray(v.tags) && v.tags.length ? v.tags.slice(0, 4).map(t => '<span class="video-card-tag">' + escapeHtml(String(t)) + '</span>').join('') : '';
        return [
            '<div class="video-card" data-video-url="' + urlAttr + '" data-video-id="' + videoId + '" data-video-title="' + titleAttr + '" data-video-desc="' + descAttr + '" data-video-sprite="' + spriteAttr + '" data-video-duration="' + durationSec + '" data-video-sprite-cols="' + spriteCols + '" data-video-sprite-rows="' + spriteRows + '" data-video-hls="' + hlsAttr + '" data-video-mask="' + maskAttr + '" data-video-high-energy="' + highEnergyAttr + '">',
            '  <div class="thumbnail video-preview-container">',
            '    <video src="' + url + '#t=0.5" muted loop playsinline preload="metadata" onmouseover="this.play().catch(function(){})" onmouseout="this.pause(); this.currentTime=0.5;" style="width:100%; height:100%; object-fit:cover;"></video>',
            '    <div class="play-overlay"><i class="fa-solid fa-play-circle"></i></div>',
            durationBadge,
            '    <div class="video-card-meta"><span><i class="fa-regular fa-thumbs-up"></i> ' + likeCount + '</span></div>',
            '    <div class="video-card-actions" onclick="event.stopPropagation()">',
            '      <button type="button" class="video-card-action-btn' + (v.user_favorited ? ' active' : '') + '" data-action="favorite" data-video-id="' + videoId + '" title="收藏"><i class="' + fav + ' fa-star"></i></button>',
            '      <button type="button" class="video-card-action-btn' + (v.user_watch_later ? ' active' : '') + '" data-action="watch_later" data-video-id="' + videoId + '" title="稍后看"><i class="' + watch + ' fa-clock"></i></button>',
            '    </div>',
            '  </div>',
            '  <div class="info"><h4>' + title + '</h4><p>' + description + '</p>' + (tagsList ? '<div class="video-card-tags">' + tagsList + '</div>' : '') + '</div>',
            '</div>'
        ].join('');
    }).join('');

    let paginationHtml = '';
    if (totalPages > 1) {
        paginationHtml =
            '<div class="examples-pagination">' +
                '<button class="examples-page-btn examples-page-prev" ' + (examplesPage === 1 ? 'disabled' : '') + '>上一页</button>' +
                '<span class="examples-page-info">第 <span class="examples-page-number">' + examplesPage + '</span> / ' + totalPages + ' 页</span>' +
                '<button class="examples-page-btn examples-page-next" ' + (examplesPage === totalPages ? 'disabled' : '') + '>下一页</button>' +
            '</div>';
    }

    grid.innerHTML = cardsHtml + paginationHtml;

    if (totalPages > 1) {
        const prevBtn = grid.querySelector('.examples-page-prev');
        const nextBtn = grid.querySelector('.examples-page-next');
        if (prevBtn) {
            prevBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (examplesPage > 1) {
                    examplesPage -= 1;
                    renderExampleCards(examplesLastVideos);
                }
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (examplesPage < totalPages) {
                    examplesPage += 1;
                    renderExampleCards(examplesLastVideos);
                }
            });
        }
    }

    if (!grid.dataset.delegateBound) {
        grid.dataset.delegateBound = '1';
        grid.addEventListener('click', (e) => {
            const actionBtn = e.target.closest('.video-card-action-btn');
            if (actionBtn) {
                e.preventDefault();
                e.stopPropagation();
                const videoId = actionBtn.dataset.videoId;
                const action = actionBtn.dataset.action;
                if (action === 'favorite') toggleFavoriteOnCard(videoId, actionBtn);
                else if (action === 'watch_later') toggleWatchLaterOnCard(videoId, actionBtn);
                return;
            }
            const card = e.target.closest('.video-card');
            if (card) {
                const durationSec = card.getAttribute('data-video-duration');
                let highEnergy;
                try {
                    const s = card.getAttribute('data-video-high-energy');
                    highEnergy = s ? JSON.parse(s) : undefined;
                } catch (_) { highEnergy = undefined; }
                const opts = {
                    spriteUrl: card.getAttribute('data-video-sprite') || undefined,
                    durationSec: durationSec !== '' && durationSec != null ? parseFloat(durationSec, 10) : undefined,
                    spriteCols: parseInt(card.getAttribute('data-video-sprite-cols'), 10) || 10,
                    spriteRows: parseInt(card.getAttribute('data-video-sprite-rows'), 10) || 10,
                    hlsUrl: card.getAttribute('data-video-hls') || undefined,
                    maskUrl: card.getAttribute('data-video-mask') || undefined,
                    highEnergy: Array.isArray(highEnergy) ? highEnergy : undefined
                };
                playExample(
                    card.getAttribute('data-video-url') || '',
                    card.getAttribute('data-video-title') || '',
                    card.getAttribute('data-video-desc') || '',
                    card.getAttribute('data-video-id') || '',
                    opts
                );
            }
        });
    }
    initExamplesFilterTabs();
}

async function toggleFavoriteOnCard(videoId, btn) {
    try {
        const meRes = await fetch('/api/user/me', { credentials: 'include' });
        const me = await meRes.json();
        if (me.status !== 'success' || !me.username) {
            toggleAuthModal(true);
            return;
        }
    } catch (_) {
        if (typeof showToast === 'function') showToast('请先登录', 'error');
        return;
    }
    const isActive = btn.classList.contains('active');
    const method = isActive ? 'DELETE' : 'POST';
    const url = isActive ? '/api/examples/favorites?video_id=' + encodeURIComponent(videoId) : '/api/examples/favorites';
    const body = method === 'POST' ? JSON.stringify({ video_id: videoId }) : undefined;
    try {
        const res = await fetch(url, { method, credentials: 'include', headers: method === 'POST' ? { 'Content-Type': 'application/json' } : {}, body });
        const data = await res.json();
        if (data.status === 'success') {
            btn.classList.toggle('active', !!data.user_favorited);
            btn.querySelector('i').className = (data.user_favorited ? 'fa-solid' : 'fa-regular') + ' fa-star';
            if (typeof showToast === 'function') showToast(data.user_favorited ? '已收藏' : '已取消收藏', 'success');
        } else if (data.message && typeof showToast === 'function') showToast(data.message, 'error');
    } catch (_) { if (typeof showToast === 'function') showToast('网络错误', 'error'); }
}

async function toggleWatchLaterOnCard(videoId, btn) {
    try {
        const meRes = await fetch('/api/user/me', { credentials: 'include' });
        const me = await meRes.json();
        if (me.status !== 'success' || !me.username) {
            toggleAuthModal(true);
            return;
        }
    } catch (_) {
        if (typeof showToast === 'function') showToast('请先登录', 'error');
        return;
    }
    const isActive = btn.classList.contains('active');
    const method = isActive ? 'DELETE' : 'POST';
    const url = isActive ? '/api/examples/watch-later?video_id=' + encodeURIComponent(videoId) : '/api/examples/watch-later';
    const body = method === 'POST' ? JSON.stringify({ video_id: videoId }) : undefined;
    try {
        const res = await fetch(url, { method, credentials: 'include', headers: method === 'POST' ? { 'Content-Type': 'application/json' } : {}, body });
        const data = await res.json();
        if (data.status === 'success') {
            btn.classList.toggle('active', !!data.user_watch_later);
            btn.querySelector('i').className = (data.user_watch_later ? 'fa-solid' : 'fa-regular') + ' fa-clock';
            if (typeof showToast === 'function') showToast(data.user_watch_later ? '已加入稍后看' : '已移除', 'success');
        } else if (data.message && typeof showToast === 'function') showToast(data.message, 'error');
    } catch (_) { if (typeof showToast === 'function') showToast('网络错误', 'error'); }
}

let currentVideoId = '';
let currentVideoTitle = '';
/** 续播时间（秒），用于复习推荐「继续观看」 */
let currentVideoResumeTime = 0;
let danmakuList = [];
const danmakuShownCountRef = { value: 0 };
let playbackGeneration=0;
let playlist=null;
function mergeDanmaku(entries){
    const map=new Map();for(const d of [...danmakuList,...entries]){
        const key=d.id?String(d.id):JSON.stringify([d.time,d.username,d.text,d.color,d.mode]);map.set(key,d);
    }
    danmakuList=[...map.values()].sort((a,b)=>a.time-b.time);danmakuCanvasManager?.emit();renderDanmakuArchive();
}
let heartbeatTimerId = null;

/** 核心播放逻辑：HLS(MSE) 与 MP4 回退 */
let currentHlsInstance = null;

function destroyHls() {
    if (currentHlsInstance) {
        try { currentHlsInstance.destroy(); } catch (_) {}
        currentHlsInstance = null;
    }
}

function setVideoSource(player, url, opts = {}) {
    if (!player) return;
    destroyHls();
    const hlsUrl = opts.hlsUrl || (url && /\.m3u8(\?|$)/i.test(url) ? url : null);
    const Hls = typeof window !== 'undefined' && window.Hls;

    if (hlsUrl && Hls && Hls.isSupported()) {
        currentHlsInstance = new Hls({
            maxBufferLength: 30,
            maxMaxBufferLength: 60
        });
        currentHlsInstance.loadSource(hlsUrl);
        currentHlsInstance.attachMedia(player);
        currentHlsInstance.on(Hls.Events.ERROR, (_, data) => {
            if (data.fatal && data.type === Hls.ErrorTypes.NETWORK) {
                player.src = url && !/\.m3u8/i.test(url) ? url : '';
                player.load();
            }
        });
        player.removeAttribute('src');
    } else if (hlsUrl && player.canPlayType && player.canPlayType('application/vnd.apple.mpegurl')) {
        player.src = hlsUrl;
        player.load();
    } else {
        player.src = url || '';
        player.load();
    }
}

/** 雪碧图预览：当前视频的 sprite 元数据（由 playExample 设置） */
let currentSpriteUrl = '';
let currentSpriteCols = 10;
let currentSpriteRows = 10;
let currentSpriteDuration = 0;

function updatePreviewBox(progressTooltip, previewBox, previewTime, timeSec, duration) {
    const timeEl = previewTime || (progressTooltip && progressTooltip.querySelector('.custom-player-preview-time'));
    const boxEl = previewBox || (progressTooltip && progressTooltip.querySelector('.custom-player-preview-box'));
    if (timeEl) timeEl.textContent = formatDuration(timeSec);

    if (!boxEl || !currentSpriteUrl || !duration || duration <= 0) {
        if (progressTooltip) progressTooltip.classList.remove('has-sprite');
        return;
    }
    progressTooltip.classList.add('has-sprite');
    const total = currentSpriteCols * currentSpriteRows;
    const index = Math.min(Math.floor((timeSec / duration) * total), total - 1);
    const col = index % currentSpriteCols;
    const row = Math.floor(index / currentSpriteCols);
    const cellW = 160;
    const cellH = 90;
    boxEl.style.backgroundImage = `url(${currentSpriteUrl})`;
    boxEl.style.backgroundSize = `${currentSpriteCols * cellW}px ${currentSpriteRows * cellH}px`;
    boxEl.style.backgroundPosition = `-${col * cellW}px -${row * cellH}px`;
}
const DANMAKU_TRACKS = 8;
const DANMAKU_SPEED = 120;
const DANMAKU_GAP = 24;
const DANMAKU_POOL_MAX = 256;

/** Canvas 弹幕：requestAnimationFrame 60fps + 轨道碰撞 + 对象池 + 可选防挡蒙版 */
function createDanmakuCanvasManager() {
    return createTeachingDanmaku({getOpacity:()=>Settings.getDanmakuOpacity()/100,getFontSize:()=>({small:16,medium:20,large:26}[Settings.getDanmakuFontSize()]||20)});
}

let danmakuCanvasManager = null;

function loadVideoNotes(videoId) {
    const listEl = document.getElementById('video-notes-list');
    if (!listEl) return;
    listEl.innerHTML = '<div class="video-comment-item" style="color:rgba(255,255,255,0.5);">加载中…</div>';
    fetch('/api/examples/notes?video_id=' + encodeURIComponent(videoId), { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            if(videoId!==currentVideoId)return;
            if (data.status !== 'success' || !Array.isArray(data.data)) {
                listEl.innerHTML = '<div class="video-comment-item" style="color:rgba(255,255,255,0.5);">暂无笔记</div>';
                return;
            }
            const items = data.data;
            if (items.length === 0) {
                listEl.innerHTML = '<div class="video-comment-item" style="color:rgba(255,255,255,0.5);">暂无笔记，点击下方添加</div>';
                return;
            }
            listEl.innerHTML = items.map(n => {
                const t = Number(n.time_sec);
                const timeStr = formatDuration(t);
                const fullContent = (n.content || '').trim();
                const content = fullContent;
                const contentAttr = escapeAttr(fullContent.slice(0, 500));
                const titleAttr = escapeAttr(currentVideoTitle || '');
                return '<div class="video-note-item" data-time="' + t + '" data-content="' + contentAttr + '" data-time-sec="' + t + '" data-video-title="' + titleAttr + '" role="button" tabindex="0">' +
                    '<span class="video-note-time">' + escapeHtml(timeStr) + '</span><span class="video-note-content">' + escapeHtml(content) + '</span>' +
                    '<button type="button" class="video-note-delete" data-note-id="' + n.id + '" aria-label="删除笔记">删除</button><button type="button" class="video-note-to-exercise-btn" title="根据此笔记让智能体出一道同类练习题"><i class="fa-solid fa-pen-to-square"></i></button></div>';
            }).join('');
            listEl.querySelectorAll('.video-note-content').forEach(el=>textWithMath(el,el.textContent));
            listEl.querySelectorAll('.video-note-delete').forEach(button=>{button.onclick=async e=>{e.stopPropagation();button.disabled=true;try{const r=await fetch('/api/examples/notes/'+button.dataset.noteId,{method:'DELETE'});const result=await r.json();if(!r.ok||result.status!=='success')throw new Error(result.message||'删除失败');if(currentVideoId===videoId)loadVideoNotes(videoId);}catch(error){showToast(error.message,'error');button.disabled=false;}};});
            listEl.querySelectorAll('.video-note-item').forEach(el => {
                el.addEventListener('keydown',e=>{if(e.target===el&&(e.key==='Enter'||e.key===' ')){e.preventDefault();el.click();}});
                el.addEventListener('click', (e) => {
                    if (e.target.closest('button')) return;
                    const player = document.getElementById('example-video-player');
                    const time = parseFloat(el.dataset.time, 10);
                    if (player && Number.isFinite(time)) { player.currentTime = time; safePlay(player); }
                });
            });
            listEl.querySelectorAll('.video-note-to-exercise-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const item = btn.closest('.video-note-item');
                    if (!item) return;
                    const content = (item.dataset.content || '').trim();
                    const timeSec = item.dataset.timeSec || '0';
                    const videoTitle = (item.dataset.videoTitle || '').trim();
                    const timeStr = item.querySelector('.video-note-time') ? item.querySelector('.video-note-time').textContent : timeSec;
                    const prompt = '请根据以下学习笔记出一道同类数学练习题（含步骤与答案），以 Markdown 格式回复。\n\n笔记内容：' + (content || '(无)') + '\n视频时间点：' + timeStr + (videoTitle ? '\n视频：' + videoTitle : '');
                    closeVideoModal();import('./agent-workspace.js').then(A=>A.prefillAgent(prompt));
                });
            });
        })
        .catch(() => { listEl.innerHTML = '<div class="video-comment-item" style="color:rgba(255,255,255,0.5);">加载失败</div>'; });
}

let videoNotesBound = false;
function bindVideoNotesOnce() {
    if (videoNotesBound) return;
    videoNotesBound = true;
    const noteInput = document.getElementById('video-note-input');
    const noteSend = document.getElementById('video-note-send');
    if (!noteSend || !noteInput) return;
    noteSend.addEventListener('click', () => {
        const content = noteInput.value ? noteInput.value.trim() : '';
        if (!content || !currentVideoId) return;
        const player = document.getElementById('example-video-player');
        const timeSec = player && Number.isFinite(player.currentTime) ? player.currentTime : 0;
        const sentVideo=currentVideoId;
        noteSend.disabled = true;
        fetch('/api/examples/notes', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_id: currentVideoId, time_sec: timeSec, content })
        })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    if(currentVideoId!==sentVideo)return;
                    noteInput.value = '';
                    loadVideoNotes(currentVideoId);
                    if (typeof showToast === 'function') showToast('笔记已添加', 'success');
                } else if (data.message && typeof showToast === 'function') showToast(data.message, 'error');
            })
            .catch(() => { if (typeof showToast === 'function') showToast('网络错误', 'error'); })
            .finally(() => { noteSend.disabled = false; });
    });
    noteInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') noteSend.click(); });
}

function loadComments(videoId) {
    const listEl = document.getElementById('video-comments-list');
    if (!listEl) return;
    listEl.innerHTML = '<div class="video-comment-item" style="color:rgba(255,255,255,0.5);">加载中…</div>';
    fetch('/api/examples/comments?video_id=' + encodeURIComponent(videoId), { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            if(videoId!==currentVideoId)return;
            if (data.status !== 'success' || !Array.isArray(data.data)) {
                listEl.innerHTML = '<div class="video-comment-item" style="color:rgba(255,255,255,0.5);">暂无评论</div>';
                return;
            }
            const items = data.data;
            if (items.length === 0) {
                listEl.innerHTML = '<div class="video-comment-item" style="color:rgba(255,255,255,0.5);">暂无评论，登录后抢沙发～</div>';
                return;
            }
            listEl.innerHTML = items.map(c => {
                const timeStr = c.created_at ? new Date(c.created_at * 1000).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
                return '<div class="video-comment-item"><span class="video-comment-user">' + escapeHtml(c.username || '') + '</span><span class="video-comment-content">' + escapeHtml(c.content || '') + '</span><div class="video-comment-time">' + escapeHtml(timeStr) + '</div></div>';
            }).join('');
        })
        .catch(() => {
            listEl.innerHTML = '<div class="video-comment-item" style="color:rgba(255,255,255,0.5);">加载失败</div>';
        });
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/** 弹幕分段时长（秒），与后端 segment 一致 */
const DANMAKU_SEGMENT_SECONDS = 360;

function loadDanmaku(videoId, onLoaded) {
    danmakuList = [];
    danmakuShownCountRef.value = 0;
    if (!videoId) {
        if (onLoaded) onLoaded();
        return;
    }
    const loadSegment = (segmentIndex) =>
        fetch('/api/v1/danmaku/list?video_id=' + encodeURIComponent(videoId) + (segmentIndex != null ? '&segment_index=' + segmentIndex : ''), { credentials: 'include' })
            .then(r => r.json());
    loadSegment(null)
        .then(data => {
            if(videoId!==currentVideoId)return;
            const list = (data.code === 0 && Array.isArray(data.data)) ? data.data : [];
            const merged = list.map(d => {
                const [time, mode, color, author, content,id] = Array.isArray(d) ? d : [d.time,d.mode,d.color,d.username,d.text,d.id];
                return { id,time: Number(time),mode,color,text: content || '', username: author || '' };
            });
            mergeDanmaku(merged.filter(d => Number.isFinite(d.time)));
            if (onLoaded) onLoaded();
            if (danmakuCanvasManager) danmakuCanvasManager.resize();
        })
        .catch(() => {
            if (onLoaded) onLoaded();
        });
}

let danmakuVisible = true;
let currentDanmakuUsername = '';
let customPlayerBound = false;

/** WebSocket：在线人数 + 新弹幕实时推送 + 30s 心跳 */
let currentVideoWs = null;
let currentVideoWsHeartbeat = null;

function closeVideoWs() {
    if (currentVideoWsHeartbeat) {
        clearInterval(currentVideoWsHeartbeat);
        currentVideoWsHeartbeat = null;
    }
    if (currentVideoWs) {
        try { currentVideoWs.close(); } catch (_) {}
        currentVideoWs = null;
    }
    const el = document.getElementById('video-viewer-count');
    if (el) el.textContent = '';
}

function connectVideoWs(videoId) {
    closeVideoWs();
    if (!videoId) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/api/examples/ws/${encodeURIComponent(videoId)}`;
    try {
        const ws = new WebSocket(url);
        currentVideoWs = ws;
        ws.onmessage = (e) => {
            if(currentVideoWs!==ws||videoId!==currentVideoId)return;
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'viewer_count') {
                    const el = document.getElementById('video-viewer-count');
                    if (el) el.textContent = msg.count > 0 ? msg.count + ' 人正在看' : '';
                } else if (msg.type === 'new_danmaku' && msg.data) {
                    mergeDanmaku([msg.data]);
                } else if(msg.type==='delete_danmaku'){
                    danmakuList=danmakuList.filter(d=>d.id!==msg.id);danmakuCanvasManager?.emit();renderDanmakuArchive();
                }
            } catch (_) {}
        };
        ws.onclose = () => { if(currentVideoWs===ws)currentVideoWs = null; };
        ws.onopen = () => {
            if(currentVideoWs!==ws){ws.close();return;}
            currentVideoWsHeartbeat = setInterval(() => {
                if (currentVideoWs && currentVideoWs.readyState === WebSocket.OPEN)
                    currentVideoWs.send(JSON.stringify({ type: 'ping' }));
            }, 30000);
        };
    } catch (_) {}
}

function updateModalAuthUI(loggedIn) {
    const commentForm = document.getElementById('video-comment-form');
    const commentHint = document.getElementById('video-comment-login-hint');
    const danmakuWrap = document.getElementById('video-danmaku-input-wrap');
    const danmakuHint = document.getElementById('video-danmaku-login-hint');
    const noteForm = document.getElementById('video-note-form');
    const noteHint = document.getElementById('video-note-login-hint');
    if (commentForm) commentForm.style.display = loggedIn ? 'flex' : 'none';
    if (commentHint) commentHint.style.display = loggedIn ? 'none' : 'block';
    if (danmakuWrap) danmakuWrap.style.display = loggedIn ? 'flex' : 'none';
    if (danmakuHint) danmakuHint.style.display = loggedIn ? 'none' : 'block';
    if (noteForm) noteForm.style.display = loggedIn ? 'flex' : 'none';
    if (noteHint) noteHint.style.display = loggedIn ? 'none' : 'block';
}

if (typeof window !== 'undefined') {
    window.addEventListener('auth-success', () => {
        const modal = document.getElementById('video-modal');
        if (modal && modal.classList.contains('show')) {
            fetch('/api/user/me', { credentials: 'include' })
                .then(r => r.status === 200 ? r.json() : null)
                .then(data => {
                    const loggedIn = !!(data && data.status === 'success' && data.username);
                    updateModalAuthUI(loggedIn);
                    if (loggedIn) currentDanmakuUsername = data.username;
                })
                .catch(() => {});
        }
    });
}

function initCustomPlayer() {
    if (customPlayerBound) return;
    customPlayerBound = true;

    const player = document.getElementById('example-video-player');
    const wrapper = document.getElementById('video-player-wrapper');
    const centerPlay = document.getElementById('custom-player-center-play');
    const playBtn = document.getElementById('custom-player-play');
    const timeEl = document.getElementById('custom-player-time');
    const progressWrap = document.getElementById('custom-player-progress-wrap');
    const progressTrack = document.getElementById('custom-player-progress-track');
    const progressPlayed = document.getElementById('custom-player-progress-played');
    const progressLoaded = document.getElementById('custom-player-progress-loaded');
    const progressHover = document.getElementById('custom-player-progress-hover');
    const progressTooltip = document.getElementById('custom-player-progress-tooltip');
    const volumeBtn = document.getElementById('custom-player-volume-btn');
    const volumeSlider = document.getElementById('custom-player-volume-slider');
    const speedBtn = document.getElementById('custom-player-speed-btn');
    const speedMenu = document.getElementById('custom-player-speed-menu');
    const fullscreenBtn = document.getElementById('custom-player-fullscreen');

    function syncPlayPauseUI() {
        const paused = !player || player.paused;
        wrapper?.classList.toggle('is-paused',paused);
        playBtn?.setAttribute('aria-label',paused?'播放':'暂停');
        if (centerPlay) {
            centerPlay.classList.toggle('hidden', !paused);
            const icon = centerPlay.querySelector('i');
            if (icon) icon.className = 'fa-solid fa-play';
        }
        if (playBtn) {
            const icon = playBtn.querySelector('i');
            if (icon) icon.className = paused ? 'fa-solid fa-play' : 'fa-solid fa-pause';
        }
    }

    function syncTimeUI() {
        const cur = player ? player.currentTime : 0;
        const dur = player && player.duration && Number.isFinite(player.duration) ? player.duration : 0;
        if (timeEl) timeEl.textContent = formatDuration(cur) + ' / ' + formatDuration(dur);
        if (progressPlayed && dur > 0) progressPlayed.style.width = (cur / dur * 100) + '%';
        if(progressWrap){progressWrap.setAttribute('aria-valuemax',String(dur));progressWrap.setAttribute('aria-valuenow',String(Math.round(cur)));progressWrap.setAttribute('aria-valuetext',formatDuration(cur)+' / '+formatDuration(dur));}
    }

    function syncBufferUI() {
        if (!player || !progressLoaded) return;
        try {
            const b = player.buffered;
            if (b.length && player.duration) progressLoaded.style.width = (b.end(b.length - 1) / player.duration * 100) + '%';
        } catch (_) {}
    }

    function seekFromProgress(e) {
        if (!player || !progressTrack) return;
        const rect = progressTrack.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const p = Math.max(0, Math.min(1, x / rect.width));
        player.currentTime = p * (player.duration || 0);
    }

    if (player) {
        player.removeAttribute('controls');
        player.addEventListener('click', () => {
            if (player.paused) safePlay(player); else player.pause();
        });
        player.addEventListener('play', syncPlayPauseUI);
        player.addEventListener('pause', syncPlayPauseUI);
        player.addEventListener('timeupdate', syncTimeUI);
        player.addEventListener('progress', syncBufferUI);
        player.addEventListener('loadedmetadata', () => { syncTimeUI(); syncBufferUI(); });
    }

    if (centerPlay) centerPlay.addEventListener('click', (e) => { e.stopPropagation(); if (player) safePlay(player); });

    if (playBtn) playBtn.addEventListener('click', (e) => { e.stopPropagation(); if (player) (player.paused ? safePlay(player) : player.pause()); });

    if (progressWrap && progressTrack) {
        progressWrap.tabIndex=0;progressWrap.setAttribute('role','slider');progressWrap.setAttribute('aria-label','播放进度');progressWrap.setAttribute('aria-valuemin','0');
        progressWrap.addEventListener('keydown',e=>{
            if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
            e.preventDefault();e.stopPropagation();const dur=Number.isFinite(player.duration)?player.duration:0;
            player.currentTime=e.key==='Home'?0:e.key==='End'?dur:Math.max(0,Math.min(dur,player.currentTime+(e.key==='ArrowRight'?5:-5)));
        });
        let dragging=false;
        progressWrap.addEventListener('pointerdown',e=>{if(e.button!==0)return;dragging=true;progressWrap.setPointerCapture(e.pointerId);seekFromProgress(e);});
        progressWrap.addEventListener('pointermove',e=>{if(dragging)seekFromProgress(e);});
        progressWrap.addEventListener('pointerup',()=>{dragging=false;});
        progressWrap.addEventListener('pointercancel',()=>{dragging=false;});
        const previewTimeEl = document.getElementById('custom-player-preview-time');
        const previewBoxEl = document.getElementById('custom-player-preview-box');
        progressWrap.addEventListener('click', (e) => { e.stopPropagation(); seekFromProgress(e); });
        progressWrap.addEventListener('mousemove', (e) => {
            if (!player || !progressTrack || !progressTooltip || !progressHover) return;
            const rect = progressTrack.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const p = Math.max(0, Math.min(1, x / rect.width));
            const duration = player.duration && Number.isFinite(player.duration) ? player.duration : currentSpriteDuration;
            const t = p * (duration || 0);
            progressTooltip.style.left = (p * 100) + '%';
            progressHover.style.width = (p * 100) + '%';
            updatePreviewBox(progressTooltip, previewBoxEl, previewTimeEl, t, duration);
        });
        progressWrap.addEventListener('mouseleave', () => {
            if (progressHover) progressHover.style.width = '0%';
        });
    }

    const volumeWrap = document.getElementById('custom-player-volume-wrap');
    if (volumeSlider && player) {
        volumeSlider.addEventListener('input', () => {
            player.volume = volumeSlider.value / 100;
            if (volumeBtn) {
                const icon = volumeBtn.querySelector('i');
                if (icon) icon.className = player.volume === 0 ? 'fa-solid fa-volume-xmark' : player.volume < 0.5 ? 'fa-solid fa-volume-low' : 'fa-solid fa-volume-high';
            }
        });
    }
    if (volumeBtn && player) {
        volumeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (volumeWrap) volumeWrap.classList.toggle('volume-open');
            const icon = volumeBtn.querySelector('i');
            if (icon) icon.className = player.volume === 0 ? 'fa-solid fa-volume-xmark' : player.volume < 0.5 ? 'fa-solid fa-volume-low' : 'fa-solid fa-volume-high';
        });
        volumeBtn.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            if (player.volume > 0) {
                player.dataset.prevVolume = String(player.volume);
                player.volume = 0;
                volumeSlider.value = 0;
            } else {
                player.volume = parseFloat(player.dataset.prevVolume || '1', 10);
                volumeSlider.value = player.volume * 100;
            }
            const icon = volumeBtn.querySelector('i');
            if (icon) icon.className = player.volume === 0 ? 'fa-solid fa-volume-xmark' : player.volume < 0.5 ? 'fa-solid fa-volume-low' : 'fa-solid fa-volume-high';
        });
    }
    document.addEventListener('click', (e) => {
        if (volumeWrap && !volumeWrap.contains(e.target)) volumeWrap.classList.remove('volume-open');
    });

    if (speedMenu && speedBtn && player) {
        const rateStr = (r) => r + 'x';
        speedBtn.textContent = rateStr(player.playbackRate || 1);
        speedMenu.querySelectorAll('button').forEach(b => {
            if (Math.abs(parseFloat(b.getAttribute('data-rate'), 10) - (player.playbackRate || 1)) < 0.01) b.classList.add('active');
            b.addEventListener('click', () => {
                const rate = parseFloat(b.getAttribute('data-rate'), 10);
                player.playbackRate = rate;
                speedBtn.textContent = rateStr(rate);
                speedMenu.classList.remove('show');
                speedMenu.querySelectorAll('button').forEach(x => x.classList.remove('active'));
                b.classList.add('active');
            });
        });
        speedBtn.addEventListener('click', (e) => { e.stopPropagation(); speedMenu.classList.toggle('show'); });
    }

    document.addEventListener('click', (e) => {
        if (speedMenu && speedBtn && !speedMenu.contains(e.target) && e.target !== speedBtn) speedMenu.classList.remove('show');
    });

    if (fullscreenBtn && wrapper) {
        fullscreenBtn.addEventListener('click', () => {
            if (!document.fullscreenElement) {
                wrapper.requestFullscreen().then(() => {
                    const icon = fullscreenBtn.querySelector('i');
                    if (icon) icon.className = 'fa-solid fa-compress';
                }).catch(() => {});
            } else {
                document.exitFullscreen().then(() => {
                    const icon = fullscreenBtn.querySelector('i');
                    if (icon) icon.className = 'fa-solid fa-expand';
                }).catch(() => {});
            }
        });
    }
    document.addEventListener('fullscreenchange', () => {
        if (fullscreenBtn) {
            const icon = fullscreenBtn.querySelector('i');
            if (icon) icon.className = document.fullscreenElement ? 'fa-solid fa-compress' : 'fa-solid fa-expand';
        }
    });

    /* 键盘：空格播放/暂停，左右 5 秒，上下音量 */
    if (wrapper) {
        wrapper.addEventListener('keydown', (e) => {
            if (e.target.closest('input, textarea') || e.target.closest('.custom-player-speed-menu')) return;
            switch (e.key) {
                case ' ':
                    e.preventDefault();
                    if (player) (player.paused ? safePlay(player) : player.pause());
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    if (player) player.currentTime = Math.max(0, player.currentTime - 5);
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    if (player) player.currentTime = Math.min(player.duration || 0, player.currentTime + 5);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    if (player && volumeSlider) {
                        const v = Math.min(100, (player.volume * 100) + 10);
                        player.volume = v / 100;
                        volumeSlider.value = v;
                        showVolumeToast(Math.round(v));
                        if (volumeBtn) {
                            const icon = volumeBtn.querySelector('i');
                            if (icon) icon.className = player.volume === 0 ? 'fa-solid fa-volume-xmark' : player.volume < 0.5 ? 'fa-solid fa-volume-low' : 'fa-solid fa-volume-high';
                        }
                    }
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    if (player && volumeSlider) {
                        const v = Math.max(0, (player.volume * 100) - 10);
                        player.volume = v / 100;
                        volumeSlider.value = v;
                        showVolumeToast(Math.round(v));
                        if (volumeBtn) {
                            const icon = volumeBtn.querySelector('i');
                            if (icon) icon.className = player.volume === 0 ? 'fa-solid fa-volume-xmark' : player.volume < 0.5 ? 'fa-solid fa-volume-low' : 'fa-solid fa-volume-high';
                        }
                    }
                    break;
            }
        });
        wrapper.addEventListener('dblclick', (e) => {
            if (e.target.closest('.custom-player-controls')) return;
            e.preventDefault();
            if (!document.fullscreenElement) wrapper.requestFullscreen().catch(() => {});
            else document.exitFullscreen().catch(() => {});
        });
    }

    bindPlayerContextMenu();
    bindPlayerStatsPanel();
    bindHighEnergyBar();
    bindVolumeToast();

    window.syncCustomPlayerUI = function () {
        syncPlayPauseUI();
        syncTimeUI();
        syncBufferUI();
    };
}

let volumeToastTimer = null;
function showVolumeToast(percent) {
    const el = document.getElementById('player-volume-toast');
    if (!el) return;
    el.textContent = percent + '%';
    el.classList.add('show');
    clearTimeout(volumeToastTimer);
    volumeToastTimer = setTimeout(() => el.classList.remove('show'), 800);
}

function bindVolumeToast() {
    const volumeSlider = document.getElementById('custom-player-volume-slider');
    const player = document.getElementById('example-video-player');
    if (volumeSlider && player) {
        volumeSlider.addEventListener('input', () => {
            showVolumeToast(Math.round(volumeSlider.value));
        });
    }
}

function bindPlayerContextMenu() {
    const wrapper = document.getElementById('video-player-wrapper');
    const menu = document.getElementById('player-context-menu');
    if (!wrapper || !menu) return;
    menu.querySelectorAll('[data-action=color],[data-action=sound],[data-action=changelog]').forEach(b=>b.remove());
    wrapper.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        menu.classList.add('show');
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
        menu.querySelectorAll('button').forEach(btn => {
            const action = btn.getAttribute('data-action');
            if (action === 'loop') {
                const player = document.getElementById('example-video-player');
                btn.innerHTML = (player && player.loop ? '<i class="fa-solid fa-check"></i> ' : '<i class="fa-solid fa-repeat"></i> ') + '循环播放';
            }
        });
    });
    menu.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', () => {
            const action = btn.getAttribute('data-action');
            const player = document.getElementById('example-video-player');
            if (action === 'loop' && player) {
                player.loop = !player.loop;
                if (typeof showToast === 'function') showToast(player.loop ? '已开启循环' : '已关闭循环', 'success');
            } else if (action === 'copy' && player) {
                const url = currentVideoId ? location.origin + '/?section=examples&video=' + encodeURIComponent(currentVideoId) : '';
                if (url) navigator.clipboard.writeText(url).then(() => {
                    if (typeof showToast === 'function') showToast('已复制视频地址', 'success');
                }).catch(() => {});
            } else if (action === 'stats') {
                showPlayerStatsPanel();
            } else if (action === 'shortcuts' && typeof showToast === 'function') {
                showToast('空格 播放/暂停 · 左右键 进退 5 秒 · 上下键 音量', 'info');
            }
            menu.classList.remove('show');
        });
    });
    document.addEventListener('click', () => menu.classList.remove('show'));
}

function hidePlayerContextMenu() {
    const menu = document.getElementById('player-context-menu');
    if (menu) menu.classList.remove('show');
}

function showPlayerStatsPanel() {
    const panel = document.getElementById('player-stats-panel');
    const body = document.getElementById('player-stats-body');
    const player = document.getElementById('example-video-player');
    if (!panel || !body) return;
    const w = player ? player.videoWidth : 0;
    const h = player ? player.videoHeight : 0;
    const viewport = window.innerWidth + ' x ' + window.innerHeight;
    const lines = [
        'Player Logic: WisComPer Custom Player v1',
        'Video ID: ' + (currentVideoId || '-'),
        'Resolution: ' + (w && h ? w + ' x ' + h : '-'),
        'Codecs: avc1 (MP4)',
        'Viewport: ' + viewport,
        'Dropped Frames: N/A',
        'Network: N/A'
    ];
    body.textContent = lines.join('\n');
    panel.classList.add('show');
}

function hidePlayerStatsPanel() {
    const panel = document.getElementById('player-stats-panel');
    if (panel) panel.classList.remove('show');
}

function bindPlayerStatsPanel() {
    const closeBtn = document.getElementById('player-stats-close');
    const panel = document.getElementById('player-stats-panel');
    if (closeBtn && panel) closeBtn.addEventListener('click', () => hidePlayerStatsPanel());
}

const HIGH_ENERGY_SAMPLES = 100;
const HIGH_ENERGY_PEAK_THRESHOLD = 70;

let currentHighEnergyData = [];
let watchedSegments = [];

function getHighEnergyData(duration) {
    if (currentHighEnergyData.length > 0) return currentHighEnergyData;
    const len = Math.max(10, Math.min(HIGH_ENERGY_SAMPLES, Math.floor((duration || 60) / 2)));
    const arr = Array(len).fill(0);
    for(const bullet of danmakuList){const i=Math.floor(bullet.time/Math.max(1,duration||60)*len);if(i>=0&&i<len)arr[i]++;}
    return arr;
}

function mergeWatchedSegment(start, end) {
    const seg = [start, end];
    const out = [];
    for (const s of watchedSegments) {
        if (s[1] < seg[0] || s[0] > seg[1]) out.push(s);
        else {seg[0] = Math.min(seg[0], s[0]); seg[1] = Math.max(seg[1], s[1]);}
    }
    out.push(seg);
    out.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const s of out) {
        if (merged.length && merged[merged.length - 1][1] >= s[0] - 0.5)
            merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], s[1]);
        else merged.push([...s]);
    }
    watchedSegments = merged;
}

/** 复习推荐：显示「从 x:xx 继续观看」并绑定继续按钮 */
function updateResumeRecommendUI() {
    const block = document.getElementById('video-resume-recommend');
    const textEl = document.getElementById('video-resume-text');
    const btn = document.getElementById('video-resume-btn');
    const player = document.getElementById('example-video-player');
    if (!block || !textEl || !btn) return;
    if (currentVideoResumeTime > 0 && player && player.duration && currentVideoResumeTime < player.duration - 2) {
        block.style.display = 'flex';
        textEl.textContent = '上次观看到 ' + formatDuration(Math.floor(currentVideoResumeTime)) + '，';
        btn.onclick = () => {
            if (player && Number.isFinite(currentVideoResumeTime)) {
                player.currentTime = currentVideoResumeTime;
                safePlay(player);
            }
        };
    } else {
        block.style.display = 'none';
    }
}

/** 更新「已观看约 xx%」摘要文案 */
function updateVideoProgressSummary() {
    const el = document.getElementById('video-progress-summary');
    const player = document.getElementById('example-video-player');
    if (!el || !player || !Number.isFinite(player.duration) || player.duration <= 0) {
        if (el) el.textContent = '';
        return;
    }
    const dur = player.duration;
    let watched = 0;
    for (const [s, e] of watchedSegments) {
        watched += Math.max(0, e - s);
    }
    const pct = Math.max(0, Math.min(100, (watched / dur) * 100));
    el.textContent = `本次已观看约 ${pct.toFixed(0)}%`;
}

/** Save a video time point together with the learner's correction. */
async function addCurrentTimeToWrongbook(){
    if(!currentVideoId)return;
    const player=document.getElementById('example-video-player');player?.pause();
    return editWrongbook({source_type:'video',video_id:currentVideoId,title:currentVideoTitle,problem:currentVideoTitle,time_sec:Math.floor(player?.currentTime||0),note:document.getElementById('video-note-input')?.value||''});
}

/** 创作者：导出发布包（标题+弹幕+字幕模板 JSON，供 B 站等平台使用） */
function exportPublishPack() {
    if (!currentVideoId) return;
    const titleEl = document.getElementById('video-modal-title');
    const descEl = document.getElementById('video-modal-desc');
    const title = (titleEl && titleEl.innerText) ? titleEl.innerText.trim() : '';
    const description = (descEl && descEl.innerText) ? descEl.innerText.trim() : '';
    fetch('/api/v1/danmaku/list?video_id=' + encodeURIComponent(currentVideoId), { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            const list = (data.code === 0 && Array.isArray(data.data)) ? data.data : [];
            const danmaku = list.map(d => {
                const [time, mode, color, author, text] = Array.isArray(d) ? d : [d.time, 1, 16777215, d.username, d.text];
                return { time: Number(time), mode: mode || 1, color: color || 16777215, author: author || '', text: text || '' };
            });
            const pack = {
                title,
                description,
                video_id: currentVideoId,
                export_time: new Date().toISOString(),
                danmaku,
                subtitle_template: []
            };
            const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'publish_' + (currentVideoId || 'video') + '_' + Date.now() + '.json';
            a.click();
            URL.revokeObjectURL(a.href);
            if (typeof showToast === 'function') showToast('发布包已下载', 'success');
        })
        .catch(() => { if (typeof showToast === 'function') showToast('获取弹幕失败', 'error'); });
}

/** 教师：导出 HTML 课件（内嵌当前视频播放器，方便直接插入 PPT 或单独展示） */
function exportHtmlCourseware() {
    if (!currentVideoId) return;
    const videoEl = document.getElementById('example-video-player');
    const titleEl = document.getElementById('video-modal-title');
    const descEl = document.getElementById('video-modal-desc');
    const title = (titleEl && titleEl.innerText) ? titleEl.innerText.trim() : '数学可视化课件';
    const description = (descEl && descEl.innerText) ? descEl.innerText.trim() : '';
    const src = location.origin+'/assets/storage/'+encodeURIComponent(currentVideoId)+'.mp4';
    if (!src) {
        if (typeof showToast === 'function') showToast('当前视频地址不可用，无法导出课件', 'error');
        return;
    }

    // 简单的独立 HTML 页面：内嵌响应式视频播放器与标题说明，可直接在浏览器打开或插入到 PPT 的 Web 控件中
    const safeTitle = title.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const safeDesc = description.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>${safeTitle}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { margin:0; padding:1.5rem; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#020617; color:#e5e7eb; }
    .wrap { max-width:960px; margin:0 auto; }
    h1 { font-size:1.6rem; margin-bottom:0.75rem; }
    p.desc { font-size:0.95rem; color:#9ca3af; margin-bottom:1.25rem; }
    .player-frame { position:relative; width:100%; padding-top:56.25%; border-radius:0.75rem; overflow:hidden; box-shadow:0 18px 45px rgba(15,23,42,0.8); background:#020617; }
    .player-frame video { position:absolute; top:0; left:0; width:100%; height:100%; object-fit:contain; background:#020617; }
    .hint { margin-top:1rem; font-size:0.8rem; color:#9ca3af; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>${safeTitle}</h1>
    ${safeDesc ? `<p class="desc">${safeDesc}</p>` : ''}
    <div class="player-frame">
      <video src="${src}" controls playsinline></video>
    </div>
    <p class="hint">本课件引用本站视频，需要网络及本站服务可访问。可直接在浏览器打开。</p>
  </div>
</body>
</html>`;

    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'courseware_' + (currentVideoId || 'video') + '_' + Date.now() + '.html';
    a.click();
    URL.revokeObjectURL(a.href);
    if (typeof showToast === 'function') showToast('HTML 课件已下载', 'success');
}

/** 教师：将当前视频加入课件包（自动为用户创建默认课件包） */
async function addCurrentVideoToCoursePack() {
    if(currentVideoId) return chooseCoursePack(currentVideoId);
}

/** Open the real notebook filtered to the current video. */
function showWrongbookForCurrentVideo(){const video_id=currentVideoId;closeVideoModal();openWrongbook({video_id});}

function bindHighEnergyBar() {
    const player = document.getElementById('example-video-player');
    const barEl = document.getElementById('player-layer-high-energy');
    const pathEl = document.getElementById('high-energy-path');
    const watchedPathEl = document.getElementById('high-energy-watched-path');
    const svgEl = document.getElementById('high-energy-svg');
    const tooltipEl = document.getElementById('high-energy-tooltip');
    if (!barEl || !pathEl || !svgEl) return;
    let lastData = [];
    function draw() {
        const dur = player && player.duration && Number.isFinite(player.duration) ? player.duration : 60;
        const data = getHighEnergyData(dur);
        lastData = data;
        const w = barEl.offsetWidth || 400;
        const h = barEl.offsetHeight || 18;
        const max = Math.max(1, ...data);
        const pts = data.map((v, i) => {
            const x = (i / (data.length - 1 || 1)) * w;
            const y = h - (v / max) * h * 0.88 - 1;
            return [x, y];
        });
        if (pts.length < 2) {
            pathEl.setAttribute('d', '');
        } else {
            const n = pts.length;
            const k = 1 / 6;
            let d = 'M0,' + h + ' L0,' + pts[0][1];
            for (let i = 0; i < n - 1; i++) {
                const [x0, y0] = pts[i];
                const [x1, y1] = pts[i + 1];
                const prev = i > 0 ? pts[i - 1] : [x0, y0];
                const next = i + 2 < n ? pts[i + 2] : [x1, y1];
                const cp1x = x0 + (x1 - prev[0]) * k;
                const cp1y = y0 + (y1 - prev[1]) * k;
                const cp2x = x1 - (next[0] - x0) * k;
                const cp2y = y1 - (next[1] - y0) * k;
                d += ' C' + cp1x + ',' + cp1y + ' ' + cp2x + ',' + cp2y + ' ' + x1 + ',' + y1;
            }
            d += ' L' + w + ',' + h + ' Z';
            pathEl.setAttribute('d', d);
        }
        if (watchedPathEl && dur > 0 && watchedSegments.length > 0) {
            let wd = '';
            for (const [s, e] of watchedSegments) {
                const x0 = (s / dur) * w;
                const x1 = (e / dur) * w;
                wd += 'M' + x0 + ',' + h + ' L' + x0 + ',0 L' + x1 + ',0 L' + x1 + ',' + h + ' Z ';
            }
            watchedPathEl.setAttribute('d', wd);
        } else if (watchedPathEl) watchedPathEl.setAttribute('d', '');
        svgEl.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    }
    barEl.addEventListener('mousemove', (e) => {
        if (!tooltipEl || lastData.length === 0) return;
        const rect = barEl.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const w = rect.width;
        const idx = Math.floor((x / w) * (lastData.length - 1));
        const idxClamped = Math.max(0, Math.min(idx, lastData.length - 1));
        const value = lastData[idxClamped];
        if (value >= HIGH_ENERGY_PEAK_THRESHOLD) {
            tooltipEl.classList.add('show');
            tooltipEl.style.left = (x / w * 100) + '%';
            tooltipEl.style.transform = 'translateX(-50%)';
        } else {
            tooltipEl.classList.remove('show');
        }
    });
    barEl.addEventListener('mouseleave', () => { if (tooltipEl) tooltipEl.classList.remove('show'); });
    if (player) {
        player.addEventListener('loadedmetadata', draw);
        player.addEventListener('resize', draw);
        let lastTime=null,lastWall=0;
        const reset=()=>{lastTime=null;lastWall=performance.now();};
        for(const event of ['seeking','loadedmetadata','pause','play'])player.addEventListener(event,reset);
        player.addEventListener('timeupdate', () => {
            const t = player.currentTime;
            const now=performance.now(),delta=t-lastTime,elapsed=(now-lastWall)/1000;
            if(!player.paused&&!player.seeking&&lastTime!==null&&delta>0&&delta<=elapsed*player.playbackRate+.3)mergeWatchedSegment(lastTime,t);
            lastTime=t;lastWall=now;
            draw();
            updateVideoProgressSummary();
        });
    }
    const ro = new ResizeObserver(draw);
    ro.observe(barEl);
    draw();
}

function setWatchedSegmentsFromLastProgress(lastPlayTime) {
    watchedSegments = [];
}

function stopHeartbeat() {
    if (heartbeatTimerId) {
        clearInterval(heartbeatTimerId);
        heartbeatTimerId = null;
    }
}

function startHeartbeat() {
    stopHeartbeat();
    if (!currentVideoId) return;
    const player = document.getElementById('example-video-player');
    const send = () => {
        if (!player || !currentVideoId) return;
        fetch('/api/v1/player/heartbeat', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_id: currentVideoId, progress: player.currentTime || 0 })
        }).catch(() => {});
    };
    send();
    heartbeatTimerId = setInterval(send, 30000);
}

export function playExample(videoSrc, title, desc, videoId, options = {}) {
    if(currentVideoId)closeVideoModal();
    playlist=options.playlist||null;
    const generation=++playbackGeneration;
    const player = document.getElementById('example-video-player');
    const titleEl = document.getElementById('video-modal-title');
    const descEl = document.getElementById('video-modal-desc');

    initCustomPlayer();

    if (videoId) currentVideoId = videoId;
    else if (videoSrc) {
        const base = videoSrc.split('/').pop() || '';
        currentVideoId = base.replace(/\.(mp4|m3u8)$/i, '');
    } else currentVideoId = '';
    currentVideoTitle = title || '';

    currentSpriteUrl = options.spriteUrl || '';
    currentSpriteCols = Math.max(1, options.spriteCols || 10);
    currentSpriteRows = Math.max(1, options.spriteRows || 10);
    currentSpriteDuration = options.durationSec != null && Number.isFinite(options.durationSec) ? options.durationSec : 0;
    currentHighEnergyData = Array.isArray(options.highEnergy) ? options.highEnergy : [];

    const initialTime = options.initialTime != null && Number.isFinite(options.initialTime) ? options.initialTime : null;
    const applyConfig = (videoSrcFromConfig, lastPlayTime, fallbackSrc) => {
        if(generation!==playbackGeneration)return;
        const startTime = initialTime != null ? initialTime : (lastPlayTime > 0 && Number.isFinite(lastPlayTime) ? lastPlayTime : 0);
        setWatchedSegmentsFromLastProgress(startTime);
        if (player) {
            setVideoSource(player, videoSrcFromConfig, { hlsUrl: options.hlsUrl });
            const onReady = () => {
                if(generation!==playbackGeneration)return;
                if (startTime > 0) player.currentTime = startTime;
                startHeartbeat();
                safePlay(player);
            };
            if (player.readyState >= 2) onReady();
            else player.addEventListener('loadedmetadata', onReady, { once: true });
            if (fallbackSrc) {
                const onError = () => {
                    player.removeEventListener('error', onError);
                    if(generation!==playbackGeneration)return;
                    setVideoSource(player, fallbackSrc, { hlsUrl: options.hlsUrl });
                    player.load();
                    safePlay(player);
                };
                player.addEventListener('error', onError, { once: true });
            }
        }
        if (typeof window.syncCustomPlayerUI === 'function') setTimeout(window.syncCustomPlayerUI, 0);
    };

    fetch('/api/v1/player/config/' + encodeURIComponent(currentVideoId), { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            if (data && data.code === 0 && data.data && data.data.video_src) {
                const lastPlay = initialTime != null ? initialTime : (data.data.last_play_time ?? 0);
                if (initialTime == null && lastPlay > 0) currentVideoResumeTime = lastPlay;
                else currentVideoResumeTime = 0;
                applyConfig(data.data.video_src, lastPlay, data.data.fallback_src || null);
            } else {
                currentVideoResumeTime = 0;
                applyConfig(videoSrc, initialTime != null ? initialTime : 0, null);
            }
            updateResumeRecommendUI();
        })
        .catch(() => {
            currentVideoResumeTime = 0;
            applyConfig(videoSrc, initialTime != null ? initialTime : 0, null);
            updateResumeRecommendUI();
        });
    if (titleEl) titleEl.innerText = title;
    if (descEl) descEl.innerText = desc || "暂无简介";

    const commentsList = document.getElementById('video-comments-list');
    if (commentsList) commentsList.innerHTML = '';
    loadComments(currentVideoId);

    const layer = document.getElementById('video-danmaku-layer');
    const canvas = document.getElementById('video-danmaku-canvas');
    if (layer) {
        danmakuVisible = Settings.getDanmakuEnabled ? Settings.getDanmakuEnabled() : true;
        const screenMode = Settings.getDanmakuScreen ? Settings.getDanmakuScreen() : 'full';
        layer.classList.remove('half-screen', 'quarter-screen');
        if (screenMode === 'half') layer.classList.add('half-screen');
        else if (screenMode === 'quarter') layer.classList.add('quarter-screen');
        layer.style.display = danmakuVisible ? '' : 'none';
    }
    if (!danmakuCanvasManager) danmakuCanvasManager = createDanmakuCanvasManager();
    danmakuCanvasManager.init({
        canvas,
        container: layer,
        getTime: () => (player ? player.currentTime : 0),
        getVisible: () => danmakuVisible,
        getList: () => danmakuList,
        shownCountRef: danmakuShownCountRef,
        maskUrl: options.maskUrl || null
    });
    danmakuCanvasManager.start();
    loadDanmaku(currentVideoId, () => danmakuCanvasManager && danmakuCanvasManager.resize());
    connectVideoWs(currentVideoId);

    const toggleBtn = document.getElementById('video-danmaku-toggle-btn');
    if (toggleBtn) {
        toggleBtn.classList.toggle('active', danmakuVisible);
        toggleBtn.onclick = () => {
            danmakuVisible = !danmakuVisible;
            if (layer) layer.style.display = danmakuVisible ? '' : 'none';
            toggleBtn.classList.toggle('active', danmakuVisible);
        };
    }
    const screenBtn = document.getElementById('video-danmaku-screen-btn');
    const screenLabel = document.getElementById('video-danmaku-screen-label');
    const screenIcon = document.getElementById('video-danmaku-screen-icon');
    function updateScreenUI(mode) {
        if (layer) {
            layer.classList.remove('half-screen', 'quarter-screen');
            if (mode === 'half') layer.classList.add('half-screen');
            else if (mode === 'quarter') layer.classList.add('quarter-screen');
        }
        if (screenLabel) screenLabel.textContent = mode === 'quarter' ? '1/4屏' : mode === 'half' ? '半屏' : '全屏';
        if (screenIcon) {
            screenIcon.className = mode === 'quarter' ? 'fa-solid fa-compress' : mode === 'half' ? 'fa-solid fa-rectangle-half' : 'fa-solid fa-expand';
        }
    }
    const screenMode = Settings.getDanmakuScreen ? Settings.getDanmakuScreen() : 'full';
    updateScreenUI(screenMode);
    if (screenBtn) {
        screenBtn.onclick = () => {
            const current = Settings.getDanmakuScreen ? Settings.getDanmakuScreen() : 'full';
            const next = current === 'full' ? 'half' : current === 'half' ? 'quarter' : 'full';
            if (Settings.setDanmakuScreen) Settings.setDanmakuScreen(next);
            updateScreenUI(next);
        };
    }
    const likeBtn = document.getElementById('video-like-btn');
    const likeCountEl = document.getElementById('video-like-count');
    let userHasLiked = false;
    let likeCount = 0;
    function updateLikeUI() {
        if(generation!==playbackGeneration)return;
        if (likeCountEl) likeCountEl.textContent = likeCount;
        if (likeBtn) {
            likeBtn.classList.toggle('liked', userHasLiked);
            likeBtn.querySelector('i').className = userHasLiked ? 'fa-solid fa-thumbs-up' : 'fa-regular fa-thumbs-up';
        }
    }
    fetch('/api/examples/likes?video_id=' + encodeURIComponent(currentVideoId), { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                likeCount = data.like_count || 0;
                userHasLiked = !!data.user_has_liked;
                updateLikeUI();
            }
        })
        .catch(() => updateLikeUI());
    if (likeBtn) {
        likeBtn.onclick = () => {
            fetch('/api/user/me', { credentials: 'include' })
                .then(r => r.json())
                .then(me => {
                    if(generation!==playbackGeneration)return;
                    if (me.status !== 'success' || !me.username) {
                        if (typeof toggleAuthModal === 'function') toggleAuthModal(true);
                        return;
                    }
                    return fetch('/api/examples/like', {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ video_id: currentVideoId, action: userHasLiked ? 'unlike' : 'like' })
                    }).then(r => r.json());
                })
                .then(data => {
                    if (!data) return;
                    if (data.status === 'success') {
                        likeCount = data.like_count || 0;
                        userHasLiked = !!data.user_has_liked;
                        updateLikeUI();
                        if (typeof showToast === 'function') showToast(userHasLiked ? '已点赞' : '已取消', 'success');
                    } else if (data.message && typeof showToast === 'function') showToast(data.message, 'error');
                })
                .catch(() => { if (typeof showToast === 'function') showToast('网络错误', 'error'); });
        };
    }

    let userFavorited = false;
    let userWatchLater = false;
    fetch('/api/user/me', { credentials: 'include' })
        .then(r => r.json())
        .then(me => {
                    if(generation!==playbackGeneration)return;
            if (me.status === 'success' && me.username) {
                return Promise.all([
                    fetch('/api/examples/favorites', { credentials: 'include' }).then(r => r.json()),
                    fetch('/api/examples/watch-later', { credentials: 'include' }).then(r => r.json())
                ]).then(([favRes, wlRes]) => {
                    const favList = (favRes.status === 'success' && favRes.data) ? favRes.data : [];
                    const wlList = (wlRes.status === 'success' && wlRes.data) ? wlRes.data : [];
                    userFavorited = favList.some(x => x.video_id === currentVideoId);
                    userWatchLater = wlList.some(x => x.video_id === currentVideoId);
                    updateModalFavoriteWatchLaterUI(userFavorited, userWatchLater);
                });
            } else {
                updateModalFavoriteWatchLaterUI(false, false);
            }
        })
        .catch(() => updateModalFavoriteWatchLaterUI(false, false));

    function updateModalFavoriteWatchLaterUI(fav, wl) {
        if(generation!==playbackGeneration)return;
        const favBtn = document.getElementById('video-favorite-btn');
        const wlBtn = document.getElementById('video-watch-later-btn');
        if (favBtn) {
            favBtn.classList.toggle('active', fav);
            const icon = favBtn.querySelector('i');
            if (icon) icon.className = fav ? 'fa-solid fa-star' : 'fa-regular fa-star';
            favBtn.onclick = () => {
                fetch('/api/user/me', { credentials: 'include' }).then(r => r.json()).then(me => {
                    if(generation!==playbackGeneration)return;
                    if (me.status !== 'success' || !me.username) { if (typeof toggleAuthModal === 'function') toggleAuthModal(true); return Promise.reject(new Error('未登录')); }
                    const method = fav ? 'DELETE' : 'POST';
                    const url = fav ? '/api/examples/favorites?video_id=' + encodeURIComponent(currentVideoId) : '/api/examples/favorites';
                    return fetch(url, { method, credentials: 'include', headers: method === 'POST' ? { 'Content-Type': 'application/json' } : {}, body: method === 'POST' ? JSON.stringify({ video_id: currentVideoId }) : undefined }).then(r => r.json());
                }).then(data => {
                    if (data && data.status === 'success') {
                        userFavorited = !!data.user_favorited;
                        updateModalFavoriteWatchLaterUI(userFavorited, userWatchLater);
                        if (typeof showToast === 'function') showToast(data.user_favorited ? '已收藏' : '已取消收藏', 'success');
                    } else if (data && data.message && typeof showToast === 'function') {
                        showToast(data.message, 'error');
                    }
                }).catch(() => { if (typeof showToast === 'function') showToast('网络错误或请先登录', 'error'); });
            };
        }
        if (wlBtn) {
            wlBtn.classList.toggle('active', wl);
            const icon = wlBtn.querySelector('i');
            if (icon) icon.className = wl ? 'fa-solid fa-clock' : 'fa-regular fa-clock';
            wlBtn.onclick = () => {
                fetch('/api/user/me', { credentials: 'include' }).then(r => r.json()).then(me => {
                    if(generation!==playbackGeneration)return;
                    if (me.status !== 'success' || !me.username) { if (typeof toggleAuthModal === 'function') toggleAuthModal(true); return Promise.reject(new Error('未登录')); }
                    const method = wl ? 'DELETE' : 'POST';
                    const url = wl ? '/api/examples/watch-later?video_id=' + encodeURIComponent(currentVideoId) : '/api/examples/watch-later';
                    return fetch(url, { method, credentials: 'include', headers: method === 'POST' ? { 'Content-Type': 'application/json' } : {}, body: method === 'POST' ? JSON.stringify({ video_id: currentVideoId }) : undefined }).then(r => r.json());
                }).then(data => {
                    if (data && data.status === 'success') {
                        userWatchLater = !!data.user_watch_later;
                        updateModalFavoriteWatchLaterUI(userFavorited, userWatchLater);
                        if (typeof showToast === 'function') showToast(data.user_watch_later ? '已加入稍后看' : '已移除', 'success');
                    } else if (data && data.message && typeof showToast === 'function') {
                        showToast(data.message, 'error');
                    }
                }).catch(() => { if (typeof showToast === 'function') showToast('网络错误或请先登录', 'error'); });
            };
        }
    }

    const shareBtn = document.getElementById('video-share-btn');
    if (shareBtn) {
        shareBtn.onclick = () => {
            const t = player && Number.isFinite(player.currentTime) ? Math.floor(player.currentTime) : 0;
            const url = location.origin + location.pathname + '?section=examples&video=' + encodeURIComponent(currentVideoId) + (t > 0 ? '&t=' + t : '');
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(url).then(() => { if (typeof showToast === 'function') showToast('链接已复制（含当前时间点）', 'success'); }).catch(() => { prompt('复制链接：', url); });
            } else { prompt('复制链接：', url); }
        };
    }

    loadVideoNotes(currentVideoId);
    updateVideoProgressSummary();

    // 绑定学习闭环按钮
    const wrongBtn = document.getElementById('video-mark-wrong-btn');
    const openWrongBtn = document.getElementById('video-open-wrongbook-btn');
    if (wrongBtn) {
        wrongBtn.onclick = () => addCurrentTimeToWrongbook();
    }
    if (openWrongBtn) {
        openWrongBtn.onclick = () => showWrongbookForCurrentVideo();
    }

    // 创作者 / 教师：导出发布包 & 加入课件包
    const exportPublishBtn = document.getElementById('video-export-publish-btn');
    if (exportPublishBtn) {
        exportPublishBtn.onclick = () => exportPublishPack();
    }
    const exportHtmlBtn = document.getElementById('video-export-html-btn');
    if (exportHtmlBtn) {
        exportHtmlBtn.onclick = () => exportHtmlCourseware();
    }
    const addCoursePackBtn = document.getElementById('video-add-course-pack-btn');
    if (addCoursePackBtn) {
        addCoursePackBtn.onclick = () => addCurrentVideoToCoursePack();
    }
    bindVideoNotesOnce();

    fetch('/api/user/me', { credentials: 'include' })
        .then(r => r.status === 200 ? r.json() : null)
        .then(data => {
            if(generation!==playbackGeneration)return;
            currentDanmakuUsername = (data && data.status === 'success' && data.username) ? data.username : '';
            updateModalAuthUI(!!currentDanmakuUsername);renderDanmakuArchive();
        })
        .catch(() => {
            currentDanmakuUsername = '';
            updateModalAuthUI(false);
        });

    toggleModal('video-modal', true);
    enhanceTeachingPlayer();
    const wrapper = document.getElementById('video-player-wrapper');
    if (wrapper) setTimeout(() => wrapper.focus(), 100);

    bindCommentAndDanmakuOnce();
}

let commentDanmakuBound = false;

function bindCommentAndDanmakuOnce() {
    if (commentDanmakuBound) return;
    commentDanmakuBound = true;

    const commentInput = document.getElementById('video-comment-input');
    const commentSend = document.getElementById('video-comment-send');
    const danmakuInput = document.getElementById('video-danmaku-input');
    const danmakuSend = document.getElementById('video-danmaku-send');

    function sendComment() {
        const content = commentInput && commentInput.value ? commentInput.value.trim() : '';
        if (!content || !currentVideoId) return;
        commentSend.disabled = true;
        fetch('/api/examples/comments', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_id: currentVideoId, content })
        })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    if (commentInput) commentInput.value = '';
                    loadComments(currentVideoId);
                    if (typeof showToast === 'function') showToast('评论已发送', 'success');
                } else {
                    if (typeof showToast === 'function') showToast(data.message || '发送失败', 'error');
                }
            })
            .catch(() => { if (typeof showToast === 'function') showToast('网络错误', 'error'); })
            .finally(() => { if (commentSend) commentSend.disabled = false; });
    }

    function sendDanmaku() {
        const text = danmakuInput && danmakuInput.value ? danmakuInput.value.trim() : '';
        const player = document.getElementById('example-video-player');
        const time = player ? player.currentTime : 0;
        if (!text || !currentVideoId) return;
        const videoId=currentVideoId;
        danmakuSend.disabled = true;
        fetch('/api/v1/danmaku/send', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_id:videoId,text,time,color:parseInt(document.getElementById('video-danmaku-color')?.value.slice(1)||'ffffff',16),mode:Number(document.getElementById('video-danmaku-mode')?.value||1) })
        })
            .then(r => r.json())
            .then(data => {
                const ok = data.status === 'success' || (data && data.code === 0);
                const payload = data.data || {};
                if (ok && payload) {
                    if(videoId!==currentVideoId)return;
                    if (danmakuInput) danmakuInput.value = '';
                    mergeDanmaku([payload]);
                    if (typeof showToast === 'function') showToast('弹幕已发送', 'success');
                } else {
                    if (typeof showToast === 'function') showToast(data.message || '发送失败', 'error');
                }
            })
            .catch(() => { if (typeof showToast === 'function') showToast('网络错误', 'error'); })
            .finally(() => { if (danmakuSend) danmakuSend.disabled = false; });
    }

    if (commentSend) commentSend.addEventListener('click', sendComment);
    if (commentInput) commentInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendComment(); });
    if (danmakuSend) danmakuSend.addEventListener('click', sendDanmaku);
    if (danmakuInput) danmakuInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendDanmaku(); });
}

/** 根据 video_id 打开视频（用于直达链接）。可选 initialTime 秒。 */
export function playCoursePack(pack,index=0){
    return playExampleByVideoId(pack.video_ids[index],0,{id:pack.id,name:pack.name,video_ids:[...pack.video_ids],index});
}
export function playExampleByVideoId(videoId, initialTime,course=null) {
    if (!videoId) return;
    const request=++playbackGeneration;
    return fetch('/api/examples', { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            if(request!==playbackGeneration)return;
            if (data.status !== 'success' || !Array.isArray(data.data)) throw new Error('视频目录读取失败，请重试');
            teachingCatalog = data.data;
            const v = data.data.find(x => (x.video_id || x.filename?.replace(/\.mp4$/i, '')) === videoId);
            if (!v) throw new Error('该视频已不可用，请编辑课包重新选择');
            const opts = {
                playlist:course,
                spriteUrl: v.sprite_url,
                durationSec: v.duration_sec,
                spriteCols: v.sprite_cols || 10,
                spriteRows: v.sprite_rows || 10,
                hlsUrl: v.hls_url,
                maskUrl: v.mask_url,
                highEnergy: Array.isArray(v.high_energy) ? v.high_energy : undefined,
                initialTime: initialTime != null && Number.isFinite(Number(initialTime)) ? Number(initialTime) : undefined
            };
            playExample(v.url || '', v.title || '', v.description || '', v.video_id || videoId, opts);
        })
        .catch(error=>{if(request===playbackGeneration)showToast(error.message,'error');});
}

export function closeVideoModal() {
    const player = document.getElementById('example-video-player');
    playbackGeneration++;
    if(currentVideoId&&currentDanmakuUsername&&player?.readyState>=1)fetch('/api/v1/player/heartbeat',{method:'POST',credentials:'include',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({video_id:currentVideoId,progress:player.currentTime||0})}).catch(()=>{});
    stopHeartbeat();
    closeVideoWs();
    destroyHls();
    if (danmakuCanvasManager) danmakuCanvasManager.stop();
    currentVideoId = '';
    playlist=null;
    currentSpriteUrl = '';
    if (player) {
        player.pause();
        player.removeAttribute('src');
        player.load();
    }
    hidePlayerContextMenu();
    hidePlayerStatsPanel();
    toggleModal('video-modal', false);
}

export function focusPlayerFeature(feature){
    window.pendingTeachingFeature=feature;
    const modal=document.getElementById('video-modal');
    if(currentVideoId&&modal?.classList.contains('show')){enhanceTeachingPlayer();return;}
    showToast('选择一个教学案例，即可打开'+({notes:'时间戳笔记',danmaku:'弹幕设置',lesson:'教案与课包',comments:'评论'}[feature]||'播放器'),'info');
}
function enhanceTeachingPlayer(){
    const modal=document.getElementById('video-modal');if(!modal)return;
    let courseNav=modal.querySelector('.course-player-nav');
    if(!courseNav){courseNav=document.createElement('nav');courseNav.className='course-player-nav';courseNav.setAttribute('aria-label','课包播放顺序');modal.querySelector('.video-modal-header').after(courseNav);}
    courseNav.hidden=!playlist;
    if(playlist){
        const course=playlist;
        courseNav.innerHTML=`<span>${escapeHtml(course.name)} · ${course.index+1} / ${course.video_ids.length}</span><button data-previous ${course.index===0?'disabled':''}>上一节</button><button data-next ${course.index===course.video_ids.length-1?'disabled':''}>下一节</button><button data-read-lesson>教案与课堂练习</button>`;
        courseNav.querySelector('[data-previous]').onclick=()=>playCoursePack(course,course.index-1);
        courseNav.querySelector('[data-next]').onclick=()=>playCoursePack(course,course.index+1);
        courseNav.querySelector('[data-read-lesson]').onclick=()=>{document.getElementById('example-video-player')?.pause();openCoursePack(course.id);};
    }
    const bar=modal.querySelector('#video-danmaku-input-wrap');
    if(bar&&!bar.querySelector('.video-danmaku-style')){
        const controls=document.createElement('div');controls.className='video-danmaku-style';controls.innerHTML='<input id="video-danmaku-color" type="color" value="#ffffff" aria-label="弹幕颜色"><select id="video-danmaku-mode" aria-label="弹幕位置"><option value="1">滚动</option><option value="5">顶部</option><option value="4">底部</option></select>';bar.prepend(controls);
    }
    const exports=modal.querySelector('.video-creator-export');
    if(!modal.querySelector('#video-danmaku-archive')){const archive=document.createElement('section');archive.id='video-danmaku-archive';archive.innerHTML='<h3>已保存的弹幕</h3><p>点击时间可回到对应片段；可以删除自己发送的弹幕。</p><div class="danmaku-archive-list"></div>';modal.querySelector('#video-modal-notes')?.before(archive);}
    if(exports&&!exports.querySelector('[data-lesson-create]')){const b=document.createElement('button');b.className='action-btn secondary';b.dataset.lessonCreate='';b.textContent='为此视频编写教案';b.onclick=()=>editCoursePack(null,currentVideoId);exports.prepend(b);}
    if(!modal.querySelector('.teaching-player-tabs')){
        const tabs=document.createElement('nav');tabs.className='teaching-player-tabs';tabs.setAttribute('aria-label','播放器学习工具');
        const panels={notes:['笔记','#video-modal-notes','#video-modal-study','#video-resume-recommend'],danmaku:['弹幕','#video-danmaku-archive'],lesson:['教案与课包','.video-creator-export'],comments:['评论','.video-modal-comments']};
        tabs.innerHTML=Object.entries(panels).map(([key,[title]])=>`<button type="button" data-player-tab="${key}">${title}</button>`).join('');modal.querySelector('#video-modal-notes')?.before(tabs);
        tabs.onclick=e=>{const key=e.target.closest('[data-player-tab]')?.dataset.playerTab;if(!key)return;tabs.querySelectorAll('button').forEach(b=>{b.classList.toggle('active',b.dataset.playerTab===key);b.setAttribute('aria-pressed',String(b.dataset.playerTab===key));});for(const [id,[,...selectors]] of Object.entries(panels))for(const selector of selectors){const p=modal.querySelector(selector);if(p){p.classList.add('teaching-player-panel');p.hidden=id!==key;}}};
        tabs.querySelector('button').click();
    }
    const target=window.pendingTeachingFeature;
    if(target){window.pendingTeachingFeature=null;modal.querySelector(`[data-player-tab="${target}"]`)?.click();if(target==='danmaku')modal.querySelector('#video-danmaku-input')?.focus();}
    renderDanmakuArchive();
    layoutTeachingPlayer(modal);
}

function layoutTeachingPlayer(modal) {
    const panel=modal.querySelector('.video-modal-panel');
    if(!panel.querySelector('.teaching-watch-layout')){
        modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','video-modal-title');
        const layout=document.createElement('div');layout.className='teaching-watch-layout';
        const main=document.createElement('div');main.className='teaching-watch-main';
        const side=document.createElement('aside');side.className='teaching-watch-sidebar';side.setAttribute('aria-label','选集与学习工具');
        layout.append(main,side);panel.append(layout);
        for(const selector of ['#video-player-wrapper','.video-danmaku-bar','.video-meta-actions']){const el=panel.querySelector(selector);if(el)main.append(el);}
        const actions=document.createElement('div');actions.className='teaching-watch-actions';
        actions.innerHTML='<span>边看边学，把理解留在课堂里</span><button type="button" data-watch-create><i class="fa-solid fa-folder-plus"></i> 创建课包</button>';
        actions.querySelector('button').onclick=()=>{document.getElementById('example-video-player')?.pause();editCoursePack(null,currentVideoId);};main.append(actions);
        const episodes=document.createElement('section');episodes.className='teaching-episodes';side.append(episodes);
        for(const selector of ['.course-player-nav','.teaching-player-tabs','#video-modal-notes','#video-modal-study','#video-resume-recommend','#video-danmaku-archive','.video-creator-export','.video-modal-comments']){const el=panel.querySelector(selector);if(el)side.append(el);}
        const theater=document.createElement('button');theater.type='button';theater.id='custom-player-theater';theater.className='custom-player-btn';theater.title='宽屏模式';theater.setAttribute('aria-label','宽屏模式');theater.setAttribute('aria-pressed','false');theater.innerHTML='<i class="fa-solid fa-desktop"></i>';
        theater.onclick=()=>{const enabled=panel.classList.toggle('is-theater');theater.setAttribute('aria-pressed',String(enabled));window.dispatchEvent(new Event('resize'));};
        panel.querySelector('#custom-player-fullscreen').before(theater);
        const video=document.getElementById('example-video-player');
        video.addEventListener('ended',()=>{
            if(video.loop||!modal.classList.contains('show')||document.querySelector('dialog[open]'))return;
            if(playlist&&playlist.index+1<playlist.video_ids.length&&modal.querySelector('[data-auto-next]')?.checked)playCoursePack(playlist,playlist.index+1);
        });
    }
    const episodes=panel.querySelector('.teaching-episodes');
    const course=playlist;
    const items=course?course.video_ids.map(id=>teachingCatalog.find(v=>v.video_id===id)||{video_id:id,title:id}):teachingCatalog;
    const autoNext=episodes.querySelector('[data-auto-next]')?.checked??false;
    episodes.innerHTML=`<header><div><span class="assistant-eyebrow">${course?'COURSE COLLECTION':'EXPLORE & LEARN'}</span><h3>${escapeHtml(course?.name||'教学选集')}</h3></div><span>${items.length} 节</span></header>${course?`<label class="teaching-auto-next"><input type="checkbox" data-auto-next ${autoNext?'checked':''}> 自动连播</label>`:''}<div class="teaching-episode-list">${items.map((v,i)=>`<button type="button" data-episode="${i}" ${v.video_id===currentVideoId?'aria-current="true"':''}><span>${String(i+1).padStart(2,'0')}</span><strong>${escapeHtml(v.title)}</strong><small>${v.video_id===currentVideoId?'正在播放':v.duration_sec?formatDuration(v.duration_sec):'播放'}</small></button>`).join('')}</div>`;
    episodes.onclick=e=>{const b=e.target.closest('[data-episode]');if(!b)return;const index=Number(b.dataset.episode);if(course)playCoursePack(course,index);else playExampleByVideoId(items[index].video_id);};
    const active=episodes.querySelector('[aria-current]'), list=episodes.querySelector('.teaching-episode-list');
    if(active&&list)list.scrollTop=active.offsetTop-list.firstElementChild.offsetTop;
}
function renderDanmakuArchive(){
    const host=document.querySelector('.danmaku-archive-list');if(!host)return;
    host.innerHTML=danmakuList.map(d=>`<div><button data-bullet-time="${Number(d.time)}">${formatDuration(d.time)}</button><span>${escapeHtml(d.text)}</span>${d.username===currentDanmakuUsername&&d.id?`<button data-delete-bullet="${d.id}" aria-label="删除自己的弹幕">删除</button>`:''}</div>`).join('')||'<p>还没有弹幕，发送后会保存到当前视频。</p>';
    host.onclick=async e=>{const b=e.target.closest('button');if(!b)return;const player=document.getElementById('example-video-player');if(b.hasAttribute('data-bullet-time')){player.currentTime=Number(b.dataset.bulletTime);return;}if(b.dataset.deleteBullet){b.disabled=true;try{const r=await fetch('/api/v1/danmaku/'+b.dataset.deleteBullet,{method:'DELETE'});if(!r.ok)throw new Error('删除失败，请重试');danmakuList=danmakuList.filter(d=>String(d.id)!==b.dataset.deleteBullet);danmakuCanvasManager?.emit();renderDanmakuArchive();}catch(error){showToast(error.message,'error');b.disabled=false;}}};
}

window.addEventListener('wrongbook-updated',()=>{if(document.querySelector('.examples-filter-tab.active')?.dataset.filter==='wrongbook')loadExamples();});
