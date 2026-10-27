const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const COLORS = { hub: '#6366f1', topic: '#0d9488', formula: '#8b5cf6', sample: '#3b82f6', project: '#d97706', feature: '#64748b' };
const KINDS = { hub: '入口', topic: '主题', formula: '公式', sample: '示例', project: '作品', feature: '功能' };
const SYMBOLS = { hub: '◈', topic: '◎', formula: 'ƒ', sample: '▷', project: '◇', feature: '✦' };
const ACTION_SYMBOLS = { create: '✦', library: 'ƒ', samples: '▷', projects: '◇', 'input-text': 'T', 'input-formula': 'ƒ', 'input-image': '▧', sketch: '✎', search: '⌕', settings: '⚙', jobs: '≡', learning: '▤', 'course-packs': '▥', versions: '↺', export: '↑', help: '?', tutorial: '▷' };
const endpoint = value => typeof value === 'string' ? value : value?.id;

/** Only recorded links are traversed. Search may select disconnected nodes directly. */
export function graphPath(graph, start, end) {
  const ids = new Set((graph.nodes || []).map(node => node.id));
  if (!ids.has(start) || !ids.has(end)) return [];
  const previous = new Map([[start, null]]), queue = [start], adjacent = new Map();
  for (const link of graph.links || []) {
    const a = endpoint(link.source), b = endpoint(link.target);
    if (!ids.has(a) || !ids.has(b)) continue;
    if (!adjacent.has(a)) adjacent.set(a, []); if (!adjacent.has(b)) adjacent.set(b, []);
    adjacent.get(a).push(b); adjacent.get(b).push(a);
  }
  for (let index = 0; index < queue.length; index++) {
    const id = queue[index]; if (id === end) break;
    for (const neighbor of adjacent.get(id) || []) if (!previous.has(neighbor)) { previous.set(neighbor, id); queue.push(neighbor); }
  }
  if (!previous.has(end)) return [];
  const route = []; for (let id = end; id !== null; id = previous.get(id)) route.push(id);
  return route.reverse();
}

/** Deterministic 3D spring layout; input records and their links are never mutated. */
export function layoutGraph(graph) {
  const nodes = (graph.nodes || []).slice(0, 360), count = nodes.length;
  const index = new Map(nodes.map((node, i) => [node.id, i]));
  const links = (graph.links || []).flatMap(link => {
    const a = index.get(endpoint(link.source)), b = index.get(endpoint(link.target));
    return a === undefined || b === undefined || a === b ? [] : [[a, b]];
  });
  const positions = nodes.map((node, i) => {
    const angle = i * 2.399963, y = 1 - 2 * (i + .5) / Math.max(count, 1), r = Math.sqrt(1 - y * y);
    return [Math.cos(angle) * r * 120, y * 100, Math.sin(angle) * r * 100];
  });
  const velocity = positions.map(() => [0, 0, 0]);
  for (let step = 0; step < 100; step++) {
    const forces = positions.map(p => p.map(v => -v * .007));
    for (let a = 0; a < count; a++) for (let b = a + 1; b < count; b++) {
      const delta = positions[a].map((v, j) => v - positions[b][j]);
      const square = Math.max(16, delta.reduce((sum, v) => sum + v * v, 0));
      const scale = 1400 / (square * Math.sqrt(square));
      for (let j = 0; j < 3; j++) { const force = delta[j] * scale; forces[a][j] += force; forces[b][j] -= force; }
    }
    for (const [a, b] of links) {
      const delta = positions[b].map((v, j) => v - positions[a][j]);
      const distance = Math.hypot(...delta) || 1, scale = (distance - 43) / distance * .025;
      for (let j = 0; j < 3; j++) { const force = delta[j] * scale; forces[a][j] += force; forces[b][j] -= force; }
    }
    for (let i = 0; i < count; i++) for (let j = 0; j < 3; j++) {
      velocity[i][j] = (velocity[i][j] + forces[i][j]) * .78;
      positions[i][j] += clamp(velocity[i][j], -4, 4);
    }
  }
  return { nodes, links, positions };
}

/** A renderer-only view. Actions, graph records and navigation remain in its owner. */
export async function mountNebulaGraph(host, { graph, selected, labelIds = [], route = [], onSelect, renderMath, onUnavailable = () => {}, isCurrent = () => true, preferences = {} }) {
  const T = await import('/vendor/three/three.module.js');
  if (!isCurrent()) return null;
  const canvas = document.createElement('canvas'); canvas.className = 'nebula-canvas'; canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', '三维知识图谱。拖动旋转，双指或滚轮缩放，方向键旋转，加减键缩放。也可使用搜索和关联节点导航。');
  const context = canvas.getContext('webgl2', { alpha: true, antialias: true, powerPreference: 'low-power' });
  if (!context) throw new Error('此设备暂不支持 WebGL，已切换二维图谱。');
  const renderer = new T.WebGLRenderer({ canvas, context, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5)); renderer.setClearColor(0x000000, 0);
  const scene = new T.Scene(), camera = new T.PerspectiveCamera(42, 1, .1, 1800), cluster = new T.Group(); scene.add(cluster);
  scene.add(new T.AmbientLight(0xffffff, 2));
  const light = new T.DirectionalLight(0xffffff, 3); light.position.set(100, 180, 250); scene.add(light);
  const data = layoutGraph(graph), positions = data.positions.map(p => new T.Vector3(...p));
  const nodeIndex = new Map(data.nodes.map((node, i) => [node.id, i]));
  const sphere = new T.SphereGeometry(1, 14, 10), material = new T.MeshStandardMaterial({ roughness: .38, metalness: .08 });
  const points = new T.InstancedMesh(sphere, material, data.nodes.length), matrix = new T.Object3D();
  const color = new T.Color();
  data.nodes.forEach((node, i) => {
    matrix.position.copy(positions[i]); matrix.scale.setScalar(node.kind === 'hub' ? 4.8 : node.kind === 'topic' ? 3.6 : 2.5); matrix.updateMatrix();
    points.setMatrixAt(i, matrix.matrix); points.setColorAt(i, color.set(COLORS[node.kind] || COLORS.feature));
  });
  points.instanceMatrix.needsUpdate = true; if (points.instanceColor) points.instanceColor.needsUpdate = true; cluster.add(points);
  const edgePositions = new Float32Array(data.links.length * 6), edgeColors = new Float32Array(data.links.length * 6);
  data.links.forEach(([a, b], i) => { positions[a].toArray(edgePositions, i * 6); positions[b].toArray(edgePositions, i * 6 + 3); });
  const edgesGeometry = new T.BufferGeometry(); edgesGeometry.setAttribute('position', new T.BufferAttribute(edgePositions, 3));
  edgesGeometry.setAttribute('color', new T.BufferAttribute(edgeColors, 3));
  const edgesMaterial = new T.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: .36 });
  cluster.add(new T.LineSegments(edgesGeometry, edgesMaterial));
  const ringGeometry = new T.TorusGeometry(5, .32, 8, 36), ringMaterial = new T.MeshBasicMaterial({ color: '#7c3aed' });
  const ring = new T.Mesh(ringGeometry, ringMaterial); cluster.add(ring);
  const markerGeometry = new T.SphereGeometry(1.5, 10, 8), markerMaterial = new T.MeshBasicMaterial({ color: '#0ea5e9' });
  const marker = new T.Mesh(markerGeometry, markerMaterial); marker.visible = false; cluster.add(marker);
  const labels = document.createElement('div'); labels.className = 'nebula-labels';
  const leaders = document.createElementNS('http://www.w3.org/2000/svg','svg'); leaders.classList.add('nebula-leaders'); leaders.setAttribute('aria-hidden','true'); labels.append(leaders);
  host.replaceChildren(canvas, labels); host.classList.add('nebula-host'); host.dataset.renderer = 'webgl'; host.dataset.graphState = 'paused';
  host.dataset.nodeCount = String(data.nodes.length); host.dataset.linkCount = String(data.links.length);
  const buttons = new Map(), listeners = [], raycaster = new T.Raycaster();
  const systemMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let settings = { reducedMotion: false, graphMotion: true, graphLabels: true, ...preferences };
  let active = true, intersecting = true, disposed = false, frame = 0, last = 0, angle = .22, elevation = .18, distance = 320, frameCount = 0;
  let selectedId = selected, visibleIds = new Set(labelIds), routeIds = route, travel = 0, suppress = 0, navigation = null;
  let size = { width: 1, height: 1 }, focus = new T.Vector3(), focusTarget = new T.Vector3(), clickCandidate = null;
  const touches = new Map(); let gesture = null, hover = null;
  const reduced = () => systemMotion.matches || settings.reducedMotion === true;
  const motion = () => !reduced() && settings.graphMotion !== false;
  const labelsOn = () => settings.graphLabels !== false && settings.graphLabels !== 'none';
  const canRender = () => active && intersecting && !document.hidden && !disposed && host.getClientRects().length > 0;
  function listen(target, name, callback, options) { target.addEventListener(name, callback, options); listeners.push(() => target.removeEventListener(name, callback, options)); }
  function refreshColors() {
    const dark = document.documentElement.dataset.theme === 'dark';
    data.links.forEach(([a, b], i) => {
      const ids = [data.nodes[a].id, data.nodes[b].id];
      const routeEdge = routeIds.some((id, j) => j && ((id === ids[0] && routeIds[j - 1] === ids[1]) || (id === ids[1] && routeIds[j - 1] === ids[0])));
      color.set(routeEdge ? (dark ? '#b5a1ff' : '#8968d7') : ids.includes(selectedId) ? (dark ? '#8ca8ec' : '#8b9ed2') : (dark ? '#53638d' : '#bdc8e1'));
      color.toArray(edgeColors, i * 6); color.toArray(edgeColors, i * 6 + 3);
    }); edgesGeometry.attributes.color.needsUpdate = true;
  }
  function refreshLabels() {
    for (const [id, entry] of buttons) if (!visibleIds.has(id) && id !== selectedId) { entry.button.remove(); entry.leader.remove(); buttons.delete(id); }
    for (const id of new Set([selectedId, ...visibleIds])) {
      const i = nodeIndex.get(id); if (i === undefined) continue;
      let entry = buttons.get(id);
      if (!entry) {
        const node = data.nodes[i], button = document.createElement('button'); button.type = 'button'; button.className = 'nebula-label'; button.dataset.nodeId = id;
        button.title = node.label; button.setAttribute('aria-label', `${KINDS[node.kind] || '节点'}：${node.label}`);
        const symbol = document.createElement('span'); symbol.className = 'nebula-symbol'; symbol.textContent = (node.action?.type === 'navigate' ? ACTION_SYMBOLS[node.action.id] : null) || SYMBOLS[node.kind] || '✦'; symbol.setAttribute('aria-hidden', 'true');
        const title = document.createElement('strong'); title.textContent = node.label; button.append(symbol, title);
        if (node.latex) { const math = document.createElement('span'); math.className = 'nebula-math'; renderMath(math, node.latex); button.append(math); }
        button.style.setProperty('--nebula-node-color', COLORS[node.kind] || COLORS.feature);
        const leader = document.createElementNS(leaders.namespaceURI,'line'); leaders.append(leader);
        labels.append(button); entry = { button, leader, i }; buttons.set(id, entry);
      }
      entry.button.classList.toggle('nebula-selected', id === selectedId); entry.button.setAttribute('aria-pressed', String(id === selectedId));
    }
  }
  function resize() {
    if (disposed) return;
    const previousSize = size;
    size = { width: Math.max(1, host.clientWidth), height: Math.max(1, host.clientHeight) };
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5)); renderer.setSize(size.width, size.height, false);
    camera.aspect = size.width / size.height; camera.updateProjectionMatrix();
    if (size.width !== previousSize.width || size.height !== previousSize.height) updateSelection(selectedId, [...visibleIds], routeIds);
    else invalidate();
  }
  function projectLabels() {
    const occupied = [], vector = new T.Vector3();
    const ordered = [...buttons.entries()].sort(([a], [b]) => Number(b === selectedId) - Number(a === selectedId));
    for (const [id, { button, leader, i }] of ordered) {
      vector.copy(positions[i]).applyMatrix4(cluster.matrixWorld).project(camera);
      const valid = vector.z > -1 && vector.z < 1 && Math.abs(vector.x) < 1.2 && Math.abs(vector.y) < 1.2 && labelsOn();
      button.hidden = !valid; leader.style.display = valid ? '' : 'none'; if (!valid) continue;
      const width = button.offsetWidth || 105, height = button.offsetHeight || 42;
      const anchorX = (vector.x + 1) / 2 * size.width, anchorY = (1 - vector.y) / 2 * size.height;
      const baseX = clamp(anchorX, width / 2 + 8, size.width - width / 2 - 8), baseY = clamp(anchorY - 11 - height / 2, height / 2 + 9, size.height - height / 2 - 9);
      let x = baseX, y = baseY, best = Infinity;
      for (let dy = -3; dy <= 3; dy++) for (let dx = -2; dx <= 2; dx++) {
        const cx = clamp(baseX + dx * (width + 8), width / 2 + 6, size.width - width / 2 - 6);
        const cy = clamp(baseY + dy * (height + 9), height / 2 + 9, size.height - height / 2 - 9);
        const overlap = occupied.reduce((sum,r) => sum + Math.max(0,(r.w+width)/2+6-Math.abs(r.x-cx))*Math.max(0,(r.h+height)/2+6-Math.abs(r.y-cy)),0);
        const score = overlap * 10000 + (cx-baseX)**2 + (cy-baseY)**2;
        if (score < best) { best = score; x = cx; y = cy; }
      }
      occupied.push({ x, y, w: width, h: height });
      for (const [name,value] of Object.entries({x1:anchorX,y1:anchorY,x2:x,y2:y}))leader.setAttribute(name,value);
      button.style.left = `${x}px`; button.style.top = `${y}px`; button.style.zIndex = id === selectedId ? '5' : String(Math.max(1, Math.round(3 - vector.z)));
    }
  }
  function draw(time) {
    frame = 0; if (!canRender()) { host.dataset.graphState = 'paused'; return; }
    const dt = Math.min(.05, (time - (last || time)) / 1000); last = time;
    if (motion() && !touches.size && !hover && !host.contains(document.activeElement)) angle += dt * .035;
    if (navigation) {
      const t = reduced() ? 1 : clamp((time - navigation.start) / 650, 0, 1), ease = t * t * (3 - 2 * t);
      focus.lerpVectors(navigation.from, focusTarget, ease); if (t === 1) navigation = null;
    }
    camera.position.set(focus.x + Math.cos(elevation) * Math.sin(angle) * distance, focus.y + Math.sin(elevation) * distance, focus.z + Math.cos(elevation) * Math.cos(angle) * distance); camera.lookAt(focus);
    ring.visible = nodeIndex.has(selectedId); if (ring.visible) { ring.position.copy(positions[nodeIndex.get(selectedId)]); ring.quaternion.copy(camera.quaternion); }
    marker.visible = motion() && routeIds.length > 1;
    if (marker.visible) {
      travel = (travel + dt * .65) % (routeIds.length - 1); const segment = Math.floor(travel);
      const a = positions[nodeIndex.get(routeIds[segment])], b = positions[nodeIndex.get(routeIds[segment + 1])];
      if (a && b) marker.position.lerpVectors(a, b, travel - segment); else marker.visible = false;
    }
    renderer.render(scene, camera); projectLabels(); frameCount++;
    host.dataset.frameCount = String(frameCount); host.dataset.camera = `${angle.toFixed(3)},${elevation.toFixed(3)},${distance.toFixed(1)}`;
    host.dataset.graphState = motion() ? 'active' : 'still';
    if (motion() || navigation) frame = requestAnimationFrame(draw);
  }
  function invalidate() { if (canRender() && !frame) frame = requestAnimationFrame(draw); }
  function pause() { if (frame) cancelAnimationFrame(frame); frame = 0; last = 0; host.dataset.graphState = 'paused'; }
  function updateSelection(id, ids = [], path = []) {
    selectedId = id; visibleIds = new Set(ids); routeIds = path.filter(value => nodeIndex.has(value)); travel = 0;
    const index = nodeIndex.get(id);
    if (index !== undefined) {
      const related = [index, ...ids.map(value => nodeIndex.get(value)).filter(value => value !== undefined)];
      const center = related.reduce((sum, value) => sum.add(positions[value]), new T.Vector3()).divideScalar(related.length);
      focusTarget.copy(positions[index]).lerp(center, .45);
      const extent = Math.max(42, ...related.map(value => positions[value].distanceTo(focusTarget)));
      distance=clamp(Math.max(220,extent*2.45/Math.min(1,camera.aspect)+55),70,750);
      if (reduced()) { focus.copy(focusTarget); navigation = null; }
      else navigation = { from: focus.clone(), start: performance.now() };
    }
    refreshColors(); refreshLabels(); invalidate();
  }
  function hit(event) {
    const rect = canvas.getBoundingClientRect(); raycaster.setFromCamera(new T.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
    const result = raycaster.intersectObject(points)[0]; return result ? data.nodes[result.instanceId]?.id : null;
  }
  function beginGesture() {
    const values = [...touches.values()];
    gesture = values.length >= 2 ? { type: 'pinch', span: Math.hypot(values[1].x - values[0].x, values[1].y - values[0].y), distance } : values.length ? { type: 'orbit', x: values[0].x, y: values[0].y, angle, elevation, moved: false } : null;
  }
  listen(host, 'pointerdown', event => {
    if (event.button !== 0) return;
    clickCandidate = event.target.closest('.nebula-label')?.dataset.nodeId || null;
    touches.set(event.pointerId, { x: event.clientX, y: event.clientY }); beginGesture();
    if (touches.size > 1) { clickCandidate = null; suppress = performance.now() + 500; }
    canvas.setPointerCapture(event.pointerId); if (event.target === canvas) canvas.focus({ preventScroll: true });
  });
  listen(host, 'pointermove', event => {
    if (!touches.has(event.pointerId)) return;
    touches.set(event.pointerId, { x: event.clientX, y: event.clientY }); const values = [...touches.values()];
    if (gesture?.type === 'pinch' && values.length > 1) {
      const span = Math.hypot(values[1].x - values[0].x, values[1].y - values[0].y); distance = clamp(gesture.distance * gesture.span / Math.max(span, 10), 70, 750); suppress = performance.now() + 500;
    } else if (gesture?.type === 'orbit') {
      const dx = values[0].x - gesture.x, dy = values[0].y - gesture.y;
      if (dx * dx + dy * dy < 25 && !gesture.moved) return;
      gesture.moved = true; angle = gesture.angle - dx * .007; elevation = clamp(gesture.elevation + dy * .006, -1.35, 1.35); suppress = performance.now() + 500;
    }
    event.preventDefault(); navigation = null; host.dataset.dragging = 'true'; invalidate();
  });
  const finish = event => { touches.delete(event.pointerId); if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId); beginGesture(); if (!touches.size) delete host.dataset.dragging; invalidate(); };
  listen(canvas, 'pointerup', finish); listen(canvas, 'pointercancel', finish); listen(canvas, 'lostpointercapture', event => { if (touches.has(event.pointerId)) finish(event); });
  listen(host, 'click', event => {
    if (event.detail && performance.now() < suppress) { event.preventDefault(); return; }
    const id = event.target.closest('.nebula-label')?.dataset.nodeId || clickCandidate || (event.target === canvas ? hit(event) : null); clickCandidate = null; if (id) onSelect(id);
  });
  listen(host, 'pointerover', event => { hover = event.target.closest('.nebula-label')?.dataset.nodeId || null; });
  listen(host, 'pointerleave', () => { hover = null; });
  listen(host, 'wheel', event => { event.preventDefault(); distance = clamp(distance * Math.exp(clamp(event.deltaY, -100, 100) * .002), 70, 750); invalidate(); }, { passive: false });
  listen(canvas, 'keydown', event => {
    const keys = { ArrowLeft: [-.12, 0], ArrowRight: [.12, 0], ArrowUp: [0, .12], ArrowDown: [0, -.12] };
    if (Object.hasOwn(keys, event.key)) { event.preventDefault(); angle += keys[event.key][0]; elevation = clamp(elevation + keys[event.key][1], -1.35, 1.35); invalidate(); }
    else if (['+', '=', '-'].includes(event.key)) { event.preventDefault(); distance = clamp(distance * (event.key === '-' ? 1.15 : .87), 70, 750); invalidate(); }
  });
  listen(document, 'visibilitychange', () => { if (document.hidden) pause(); else invalidate(); });
  listen(systemMotion, 'change', () => { if (reduced()) { navigation = null; focus.copy(focusTarget); } pause(); invalidate(); });
  listen(canvas, 'webglcontextlost', event => { event.preventDefault(); pause(); onUnavailable('三维画面已暂停，已切换二维图谱。'); });
  const resizeObserver = new ResizeObserver(resize); resizeObserver.observe(host);
  const themeObserver = new MutationObserver(() => { refreshColors(); invalidate(); }); themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  const intersection = new IntersectionObserver(entries => { intersecting = entries[0].isIntersecting; if (intersecting) invalidate(); else pause(); }); intersection.observe(host);
  refreshColors(); refreshLabels(); resize(); updateSelection(selectedId, labelIds, route);
  return {
    select: updateSelection,
    setActive(value) { active = Boolean(value); if (active) { resize(); invalidate(); } else pause(); },
    setPreferences(value = {}) { settings = { ...settings, ...value }; if (reduced()) { navigation = null; focus.copy(focusTarget); } pause(); invalidate(); },
    zoom(factor) { distance = clamp(distance * factor, 70, 750); invalidate(); },
    reset() { angle = .22; elevation = .18; distance = clamp(Math.max(...positions.map(p=>p.length()),80)*2.7/Math.min(1,camera.aspect)+80,270,750); focusTarget.set(0, 0, 0); focus.copy(focusTarget); navigation = null; invalidate(); },
    dispose() {
      if (disposed) return; disposed = true; pause();
      for (const id of touches.keys()) if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id);
      touches.clear(); listeners.forEach(remove => remove()); resizeObserver.disconnect(); themeObserver.disconnect(); intersection.disconnect();
      points.dispose(); sphere.dispose(); material.dispose(); edgesGeometry.dispose(); edgesMaterial.dispose(); ringGeometry.dispose(); ringMaterial.dispose(); markerGeometry.dispose(); markerMaterial.dispose();
      renderer.dispose(); renderer.forceContextLoss(); host.replaceChildren(); host.classList.remove('nebula-host'); host.dataset.graphState = 'disposed'; buttons.clear();
    },
  };
}
