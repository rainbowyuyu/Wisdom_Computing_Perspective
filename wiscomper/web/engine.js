/* A fixed renderer for the versioned scene contract. No executable scene content. */
import {interactionDefaults, updateInteractionValues, dragValue, interactionOffsets, applyInteractionOffsets, normalizeView} from './interactions.js';
const FIELDS = ['x', 'y', 'z', 'rotation', 'rotation_x', 'rotation_y', 'scale', 'opacity', 'draw'];
const clamp = (n, a = 0, b = 1) => Math.min(b, Math.max(a, n));
const defaults = {x: 0, y: 0, z: 0, rotation: 0, rotation_x: 0, rotation_y: 0, scale: 1, opacity: 1, draw: 1};
const cloneState = o => Object.fromEntries(FIELDS.map(k => [k, o[k] ?? defaults[k]]));

export function compileFrames(object) {
  let previous = cloneState(object);
  return (object.frames || []).map(frame => {
    const state = {...previous};
    for (const key of FIELDS) if (frame[key] != null) state[key] = frame[key];
    previous = state;
    return {t: frame.t, ...state};
  });
}

export function sampleObject(object, seconds, frames = compileFrames(object)) {
  if (!frames.length || seconds < frames[0].t) return cloneState(object);
  let low = 0, high = frames.length - 1;
  while (low < high) { const middle = Math.ceil((low + high) / 2); if (frames[middle].t <= seconds) low = middle; else high = middle - 1; }
  const i = low;
  const a = frames[i], b = frames[i + 1];
  if (!b) return cloneState(a);
  const u = clamp((seconds - a.t) / (b.t - a.t));
  return Object.fromEntries(FIELDS.map(k => [k, a[k] + (b[k] - a[k]) * u]));
}

export function partialPath(points, fraction) {
  if (!points.length || fraction <= 0) return [];
  if (fraction >= 1) return points.map(p => [...p]);
  const lengths = points.slice(1).map((p, i) => Math.hypot(...[0, 1, 2].map(j => (p[j] || 0) - (points[i][j] || 0))));
  let remaining = lengths.reduce((a, b) => a + b, 0) * fraction;
  const result = [[...points[0]]];
  for (let i = 0; i < lengths.length; i++) {
    if (remaining >= lengths[i]) { result.push([...points[i + 1]]); remaining -= lengths[i]; }
    else {
      const u = lengths[i] ? remaining / lengths[i] : 0;
      result.push(Array.from({length: Math.max(points[i].length, points[i + 1].length)}, (_, j) => (points[i][j] || 0) + ((points[i + 1][j] || 0) - (points[i][j] || 0)) * u));
      break;
    }
  }
  return result;
}

let katexPromise;
async function loadKatex() {
  if (globalThis.katex) return globalThis.katex;
  if (!katexPromise) katexPromise = new Promise((resolve, reject) => {
    if (!document.querySelector('link[data-scene-katex]')) {
      const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/vendor/katex/katex.min.css'; css.dataset.sceneKatex = 'true'; document.head.append(css);
    }
    const script = document.createElement('script'); script.src = '/vendor/katex/katex.min.js';
    script.onload = () => globalThis.katex ? resolve(globalThis.katex) : reject(new Error('公式渲染器未能加载。'));
    script.onerror = () => reject(new Error('本地公式渲染依赖不可用。'));
    document.head.append(script);
  }).catch(error => { katexPromise = null; throw error; });
  return katexPromise;
}

function style(el, values) { Object.assign(el.style, values); return el; }
function distanceToSegment(px, py, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], d = dx * dx + dy * dy;
  const t = d ? clamp(((px - a[0]) * dx + (py - a[1]) * dy) / d) : 0;
  return Math.hypot(px - a[0] - t * dx, py - a[1] - t * dy);
}

export class ScenePlayer {
  constructor(host) {
    if (!host) throw new Error('需要指定场景容器。');
    this.host = host; this._time = 0; this._playing = false; this.speed = 1;
    this.hidden = new Set(); this.images = new Map(); this.nodes = new Map(); this.frameTables = new Map(); this.states = new Map(); this.objectTable = new Map();
    this.generation = 0; this.disposed = false; this.selected = null;
    this.interactionValues = {}; this.view = null; this.manipulationMode = 'interact'; this.pointers = new Map(); this.gesture = null;
    this.surface = style(document.createElement('div'), {position: 'absolute', overflow: 'hidden', touchAction: 'none', userSelect: 'none'});
    this.canvas = style(document.createElement('canvas'), {position: 'absolute', inset: '0', width: '100%', height: '100%'});
    this.overlay = style(document.createElement('div'), {position: 'absolute', inset: '0', pointerEvents: 'none', overflow: 'hidden'});
    this.surface.append(this.canvas, this.overlay); host.append(this.surface);
    this.inputHandlers = {
      pointerdown: event => this._pointerDown(event), pointermove: event => this._pointerMove(event),
      pointerup: event => this._pointerEnd(event), pointercancel: event => this._pointerEnd(event, true),
      lostpointercapture: event => this._pointerEnd(event, true), wheel: event => this._wheel(event),
    };
    for (const [type, handler] of Object.entries(this.inputHandlers)) this.surface.addEventListener(type, handler, {passive: false});
    this.resizeObserver = new ResizeObserver(() => this.resize()); this.resizeObserver.observe(host);
    this.resize();
  }
  get time() { return this._time; }
  get playing() { return this._playing; }
  async load(scene) {
    this.pause(); const generation = ++this.generation; this._clearScene();
    this.scene = scene; this._time = 0; this.hidden.clear(); this.selected = null;
    this.interactionValues = interactionDefaults(scene.interactions); this.view = null; this.manipulationMode = scene.mode === '3d' ? 'observe' : 'interact';
    this._updateCursor();
    this.surface.style.background = scene.background;
    for (const object of scene.objects) { this.frameTables.set(object.id, compileFrames(object)); this.objectTable.set(object.id, object); }
    if (scene.objects.some(o => o.kind === 'formula')) await loadKatex();
    if (generation !== this.generation || this.disposed) return;
    await Promise.all(scene.objects.filter(o => o.kind === 'image').map(async object => {
      if (!/^[a-zA-Z0-9_-]{1,64}$/.test(object.asset_id || '')) throw new Error('图片素材引用无效。');
      const image = new Image(); image.decoding = 'sync';
      await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = () => reject(new Error('无法读取场景图片。')); image.src = `/api/assets/${encodeURIComponent(object.asset_id)}`; });
      if (generation === this.generation) this.images.set(object.id, image);
    }));
    if (generation !== this.generation || this.disposed) return;
    if (scene.mode === '3d') await this._init3d(scene, generation);
    if (generation !== this.generation || this.disposed) return;
    for (const object of scene.objects) {
      if (object.kind === 'formula' || (scene.mode === '3d' && object.kind === 'text')) this._makeOverlay(object);
    }
    if (document.fonts) await document.fonts.ready;
    this.resize(); this.seek(0);
  }
  _makeOverlay(object) {
    const node = style(document.createElement('div'), {position: 'absolute', color: object.color, whiteSpace: 'nowrap', transformOrigin: 'center', textAlign: 'center', fontFamily: 'Arial, Microsoft YaHei, sans-serif'});
    node.dataset.objectId = object.id;
    if (object.kind === 'formula') {
      for (const [key, latex] of [['first', object.latex], ['next', object.latex_next]]) {
        if (!latex && key === 'next') continue;
        const span = style(document.createElement('span'), {display: 'block', gridArea: '1 / 1'});
        globalThis.katex.render(latex || '\\text{公式}', span, {throwOnError: false, trust: false, strict: 'error', displayMode: true, maxExpand: 1000, maxSize: 20});
        span.querySelectorAll('.katex-display').forEach(display => { display.style.margin = '0'; });
        span.dataset.phase = key; node.append(span);
      }
      node.style.display = 'grid';
    } else { node.textContent = object.text; if (this.scene.mode === '3d') node.style.textShadow = '0 1px 5px #08121f, 0 0 12px #08121f'; }
    this.overlay.append(node); this.nodes.set(object.id, node);
  }
  async _init3d(scene, generation) {
    const T = await import('/vendor/three/three.module.js');
    if (generation !== this.generation || this.disposed) return;
    this.T = T;
    // Canvas contexts cannot switch between 2D and WebGL; recreate on each load.
    this.renderer = new T.WebGLRenderer({canvas: this.canvas, antialias: true, alpha: false, preserveDrawingBuffer: true});
    this.renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = T.SRGBColorSpace;
    this.world = new T.Scene(); this.world.background = new T.Color(scene.background);
    this.camera = new T.PerspectiveCamera(40, 16 / 9, .1, 200);
    this.world.add(new T.AmbientLight(0xffffff, 1.6));
    const light = new T.DirectionalLight(0xffffff, 3); light.position.set(6, 9, 10); this.world.add(light);
    const rim = new T.DirectionalLight(0x96bfff, 1.5); rim.position.set(-6, 2, -5); this.world.add(rim);
    this.meshes = new Map(); this.renderMaterials = new Map();
    for (const object of scene.objects) {
      let node;
      if (['group', 'text', 'formula'].includes(object.kind)) node = new T.Group();
      else if (['line', 'arrow', 'path'].includes(object.kind)) {
        node = new T.Group();
        const geometry = new T.BufferGeometry(); geometry.setAttribute('position', new T.BufferAttribute(new Float32Array(object.points.length * 3), 3));
        const line = new T.Line(geometry, new T.LineBasicMaterial({color: object.stroke, transparent: true})); node.add(line); node.userData.line = line;
        if (object.kind === 'arrow') { const cone = new T.Mesh(new T.ConeGeometry(.1, .3, 16), new T.MeshStandardMaterial({color: object.stroke, transparent: true})); node.add(cone); node.userData.cone = cone; }
      } else {
        const material = new T.MeshStandardMaterial({color: object.color, roughness: .4, metalness: .22, transparent: true, side: T.DoubleSide, wireframe: !object.filled});
        let geometry;
        if (object.kind === 'sphere') geometry = new T.SphereGeometry(object.radius, 40, 24);
        else if (object.kind === 'cylinder') geometry = new T.CylinderGeometry(object.radius, object.radius, object.height, 40);
        else if (object.kind === 'cone') geometry = new T.ConeGeometry(object.radius, object.height, 40);
        else if (object.kind === 'torus') geometry = new T.TorusGeometry(object.radius, object.tube_radius ?? .1, 12, 96);
        else if (object.kind === 'prism') {
          const shape = new T.Shape(); object.points.forEach((p, i) => i ? shape.lineTo(p[0], p[1]) : shape.moveTo(p[0], p[1])); shape.closePath();
          geometry = new T.ExtrudeGeometry(shape, {depth: object.depth, bevelEnabled: false, steps: 1, curveSegments: 16}); geometry.translate(0, 0, -object.depth / 2); geometry.computeVertexNormals();
        }
        else if (object.kind === 'circle') geometry = new T.CircleGeometry(object.radius, 64);
        else if (object.kind === 'rect' || object.kind === 'image') geometry = new T.PlaneGeometry(object.width, object.height);
        else geometry = new T.BoxGeometry(object.width, object.height, object.depth);
        if (object.kind === 'image') { const texture = new T.Texture(this.images.get(object.id)); texture.colorSpace = T.SRGBColorSpace; texture.needsUpdate = true; material.map = texture; material.color.set('#ffffff'); material.metalness = 0; }
        node = new T.Mesh(geometry, material);
      }
      node.userData.objectId = object.id; this.meshes.set(object.id, node);
      const owned = []; node.traverse(child => { if (child.material) owned.push(...(Array.isArray(child.material) ? child.material : [child.material])); }); this.renderMaterials.set(object.id, owned);
    }
    // Resolve after creating every node: JSON order is not a hierarchy constraint.
    for (const object of scene.objects) {
      const parent = object.parent_id ? this.meshes.get(object.parent_id) : this.world;
      if (!parent) throw new Error('三维图层引用了不存在的父对象。');
      parent.add(this.meshes.get(object.id));
    }
    this.raycaster = new T.Raycaster(); this.raycaster.params.Line.threshold = .15;
  }
  resize() {
    const box = this.host.getBoundingClientRect(); this.width = Math.max(16, Math.min(box.width, box.height * 16 / 9)); this.height = this.width * 9 / 16;
    Object.assign(this.surface.style, {width: `${this.width}px`, height: `${this.height}px`, left: `${(box.width - this.width) / 2}px`, top: `${(box.height - this.height) / 2}px`});
    this.unit = this.width / 16;
    if (this.renderer) this.renderer.setSize(this.width, this.height, false);
    else { const dpr = Math.min(globalThis.devicePixelRatio || 1, 2); this.canvas.width = Math.round(this.width * dpr); this.canvas.height = Math.round(this.height * dpr); }
    if (this.scene) this._render();
  }
  seek(seconds) { this._time = clamp(Number.isFinite(seconds) ? seconds : 0, 0, this.scene?.duration || 0); this._render(); this._emit(); }
  play() {
    if (!this.scene || this._playing) return;
    if (this._time >= this.scene.duration) this.seek(0);
    this._playing = true; let previous;
    const tick = now => {
      if (!this._playing) return;
      if (previous != null) this._time = Math.min(this.scene.duration, this._time + (now - previous) / 1000 * this.speed);
      previous = now;
      if (this._time >= this.scene.duration) this._playing = false;
      this._render(); this._emit(); if (this._playing) this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick); this._emit();
  }
  pause() { this._playing = false; cancelAnimationFrame(this.raf); this._emit(); }
  setSpeed(speed) { this.speed = clamp(Number(speed) || 1, .1, 4); }
  setVisible(id, visible) { if (visible) this.hidden.delete(id); else this.hidden.add(id); this._render(); }
  setInteractionValues(values) { this.interactionValues = updateInteractionValues(this.scene?.interactions || [], this.interactionValues, values); this._render(); }
  getInteractionValues() { return {...this.interactionValues}; }
  setView(camera) { this._cancelInput(); this.view = this.scene?.mode === '3d' ? normalizeView(camera) : null; this._render(); }
  getView() { return this.view ? {...this.view} : null; }
  setManipulationMode(mode) {
    if (!['observe', 'interact'].includes(mode)) return;
    this._cancelInput(true); this.manipulationMode = mode; this._updateCursor();
  }
  resetExploration() {
    this._cancelInput(); this.interactionValues = interactionDefaults(this.scene?.interactions); this.view = null; this._render();
  }
  select(id) { this.selected = this.scene?.objects.some(o => o.id === id) ? id : null; this._render(); this.host.dispatchEvent(new CustomEvent('scene-select', {detail: {id: this.selected}})); }
  _emit() { this.host.dispatchEvent(new CustomEvent('scene-time', {detail: {time: this._time, duration: this.scene?.duration || 0, playing: this._playing}})); }
  _render() {
    if (!this.scene || this.disposed) return;
    const offsets = interactionOffsets(this.scene.interactions, this.interactionValues);
    for (const object of this.scene.objects) this.states.set(object.id, applyInteractionOffsets(sampleObject(object, this._time, this.frameTables.get(object.id)), offsets.get(object.id)));
    if (this.scene.mode === '3d') { if (this.renderer) this._render3d(); }
    else this._render2d();
    for (const object of this.scene.objects) {
      const node = this.nodes.get(object.id); if (!node) continue;
      const state = this.states.get(object.id); let x = (state.x + 8) * this.unit, y = (4.5 - state.y) * this.unit, inView = true, opacity = state.opacity, scale = state.scale;
      if (this.scene.mode === '3d' && this.camera) {
        const anchor = this.meshes.get(object.id), point = anchor.getWorldPosition(new this.T.Vector3()).project(this.camera); x = (point.x + 1) * this.width / 2; y = (1 - point.y) * this.height / 2;
        inView = point.z >= -1 && point.z <= 1 && Math.abs(point.x) <= 1.15 && Math.abs(point.y) <= 1.15 && anchor.userData.effectiveVisible;
        opacity = anchor.userData.effectiveOpacity; scale = anchor.getWorldScale(new this.T.Vector3()).x;
      }
      node.style.visibility = this.hidden.has(object.id) || !inView ? 'hidden' : 'visible';
      Object.assign(node.style, {left: `${x}px`, top: `${y}px`, fontSize: `${object.font_size * this.unit}px`, opacity: String(opacity), transform: `translate(-50%, -50%) rotate(${this.scene.mode === '3d' ? 0 : -state.rotation}rad) scale(${scale})`, outline: this.selected === object.id ? '1px dashed #ffffff99' : 'none'});
      const transition = clamp((this._time - this.scene.duration / 2) / .6 + .5);
      if (object.latex_next) { node.children[0].style.opacity = String(1 - transition); node.children[1].style.opacity = String(transition); }
    }
  }
  _render2d() {
    const ctx = this.canvas.getContext('2d'); if (!ctx) return;
    const sx = this.canvas.width / this.width; ctx.setTransform(sx, 0, 0, sx, 0, 0); ctx.fillStyle = this.scene.background; ctx.fillRect(0, 0, this.width, this.height);
    for (const object of this.scene.objects) {
      if (object.kind === 'formula' || this.hidden.has(object.id)) continue;
      const state = this.states.get(object.id); if (state.opacity <= 0) continue;
      ctx.save(); ctx.translate((state.x + 8) * this.unit, (4.5 - state.y) * this.unit); ctx.rotate(-state.rotation); ctx.scale(state.scale * this.unit, state.scale * this.unit);
      ctx.globalAlpha = state.opacity; ctx.fillStyle = object.color; ctx.strokeStyle = object.stroke; ctx.lineWidth = object.line_width; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      const points = partialPath(object.points || [], state.draw);
      if (['line', 'path', 'arrow'].includes(object.kind)) {
        if (points.length > 1) {
          ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(p[0], -p[1]) : ctx.moveTo(p[0], -p[1])); ctx.stroke();
          if (object.kind === 'arrow') { const a = points.at(-2), b = points.at(-1), angle = Math.atan2(-(b[1] - a[1]), b[0] - a[0]), head = Math.max(.13, object.line_width * 4); ctx.beginPath(); ctx.moveTo(b[0], -b[1]); ctx.lineTo(b[0] - head * Math.cos(angle - .45), -b[1] - head * Math.sin(angle - .45)); ctx.lineTo(b[0] - head * Math.cos(angle + .45), -b[1] - head * Math.sin(angle + .45)); ctx.closePath(); ctx.fillStyle = object.stroke; ctx.fill(); }
        }
      } else if (['circle', 'sphere'].includes(object.kind)) {
        ctx.beginPath(); ctx.arc(0, 0, object.radius, 0, Math.PI * 2 * state.draw); if (object.filled) ctx.fill(); ctx.stroke();
      } else if (['rect', 'box', 'cylinder'].includes(object.kind)) {
        const w = object.kind === 'cylinder' ? object.radius * 2 : object.width;
        const path = [[-w / 2, object.height / 2], [w / 2, object.height / 2], [w / 2, -object.height / 2], [-w / 2, -object.height / 2], [-w / 2, object.height / 2]];
        if (object.filled) ctx.fillRect(-w / 2, -object.height / 2, w, object.height);
        ctx.beginPath(); partialPath(path, state.draw).forEach((p, i) => i ? ctx.lineTo(p[0], -p[1]) : ctx.moveTo(p[0], -p[1])); ctx.stroke();
      } else if (object.kind === 'text') {
        ctx.font = `${object.font_size}px Arial, "Microsoft YaHei", sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const lines = String(object.text).split('\n'); lines.forEach((line, i) => ctx.fillText(line, 0, (i - (lines.length - 1) / 2) * object.font_size * 1.35));
      } else if (object.kind === 'image') {
        const image = this.images.get(object.id); if (image) { const ratio = Math.min(object.width / image.width, object.height / image.height), w = image.width * ratio, h = image.height * ratio; ctx.drawImage(image, -w / 2, -h / 2, w, h); }
      }
      if (this.selected === object.id) { const bounds = this._bounds(object); ctx.globalAlpha = .8; ctx.strokeStyle = '#ffffff'; ctx.lineWidth = .018; ctx.setLineDash([.08, .06]); ctx.strokeRect(bounds[0] - .08, -bounds[3] - .08, bounds[2] - bounds[0] + .16, bounds[3] - bounds[1] + .16); }
      ctx.restore();
    }
  }
  _render3d() {
    const T = this.T, {azimuth: angle, elevation, distance} = this._cameraAtTime();
    this.camera.position.set(distance * Math.cos(elevation) * Math.sin(angle), distance * Math.sin(elevation), distance * Math.cos(elevation) * Math.cos(angle)); this.camera.lookAt(0, 0, 0); this.camera.updateMatrixWorld();
    const effective = new Map();
    const inherited = id => {
      if (effective.has(id)) return effective.get(id);
      const object = this.objectTable.get(id), state = this.states.get(id), parent = object.parent_id ? inherited(object.parent_id) : {opacity: 1, visible: true, selected: false};
      const value = {opacity: state.opacity * parent.opacity, visible: !this.hidden.has(id) && state.opacity > 0 && parent.visible, selected: this.selected === id || parent.selected}; effective.set(id, value); return value;
    };
    for (const object of this.scene.objects) {
      const node = this.meshes.get(object.id); if (!node) continue; const state = this.states.get(object.id);
      const visibility = inherited(object.id);
      node.visible = visibility.visible; node.userData.effectiveVisible = visibility.visible; node.userData.effectiveOpacity = visibility.opacity;
      node.position.set(state.x, state.y, state.z); node.rotation.set(state.rotation_x, state.rotation_y, state.rotation, 'XYZ'); node.scale.setScalar(state.scale);
      for (const material of this.renderMaterials.get(object.id) || []) { material.opacity = visibility.opacity; material.depthWrite = visibility.opacity >= .99; if (material.emissive) material.emissive.set(visibility.selected ? '#293c45' : '#000000'); }
      if (node.userData.line) {
        const points = partialPath(object.points, state.draw), geometry = node.userData.line.geometry;
        const positions = geometry.getAttribute('position'); points.forEach((p, i) => positions.setXYZ(i, p[0], p[1], p[2] || 0)); positions.needsUpdate = true; geometry.setDrawRange(0, points.length); geometry.computeBoundingSphere(); node.userData.line.visible = points.length > 1;
        const cone = node.userData.cone;
        if (cone) { cone.visible = points.length > 1; if (points.length > 1) { const a = new T.Vector3(...[points.at(-2)[0], points.at(-2)[1], points.at(-2)[2] || 0]), b = new T.Vector3(...[points.at(-1)[0], points.at(-1)[1], points.at(-1)[2] || 0]), direction = b.clone().sub(a).normalize(); cone.position.copy(b).addScaledVector(direction, -.12); cone.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), direction); } }
      }
    }
    this.world.updateMatrixWorld(true); this.renderer.render(this.world, this.camera);
  }
  _bounds(object) {
    if (object.points?.length) return [Math.min(...object.points.map(p => p[0])), Math.min(...object.points.map(p => p[1])), Math.max(...object.points.map(p => p[0])), Math.max(...object.points.map(p => p[1]))];
    let w = object.width, h = object.height;
    if (['circle', 'sphere'].includes(object.kind)) w = h = object.radius * 2;
    if (object.kind === 'text') { w = Math.max(...object.text.split('\n').map(s => [...s].length)) * object.font_size * .8; h = object.text.split('\n').length * object.font_size * 1.35; }
    return [-w / 2, -h / 2, w / 2, h / 2];
  }
  _cameraAtTime() {
    const camera = normalizeView(this.view || this.scene?.camera || {});
    return {...camera, azimuth: camera.azimuth + camera.orbit * this._time / (this.scene?.duration || 1), orbit: 0};
  }
  _dragControl(id) {
    // A declared assembly can be manipulated by grabbing any of its visible parts.
    while (id) {
      const control = this.scene?.interactions?.find(item => item.drag?.target_id === id);
      if (control) return control;
      id = this.objectTable.get(id)?.parent_id;
    }
    return null;
  }
  _updateCursor(event) {
    if (this.gesture?.started && ['orbit', 'pinch'].includes(this.gesture.type)) this.surface.style.cursor = 'grabbing';
    else if (this.scene?.mode === '3d' && this.manipulationMode === 'observe') this.surface.style.cursor = 'grab';
    else {
      const control = event && this._dragControl(this._hitTest(event));
      this.surface.style.cursor = control ? (control.drag.axis === 'vertical' ? 'ns-resize' : 'ew-resize') : 'default';
    }
  }
  _interactionEvent(committed) { this.host.dispatchEvent(new CustomEvent('scene-interaction', {detail: {values: this.getInteractionValues(), committed}})); }
  _viewEvent(committed) { this.host.dispatchEvent(new CustomEvent('scene-view', {detail: {camera: this.getView(), committed}})); }
  _commitGesture() {
    if (!this.gesture?.changed) return;
    if (this.gesture.type === 'interaction') this._interactionEvent(true);
    else if (['orbit', 'pinch'].includes(this.gesture.type)) this._viewEvent(true);
    this.gesture.changed = false;
  }
  _commitWheel() {
    if (!this.wheelTimer) return;
    clearTimeout(this.wheelTimer); this.wheelTimer = null; this._viewEvent(true);
  }
  _cancelInput(commit = false) {
    if (commit) { this._commitGesture(); this._commitWheel(); }
    clearTimeout(this.wheelTimer); this.wheelTimer = null; this.gesture = null;
    const ids = [...this.pointers.keys()]; this.pointers.clear();
    for (const id of ids) if (this.surface.hasPointerCapture(id)) this.surface.releasePointerCapture(id);
    this._updateCursor();
  }
  _pointerDown(event) {
    if (!this.scene || this.disposed || (event.pointerType === 'mouse' && event.button !== 0)) return;
    event.preventDefault(); this._commitWheel();
    this.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
    this.surface.setPointerCapture(event.pointerId);
    if (this.pointers.size > 1) {
      this._commitGesture();
      if (this.scene.mode === '3d') {
        const points = [...this.pointers.values()].slice(0, 2);
        this.gesture = {type: 'pinch', center: {x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2}, gap: Math.max(1, Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y)), camera: this._cameraAtTime(), moved: true, changed: false};
      } else this.gesture = {type: 'select', moved: true, changed: false};
      return;
    }
    const hit = this._hitTest(event), control = this.manipulationMode === 'interact' ? this._dragControl(hit) : null;
    const type = control ? 'interaction' : this.scene.mode === '3d' && (this.manipulationMode === 'observe' || !hit) ? 'orbit' : 'select';
    this.gesture = {type, pointerId: event.pointerId, x: event.clientX, y: event.clientY, hit, control, initial: control ? this.interactionValues[control.id] : null, moved: false, started: false, changed: false};
  }
  _pointerMove(event) {
    if (!this.pointers.has(event.pointerId) || !this.gesture) { this._updateCursor(event); return; }
    event.preventDefault(); this.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
    const gesture = this.gesture;
    let dx, dy, ratio = 1;
    if (gesture.type === 'pinch') {
      const points = [...this.pointers.values()].slice(0, 2);
      if (points.length < 2) return;
      const gap = Math.max(1, Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y));
      dx = (points[0].x + points[1].x) / 2 - gesture.center.x; dy = (points[0].y + points[1].y) / 2 - gesture.center.y; ratio = gesture.gap / gap;
      if (!gesture.started && Math.max(Math.hypot(dx, dy), Math.abs(gap - gesture.gap)) < 5) return;
    } else {
      if (event.pointerId !== gesture.pointerId) return;
      dx = event.clientX - gesture.x; dy = event.clientY - gesture.y;
      if (!gesture.started && Math.hypot(dx, dy) < 5) return;
    }
    gesture.moved = true;
    if (gesture.type === 'select') return;
    if (!gesture.started) {
      gesture.started = true; gesture.camera = this._cameraAtTime(); this.pause();
      if (gesture.type === 'interaction') this.select(gesture.hit);
      this._updateCursor();
    }
    if (gesture.type === 'interaction') {
      const value = dragValue(gesture.control, gesture.initial, gesture.control.drag.axis === 'vertical' ? -dy : dx);
      if (value === this.interactionValues[gesture.control.id]) return;
      this.interactionValues = {...this.interactionValues, [gesture.control.id]: value}; this._render(); gesture.changed = true; this._interactionEvent(false);
    } else {
      const camera = normalizeView({...gesture.camera, azimuth: gesture.camera.azimuth - dx * .006, elevation: gesture.camera.elevation + dy * .006, distance: gesture.camera.distance * ratio, orbit: 0});
      if (this.view && Object.keys(camera).every(key => this.view[key] === camera[key])) return;
      this.view = camera; this._render(); gesture.changed = true; this._viewEvent(false);
    }
  }
  _pointerEnd(event, cancelled = false) {
    if (!this.pointers.has(event.pointerId)) return;
    // Include a final movement even when a browser coalesces the last pointermove.
    if (!cancelled) this._pointerMove(event);
    const gesture = this.gesture;
    this.pointers.delete(event.pointerId);
    if (this.surface.hasPointerCapture(event.pointerId)) this.surface.releasePointerCapture(event.pointerId);
    this._commitGesture();
    if (!cancelled && gesture && !gesture.moved && gesture.pointerId === event.pointerId) this._pick(event);
    this.gesture = null;
    if (this.pointers.size === 1) {
      const [pointerId, point] = [...this.pointers][0];
      // Continuing a pinch with one finger may orbit, but must never become a click.
      this.gesture = {type: this.scene.mode === '3d' ? 'orbit' : 'select', pointerId, x: point.x, y: point.y, moved: true, started: false, changed: false};
    }
    this._updateCursor();
  }
  _wheel(event) {
    if (!this.scene || this.scene.mode !== '3d' || this.disposed) return;
    event.preventDefault();
    if (this.pointers.size || !Number.isFinite(event.deltaY) || event.deltaY === 0) return;
    const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? this.height : 1);
    const camera = this._cameraAtTime(), next = normalizeView({...camera, distance: camera.distance * Math.exp(clamp(pixels, -1000, 1000) * .0015), orbit: 0});
    if (next.distance === camera.distance) return;
    this.pause(); this.view = next; this._render(); this._viewEvent(false);
    clearTimeout(this.wheelTimer); this.wheelTimer = setTimeout(() => { this.wheelTimer = null; this._viewEvent(true); }, 160);
  }
  _pick(event) { this.select(this._hitTest(event)); }
  _hitTest(event) {
    if (!this.scene) return null;
    for (const [id, node] of [...this.nodes].reverse()) { if (node.style.visibility === 'hidden' || Number(node.style.opacity) <= .02) continue; const b = node.getBoundingClientRect(); if (event.clientX >= b.left && event.clientX <= b.right && event.clientY >= b.top && event.clientY <= b.bottom) return id; }
    const rect = this.surface.getBoundingClientRect(), x = (event.clientX - rect.left) / this.unit - 8, y = 4.5 - (event.clientY - rect.top) / this.unit;
    if (this.scene.mode === '3d' && this.raycaster) {
      this.raycaster.setFromCamera(new this.T.Vector2(x / 8, y / 4.5), this.camera);
      // Query each actual mesh once, excluding invisible descendants of a group.
      const pickable = []; this.world.traverse(node => { if (!(node.isMesh || node.isLine) || !node.visible) return; let ancestor = node; while (ancestor && !ancestor.userData.objectId) ancestor = ancestor.parent; if (ancestor?.userData.effectiveVisible && ancestor.userData.effectiveOpacity > .02) pickable.push(node); });
      const hits = this.raycaster.intersectObjects(pickable, false).map(hit => { let node = hit.object; while (node && !node.userData.objectId) node = node.parent; return node; }).filter(Boolean);
      // A faint context shell must not block selection of the visible mechanism.
      // It remains selectable where the ray does not hit a stronger foreground object.
      const picked = hits.find(node => node.userData.effectiveOpacity >= .15) || hits[0];
      if (picked) return picked.userData.objectId;
    } else {
      for (const object of [...this.scene.objects].reverse()) {
        if (this.hidden.has(object.id) || object.kind === 'formula') continue; const s = this.states.get(object.id); if (!s || s.opacity <= .02) continue;
        const dx = (x - s.x) / s.scale, dy = (y - s.y) / s.scale, px = dx * Math.cos(s.rotation) + dy * Math.sin(s.rotation), py = -dx * Math.sin(s.rotation) + dy * Math.cos(s.rotation);
        if (['line', 'arrow', 'path'].includes(object.kind)) { const points = partialPath(object.points, s.draw); if (points.slice(1).some((p, i) => distanceToSegment(px, py, points[i], p) < Math.max(.12, object.line_width * 2))) return object.id; }
        else { const b = this._bounds(object); if (px >= b[0] && px <= b[2] && py >= b[1] && py <= b[3]) return object.id; }
      }
    }
    return null;
  }
  _clearScene() {
    this._cancelInput();
    if (this.world) {
      const geometries = new Set(), materials = new Set(), textures = new Set();
      this.world.traverse(node => { if (node.geometry) geometries.add(node.geometry); for (const material of node.material ? (Array.isArray(node.material) ? node.material : [node.material]) : []) materials.add(material); });
      for (const material of materials) { if (material.map) textures.add(material.map); material.dispose(); } for (const geometry of geometries) geometry.dispose(); for (const texture of textures) texture.dispose();
    }
    if (this.renderer) { this.renderer.dispose(); this.renderer.forceContextLoss(); }
    this.renderer = null; this.world = null; this.camera = null; this.meshes = null; this.raycaster = null; this.renderMaterials = null;
    this.images.clear(); this.nodes.clear(); this.states.clear(); this.frameTables.clear(); this.objectTable.clear(); this.overlay.replaceChildren();
    const canvas = style(document.createElement('canvas'), {position: 'absolute', inset: '0', width: '100%', height: '100%'}); this.canvas.replaceWith(canvas); this.canvas = canvas;
  }
  dispose() { this.pause(); this.disposed = true; this.generation++; this.resizeObserver.disconnect(); for (const [type, handler] of Object.entries(this.inputHandlers)) this.surface.removeEventListener(type, handler); this._clearScene(); this.surface.remove(); }
}
