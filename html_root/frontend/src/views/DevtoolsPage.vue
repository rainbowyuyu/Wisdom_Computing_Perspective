<template>
  <section id="devtools" class="section">
    <!-- 文档锚点：供 update.md 中 #section-devtools 使用 -->
    <div id="section-devtools"></div>
    <h2 class="section-title">代码开发者工作台</h2>

    <div class="workspace">
      <!-- 左侧导航 -->
      <div class="tools-panel" style="flex: 0 0 240px">
        <div class="control-group">
          <label>工具箱</label>
          <div class="tools-list">
            <button
              class="tab-btn active" data-tool="latex"
              @click="switchDevTool('latex')"
            >
              <i class="fa-solid fa-square-root-variable"></i>
              LaTeX 可视化编辑器
            </button>
            <button class="tab-btn" data-tool="manim" @click="switchDevTool('manim')">
              <i class="fa-brands fa-python"></i>
              Manim 代码云端渲染工作台
            </button>
            <button class="tab-btn" data-tool="rainbow" @click="switchDevTool('rainbow')">
              <i class="fa-solid fa-layer-group"></i>
              rainbow鱼的扩展库
              <span
                style="
                  font-size: 0.6rem;
                  background: var(--primary-color);
                  color: white;
                  padding: 1px 4px;
                  border-radius: 4px;
                  margin-left: 5px;
                "
              >
                NEW
              </span>
            </button>
          </div>
        </div>

        <div class="control-group" style="margin-top: auto">
          <label>快捷键</label>
          <div
            style="
              font-size: 0.8rem;
              color: var(--text-secondary);
              line-height: 1.6;
            "
          >
            <p>
              <kbd>Ctrl</kbd>
              +
              <kbd>Enter</kbd>
              运行代码
            </p>
            <p>
              <kbd>Tab</kbd>
              自动补全 (Beta)
            </p>
          </div>
        </div>
      </div>

      <!-- 右侧工作区 -->
      <div class="workspace-main">
        <!-- 1. LaTeX 编辑器 -->
        <div id="dev-latex" class="dev-panel">
          <div class="dev-split-view">
            <!-- 输入区 (MathLive) -->
            <div class="dev-col">
              <div class="dev-label">
                <span>
                  <i class="fa-solid fa-keyboard"></i>
                  可视化输入
                </span>
                <span style="font-size: 0.7rem; opacity: 0.7">
                  MathLive Engine
                </span>
              </div>
              <div style="flex: 1; display: flex; align-items: center">
                <math-field id="dev-latex-mathfield" virtual-keyboard-mode="manual">
                  x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}
                </math-field>
              </div>
            </div>

            <!-- 源码预览区 -->
            <div class="dev-col">
              <div class="dev-label">
                <span>
                  <i class="fa-solid fa-code"></i>
                  LaTeX 源码
                </span>
                <div class="dev-latex-toolbar">
                  <div class="dev-latex-toolbar-main">
                    <button
                      class="action-btn tertiary"
                      type="button"
                      @click="goToFormulasForImport"
                    >
                      <i class="fa-solid fa-database"></i>
                      导入算式
                    </button>
                    <button
                      class="action-btn secondary"
                      type="button"
                      @click="saveCurrentLatexToFormulas"
                    >
                      <i class="fa-solid fa-floppy-disk"></i>
                      保存算式
                    </button>
                    <button
                      class="action-btn secondary"
                      type="button"
                      @click="copyDevLatex"
                    >
                      <i class="fa-regular fa-copy"></i>
                      复制 LaTeX
                    </button>
                    <button
                      class="action-btn tertiary"
                      type="button"
                      @click="copyDevLatexAsMathML"
                    >
                      <i class="fa-solid fa-file-word"></i>
                      复制到 Word
                    </button>
                  </div>
                  <!-- Temml 导出设置 -->
                  <div class="dev-latex-temml-settings">
                    <span class="temml-settings-label">Temml 导出</span>
                    <select id="dev-latex-temml-mode" class="temml-select">
                      <option value="Math" selected>Math</option>
                      <option value="MathML">MathML</option>
                      <option value="FlatMML">Flat MML</option>
                    </select>
                    <label class="temml-checkbox">
                      <input id="dev-latex-temml-xml" type="checkbox" checked />
                      XML
                    </label>
                    <label class="temml-checkbox">
                      <input id="dev-latex-temml-annotate" type="checkbox" />
                      Annotate
                    </label>
                  </div>
                </div>
              </div>
              <textarea
                id="dev-latex-source"
                class="tech-input"
                style="flex: 1; margin: 0; font-family: monospace; resize: none"
              ></textarea>
            </div>
          </div>

          <!-- 底部渲染预览 (KaTeX) -->
          <div class="dev-col dev-latex-preview-wrap">
            <div class="dev-label">
              <span>
                <i class="fa-solid fa-eye"></i>
                最终渲染预览
              </span>
            </div>
            <div id="dev-latex-preview"></div>
          </div>
        </div>

        <!-- 2. Manim 工作台 -->
        <div id="dev-manim" class="dev-panel" style="display: none; padding: 0">
          <div class="ide-layout" id="ide-layout-manim">
            <!-- 上：代码编辑器 + 日志 -->
            <div
              class="ide-top-panel ide-resize-pane"
              id="ide-left-pane"
              style="display: flex; flex-direction: column"
            >
              <div
                class="ide-editor ide-resize-pane"
                id="ide-editor-pane"
                style="flex: 1 1 60%; min-height: 200px"
              >
                <div class="ide-toolbar">
                  <span class="ide-toolbar-label">
                    <i class="fa-brands fa-python"></i>
                    main.py (Monaco Kernel)
                  </span>
                  <div class="ide-toolbar-actions">
                    <div class="manim-import-wrap">
                      <button
                        id="btn-manim-import"
                        type="button"
                        class="ide-btn-import"
                        @click="toggleImportPanel"
                        title="从我的脚本或 Rainbow 导入"
                      >
                        <i class="fa-solid fa-file-import"></i>
                        导入
                      </button>
                      <div
                        id="manim-import-panel"
                        class="manim-import-panel"
                        style="display: none"
                      >
                        <div class="manim-import-tabs">
                          <button
                            type="button"
                            class="manim-import-tab active"
                            data-tab="scripts"
                            @click="switchImportTab('scripts')"
                          >
                            我的脚本
                          </button>
                          <button
                            type="button"
                            class="manim-import-tab"
                            data-tab="rainbow"
                            @click="switchImportTab('rainbow')"
                          >
                            Rainbow 样例
                          </button>
                        </div>
                        <div
                          id="manim-import-scripts"
                          class="manim-import-list"
                        ></div>
                        <div
                          id="manim-import-rainbow"
                          class="manim-import-list"
                          style="display: none"
                        ></div>
                      </div>
                    </div>
                    <button
                      type="button"
                      class="ide-btn-save"
                      @click="saveScriptFromWorkbench"
                      title="保存到动画脚本库"
                    >
                      <i class="fa-solid fa-floppy-disk"></i>
                      保存
                    </button>
                    <button
                      type="button"
                      class="ide-btn-summary"
                      @click="generateVideoCopy"
                      title="总结当前脚本，生成一份适合发布的视频文案"
                    >
                      <i class="fa-solid fa-align-left"></i>
                      总结
                    </button>
                    <button
                      id="btn-manim-ai-edit"
                      type="button"
                      class="ide-btn-ai-edit"
                      @click="toggleAiEditPanel"
                      title="用自然语言编辑代码（类似 Cursor）"
                    >
                      <i class="fa-solid fa-wand-magic-sparkles"></i>
                      AI
                    </button>
                    <button
                      id="btn-manim-keyframe"
                      type="button"
                      class="ide-btn-keyframe"
                      @click="previewKeyframes"
                      title="渲染当前代码的首帧预览图"
                    >
                      <i class="fa-solid fa-film"></i>
                      关键帧
                    </button>
                    <button
                      id="btn-run-manim"
                      class="ide-btn-run"
                      @click="runDevManim"
                    >
                      <i class="fa-solid fa-play"></i>
                      运行
                    </button>
                  </div>
                </div>
                <div
                  id="monaco-container"
                  style="flex: 1; width: 100%; height: 100%; overflow: hidden"
                ></div>
              </div>
              <div
                id="ide-resize-editor-log"
                class="ide-resize-handle ide-resize-v"
                title="拖拽调整代码与日志高度"
              ></div>
              <div
                class="dev-manim-log-wrap ide-resize-pane"
                id="ide-log-pane"
                style="flex: 1 1 40%; min-height: 120px"
              >
                <div class="dev-manim-log-title">渲染日志</div>
                <pre id="dev-manim-log" class="cmd-log"></pre>
              </div>
            </div>

            <!-- 中间拖拽条（视频浮动后隐藏） -->
            <div
              id="ide-resize-top-bottom"
              class="ide-resize-handle ide-resize-v"
              title="拖拽调整上方编辑区与下方视频的高度"
              style="display: none"
            ></div>
            <!-- 下：占位 -->
            <div
              id="ide-preview-placeholder"
              class="ide-preview-placeholder"
              style="flex: 0 0 0; min-height: 0; overflow: hidden"
            ></div>
          </div>

          <!-- 浮动视频预览（可拖动） -->
          <div id="manim-video-float-wrap" class="manim-video-float-wrap">
            <div
              id="manim-video-float-header"
              class="manim-video-float-header"
              title="拖动可调整位置"
            >
              <i class="fa-solid fa-grip-vertical"></i>
              <span>视频预览</span>
            </div>
            <div
              id="ide-preview-pane"
              class="ide-preview ide-resize-pane"
              style="display: flex; flex-direction: column"
            >
              <div id="ide-video-outer" class="ide-video-container">
                <div id="ide-preview-inner-pane" class="ide-preview-inner">
                  <video
                    id="dev-manim-video"
                    class="ide-preview-video"
                    controls
                  ></video>
                  <div id="dev-manim-placeholder" class="ide-placeholder">
                    <i class="ide-placeholder-icon fa-solid fa-clapperboard"></i>
                    <p class="ide-placeholder-text">
                      编写代码并点击运行
                      <br />
                      可从「导入」选择已保存脚本或 Rainbow 样例
                    </p>
                  </div>
                  <div
                    id="dev-manim-loading"
                    class="ide-loading"
                    style="display: none"
                  >
                    <i class="ide-loading-spinner fa-solid fa-circle-notch fa-spin"></i>
                    <p class="ide-loading-text">正在云端渲染...</p>
                  </div>
                  <div
                    id="manim-keyframe-preview-in-video"
                    class="manim-keyframe-preview"
                    style="display: none"
                  >
                    <img
                      id="manim-keyframe-img-in-video"
                      src=""
                      alt="关键帧"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- AI 编辑独立浮动面板 -->
          <div id="manim-ai-edit-float" class="manim-ai-edit-float" style="display: none;"><p class="code-assistant-status" role="status">正在准备创作助手…</p></div>
        </div>

        <!-- [新增] Rainbow 扩展库面板 -->
        <div
          id="dev-rainbow"
          class="dev-panel"
          style="display: none; overflow-y: auto"
        >
          <!-- 内容将由 JS 动态生成 -->
          <div id="rainbow-content-container"></div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount } from "vue";
import { useAgentRunnerStore } from "../stores/agentRunner";

const runner = useAgentRunnerStore();

let tools: any;
let active = true;
onBeforeUnmount(()=>{ active = false; tools?.disposeDevTools(); });
onMounted(async () => {
  const url='/static/js/devtools.js?v=20260917-creator-2';tools=await import(/* @vite-ignore */ url);
  if (!active) return;
  const g:any=window;g.DevTools=tools;g.switchDevTool=tools.switchDevTool;g.runDevManim=tools.runDevManim;g.openManimWorkbenchWithCode=tools.openManimWorkbenchWithCode;g.copyDevLatex=tools.copyDevLatex;
  tools.initDevTools();

  // detect 页预填：从 sessionStorage 读取一次
  try {
    const pending = sessionStorage.getItem("pending_devtools_latex");
    if (pending) {
      sessionStorage.removeItem("pending_devtools_latex");
      tools.switchDevTool("latex");
      tools.fillLatexInDevtools(pending);
    }
  } catch (_) {}

  // 我的算式脚本库预填 Manim 代码
  try {
    const code = sessionStorage.getItem("pending_devtools_manim_code");
    if (code) {
      sessionStorage.removeItem("pending_devtools_manim_code");
      const autoRun = sessionStorage.getItem("pending_devtools_manim_autorun") === "1";
      sessionStorage.removeItem("pending_devtools_manim_autorun");
      await tools.openManimWorkbenchWithCode(code, { autoRun });
    }
  } catch (_) {}

  if (!active) return;
  runner.consumeIfCurrent("devtools", async (step) => {
    const url='/static/js/agent-workspace.js';
    const agent=await import(/* @vite-ignore */ url);
    await agent.performDevtool(step);
  });
});
function switchDevTool(tool: "latex" | "manim" | "rainbow") {
  (window as any).switchDevTool?.(tool);
}

function goToFormulasForImport() {
  (window as any).DevTools?.goToFormulasForImport?.();
}

function saveCurrentLatexToFormulas() {
  (window as any).DevTools?.saveCurrentLatexToFormulas?.();
}

function copyDevLatex() {
  (window as any).copyDevLatex?.();
}

function copyDevLatexAsMathML() {
  (window as any).DevTools?.copyDevLatexAsMathML?.();
}

function toggleImportPanel() {
  (window as any).DevTools?.toggleImportPanel?.();
}

function switchImportTab(tab: "scripts" | "rainbow") {
  (window as any).DevTools?.switchImportTab?.(tab);
}

function saveScriptFromWorkbench() {
  (window as any).DevTools?.saveScriptFromWorkbench?.();
}

function generateVideoCopy() {
  (window as any).DevTools?.generateVideoCopy?.();
}

function toggleAiEditPanel() {
  (window as any).DevTools?.toggleAiEditPanel?.();
}

function previewKeyframes() {
  (window as any).DevTools?.previewKeyframes?.();
}

function runDevManim() {
  (window as any).runDevManim?.();
}
</script>

