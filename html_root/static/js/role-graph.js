/**
 * 全站知识图谱 - 3D 力导向图
 * 节点：图标（img-nodes 风格 Sprite+Texture）+ 文字（text-nodes 风格 SpriteText）
 * 使用 site-graph 数据，依赖全局 THREE / ForceGraph3D / SpriteText（ES 模块）
 */

import { getGraphDataFor3D, ROLE_FLOWS, ROLE_LABELS, executeNodeAction, getOutNeighbors, getInNeighbors } from './site-graph.js?v=20260917-ecosystem-6';
import { escapeText } from './solution-visual.js';

const graphInstances = new WeakMap();

/** 图标映射 */
const ICON_MAP = {
  'fa-house': '⌂', 'fa-robot': '◇', 'fa-camera': '◎', 'fa-calculator': '∑', 'fa-play': '▶',
  'fa-book': '☰', 'fa-code': '</>', 'fa-folder-plus': '⊕', 'fa-wand-magic-sparkles': '✦',
  'fa-pen': '✎', 'fa-upload': '↑', 'fa-square-root-variable': '√', 'fa-video': '▷',
  'fa-puzzle-piece': '⊞', 'fa-circle-question': '?', 'fa-gear': '⚙', 'fa-search': '⌕',
  'fa-graduation-cap': '▤', 'fa-rocket': '➤', 'fa-lightbulb': '◐', 'fa-trash': '✕',
  'fa-eraser': '◻', 'fa-rotate-left': '↺', 'fa-lock': '⌒', 'fa-magnifying-glass': '⌕',
  'fa-bookmark': '▣', 'fa-book-bookmark': '▤', 'fa-clapperboard': '▶', 'fa-list-ol': '≡',
  'fa-star': '★', 'fa-clock': '◷', 'fa-chalkboard-user': '▤', 'fa-tags': '☰',
  'fa-plus': '+', 'fa-file-lines': '◆', 'fa-file': '◆', 'fa-keyboard': '⌨',
  'fa-palette': '◐', 'fa-user': '◎', 'fa-film': '▣'
};

/** 获取当前主题 */
function isDarkTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark';
}

/** 主题配色：高级柔和，贴合主页 feature-card 风格 */
const THEME = {
  light: {
    cardBg: 'rgba(255, 255, 255, 0.92)',
    cardBorder: 'rgba(226, 232, 240, 0.6)',
    text: '#334155',
    iconBg: 'rgba(99, 102, 241, 0.08)',
    iconColor: '#6366f1',
    nodeColor: '#6366f1',
    cardShadow: 'rgba(99, 102, 241, 0.04)',
  },
  dark: {
    cardBg: 'rgba(30, 41, 59, 0.88)',
    cardBorder: 'rgba(71, 85, 105, 0.3)',
    text: '#e2e8f0',
    iconBg: 'rgba(99, 102, 241, 0.15)',
    iconColor: '#a5b4fc',
    nodeColor: '#818cf8',
    cardShadow: 'rgba(0, 0, 0, 0.2)',
  },
};

/** 深色模式下软化节点颜色：降饱和、略降明度，避免在暗底上过于刺眼 */
function softenColorForDarkMode(hex) {
  const m = (hex || '#818cf8').match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  if (!m) return hex;
  let r = parseInt(m[1], 16) / 255, g = parseInt(m[2], 16) / 255, b = parseInt(m[3], 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h, s, l = (max + min) / 2;
  if (max === min) { h = s = 0; } else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      default: h = ((r - g) / d + 4) / 6;
    }
  }
  s = Math.max(0, s * 0.5);
  l = Math.min(0.75, l * 0.85 + 0.1);
  const hue2rgb = (p, q, t) => { if (t < 0) t += 1; if (t > 1) t -= 1; if (t < 1/6) return p + (q - p) * 6 * t; if (t < 1/2) return q; if (t < 2/3) return p + (q - p) * (2/3 - t) * 6; return p; };
  if (s === 0) { r = g = b = l; } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1/3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1/3);
  }
  return '#' + [r, g, b].map(x => Math.round(x * 255).toString(16).padStart(2, '0')).join('');
}

/** 圆球 + 标签卡片（图标在左、文字在右，卡片在球体正上方，无遮挡） */
function createSphereNodeWithText(node, theme) {
  const THREE = window.THREE;
  if (!THREE) return null;
  const t = THEME[theme] || THEME.light;
  const rawColor = node.color || t.nodeColor;
  const nodeColor = theme === 'dark' ? softenColorForDarkMode(rawColor) : rawColor;
  const r = Math.max(5, (node.val || 10) * 0.5);
  const iconClass = (node.icon || '').split(' ').pop() || '';
  const symbol = ICON_MAP[iconClass] || (node.role ? '◆' : (node.id === 'center' ? '✦' : '●'));
  const text = node.name || node.id;

  const scale = 2;
  const iconSize = 28 * scale;
  const fontSize = 16 * scale;
  const padding = 12 * scale;
  const iconBoxSize = 40 * scale;
  const gap = 10 * scale;

  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = `600 ${fontSize}px "Plus Jakarta Sans","Microsoft YaHei",sans-serif`;
  const tw = Math.max(ctx.measureText(text).width, text.length * fontSize * 0.9);
  const cardW = Math.ceil(iconBoxSize + gap + tw + padding * 2);
  const cardH = Math.ceil(Math.max(iconBoxSize, fontSize * 1.4) + padding * 2);

  const canvas = document.createElement('canvas');
  canvas.width = cardW;
  canvas.height = cardH;
  const c = canvas.getContext('2d');
  const rad = 16;

  /* 卡片底色：柔和渐变 / 玻璃感 */
  if (theme === 'dark') {
    const cx = cardW / 2;
    const cy = cardH / 2;
    const R = Math.sqrt(cx * cx + cy * cy) * 1.3;
    const parseRgb = (str) => {
      const m = str.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
      return m ? [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10)] : [30, 41, 59];
    };
    const [cr, cg, cb] = parseRgb(t.cardBg);
    const grad = c.createRadialGradient(cx, cy, 0, cx, cy, R);
    grad.addColorStop(0, `rgba(${cr},${cg},${cb},0.94)`);
    grad.addColorStop(0.5, `rgba(${cr},${cg},${cb},0.82)`);
    grad.addColorStop(0.9, `rgba(${cr},${cg},${cb},0.12)`);
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = grad;
  } else {
    const bgGrad = c.createLinearGradient(0, 0, cardW, cardH);
    bgGrad.addColorStop(0, 'rgba(255,255,255,0.95)');
    bgGrad.addColorStop(1, 'rgba(248,250,252,0.9)');
    c.fillStyle = bgGrad;
  }
  if (c.roundRect) {
    c.beginPath();
    c.roundRect(0, 0, cardW, cardH, rad);
    c.fill();
  } else {
    c.fillRect(0, 0, cardW, cardH);
  }
  /* 柔和边框 */
  c.strokeStyle = t.cardBorder;
  c.lineWidth = 0.5;
  if (c.roundRect) {
    c.beginPath();
    c.roundRect(0, 0, cardW, cardH, rad);
    c.stroke();
  }

  const iconX = padding + iconBoxSize / 2;
  const iconY = cardH / 2;
  c.beginPath();
  c.arc(iconX, iconY, iconBoxSize / 2 - 2, 0, Math.PI * 2);
  c.fillStyle = t.iconBg;
  c.fill();
  c.strokeStyle = t.iconColor;
  c.lineWidth = 0.8;
  c.globalAlpha = 0.7;
  c.stroke();
  c.globalAlpha = 1;
  c.fillStyle = t.iconColor;
  c.font = `700 ${iconSize}px "Plus Jakarta Sans","Microsoft YaHei",sans-serif`;
  c.textAlign = 'center';
  c.textBaseline = 'middle';
  c.fillText(symbol, iconX, iconY);

  c.fillStyle = t.text;
  c.font = `600 ${fontSize}px "Plus Jakarta Sans","Microsoft YaHei",sans-serif`;
  c.textAlign = 'left';
  c.fillText(text, padding + iconBoxSize + gap, cardH / 2);

  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const labelMat = new THREE.SpriteMaterial({
    map: tex,
    transparent: true,
    opacity: 0.92,
    depthWrite: false,
    depthTest: false,
  });
  const labelSprite = new THREE.Sprite(labelMat);
  labelSprite.renderOrder = 1000;
  labelSprite.scale.set(cardW * 0.2, cardH * 0.2, 1);
  labelSprite.position.y = r + cardH * 0.12;

  const group = new THREE.Group();
  const geo = new THREE.SphereGeometry(r, 24, 20);
  const sphereMat = new THREE.MeshLambertMaterial({
    color: nodeColor,
    transparent: true,
    opacity: 0.9,
    emissive: nodeColor,
    emissiveIntensity: 0.12,
  });
  const sphere = new THREE.Mesh(geo, sphereMat);
  sphere.renderOrder = 0;
  group.add(sphere);
  group.add(labelSprite);
  return group;
}

function buildGraphData() {
  const raw = getGraphDataFor3D();
  const nodes = raw.nodes || [];
  const links = raw.links || [];
  const id2node = new Map(nodes.map((n) => [n.id, n]));
  const resolvedLinks = links.map((l) => {
    const src = typeof l.source === 'object' ? l.source : id2node.get(l.source);
    const tgt = typeof l.target === 'object' ? l.target : id2node.get(l.target);
    return { ...l, source: src, target: tgt };
  }).filter((l) => l.source && l.target);
  resolvedLinks.forEach((link) => {
    const a = link.source;
    const b = link.target;
    if (!a.neighbors) a.neighbors = [];
    if (!b.neighbors) b.neighbors = [];
    if (!a.neighbors.includes(b)) a.neighbors.push(b);
    if (!b.neighbors.includes(a)) b.neighbors.push(a);
    if (!a.links) a.links = [];
    if (!b.links) b.links = [];
    a.links.push(link);
    b.links.push(link);
  });
  return { nodes, links: resolvedLinks };
}

export function initRoleGraph() {
    const container = document.getElementById('role-graph-3d');
  const flowPanel = document.getElementById('role-flow-panel');
  const flowTitle = document.getElementById('role-flow-title');
  const flowChain = document.getElementById('role-flow-chain');
  const flowBack = document.getElementById('role-flow-back');

  const ForceGraph3D = window.ForceGraph3D;
  if (!container || !flowPanel) return;
  if (graphInstances.has(container)) return graphInstances.get(container);
  let Graph, retryTimer, resizeFrame = 0, navigationTimer = 0;
  const cleanups = [];
  const events = new AbortController();
  const listen = (el, type, fn, options = {}) => el?.addEventListener(type, fn, {...options, signal: events.signal});
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let disposed = false;
  const cleanup = () => {
    disposed = true;
    events.abort(); clearInterval(retryTimer); clearTimeout(navigationTimer); cancelAnimationFrame(resizeFrame);
    cleanups.forEach(fn => fn());
    Graph?.pauseAnimation?.();
    Graph?.scene?.().traverse(obj => {obj.geometry?.dispose(); const mats = Array.isArray(obj.material) ? obj.material : [obj.material]; mats.filter(Boolean).forEach(m => {m.map?.dispose();m.dispose();});});
    Graph?._destructor?.();
    Graph?.renderer?.().dispose();
    container.replaceChildren();
    graphInstances.delete(container);
  };
  graphInstances.set(container, cleanup);

  const wrap = container.closest('.role-graph-wrap');
  const explorer = document.createElement('div');
  explorer.className = 'graph-explorer';
  explorer.innerHTML = '<label>查找功能 <input type="search" placeholder="搜索解题、Manim、识别…" aria-label="搜索知识图谱节点"><button type="button" class="graph-fullscreen" aria-label="全屏知识图谱">⛶</button></label><div class="graph-search-results"></div><p class="graph-fallback" hidden>3D 图谱暂不可用，可以通过上方节点继续导航。</p>';
  container.before(explorer);
  cleanups.push(() => explorer.remove());
  const allNodes = getGraphDataFor3D().nodes;
  const search = explorer.querySelector('input');
  const results = explorer.querySelector('.graph-search-results');
  const detail=document.createElement('section');detail.className='graph-node-detail';detail.hidden=true;explorer.append(detail);
  function inspectNode(node){
    detail.hidden=false;
    selectedNodeId=node.id;highlightSelection();
    const next=getOutNeighbors(node.id),previous=getInNeighbors(node.id).filter(n=>n.id!=='center');
    const descriptions={'errorbook':'收录视频时间点或分步题解，整理错因、标签和订正；按计划复习，记录掌握程度。','examples-lesson':'填写教学目标、重难点、课堂过程与练习，支持 LaTeX，保存后可继续编辑。','examples-create-course':'命名课包、挑选案例、调整播放顺序，与教案一起保存到你的账户。','examples-courseware':'阅读已保存教案，按顺序播放视频，导出教案或课包。','examples-danmaku':'选择案例后发送带时间点、颜色与位置的弹幕，暂停和拖动进度时保持同步。','examples-notes':'在视频时间点记录笔记，点击笔记回到对应片段。','examples-export':'打开已保存课包导出 Markdown 教案或 JSON 课包，也可以导入本站课包。'};
    detail.innerHTML=`<h3>${escapeText(node.name)}</h3><p>${escapeText(descriptions[node.id]||'打开对应功能，或沿关联节点继续探索学习流程。')}</p><button type="button" data-node-open="${escapeText(node.id)}">打开此功能 ↗</button><button type="button" data-node-close>收起</button><p>前置与关联入口</p><div class="graph-node-related">${previous.map(n=>`<button type="button" data-related="${escapeText(n.id)}">${escapeText(n.name)}</button>`).join('')||'<span>可直接使用</span>'}</div><p>接下来可以</p><div class="graph-node-related">${next.map(n=>`<button type="button" data-related="${escapeText(n.id)}">${escapeText(n.name)}</button>`).join('')||'<span>在当前页面完成操作</span>'}</div>`;
  }
  listen(detail,'click',e=>{const b=e.target.closest('button');if(!b)return;if(b.hasAttribute('data-node-close'))detail.hidden=true;const related=allNodes.find(n=>n.id===b.dataset.related);if(related)inspectNode(related);const node=allNodes.find(n=>n.id===b.dataset.nodeOpen);if(node)executeNodeAction(node);});
  const searchNodes = () => {
    const q = search.value.trim().toLowerCase();
    const found = allNodes.filter(n => n.id !== 'center' && (q ? [n.name, ...(n.keywords || [])].join(' ').toLowerCase().includes(q) : n.type === 'section' || n.type === 'role')).slice(0, q ? 10 : 7);
    results.innerHTML = found.map(n => `<button type="button" data-graph-node="${escapeText(n.id)}">${escapeText(n.name)}</button>`).join('') || '<span>没有匹配的节点，请换个关键词。</span>';
  };
  listen(search, 'input', searchNodes);
  listen(explorer.querySelector('.graph-fullscreen'), 'click', async () => {try {if(document.fullscreenElement)await document.exitFullscreen();else await wrap.requestFullscreen();}catch {explorer.querySelector('.graph-fallback').textContent='浏览器暂不支持全屏，仍可使用缩放按钮探索图谱。';explorer.querySelector('.graph-fallback').hidden=false;}});
  listen(results, 'click', e => {const id = e.target.closest('button')?.dataset.graphNode;const node=allNodes.find(n=>n.id===id);if(node)inspectNode(node);});
  searchNodes();
  container.setAttribute('aria-label', '三维知识图谱，亦可使用上方搜索按钮导航');
  if (wrap) {
    listen(wrap, 'contextmenu', (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, {capture:true});
    listen(wrap, 'mousedown', (e) => {
      if (e.button === 1) {
        e.preventDefault();
        e.stopPropagation();
      }
    }, {capture:true});
  }

  const openFlow = (role) => {
    const flow = ROLE_FLOWS[role];
    if (!flow) return;
    flowTitle.textContent = ROLE_LABELS[role] + ' · 推荐路径';
    flowChain.innerHTML = flow.map((step, i) => `
      <div class="role-flow-step" data-step="${i}">
        <div class="role-flow-step-node">
          <i class="${step.icon}"></i>
          <span>${step.label}</span>
          <p>${step.desc}</p>
          <button type="button" class="role-flow-enter" data-section="${step.section}">进入</button>
        </div>
        ${i < flow.length - 1 ? '<div class="role-flow-arrow"><i class="fa-solid fa-chevron-right"></i></div>' : ''}
      </div>
    `).join('');
    flowPanel.classList.add('visible');
    flowChain.querySelectorAll('.role-flow-enter').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const step=flow[Number(btn.closest('[data-step]').dataset.step)];
        executeNodeAction(step);
        flowPanel.classList.remove('visible');
      });
    });
  };
  window.RoleGraph = window.RoleGraph || {};
  window.RoleGraph.openFlow = openFlow;

  if (flowBack) listen(flowBack, 'click', () => flowPanel.classList.remove('visible'));
  listen(flowPanel, 'click', (e) => { if (e.target === flowPanel) flowPanel.classList.remove('visible'); });
  listen(document, 'keydown', (e) => {
    if (e.key === 'Escape' && flowPanel.classList.contains('visible')) flowPanel.classList.remove('visible');
  });

  const highlightNodes = new Set();
  const highlightLinks = new Set();
  let hoverNode = null;
  let selectedNodeId=null;
  function highlightSelection(){
    highlightNodes.clear();highlightLinks.clear();
    const node=Graph?.graphData().nodes.find(n=>n.id===selectedNodeId);
    if(node){highlightNodes.add(node);(node.neighbors||[]).forEach(n=>highlightNodes.add(n));(node.links||[]).forEach(l=>highlightLinks.add(l));}
    updateHighlight();
  }

  function updateHighlight() {
    if (!Graph) return;
    Graph.linkColor(Graph.linkColor());
    Graph.linkWidth(Graph.linkWidth());
    Graph.linkDirectionalParticles(Graph.linkDirectionalParticles());
  }

  function getThemeColors() {
    const dark = isDarkTheme();
    const t = THEME[dark ? 'dark' : 'light'];
    return {
      bg: dark ? '#0f172a' : '#f8fafc',
      link: dark ? 'rgba(139, 92, 246, 0.35)' : 'rgba(99, 102, 241, 0.3)',
      linkHighlight: dark ? 'rgba(139, 92, 246, 0.7)' : 'rgba(99, 102, 241, 0.6)',
      node: (n) => dark ? softenColorForDarkMode(n.color || t.nodeColor) : (n.color || t.nodeColor),
      theme: dark ? 'dark' : 'light',
    };
  }

  function doInit() {
    const w = Math.max(container.offsetWidth, container.clientWidth, 1);
    const h = Math.max(container.offsetHeight, container.clientHeight, 360);
    const data = buildGraphData();
    let colors = getThemeColors();

    const useCustomNodes = typeof window.THREE !== 'undefined';
    const getLinkColor = (l) => (highlightLinks.has(l) ? colors.linkHighlight : colors.link);
    const getLinkWidth = (l) => (highlightLinks.has(l) ? 2.5 : 1.5);
    const getLinkParticles = (l) => (highlightLinks.has(l) && !reducedMotion ? 2 : 0);

    let g = new window.ForceGraph3D(container, {
      controlType: 'orbit',
      rendererConfig: { antialias: true, alpha: true },
    })
      .width(w)
      .height(h)
      .graphData(data)
      .backgroundColor('rgba(0,0,0,0)')
      .nodeVal((n) => Math.max(10, (n.val || 12) * 0.7))
      .nodeColor(colors.node)
      .nodeLabel((n) => n.name || n.id);
    if (useCustomNodes) {
      g = g
        .nodeThreeObject((node) => createSphereNodeWithText(node, colors.theme))
        .nodeThreeObjectExtend(false)
        .nodePositionUpdate((obj, coords, node) => {
          const sprite = obj.children[1];
          if (sprite?.material && Graph) {
            const cam = Graph.camera();
            const dx = cam.position.x - coords.x;
            const dy = cam.position.y - coords.y;
            const dz = cam.position.z - coords.z;
            const dist = Math.hypot(dx, dy, dz);
            const near = 200;
            const far = 420;
            let opacity = 1 - (dist - near) / (far - near);
            sprite.material.opacity = Math.max(0.22, Math.min(1, opacity));
          }
        });
    }
    Graph = g
      .linkOpacity(0.8)
      .linkColor(getLinkColor)
      .linkWidth(getLinkWidth)
      .linkDirectionalParticles(getLinkParticles)
      .linkDirectionalParticleWidth(1.5)
      .linkDirectionalParticleSpeed(0.008)
      .linkCurvature(0.12)
      .linkResolution(8)
      .cooldownTicks(120)
      .onNodeHover((node, prev) => {
        if (container) container.style.cursor = node ? 'pointer' : 'grab';
        if ((!node && !highlightNodes.size) || (node && hoverNode === node)) return;
        highlightNodes.clear();
        highlightLinks.clear();
        if (node) {
          highlightNodes.add(node);
          (node.neighbors || []).forEach((nb) => highlightNodes.add(nb));
          (node.links || []).forEach((lk) => highlightLinks.add(lk));
        }
        if(!node)highlightSelection();
        hoverNode = node || null;
        updateHighlight();
      })
      .onLinkHover((link) => {
        highlightNodes.clear();
        highlightLinks.clear();
        if (link) {
          highlightLinks.add(link);
          highlightNodes.add(link.source);
          highlightNodes.add(link.target);
        }
        if(!link)highlightSelection();
        hoverNode = null;
        updateHighlight();
      })
      .enableNodeDrag(false)
      .onNodeClick((node) => {
        const nx = Number(node.x);
        const ny = Number(node.y);
        const nz = Number(node.z);
        const hasPos = !Number.isNaN(nx) && !Number.isNaN(ny) && !Number.isNaN(nz);
        const x = hasPos ? nx : 0, y = hasPos ? ny : 0, z = hasPos ? nz : 0;
        const dist = Math.hypot(x, y, z) || 1;
        const distance = 50;
        const distRatio = 1 + distance / dist;
        const newPos = hasPos
          ? { x: x * distRatio, y: y * distRatio, z: z * distRatio }
          : { x: 0, y: 0, z: distance };
        const lookAt = { x, y, z };
        clearTimeout(navigationTimer);
        const TRANSITION_MS = reducedMotion ? 0 : 350;
        Graph.cameraPosition(newPos, lookAt, TRANSITION_MS);
        navigationTimer = setTimeout(() => {
          if (!disposed) inspectNode(node);
        }, TRANSITION_MS + 80);
      })
      .showNavInfo(false);

    const renderer = Graph.renderer();
    if (renderer) { renderer.setClearColor(0x000000, 0); renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5)); }

    Graph.cameraPosition({ z: 400 });
    Graph.d3Force('charge').strength(-220);
    Graph.d3Force('link').distance(80);
    Graph.d3Force('center').strength(0.08);

    const ctrl = Graph.controls();
    if (ctrl) {
      const M = window.THREE?.MOUSE;
      const ROTATE = M?.ROTATE ?? 0;
      const PAN = M?.PAN ?? 2;
      ctrl.mouseButtons = { LEFT: ROTATE, RIGHT: PAN };
      ctrl.enablePan = true;
      ctrl.enableDamping = !reducedMotion;
      ctrl.dampingFactor = 0.12;
      ctrl.minDistance = 35;
      ctrl.maxDistance = 1400;
    }

    const zoomIn = () => {
      const cam = Graph.camera();
      const target = ctrl?.target || { x: 0, y: 0, z: 0 };
      const dx = cam.position.x - target.x;
      const dy = cam.position.y - target.y;
      const dz = cam.position.z - target.z;
      const scale = 0.82;
      Graph.cameraPosition(
        { x: target.x + dx * scale, y: target.y + dy * scale, z: target.z + dz * scale },
        target,
        200
      );
    };
    const zoomOut = () => {
      const cam = Graph.camera();
      const target = ctrl?.target || { x: 0, y: 0, z: 0 };
      const dx = cam.position.x - target.x;
      const dy = cam.position.y - target.y;
      const dz = cam.position.z - target.z;
      const scale = 1.22;
      Graph.cameraPosition(
        { x: target.x + dx * scale, y: target.y + dy * scale, z: target.z + dz * scale },
        target,
        200
      );
    };
    const zoomReset = () => Graph.zoomToFit(reducedMotion ? 0 : 300, 40);
    let fitted = false;
    Graph.onEngineStop(() => { if (!fitted) {fitted = true;zoomReset();} });
    const zoomInBtn = document.getElementById('role-graph-zoom-in');
    const zoomOutBtn = document.getElementById('role-graph-zoom-out');
    const zoomResetBtn = document.getElementById('role-graph-reset');
    if (zoomInBtn) listen(zoomInBtn, 'click', zoomIn);
    if (zoomOutBtn) listen(zoomOutBtn, 'click', zoomOut);
    if (zoomResetBtn) listen(zoomResetBtn, 'click', zoomReset);

    const applyResize = () => {
      if (!container?.offsetParent) return;
      const cw = Math.max(container.offsetWidth, container.clientWidth, 1);
      const ch = Math.max(container.offsetHeight, container.clientHeight, 280);
      Graph.width(cw).height(ch);
    };
    const queueResize = () => {if (!resizeFrame) resizeFrame = requestAnimationFrame(() => {resizeFrame = 0;applyResize();});};
    listen(window, 'resize', queueResize);
    const ro = new ResizeObserver(queueResize);
    ro.observe(container);
    cleanups.push(() => ro.disconnect());
    let inView = false;
    const updateVisibility = () => {
      const active = inView && !document.hidden && container.getClientRects().length > 0;
      container.dataset.graphState = active ? 'active' : 'paused';
      if(active) {Graph.resumeAnimation();queueResize();} else Graph.pauseAnimation();
    };
    const visibility = new IntersectionObserver(entries => {inView = entries[0].isIntersecting;updateVisibility();}, {threshold:0});
    visibility.observe(container);
    listen(document, 'visibilitychange', updateVisibility);
    cleanups.push(() => visibility.disconnect());
    listen(renderer.domElement, 'webglcontextlost', e => {e.preventDefault();Graph.pauseAnimation();explorer.querySelector('.graph-fallback').hidden=false;});

    const applyTheme = () => {
      const c = getThemeColors();
      colors = c;
      Graph.backgroundColor('rgba(0,0,0,0)');
      Graph.linkColor(Graph.linkColor());
      Graph.nodeColor(colors.node);
      if (useCustomNodes) {
        Graph.graphData().nodes.forEach(node => node.__threeObj?.traverse(obj => {obj.geometry?.dispose();obj.material?.map?.dispose();obj.material?.dispose();}));
        Graph.nodeThreeObject(node => createSphereNodeWithText(node, colors.theme));
      }
      const wrap = container.closest('.role-graph-wrap');
      if (wrap) wrap.dataset.graphTheme = c.theme;
    };
    const themeObs = new MutationObserver(applyTheme);
    themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    cleanups.push(() => themeObs.disconnect());
  }

  function ensureDimensions() {
    const rect = container.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function ready() {
    return ensureDimensions() && window.ForceGraph3D && window.THREE;
  }
  let initialized = false;
  const initialize = () => {
    if (initialized || disposed || !ready()) return;
    initialized = true;
    clearInterval(retryTimer);
    try { doInit(); } catch (error) {
      console.warn('3D graph unavailable', error);
      explorer.querySelector('.graph-fallback').hidden = false;
    }
  };
  const lazy = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) initialize();
  }, {rootMargin:'100px'});
  lazy.observe(container);
  cleanups.push(() => lazy.disconnect());
  let tries = 0;
  retryTimer = setInterval(() => {
    if (++tries > 80 || disposed || initialized) {
      clearInterval(retryTimer);
      if (!initialized && (!window.ForceGraph3D || !window.THREE)) explorer.querySelector('.graph-fallback').hidden = false;
      return;
    }
    const rect=container.getBoundingClientRect();
    if (rect.bottom > 0 && rect.top < innerHeight + 100) initialize();
  }, 200);
  return cleanup;
}
