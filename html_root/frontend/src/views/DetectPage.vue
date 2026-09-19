<template>
  <section id="detect" class="section">
    <h2 class="section-title" style="margin: 1.5rem 0 1rem; font-size: 1.8rem">
      智能算式识别
    </h2>

    <div class="workspace">
      <div class="tools-panel">
        <div class="tab-switch">
          <button
            class="tab-btn"
            :class="{ active: inputMode === 'draw' }"
            @click="switchInputMode('draw')"
          >
            ✍️ 手写
          </button>
          <button
            class="tab-btn"
            :class="{ active: inputMode === 'upload' }"
            @click="switchInputMode('upload')"
          >
            📤 上传
          </button>
        </div>

        <div id="draw-tools" v-show="inputMode === 'draw'">
          <div class="control-group">
            <label>绘图工具</label>
            <div class="tools-grid">
              <button
                class="tool-btn"
                :class="{ active: tool === 'pen' }"
                @click="setTool('pen')"
                data-shortcut="toolPen"
                title="画笔 (B)"
              >
                <i class="fa-solid fa-pen"></i>
              </button>
              <button
                class="tool-btn"
                :class="{ active: tool === 'eraser' }"
                @click="setTool('eraser')"
                data-shortcut="toolEraser"
                title="橡皮擦 (E)"
              >
                <i class="fa-solid fa-eraser"></i>
              </button>
              <button class="tool-btn" @click="undo" data-shortcut="undo" title="撤销 (Ctrl+Z)">
                <i class="fa-solid fa-rotate-left"></i>
              </button>
              <button
                class="tool-btn"
                @click="redo"
                data-shortcut="redo"
                title="重做 (Ctrl+Shift+Z)"
              >
                <i class="fa-solid fa-rotate-right"></i>
              </button>
              <button
                class="tool-btn"
                @click="clearCanvas"
                data-shortcut="clearCanvas"
                title="清空画布 (Ctrl+Shift+C)"
                style="color: #ef4444"
              >
                <i class="fa-solid fa-trash"></i>
              </button>
            </div>

            <button
              class="tutorial-link shortcut-hint-btn"
              @click="openSettings('shortcuts')"
              title="画板快捷键设置"
            >
              <i class="fa-solid fa-keyboard"></i>
              点击设置快捷键
            </button>
            <div
              style="
                margin-top: 1.25rem;
                padding-top: 1rem;
                border-top: 1px solid var(--border-color);
                display: flex;
                align-items: center;
                gap: 0.75rem;
              "
            >
              <label
                style="
                  margin: 0;
                  min-width: 48px;
                  font-size: 0.875rem;
                  font-weight: 600;
                  color: var(--text-main);
                  display: flex;
                  align-items: center;
                "
              >
                粗细
              </label>
              <input
                type="range"
                id="brush-size"
                min="1"
                max="20"
                v-model.number="brushSize"
                style="flex: 1"
              />
            </div>
          </div>
        </div>

        <div id="upload-tools" v-show="inputMode === 'upload'">
          <label for="image-upload" class="upload-label">
            <i class="fa-solid fa-cloud-arrow-up upload-icon"></i>
            <span class="upload-text">点击或拖拽图片到此处</span>
            <span class="upload-text">或直接粘贴剪贴板图片</span>
            <input
              id="image-upload"
              ref="fileInputRef"
              type="file"
              accept="image/*"
              @change="onFileChange"
            />
          </label>
          <div id="file-name-display" class="file-name">{{ fileName }}</div>
        </div>

        <div
          style="
            margin-top: auto;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
          "
        >
          <button
            class="action-btn full-width"
            :disabled="isRecognizing"
            @click="processRecognitionHandler"
            style="
              height: 52px;
              font-size: 1rem;
              font-weight: 700;
              border-radius: 12px;
              background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
              color: #fff;
              border: none;
              box-shadow: 0 4px 16px rgba(37, 99, 235, 0.3);
              transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            "
          >
            <i class="fa-solid fa-magnifying-glass"></i>
            立即识别
          </button>
          <p
            style="
              text-align: center;
              color: var(--text-secondary);
              font-size: 0.8rem;
              margin-top: 0.75rem;
              font-weight: 500;
            "
          >
            每次只识别一道题，请保留完整题干和图形
          </p>
        </div>
      </div>

      <div class="workspace-main">
        <div class="canvas-wrapper">
          <div id="canvas-container">
            <canvas
              id="drawing-board"
              ref="canvasRef"
              @pointerdown="onPointerDown"
              @pointermove="onPointerMove"
              @pointerup="onPointerUp"
              @pointercancel="onPointerUp"
              @pointerleave="onPointerUp"
            ></canvas>

            <div
              id="uploaded-preview-container"
              v-show="inputMode === 'upload' && !!uploadedPreviewUrl"
              style="position: relative; width: 100%; height: 100%"
            >
              <img
                id="uploaded-preview"
                ref="uploadedPreviewRef"
                :src="uploadedPreviewUrl || ''"
                alt="预览"
                style="width: 100%; height: 100%; object-fit: contain"
                @click="openImageEditor"
              />
              <div class="canvas-image-edit-hint">点击编辑</div>
            </div>
          </div>

          <button
            id="canvas-lock-btn"
            class="canvas-lock-btn"
            type="button"
            title="锁定画板（仅滑动不书写）"
            aria-label="锁定画板"
          >
            <i class="fa-solid fa-lock-open canvas-lock-icon" id="canvas-lock-icon"></i>
            <span class="canvas-lock-label" id="canvas-lock-label">锁定画板</span>
          </button>

          <div id="canvas-hint" class="canvas-hint">
            <i class="fa-solid fa-pen"></i>
            在此区域进行手写
          </div>
        </div>

        <div class="detect-action-bar">
          <button
            class="btn-detect-primary"
            type="button"
            :disabled="isRecognizing"
            @click="processRecognitionHandler"
            title="对手写或上传的公式进行识别"
          >
            <i class="fa-solid fa-magnifying-glass"></i>
            立即识别
          </button>
          <p class="detect-action-hint">一次一道题，先核对题面，再开始计算</p>
        </div>

        <div class="result-panel">
          <div class="result-header">
            <div class="result-title">
              <i class="fa-solid fa-code"></i>
              识别结果
            </div>
            <details style="position: relative">
              <summary
                style="
                  font-size: 0.85rem;
                  color: var(--text-secondary);
                  cursor: pointer;
                "
              >
                <i class="fa-solid fa-terminal"></i>
                查看源码
              </summary>
              <div class="code-detail-popup">
                <textarea
                  id="latex-code-detect"
                  ref="codeAreaRef"
                  placeholder="LaTeX 代码..."
                  style="width: 100%; height: 100px; font-family: monospace; box-sizing: border-box"
                  :value="currentLatex"
                  @input="onCodeAreaInput"
                ></textarea>
              </div>
            </details>
          </div>

          <div class="math-field-container">
            <math-field
              id="latex-output"
              ref="mathFieldRef"
              virtual-keyboard-mode="manual"
              @input="onMathFieldInput"
            >
              \text{等待识别...}
            </math-field>
          </div>

          <label class="detect-problem-label" for="detect-problem">完整题面 · 计算时以这里为准</label>
          <textarea id="detect-problem" class="tech-input detect-problem" rows="4" maxlength="6000" :value="problemText" @input="onProblemInput" placeholder="核对或补充题干、已知条件与所求；支持 LaTeX。每次只放一道题。"></textarea>
          <div v-if="isRecognizing" class="detect-loading" role="progressbar" aria-label="正在识别题目"><span></span></div>
          <p id="detect-feedback" class="detect-feedback" :data-error="!!recognitionError" role="status" aria-live="polite">{{ recognitionMessage }}</p>
          <label v-if="needsReview" class="detect-review"><input id="detect-confirm" type="checkbox" :checked="confirmed" @change="onConfirm"> 我已核对并补全题面，以完整题面为准</label>
          <button v-if="isRecognizing" id="detect-cancel" type="button" class="action-btn secondary" @click="cancelRecognition">取消识别</button>
          <div class="result-actions">
            <div style="font-size: 0.85rem; color: var(--text-secondary)">
              <i class="fa-regular fa-keyboard"></i>
              点击公式可直接修改
            </div>

            <div style="display: flex; gap: 10px; flex-wrap: wrap">
              <button
                  id="btn-save-check"
                  class="btn-calc-go"
                  :disabled="!canOperate || !currentLatex.trim()"
                @click="saveAndShowFormula"
                style="
                  background: linear-gradient(135deg, #10b981, #059669);
                  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
                "
              >
                <i class="fa-regular fa-floppy-disk"></i>
                保存并查看
              </button>

              <button
                id="btn-copy-calc"
                class="action-btn secondary"
                :disabled="!canOperate"
                @click="copyToCalcHandler"
                style="padding: 0.8rem 1.5rem; border-radius: 99px"
                title="仅跳转到计算页，不保存"
              >
                确认题面并去计算
                <i class="fa-solid fa-arrow-right"></i>
              </button>

              <button
                  id="btn-edit-in-latex"
                class="action-btn tertiary"
                type="button"
                  :disabled="!canOperate || !currentLatex.trim()"
                @click="openInDevLatexFromDetectHandler"
                style="padding: 0.8rem 1.5rem; border-radius: 99px"
              >
                <i class="fa-solid fa-pen-to-square"></i>
                去 LaTeX 编辑器
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAgentRunnerStore } from "../stores/agentRunner";

type InputMode = "draw" | "upload";
type Tool = "pen" | "eraser";
type Point = { x: number; y: number };
type Stroke = { tool: Tool; size: number; points: Point[] };

const router = useRouter();
const runner = useAgentRunnerStore();

const inputMode = ref<InputMode>("draw");

const isRecognizing = ref(false);
const currentLatex = ref('');
const problemText=ref(''), recognitionError=ref(''), recognitionMessage=ref('每次只上传一道题，保留完整题干、图形和该题的小问。');
  const needsReview=ref(false), confirmed=ref(false);
const singleProblem=ref(true);
const canOperate=computed(()=>singleProblem.value&&!!(problemText.value.trim()||currentLatex.value.trim())&&!isRecognizing.value&&!recognitionError.value&&(!needsReview.value||confirmed.value)&&!currentLatex.value.includes('?'));
let recognitionFlow:any=null, flowLoading:Promise<any>|null=null;
async function ensureRecognitionFlow(){
  if(!flowLoading)flowLoading=(async()=>{
    const path='/static/js/recognition-flow.js';
      const {createRecognitionFlow,multipleProblems}=await import(/* @vite-ignore */ path);
    recognitionFlow=createRecognitionFlow((state:any)=>{
      setLatex(state.latex);problemText.value=state.problem;recognitionError.value=state.error;
      recognitionMessage.value=state.message;needsReview.value=state.needsReview;confirmed.value=state.confirmed;
        isRecognizing.value=state.busy;
        singleProblem.value=!multipleProblems(state.problem);
    });
    return recognitionFlow;
  })();
  return flowLoading;
}
async function onProblemInput(e:Event){(await ensureRecognitionFlow()).editProblem((e.target as HTMLTextAreaElement).value);}
async function onConfirm(e:Event){(await ensureRecognitionFlow()).confirm((e.target as HTMLInputElement).checked);}
function cancelRecognition(){recognitionFlow?.cancel();}
function onSourceChanged(){onFileChange();}
async function onRecognitionResult(e:Event){(await ensureRecognitionFlow()).accept((e as CustomEvent).detail);}

const mathFieldRef = ref<any | null>(null);
const codeAreaRef = ref<HTMLTextAreaElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const uploadedPreviewRef = ref<HTMLImageElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

const uploadedFile = ref<File | null>(null);
const uploadedPreviewUrl = ref<string | null>(null);
const fileName = computed(() => uploadedFile.value?.name || "");

const tool = ref<Tool>("pen");
const brushSize = ref<number>(3);

const strokes = ref<Stroke[]>([]);
const redoStack = ref<Stroke[]>([]);

let ctx: CanvasRenderingContext2D | null = null;
let drawing = false;

function switchInputMode(mode: InputMode) {
  if(inputMode.value!==mode)recognitionFlow?.reset();
  inputMode.value = mode;
}

function setTool(t: Tool) {
  tool.value = t;
}

function openSettings(section?: string) {
  (window as any).openSettings?.(section);
}

function openImageEditor() {
  (window as any).ImageEditor?.openEditor?.("uploaded-preview", "canvas");
}

function resizeCanvas() {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const parent = canvas.parentElement as HTMLElement | null;
  if (!parent) return;
  const rect = parent.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    redrawAll();
  }
}

function getCanvasPoint(e: PointerEvent): Point {
  const canvas = canvasRef.value!;
  const rect = canvas.getBoundingClientRect();
  return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

function drawStroke(s: Stroke) {
  if (!ctx) return;
  if (!s.points.length) return;
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = s.size;
  if (s.tool === "eraser") {
    ctx.globalCompositeOperation = "destination-out";
    ctx.strokeStyle = "rgba(0,0,0,1)";
  } else {
    ctx.globalCompositeOperation = "source-over";
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#1e293b';
  }
  ctx.beginPath();
  ctx.moveTo(s.points[0].x, s.points[0].y);
  for (let i = 1; i < s.points.length; i++) ctx.lineTo(s.points[i].x, s.points[i].y);
  ctx.stroke();
  ctx.restore();
}

function redrawAll() {
  const canvas = canvasRef.value;
  if (!canvas || !ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const s of strokes.value) drawStroke(s);
}

function undo() {
  recognitionFlow?.reset();
  const last = strokes.value.pop();
  if (last) redoStack.value.push(last);
  redrawAll();
}

function redo() {
  recognitionFlow?.reset();
  const last = redoStack.value.pop();
  if (last) strokes.value.push(last);
  redrawAll();
}

function clearCanvas() {
  recognitionFlow?.reset();
  strokes.value = [];
  redoStack.value = [];
  redrawAll();
}

function onPointerDown(e: PointerEvent) {
    if (inputMode.value !== "draw") return;
    if (!canvasRef.value) return;
    recognitionFlow?.reset();
  (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  drawing = true;
  redoStack.value = [];
  const p = getCanvasPoint(e);
  const s: Stroke = { tool: tool.value, size: brushSize.value, points: [p] };
  strokes.value.push(s);
  drawStroke(s);
}

function onPointerMove(e: PointerEvent) {
  if (!drawing) return;
  if (inputMode.value !== "draw") return;
  const s = strokes.value[strokes.value.length - 1];
  if (!s) return;
  s.points.push(getCanvasPoint(e));
  drawStroke(s);
}

function onPointerUp() {
  drawing = false;
}

function setLatex(val: string) {
  currentLatex.value = val;
  const mf = mathFieldRef.value;
    if (mf && mf.value !== val && typeof mf.setValue === "function") mf.setValue(val);
  if (codeAreaRef.value) codeAreaRef.value.value = val;
}

function onMathFieldInput(e: any) {
  const v = String(e?.target?.value ?? "");
  currentLatex.value = v;
  ensureRecognitionFlow().then(f=>f.editLatex(v));
  if (codeAreaRef.value) codeAreaRef.value.value = v;
}

function onCodeAreaInput(e: Event) {
  const v = (e.target as HTMLTextAreaElement).value;
  currentLatex.value = v;
  ensureRecognitionFlow().then(f=>f.editLatex(v));
  const mf = mathFieldRef.value;
  if (mf && typeof mf.setValue === "function") mf.setValue(v);
}

function onFileChange() {
  recognitionFlow?.reset();
  const f = fileInputRef.value?.files?.[0] || null;
  uploadedFile.value = f;
  if (uploadedPreviewUrl.value) {
    URL.revokeObjectURL(uploadedPreviewUrl.value);
    uploadedPreviewUrl.value = null;
  }
  if (f) uploadedPreviewUrl.value = URL.createObjectURL(f);
}

async function canvasToBlob(): Promise<Blob | null> {
  const canvas = canvasRef.value;
  if (!canvas) return null;
  // Export opaque black ink on white paper, independent of the current theme.
  const output=document.createElement('canvas');output.width=canvas.width;output.height=canvas.height;
  const ink=output.getContext('2d');if(!ink)return null;
  ink.drawImage(canvas,0,0);ink.globalCompositeOperation='source-in';
  ink.fillStyle='#111827';ink.fillRect(0,0,output.width,output.height);
  ink.globalCompositeOperation='destination-over';ink.fillStyle='#ffffff';ink.fillRect(0,0,output.width,output.height);
  return new Promise((resolve) => output.toBlob((b) => resolve(b), "image/png"));
}

async function processRecognitionHandler() {
  if(isRecognizing.value)return;
  isRecognizing.value=true;
  try{
    const flow=await ensureRecognitionFlow();
    await flow.run(async()=>inputMode.value==='draw'?(strokes.value.length?await canvasToBlob():null):(fileInputRef.value?.files?.[0]||uploadedFile.value));
  }finally{isRecognizing.value=false;}
}

async function saveAndShowFormula() {
  (window as any).saveAndShowFormula?.();
}

async function copyToCalcHandler() {
  try{
    const {problem,context}=(await ensureRecognitionFlow()).payload();
    sessionStorage.setItem('pending_calc_latex',problem);
    sessionStorage.setItem('pending_calc_context',context);
    await router.push('/calculate');
  }catch(error:any){recognitionMessage.value=error.message;}
}

async function openInDevLatexFromDetectHandler() {
  if (!canOperate.value) {
    if (typeof (window as any).showAlert === "function") {
      await (window as any).showAlert("请先识别出有效公式后再编辑", "提示");
    }
    return;
  }
  try {
    sessionStorage.setItem("pending_devtools_latex", currentLatex.value);
  } catch (_) {}
  router.push("/devtools");
}

onMounted(() => {
  ensureRecognitionFlow();
  window.addEventListener('recognition-source-change',onSourceChanged);
  window.addEventListener('recognition-result',onRecognitionResult);
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);

  runner.consumeIfCurrent("detect", async (step) => {
    if (step.formula) setLatex(step.formula);
    if (step.trigger === "recognize") await processRecognitionHandler();
    if (step.save_to_formulas) await saveAndShowFormula();
  });
});

onUnmounted(() => {
  recognitionFlow?.cancel();
  window.removeEventListener('recognition-source-change',onSourceChanged);
  window.removeEventListener('recognition-result',onRecognitionResult);
  window.removeEventListener("resize", resizeCanvas);
  if (uploadedPreviewUrl.value) URL.revokeObjectURL(uploadedPreviewUrl.value);
});
</script>

