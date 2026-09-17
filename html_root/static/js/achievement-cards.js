/**
 * 成就闪卡：按固定顺序合成透明贴图，整体倾斜并轻移各层形成视差。
 */
const ASSET_VERSION = '20260917-artwork-3';
const MANIFEST_URL = '/assets/achievement-cards/manifest.json?v=' + ASSET_VERSION;
function artworkUrl(path) {
    return path ? path + (path.includes('?') ? '&' : '?') + 'v=' + ASSET_VERSION : '';
}

let _manifest = null;
let _manifestPromise = null;

export function loadAchievementCardManifest() {
    if (_manifest) return Promise.resolve(_manifest);
    if (_manifestPromise) return _manifestPromise;
    _manifestPromise = fetch(MANIFEST_URL)
        .then((r) => { if(!r.ok)throw new Error('卡片资源暂时不可用');return r.json(); })
        .then((data) => {
            _manifest = Array.isArray(data) ? data : [];
            return _manifest;
        })
        .catch(() => {
            _manifestPromise = null;
            return [];
        });
    return _manifestPromise;
}

export function getCardMeta(achievementId) {
    if (!_manifest || !achievementId) return null;
    return _manifest.find((c) => c && c.id === String(achievementId)) || null;
}

function tierClass(tier) {
    const t = String(tier || 'pearl').toLowerCase();
    if (t === 'gold' || t === 'silver' || t === 'pearl') return t;
    return 'pearl';
}

function lineartUrl(meta) {
    if (meta.lineart) return meta.lineart;
    if (meta.subject) return String(meta.subject).replace(/subject\.png$/, 'lineart.png');
    return '';
}

/**
 * 生成单张闪卡 HTML（背景 / 主体 / 线稿 / 文字 真分层）
 */
export function renderHoloCardHtml(meta, opts = {}) {
    if (!meta) return '';
    const size = opts.size || 'md';
    const locked = !!opts.locked;
    const showMeta = opts.showMeta !== false;
    const progress = opts.progress;
    const target = opts.target;
    const pct =
        target > 0 && progress != null
            ? Math.min(100, Math.round((progress / target) * 100))
            : null;
    const tier = tierClass(meta.tier);
    const id = escapeAttr(meta.id || '');
    const label = escapeHtml(meta.label || '');
    const condition = escapeHtml(meta.condition || opts.condition || '');
    const bg = escapeAttr(artworkUrl(meta.background || ''));
    const subject = escapeAttr(artworkUrl(meta.subject || ''));
    const text = escapeAttr(artworkUrl(meta.text || ''));
    const lineart = escapeAttr(artworkUrl(lineartUrl(meta)));
    const preview = escapeAttr(artworkUrl(meta.preview || ''));

    const progressHtml =
        pct != null
            ? `<div class="ach-holo-progress">
                <span class="ach-holo-progress-meta">${progress} / ${target}</span>
                <div class="ach-holo-progress-bar"><i style="width:${pct}%"></i></div>
               </div>`
            : '';

    return `
    <article class="ach-holo-card ach-holo-${size} ach-holo-tier-${tier}${locked ? ' is-locked' : ' is-unlocked'}"
             data-achievement-id="${id}" data-tier="${tier}" title="${label}">
      <div class="ach-holo-stage" tabindex="0" aria-label="${label}" role="img">
        <div class="ach-holo-flipper">
          <div class="ach-holo-card3d">
            <div class="ach-holo-face">
              <div class="ach-holo-layer ach-holo-bg" data-parallax="0"><img src="${bg}" alt="" draggable="false" loading="lazy"></div>
              <div class="ach-holo-layer ach-holo-subject" data-parallax="0.4">${subject ? `<img src="${subject}" alt="" draggable="false" loading="lazy">` : ''}</div>
              ${lineart ? `<div class="ach-holo-layer ach-holo-line" data-parallax="0.4"><img src="${lineart}" alt="" draggable="false" loading="lazy"></div>` : ''}
              <div class="ach-holo-layer ach-holo-text" data-parallax="0.15">${text ? `<img src="${text}" alt="" draggable="false" loading="lazy">` : ''}</div>
              <div class="ach-holo-foil" aria-hidden="true"></div>
              <div class="ach-holo-edge" aria-hidden="true"></div>
              ${locked ? '<div class="ach-holo-lock"><i class="fa-solid fa-lock"></i></div>' : ''}
            </div>
          </div>
        </div>
        ${preview ? `<img class="ach-holo-fallback" src="${preview}" alt="${label}" draggable="false" loading="lazy">` : ''}
      </div>
      ${
          showMeta
              ? `<div class="ach-holo-caption">
            <div class="ach-holo-caption-title">${label}</div>
            ${condition ? `<p class="ach-holo-caption-desc">${condition}</p>` : ''}
            ${progressHtml}
          </div>`
              : ''
      }
    </article>`;
}

/**
 * 按需更新整体转动与平面视差；贴图的绘制顺序不随转动改变。
 */
export function bindHoloCardTilt(root) {
    if (!root) return;
    const prefersReduce =
        typeof matchMedia !== 'undefined' &&
        matchMedia('(prefers-reduced-motion: reduce)').matches;

    root.querySelectorAll('.ach-holo-stage').forEach((stage) => {
        if (stage.dataset.tiltBound === '1') return;
        stage.dataset.tiltBound = '1';

        const flipper = stage.querySelector('.ach-holo-flipper');
        const face = stage.querySelector('.ach-holo-face');
        const layers = [...stage.querySelectorAll('.ach-holo-layer')];
        if (!flipper || !face) return;

        layers.forEach(el => el.style.removeProperty('transform'));
        let targetX=0, targetY=0, curX=0, curY=0, raf=0, disposed=false;
        function frame() {
            raf=0;
            if(disposed || !stage.isConnected || document.hidden) return;
            curX+=(targetX-curX)*.16; curY+=(targetY-curY)*.16;
            flipper.style.transform=`rotateX(${curX}deg) rotateY(${curY}deg)`;
            layers.forEach(el=>{
                const depth=Number(el.dataset.parallax)||0;
                el.style.setProperty('--layer-x',`${curY*depth}px`);
                el.style.setProperty('--layer-y',`${-curX*depth}px`);
            });
            if(Math.abs(targetX-curX)+Math.abs(targetY-curY)>.03) raf=requestAnimationFrame(frame);
        }
        function schedule(){if(!prefersReduce&&!raf&&!disposed)raf=requestAnimationFrame(frame);}
        const onMove = e => {
            const rect=stage.getBoundingClientRect();
            const px=Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));
            const py=Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height));
            targetX=(.5-py)*16;targetY=(px-.5)*20;
            face.style.setProperty('--mx',`${px*100}%`);
            face.style.setProperty('--my',`${py*100}%`);
            stage.classList.add('is-tilting');schedule();
        };
        const onLeave=()=>{targetX=targetY=0;stage.classList.remove('is-tilting');schedule();};
        const onError=()=>{if(stage.querySelector('.ach-holo-fallback'))stage.classList.add('use-fallback');};
        const images=[...stage.querySelectorAll('.ach-holo-layer img')];
        images.forEach(img=>{img.addEventListener('error',onError);if(img.complete&&!img.naturalWidth)onError();});
        stage.addEventListener('pointermove',onMove);
        stage.addEventListener('pointerleave',onLeave);
        stage.addEventListener('pointercancel',onLeave);
        stage._achHoloDispose=()=>{
            disposed=true;cancelAnimationFrame(raf);
            images.forEach(img=>img.removeEventListener('error',onError));
            stage.removeEventListener('pointermove',onMove);
            stage.removeEventListener('pointerleave',onLeave);
            stage.removeEventListener('pointercancel',onLeave);
            delete stage.dataset.tiltBound;
        };
    });
}

export function renderAchievementHoloGrid(achievements, opts = {}) {
    const list = Array.isArray(achievements) ? achievements : [];
    const size = opts.size || 'sm';
    return list
        .map((a) => {
            const meta = getCardMeta(a.id) || {
                id: a.id,
                label: a.label,
                condition: a.condition,
                tier: 'pearl',
                background: '/assets/achievement-cards/tutorial/background.png',
                subject: '',
                text: '',
                preview: '',
            };
            return renderHoloCardHtml(
                {
                    ...meta,
                    label: a.label || meta.label,
                    condition: a.condition || meta.condition,
                },
                {
                    size,
                    locked: !a.unlocked,
                    progress: a.progress,
                    target: a.target,
                    condition: a.condition,
                },
            );
        })
        .join('');
}

function escapeHtml(s) {
    if (!s) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, '&#39;');
}
