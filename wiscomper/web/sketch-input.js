const WIDTH = 1200, HEIGHT = 800, MAX_OPERATIONS = 500, MAX_POINTS = 8000;
function node(tag, className, text = '') { const element = document.createElement(tag); element.className = className; element.textContent = text; return element; }
function button(className, text) { const element = node('button', className, text); element.type = 'button'; return element; }

/** onImage(File) is awaited. Throw or return false to keep the sketch for retry. */
export function mountSketchInput({ onImage, notify = () => {} } = {}) {
  if (typeof onImage !== 'function') throw new Error('手写画板需要图片上传回调。');
  const dialog = node('dialog', 'sketch-dialog'); dialog.setAttribute('aria-modal', 'true');
  const uid = `sketch-${globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
  dialog.setAttribute('aria-labelledby', `${uid}-title`); dialog.setAttribute('aria-describedby', `${uid}-intro`);
  const header = node('header', 'sketch-header'), heading = node('div', 'sketch-heading');
  heading.append(node('span', 'sketch-eyebrow', '把想法画下来'));
  const title = node('h2', 'sketch-title', '手写与草图'); title.id = `${uid}-title`; heading.append(title);
  const close = button('sketch-close', '×'); close.setAttribute('aria-label', '关闭手写画板'); header.append(heading, close);
  const intro = node('p', 'sketch-intro', '写下公式，或画出对象与关系。添加为参考图片后，可以补充文字说明再生成。'); intro.id = `${uid}-intro`;
  const toolbar = node('div', 'sketch-toolbar'); toolbar.setAttribute('aria-label', '画板工具');
  const tools = node('div', 'sketch-tools'), history = node('div', 'sketch-history');
  const pen = button('sketch-tool', '画笔'), eraser = button('sketch-tool', '橡皮');
  pen.dataset.tool = 'pen'; eraser.dataset.tool = 'erase';
  const widthLabel = node('label', 'sketch-width'); widthLabel.append(node('span', '', '粗细'));
  const widthInput = node('input', ''); widthInput.type = 'range'; widthInput.min = '2'; widthInput.max = '16'; widthInput.step = '1'; widthInput.value = '6'; widthInput.setAttribute('aria-label', '笔画粗细'); widthLabel.append(widthInput);
  tools.append(pen, eraser, widthLabel);
  const undo = button('sketch-undo', '撤销'), redo = button('sketch-redo', '重做'), clear = button('sketch-clear', '清空');
  undo.title = 'Ctrl / ⌘ + Z'; redo.title = 'Ctrl / ⌘ + Shift + Z'; history.append(undo, redo, clear); toolbar.append(tools, history);
  const stage = node('div', 'sketch-stage');
  const canvas = node('canvas', 'sketch-canvas'); canvas.width = WIDTH; canvas.height = HEIGHT; canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', '手写画板，可用鼠标、触控笔或手指书写'); stage.append(canvas);
  const footer = node('footer', 'sketch-footer'), footerCopy = node('div', 'sketch-footer-copy');
  const status = node('p', 'sketch-status', '在空白处开始书写。'); status.setAttribute('role', 'status');
  const note = node('p', 'sketch-note', '手写内容暂存在当前页面。关闭画板后可继续编辑，刷新页面会清除。'); footerCopy.append(status, note);
  const submit = button('sketch-submit', '用作参考图片'); footer.append(footerCopy, submit);
  dialog.append(header, intro, toolbar, stage, footer); document.body.append(dialog);
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) { dialog.remove(); throw new Error('此浏览器无法打开手写画板。'); }
  const backing = document.createElement('canvas'); backing.width = WIDTH; backing.height = HEIGHT;
  const backingContext = backing.getContext('2d');
  let operations = [], cursor = 0, current = null, pointerId = null, tool = 'pen', busy = false, disposed = false, initialFocus = null;
  const listeners = [];
  function listen(target, event, action, options) { target.addEventListener(event, action, options); listeners.push(() => target.removeEventListener(event, action, options)); }
  function tell(text, error = false) { status.textContent = text; status.classList.toggle('error', error); }
  function stroke(operation) {
    if (operation.kind === 'clear') { context.fillStyle = '#fff'; context.fillRect(0, 0, WIDTH, HEIGHT); return; }
    context.lineCap = 'round'; context.lineJoin = 'round'; context.lineWidth = operation.width;
    context.strokeStyle = operation.kind === 'erase' ? '#fff' : '#1d2b42'; context.fillStyle = context.strokeStyle;
    const points = operation.points;
    if (!points.length) return;
    if (points.length === 1) { context.beginPath(); context.arc(points[0].x, points[0].y, operation.width / 2, 0, Math.PI * 2); context.fill(); return; }
    context.beginPath(); context.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) context.lineTo(points[i].x, points[i].y);
    context.stroke();
  }
  function render() {
    context.fillStyle = '#fff'; context.fillRect(0, 0, WIDTH, HEIGHT); for (const operation of operations.slice(0, cursor)) stroke(operation);
    backingContext?.drawImage(canvas, 0, 0); if (current) stroke(current);
  }
  function update() {
    pen.setAttribute('aria-pressed', String(tool === 'pen')); eraser.setAttribute('aria-pressed', String(tool === 'erase'));
    canvas.dataset.tool = tool; canvas.style.cursor = tool === 'erase' ? 'cell' : 'crosshair';
    for (const control of [pen, eraser, widthInput, close]) control.disabled = busy;
    undo.disabled = busy || cursor === 0 || Boolean(current); redo.disabled = busy || cursor >= operations.length || Boolean(current);
    clear.disabled = busy || cursor === 0 || Boolean(current); submit.disabled = busy || cursor === 0 || Boolean(current);
    submit.textContent = busy ? '正在添加…' : '用作参考图片'; dialog.setAttribute('aria-busy', String(busy));
  }
  function append(operation) {
    if (cursor >= MAX_OPERATIONS) { tell('已达到本次画板的笔画上限，请先用作图片，或撤销部分笔画。', true); render(); return; }
    operations = operations.slice(0, cursor); operations.push(operation); cursor++;
  }
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return { x: Math.max(0, Math.min(WIDTH, (event.clientX - rect.left) / rect.width * WIDTH)), y: Math.max(0, Math.min(HEIGHT, (event.clientY - rect.top) / rect.height * HEIGHT)) };
  }
  function finishStroke() {
    if (!current) return;
    const operation = current, captured = pointerId; current = null; pointerId = null; append(operation);
    if (captured !== null && canvas.hasPointerCapture?.(captured)) canvas.releasePointerCapture(captured);
    render(); update();
  }
  listen(canvas, 'pointerdown', event => {
    if (disposed || busy || current || !event.isPrimary || event.button !== 0) return;
    if (cursor >= MAX_OPERATIONS) { tell('笔画较多，请先用作参考图片，或撤销部分笔画。', true); return; }
    event.preventDefault(); canvas.focus({ preventScroll: true });
    pointerId = event.pointerId; current = { kind: tool, width: tool === 'erase' ? Math.max(28, Number(widthInput.value) * 5) : Number(widthInput.value), points: [point(event)] };
    canvas.setPointerCapture(event.pointerId); tell(tool === 'erase' ? '正在擦除，可撤销恢复。' : '书写完成后，选择「用作参考图片」。'); render(); update();
  });
  listen(canvas, 'pointermove', event => {
    if (!current || event.pointerId !== pointerId) return;
    event.preventDefault();
    const events = event.getCoalescedEvents?.() || [event];
    for (const item of events.length ? events : [event]) {
      if (current.points.length >= MAX_POINTS) break;
      const next = point(item), last = current.points.at(-1);
      if (Math.abs(next.x - last.x) + Math.abs(next.y - last.y) >= .3) current.points.push(next);
    }
    if (backingContext) { context.drawImage(backing, 0, 0); stroke(current); } else render();
  });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) listen(canvas, name, event => { if (event.pointerId === pointerId) finishStroke(); });
  function undoStroke() { if (busy || current || !cursor) return; cursor--; render(); update(); tell('已撤销，可以继续书写或重做。'); }
  function redoStroke() { if (busy || current || cursor >= operations.length) return; cursor++; render(); update(); tell('已重做。'); }
  listen(pen, 'click', () => { tool = 'pen'; update(); }); listen(eraser, 'click', () => { tool = 'erase'; update(); });
  listen(undo, 'click', undoStroke); listen(redo, 'click', redoStroke);
  listen(clear, 'click', () => { if (busy || current) return; append({ kind: 'clear' }); render(); update(); tell('画板已清空，可撤销恢复。'); });
  function closeDialog() { if (busy) { tell('正在添加图片，请稍候。'); return; } finishStroke(); dialog.close(); }
  listen(close, 'click', closeDialog); listen(dialog, 'cancel', event => { event.preventDefault(); closeDialog(); });
  listen(dialog, 'close', () => { if (!dialog.open && initialFocus?.isConnected && initialFocus.getClientRects().length) initialFocus.focus({ preventScroll: true }); });
  listen(dialog, 'keydown', event => {
    event.stopPropagation();
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); event.shiftKey ? redoStroke() : undoStroke(); }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') { event.preventDefault(); redoStroke(); }
  });
  async function exportImage() {
    if (disposed || busy || current || !cursor) return;
    const pixels = context.getImageData(0, 0, WIDTH, HEIGHT).data;
    let ink = false;
    for (let i = 0; i < pixels.length; i += 4) if (pixels[i] < 245 || pixels[i + 1] < 245 || pixels[i + 2] < 245) { ink = true; break; }
    if (!ink) { tell('画板还是空白，请先写下公式或画出草图。', true); return; }
    busy = true; update(); tell('正在把草图添加到图片输入…');
    try {
      const blob = await new Promise((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('无法生成图片，请重试。')), 'image/png'));
      if (disposed) return;
      const result = await onImage(new File([blob], `wiscomper-sketch-${Date.now()}.png`, { type: 'image/png' }));
      if (disposed) return;
      if (result === false) { tell('图片尚未添加，草图已保留，可以重试。', true); return; }
      busy = false; update(); dialog.close(); notify('草图已添加为参考图片，可继续补充描述。');
    } catch (error) { if (!disposed) { tell(error?.message || '图片添加失败，草图已保留。', true); } }
    finally { if (!disposed) { busy = false; update(); } }
  }
  listen(submit, 'click', exportImage); render(); update();
  return {
    open() {
      if (disposed) return false;
      if (!dialog.open && document.querySelector('dialog[open]')) { notify('请先关闭当前窗口，再打开手写画板。'); return false; }
      if (!dialog.open) { initialFocus = document.activeElement; dialog.showModal(); }
      render(); update(); canvas.focus({ preventScroll: true }); return true;
    },
    dispose() {
      if (disposed) return;
      finishStroke(); disposed = true; listeners.forEach(remove => remove());
      if (dialog.open) dialog.close(); dialog.remove(); operations = []; current = null;
    },
  };
}
