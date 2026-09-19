import { renderFormula, normalizeLatex } from './math-text.js';
import { mountCodeAssistant } from './code-assistant.js?v=20260917-creator-2';
import { consumeEvents } from './event-stream.js';
// static/js/devtools.js

import { RAINBOW_LIB_INFO } from './rainbow_data.js';
import { toggleModal, showToast } from './ui.js';
import { sanitizeMarkdownHtml } from './sanitize.js';
import { getIsRenderCooldown, startRenderCooldown, setRenderInProgress } from './render-cooldown.js';

// 全局变量保存编辑器实例
let monacoEditor = null;

/** 工作台当前脚本状态：null 表示新建未保存，数字为已加载脚本 id */
let workbenchScriptId = null;
let workbenchScriptNote = '';

/** 仅含框架的 Manim 空白脚本（新建时填入工作台） */
const MANIM_FRAMEWORK_SCRIPT = `from manim import *

class GenScene(Scene):
    def construct(self):
        pass
`;

// 1. 工具切换逻辑
export function switchDevTool(tool) {
    initDevTools();
    document.querySelectorAll('#devtools .tab-btn').forEach(btn => btn.classList.remove('active'));
    const btn = document.querySelector(`#devtools .tab-btn[data-tool="${tool}"], #devtools .tab-btn[onclick*="${tool}"]`);
    if(btn) btn.classList.add('active');

    const latexPanel = document.getElementById('dev-latex');
    const manimPanel = document.getElementById('dev-manim');
    const rainbowPanel = document.getElementById('dev-rainbow'); // [新增]

    // 隐藏所有
    if(!latexPanel||!manimPanel)return;
    latexPanel.style.display = 'none';
    manimPanel.style.display = 'none';
    if(rainbowPanel) rainbowPanel.style.display = 'none';

    if (tool === 'latex') {
        latexPanel.style.display = 'flex';
    } else if (tool === 'manim') {
        manimPanel.style.display = 'grid';
        if (monacoEditor) {
            setTimeout(() => monacoEditor?.layout(), 50);
        } else {
            loadMonaco().catch(showEditorLoadError);
        }
        // AI 编辑面板默认打开
        const aiPanel = document.getElementById('manim-ai-edit-float');
        if (aiPanel && aiPanel.style.display === 'none') {
            aiPanel.style.display = 'flex';
        }
    } else if (tool === 'rainbow') {
        // [新增] 切换到 Rainbow 面板
        if(rainbowPanel) {
            rainbowPanel.style.display = 'block';
            renderRainbowLib(); // 渲染内容
        }
    }
    if (document.getElementById('devtools')?.checkVisibility()) {
        window.dispatchEvent(new CustomEvent('graph-station-selected', { detail: { nodeId: `devtools-${tool}`, section: 'devtools' } }));
    }
}

// 2. 初始化入口
export function initDevTools() {
    const host=document.getElementById('devtools');if(!host)return;
    // The shell may exist before the assistant markup, or survive a failed mount.
    // Check the actual mounted controls even when the rest of the tools are ready.
    if(!initManimAiEdit())return;
    if(host.dataset.devInitialized)return;
    initLatexTool();
    initManimResize();
    host.dataset.devInitialized='true';
}

/** 竖排布局：上（代码+日志）/ 下（视频）拖拽调整高度 */
function initManimResize() {
    const topPane = document.getElementById('ide-left-pane');
    const editorPane = document.getElementById('ide-editor-pane');
    const logPane = document.getElementById('ide-log-pane');
    const previewPane = document.getElementById('ide-preview-pane');
    const handleTopBottom = document.getElementById('ide-resize-top-bottom');
    const handleEditorLog = document.getElementById('ide-resize-editor-log');
    
    if (!topPane || !editorPane) return;

    // 垂直拖拽：调整上（代码+日志）与下（视频）的高度
    function dragVertical(handle, paneAbove, paneBelow, minAbove, minBelow) {
        let startY = 0, startAbove = 0;
        function onMove(e) {
            const dy = e.clientY - startY;
            const newAbove = Math.max(minAbove, startAbove + dy);
            paneAbove.style.flex = `0 0 ${newAbove}px`;
            paneBelow.style.flex = '1 1 0%';
        }
        function onUp() {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            if (window.monacoEditor) window.monacoEditor.layout();
        }
        handle.addEventListener('mousedown', function(e) {
            e.preventDefault();
            startY = e.clientY;
            startAbove = paneAbove.getBoundingClientRect().height;
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    }

    // 上/下大块：视频已浮动，仅连接 editor-log（topPane 与 placeholder 无需调整）
    if (handleEditorLog && logPane) {
        dragVertical(handleEditorLog, editorPane, logPane, 200, 120);
    }

    // 不再自动根据内容调整代码 / 日志高度，保持用户拖拽后的尺寸不变
}

/** 存储上次布局比例，用于智能调整 */
let lastEditorLines = 0;
let lastLogLines = 0;

/** 供 initMonacoEditor 调用的布局调整函数（Monaco 懒加载后绑定） */
let scheduleManimLayoutAdjust = null;

/**
 * 代码区与渲染日志随内容变化自动调整布局
 * - 代码行数增加时适当放大编辑器
 * - 日志有新输出（尤其报错）时放大日志区
 */
// 旧的自动布局逻辑保留占位，但不再生效，避免渲染日志影响高度
function initManimLayoutAutoResize(editorPane, logPane) {
    return;
}

/** 浮动视频面板：拖动顶部调整位置 */
function initManimVideoFloat() {
    const wrap = document.getElementById('manim-video-float-wrap');
    const header = document.getElementById('manim-video-float-header');
    if (!wrap || !header) return;

    let isDragging = false;
    let startX = 0, startY = 0, startLeft = 0, startTop = 0;

    header.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        isDragging = true;
        const rect = wrap.getBoundingClientRect();
        startX = e.clientX;
        startY = e.clientY;
        startLeft = rect.left;
        startTop = rect.top;
        wrap.style.right = 'auto';
        wrap.style.bottom = 'auto';
        wrap.style.left = startLeft + 'px';
        wrap.style.top = startTop + 'px';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        let left = startLeft + dx;
        let top = startTop + dy;
        const maxLeft = window.innerWidth - wrap.offsetWidth;
        const maxTop = window.innerHeight - wrap.offsetHeight;
        left = Math.max(0, Math.min(left, maxLeft));
        top = Math.max(0, Math.min(top, maxTop));
        wrap.style.left = left + 'px';
        wrap.style.top = top + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
        }
    });
}

/** AI 编辑浮动面板状态 */
let aiEditDiffEditor = null;
let aiEditPendingCode = null;

/** 关键帧断点行号集合（1-based），点击行号左侧可切换 */
let keyframeBreakpoints = new Set();

/** 切换 AI 编辑面板显示/隐藏 */
export function toggleAiEditPanel() {
    initDevTools();
    const panel = document.getElementById('manim-ai-edit-float');
    if (!panel) return;
    const visible = panel.style.display !== 'none';
    panel.style.display = visible ? 'none' : 'flex';
}

function appendKeyframeLog(msg) {
    const log = document.getElementById('dev-manim-log');
    if (log) {
        log.textContent = (log.textContent || '') + `[关键帧] ${msg}\n`;
        log.scrollTop = log.scrollHeight;
    }
}

/** 解析断点行号：优先使用用户点击设置的断点，其次 # @keyframe 注释，1-based */
function getBreakpointLine(code) {
    if (keyframeBreakpoints.size > 0) {
        const line = Math.min(...keyframeBreakpoints);
        return line;
    }
    const lines = code.split('\n');
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes('# @keyframe') || lines[i].includes('# keyframe')) {
            return i + 1;
        }
    }
    return null;
}

/** 选取最能体现 Manim 改动的行号：对象在 add 或 play 时才显示，定义行不显示（1-based）。instruction 含「添加」时取最后一个 add/play */
function getImportantChangeLine(originalCode, modifiedCode, instruction) {
    const addPattern = /self\.add\s*\(/;
    const animKeywords = /\b(Create|Write|Transform|ReplacementTransform|FadeIn|FadeOut|GrowFromCenter|DrawBorderThenFill)\s*\(/;
    const playPattern = /self\.play\s*\(/;
    const lines = modifiedCode.split('\n');
    const candidates = [];
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (addPattern.test(line) || (playPattern.test(line) && animKeywords.test(line))) candidates.push(i + 1);
        else if (playPattern.test(line)) candidates.push(i + 1);
    }
    if (candidates.length > 0) {
        const isAdd = instruction && (/添加/.test(instruction) || /add/i.test(instruction));
        return isAdd ? candidates[candidates.length - 1] : candidates[0];
    }
    const orig = originalCode.split('\n');
    const mod = modifiedCode.split('\n');
    for (let i = 0; i < Math.min(orig.length, mod.length); i++) {
        if ((orig[i] || '').trim() !== (mod[i] || '').trim()) return i + 1;
    }
    return null;
}

/** 渲染关键帧：支持断点（# @keyframe 注释），结果显示在视频预览区，输出日志 */
let devPreviewController=null;
export async function previewKeyframes({signal} = {}) {
    if(devPreviewController){if(!signal)devPreviewController.abort();return false;}
    if(devRenderController||signal?.aborted)return false;
    const code = monacoEditor ? monacoEditor.getValue() : '';
    if (!code || !code.trim()) {
        if (typeof showToast === 'function') showToast('请输入或加载代码', 'info');
        return;
    }
    const controller=new AbortController();devPreviewController=controller;
    const cancel=()=>controller.abort();signal?.addEventListener('abort',cancel,{once:true});
    const button=document.getElementById('btn-manim-keyframe'),label=button?.innerHTML;
    if(button)button.textContent='停止预览';
    const breakpointLine = getBreakpointLine(code);
    appendKeyframeLog(breakpointLine ? `正在渲染断点行 ${breakpointLine} 的关键帧...` : '正在渲染关键帧...');
    const loading = document.getElementById('dev-manim-loading');
    const loadingText = document.querySelector('#dev-manim-loading .ide-loading-text');
    const video = document.getElementById('dev-manim-video');
    const placeholder = document.getElementById('dev-manim-placeholder');
    if (loading && loadingText) {
        loading.style.display = 'flex';
        loadingText.textContent = '正在渲染关键帧...';
        if (placeholder) placeholder.style.display = 'none';
        if (video) video.style.display = 'none';
    }
    try {
        const body = { code: code.trim() };
        if (breakpointLine) body.breakpoint_line = breakpointLine;
        const res = await fetch('/api/devtools/render_keyframe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            credentials: 'include',
            signal:controller.signal,
        });
        const data = await res.json();
        if (loading) loading.style.display = 'none';
        if (data.status === 'success' && data.preview_url) {
            if(data.repaired&&data.code&&monacoEditor?.getValue().trim()===code.trim()){
                monacoEditor.pushUndoStop();monacoEditor.executeEdits('preview-repair',[{range:monacoEditor.getModel().getFullModelRange(),text:data.code}]);monacoEditor.pushUndoStop();
                appendKeyframeLog('预览错误已自动修复，修改可撤销。');
            }
            const base = window.location.origin || '';
            const url = data.preview_url.startsWith('/') ? base + data.preview_url : data.preview_url;
            appendKeyframeLog('关键帧渲染完成');
            if (video) video.style.display = 'none';
            if (placeholder) placeholder.style.display = 'none';
            const preview = document.getElementById('manim-keyframe-preview-in-video');
            const img = document.getElementById('manim-keyframe-img-in-video');
            if (preview && img) {
                img.src = url;
                preview.style.display = 'flex';
            }
            return true;
        } else {
            const err = (data.message || '渲染失败').slice(0, 150);
            appendKeyframeLog('渲染失败: ' + err);
            if (placeholder) placeholder.style.display = '';
            if (typeof showToast === 'function') showToast(err, 'error');
        }
    } catch (error) {
        if (loading) loading.style.display = 'none';
        appendKeyframeLog(error.name==='AbortError'?'已停止预览。':'网络错误');
        if (placeholder) placeholder.style.display = '';
        if (error.name!=='AbortError' && typeof showToast === 'function') showToast('网络错误', 'error');
    } finally {
        signal?.removeEventListener('abort',cancel);devPreviewController=null;
        if(button)button.innerHTML=label;
    }
    return false;
}

function hideKeyframeInVideoArea() {
    const preview = document.getElementById('manim-keyframe-preview-in-video');
    const img = document.getElementById('manim-keyframe-img-in-video');
    if (preview) preview.style.display = 'none';
    if (img) img.src = '';
}

/** 调用 render_keyframe，可选 breakpointLine，返回 preview_url 或 null */
export async function renderKeyframeForCode(code, breakpointLine = null) {
    if (!code || !code.trim()) return null;
    try {
        const body = { code: code.trim() };
        if (breakpointLine != null) body.breakpoint_line = breakpointLine;
        const res = await fetch('/api/devtools/render_keyframe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            credentials: 'include',
        });
        const data = await res.json();
        if (data.status === 'success' && data.preview_url) {
            const base = window.location.origin || '';
            return data.preview_url.startsWith('/') ? base + data.preview_url : data.preview_url;
        }
    } catch (_) {}
    return null;
}

/** 初始化 AI 编辑（独立浮动面板） */
function initManimAiEdit() {
    const panel=document.getElementById('manim-ai-edit-float');
    const dev=document.getElementById('dev-manim');if(!dev||!panel)return false;
    dev.classList.add('manim-studio');dev.append(panel);
    const preview=document.getElementById('manim-video-float-wrap')||document.getElementById('ide-preview-pane');
    if(preview){preview.classList.add('studio-preview');dev.append(preview);}
    mountCodeAssistant(panel,()=>monacoEditor,runDevManim,ensureManimEditor);
    return !!panel.codeAssistant;
}

export function disposeDevTools() {
    delete document.getElementById('devtools')?.dataset.devInitialized;
    document.getElementById('manim-ai-edit-float')?.codeAssistant?.dispose();
    devRenderController?.abort();
    devPreviewController?.abort();
    editorThemeObserver?.disconnect();editorThemeObserver=null;
    if(monacoEditor){editorDraft=monacoEditor.getValue();monacoEditor.getModel()?.dispose();monacoEditor.dispose();monacoEditor=null;window.monacoEditor=null;}
}
let editorDraft=null;
let completionProvider=null,editorThemeObserver=null;
export async function ensureManimEditor() {
    switchDevTool('manim');
    await loadMonaco();
    if(!monacoEditor)throw new Error('工作台已关闭，请重新打开后生成。');
    return monacoEditor;
}

function initAiEditFloatDrag(wrap, header) {
    if (!wrap || !header) return;
    let isDragging = false;
    let startX = 0, startY = 0, startLeft = 0, startTop = 0;
    header.addEventListener('mousedown', (e) => {
        if (e.target.closest('.manim-ai-edit-close')) return;
        if (e.button !== 0) return;
        e.preventDefault();
        isDragging = true;
        const rect = wrap.getBoundingClientRect();
        startX = e.clientX;
        startY = e.clientY;
        startLeft = rect.left;
        startTop = rect.top;
        wrap.style.right = 'auto';
        wrap.style.bottom = 'auto';
        wrap.style.left = startLeft + 'px';
        wrap.style.top = startTop + 'px';
        wrap.style.transform = 'none';
    });
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        let left = startLeft + dx;
        let top = startTop + dy;
        left = Math.max(0, Math.min(left, window.innerWidth - wrap.offsetWidth));
        top = Math.max(0, Math.min(top, window.innerHeight - wrap.offsetHeight));
        wrap.style.left = left + 'px';
        wrap.style.top = top + 'px';
    });
    document.addEventListener('mouseup', () => { isDragging = false; });
}

// --- LaTeX 模块 ---
/**
 * 同步开发者工具中的 LaTeX 三视图：
 * - MathLive 可视化输入框
 * - LaTeX 源码 textarea
 * - KaTeX 最终预览
 */
function updateDevLatexView(latex) {
    const value = latex || '';
    const mf = document.getElementById('dev-latex-mathfield');
    const source = document.getElementById('dev-latex-source');
    const preview = document.getElementById('dev-latex-preview');

    // 避免 setValue 触发多余 input 事件导致循环
    if (mf && typeof mf.getValue === 'function' && typeof mf.setValue === 'function') {
        try {
            if (mf.getValue() !== value) mf.setValue(value);
        } catch (_) {}
    }
    if (source && source.value !== value) {
        source.value = value;
    }
    if (preview) {
        renderFormula(preview,value);
    }
}

function initLatexTool() {
    const mf = document.getElementById('dev-latex-mathfield');
    const source = document.getElementById('dev-latex-source');

    // 初始值：优先 MathLive，再退回 textarea
    let initial = '';
    if (mf && typeof mf.getValue === 'function') {
        try {
            initial = mf.getValue() || '';
        } catch (_) {
            initial = '';
        }
    } else if (source) {
        initial = source.value || '';
    }
    if (initial) {
        updateDevLatexView(initial);
    }

    // MathLive → 源码 & 预览
    if (mf) {
        mf.addEventListener('input', (e) => {
            updateDevLatexView(e.target.value);
        });
    }

    // 源码 → MathLive & 预览（支持直接改 LaTeX 字符串）
    if (source) {
        source.addEventListener('input', (e) => {
            updateDevLatexView(e.target.value);
        });
    }
    // Temml 导出设置
    const modeSel = document.getElementById('dev-latex-temml-mode');
    const xmlChk = document.getElementById('dev-latex-temml-xml');
    const annChk = document.getElementById('dev-latex-temml-annotate');
    if (modeSel) {
        modeSel.addEventListener('change', () => {
            const v = modeSel.value;
            if (v === 'Math' || v === 'MathML' || v === 'FlatMML') temmlExportMode = v;
        });
    }
    if (xmlChk) {
        temmlExportXml = xmlChk.checked;
        xmlChk.addEventListener('change', () => {
            temmlExportXml = xmlChk.checked;
        });
    }
    if (annChk) {
        temmlExportAnnotate = annChk.checked;
        annChk.addEventListener('change', () => {
            temmlExportAnnotate = annChk.checked;
        });
    }
}

// 复制 LaTeX 源码（纯文本）
export function copyDevLatex() {
    const source = document.getElementById('dev-latex-source');
    if (!source) return;
    const text = source.value || '';

    // 优先使用现代 Clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch(() => {
            // 降级到旧方案
            source.select();
            document.execCommand('copy');
        });
    } else {
        source.select();
        document.execCommand('copy');
    }

    // 简单的视觉反馈
    const originalBg = source.style.backgroundColor;
    source.style.backgroundColor = '#dcfce7';
    setTimeout(() => { source.style.backgroundColor = originalBg; }, 200);
}

// 供外部模块调用：填充 LaTeX 编辑器
export function fillLatexInDevtools(latex) {
    updateDevLatexView(normalizeLatex(latex || ''));
}

// Temml 按需加载：用于生成 MathML / 可粘贴到 Word 的内容
let temmlLoadingPromise = null;
let temmlExportMode = 'Math';      // Math | MathML | FlatMML（参考 temml.org）
let temmlExportXml = true;
let temmlExportAnnotate = false;
function ensureTemmlLoaded() {
    if (window.temml) return Promise.resolve();
    if (temmlLoadingPromise) return temmlLoadingPromise;
    temmlLoadingPromise = new Promise((resolve, reject) => {
        const existing = document.getElementById('temml-loader-script');
        if (existing) {
            existing.addEventListener('load', () => resolve());
            existing.addEventListener('error', () => reject(new Error('Temml 加载失败')));
            return;
        }
        const script = document.createElement('script');
        script.id = 'temml-loader-script';
        script.src = 'https://cdn.jsdelivr.net/npm/temml@0.13.1/dist/temml.min.js';
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Temml 加载失败'));
        document.body.appendChild(script);
    });
    return temmlLoadingPromise;
}

/**
 * 复制为 MathML / HTML，便于直接粘贴到 Word / PowerPoint 等
 * - 剪贴板同时写入 text/html + text/plain
 * - 浏览器不支持 rich clipboard 时退化为复制 MathML 文本
 */
export async function copyDevLatexAsMathML() {
    const source = document.getElementById('dev-latex-source');
    const latex = normalizeLatex((source && source.value) || '');
    if (!latex.trim()) {
        if (typeof showToast === 'function') showToast('请先输入或识别公式', 'info');
        return;
    }

    try {
        await ensureTemmlLoaded();
    } catch (_) {
        if (typeof showToast === 'function') showToast('Temml 加载失败，已退回复制 LaTeX 源码', 'error');
        copyDevLatex();
        return;
    }

    if (!window.temml || typeof window.temml.render !== 'function') {
        if (typeof showToast === 'function') showToast('Temml 未正确初始化，已退回复制 LaTeX 源码', 'error');
        copyDevLatex();
        return;
    }

    // 使用 Temml 生成 MathML
    const container = document.createElement('div');
    let mathml = '';
    try {
        // 传递部分选项给 Temml（若版本不支持会自动忽略）
        window.temml.render(latex, container, {
            displayMode: true,
            xml: temmlExportXml,
            annotate: temmlExportAnnotate
        });
        mathml = container.innerHTML || '';
    } catch (e) {
        // 当选择 Math 模式时，即便 Temml 失败仍可退回纯 LaTeX
        if (temmlExportMode !== 'Math') {
            if (typeof showToast === 'function') showToast('转换 MathML 失败，已退回复制 LaTeX 源码', 'error');
        }
        mathml = '';
    }

    // 根据设置选择最终导出内容（既作为 text/plain，也作为 text/html）
    let payload = '';
    if (temmlExportMode === 'Math') {
        payload = latex;
    } else if (temmlExportMode === 'MathML') {
        if (!mathml) {
            copyDevLatex();
            return;
        }
        payload = mathml;
    } else if (temmlExportMode === 'FlatMML') {
        if (!mathml) {
            copyDevLatex();
            return;
        }
        payload = mathml.replace(/\s+/g, ' ').trim();
    } else {
        // 未知模式时退回 MathML
        if (!mathml) {
            copyDevLatex();
            return;
        }
        payload = mathml;
    }

    const htmlPayload = payload;

    let success = false;
    if (navigator.clipboard && navigator.clipboard.write && window.ClipboardItem) {
        try {
            const item = new ClipboardItem({
                'text/html': new Blob([htmlPayload], { type: 'text/html' }),
                'text/plain': new Blob([payload], { type: 'text/plain' }),
            });
            await navigator.clipboard.write([item]);
            success = true;
        } catch (_) {
            success = false;
        }
    }

    if (!success) {
        // 退化为复制纯文本
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(payload);
        } else {
            const ta = document.createElement('textarea');
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            ta.value = payload;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        }
    }

    if (typeof showToast === 'function') {
        showToast('已复制为 Word 友好的数学公式（MathML）', 'success');
    }
}

// 从 LaTeX 编辑器保存当前公式到「我的算式」库
export async function saveCurrentLatexToFormulas() {
    const latexSource = document.getElementById('dev-latex-source');
    const latex = (latexSource && latexSource.value || '').trim();
    if (!latex) {
        if (typeof showToast === 'function') showToast('请先输入公式后再保存', 'info');
        return;
    }
    const user = getCurrentUsername();
    if (!user) {
        if (typeof window.toggleAuthModal === 'function') window.toggleAuthModal(true);
        if (typeof showToast === 'function') showToast('请先登录后再保存算式', 'info');
        return;
    }
    let note = '来自开发者工具的公式';
    if (typeof window.showPrompt === 'function') {
        const result = await window.showPrompt('请输入公式备注：', note, '保存算式');
        if (result === null) return;
        note = result || note;
    }
    try {
        const res = await fetch('/api/formulas/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: user, latex, note })
        });
        const data = await res.json();
        if (data.status === 'success') {
            if (typeof showToast === 'function') showToast('已保存到「我的算式」', 'success');
        } else {
            if (typeof showToast === 'function') showToast(data.message || '保存失败', 'error');
        }
    } catch (e) {
        if (typeof showToast === 'function') showToast('网络错误，保存失败', 'error');
    }
}

// 从 LaTeX 编辑器跳转到「我的算式」，由用户选择要导入/编辑的算式
export function goToFormulasForImport() {
    const user = getCurrentUsername();
    if (!user) {
        if (typeof window.toggleAuthModal === 'function') window.toggleAuthModal(true);
        if (typeof showToast === 'function') showToast('请先登录后再从算式库导入', 'info');
        return;
    }
    if (typeof window.showSection === 'function') window.showSection('my-formulas');
    if (typeof showToast === 'function') {
        showToast('已跳转到「我的算式」，在列表中点击「编辑 → 去 LaTeX 编辑器」即可导入', 'info');
    }
}

// --- Manim 模块 (Monaco Kernel) ---
// Monaco 懒加载：仅在用户进入开发者工具时加载，减轻首屏体积
let monacoLoading=null;
function showEditorLoadError(error) {
    const container=document.getElementById('monaco-container');
    if(!container||monacoEditor)return;
    container.replaceChildren();
    const message=document.createElement('p'),retry=document.createElement('button');
    message.textContent=error.message;retry.textContent='重新加载编辑器';retry.className='action-btn secondary';
    retry.onclick=()=>{retry.disabled=true;loadMonaco().catch(showEditorLoadError);};
    container.append(message,retry);
}
async function loadMonaco() {
    if(!window.monaco){
        if(!monacoLoading){
            monacoLoading=new Promise((resolve,reject)=>{
                const base='/static/vendor/monaco-editor/0.45.0/min/vs';
                let script,settled=false;
                const finish=error=>{
                    if(settled)return;settled=true;clearTimeout(timer);
                    if(error){script?.remove();if(!window.monaco)window.require?.reset?.();reject(new Error('代码编辑器加载失败，请检查本站连接后重试。'));}
                    else resolve();
                };
                const timer=setTimeout(()=>finish(true),20000);
                const core=()=>{
                    try{
                        window.require.config({paths:{vs:base}});
                        window.require(['vs/editor/editor.main'],()=>finish(),()=>finish(true));
                    }catch{finish(true);}
                };
                if(window.require?.config){core();return;}
                document.getElementById('monaco-loader-script')?.remove();
                script=document.createElement('script');script.id='monaco-loader-script';script.src=base+'/loader.js';
                script.onload=core;script.onerror=()=>finish(true);document.body.appendChild(script);
            }).finally(()=>{monacoLoading=null;});
        }
        await monacoLoading;
    }
    initMonacoEditor();
}

function initMonacoEditor() {
    const container = document.getElementById('monaco-container');
    if (!container || monacoEditor) return;
    container.replaceChildren();

    // 1. 注册 Manim 智能补全 (模拟 Pylance)
    completionProvider ||= monaco.languages.registerCompletionItemProvider('python', {
        provideCompletionItems: function(model, position) {
            const suggestions = [
                // 核心类
                { label: 'Scene', kind: monaco.languages.CompletionItemKind.Class, insertText: 'Scene' },
                { label: 'Circle', kind: monaco.languages.CompletionItemKind.Class, insertText: 'Circle(radius=${1:1}, color=${2:BLUE})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Mobject' },
                { label: 'Square', kind: monaco.languages.CompletionItemKind.Class, insertText: 'Square(side_length=${1:2}, color=${2:RED})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Mobject' },
                { label: 'Text', kind: monaco.languages.CompletionItemKind.Class, insertText: 'Text("${1:Hello}", font_size=${2:48})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Mobject' },
                { label: 'MathTex', kind: monaco.languages.CompletionItemKind.Class, insertText: 'MathTex(r"${1:\\frac{a}{b}}")', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'LaTeX' },
                { label: 'NumberPlane', kind: monaco.languages.CompletionItemKind.Class, insertText: 'NumberPlane()', detail: 'Grid' },
                { label: 'Axes', kind: monaco.languages.CompletionItemKind.Class, insertText: 'Axes(x_range=[${1:-5, 5}], y_range=[${2:-5, 5}])', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Graph' },

                // 动画方法
                { label: 'Create', kind: monaco.languages.CompletionItemKind.Function, insertText: 'Create(${1:mobject})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Animation' },
                { label: 'Write', kind: monaco.languages.CompletionItemKind.Function, insertText: 'Write(${1:text})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Animation' },
                { label: 'FadeIn', kind: monaco.languages.CompletionItemKind.Function, insertText: 'FadeIn(${1:mobject})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Animation' },
                { label: 'Transform', kind: monaco.languages.CompletionItemKind.Function, insertText: 'Transform(${1:obj1}, ${2:obj2})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Animation' },
                { label: 'ReplacementTransform', kind: monaco.languages.CompletionItemKind.Function, insertText: 'ReplacementTransform(${1:obj1}, ${2:obj2})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Animation' },

                // 常量
                { label: 'UP', kind: monaco.languages.CompletionItemKind.Constant, insertText: 'UP', detail: 'Vector' },
                { label: 'DOWN', kind: monaco.languages.CompletionItemKind.Constant, insertText: 'DOWN', detail: 'Vector' },
                { label: 'LEFT', kind: monaco.languages.CompletionItemKind.Constant, insertText: 'LEFT', detail: 'Vector' },
                { label: 'RIGHT', kind: monaco.languages.CompletionItemKind.Constant, insertText: 'RIGHT', detail: 'Vector' },
                { label: 'ORIGIN', kind: monaco.languages.CompletionItemKind.Constant, insertText: 'ORIGIN', detail: 'Vector [0,0,0]' },
                { label: 'BLUE', kind: monaco.languages.CompletionItemKind.Color, insertText: 'BLUE', detail: 'Color' },
                { label: 'RED', kind: monaco.languages.CompletionItemKind.Color, insertText: 'RED', detail: 'Color' },
                { label: 'YELLOW', kind: monaco.languages.CompletionItemKind.Color, insertText: 'YELLOW', detail: 'Color' },
                { label: 'GREEN', kind: monaco.languages.CompletionItemKind.Color, insertText: 'GREEN', detail: 'Color' },

                // 自身方法 (Snippet)
                { label: 'play', kind: monaco.languages.CompletionItemKind.Method, insertText: 'self.play(${1:Animation})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Scene Method' },
                { label: 'wait', kind: monaco.languages.CompletionItemKind.Method, insertText: 'self.wait(${1:1})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Scene Method' },
                { label: 'add', kind: monaco.languages.CompletionItemKind.Method, insertText: 'self.add(${1:mobject})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Scene Method' }
            ];
            return { suggestions: suggestions };
        }
    });

    const defaultCode = `from manim import *

class GenScene(Scene):
    def construct(self):
        # 1. 定义对象
        circle = Circle(radius=2, color=BLUE)
        circle.set_fill(BLUE, opacity=0.5)
        
        text = Text("Hello Manim", font_size=48)
        text.next_to(circle, UP)
        
        # 2. 播放动画
        self.play(Create(circle))
        self.play(Write(text))
        self.wait(1)
        
        # 3. 变换
        square = Square(color=RED)
        self.play(Transform(circle, square))
        self.wait(1)`;

    // 2. 创建编辑器实例
    monacoEditor = monaco.editor.create(container, {
        value: editorDraft ?? defaultCode,
        language: 'python',
        theme: document.documentElement.dataset.theme==='dark'?'vs-dark':'vs',
        automaticLayout: true, // 自动响应 resize (性能开销稍大，但方便)
        fontSize: 14,
        fontFamily: "'JetBrains Mono', 'Consolas', 'Courier New', monospace",
        minimap: { enabled: false }, // 关闭缩略图，节省空间
        scrollBeyondLastLine: false,
        padding: { top: 15, bottom: 15 },
        lineNumbersMinChars: 3,
        glyphMargin: true,
        wordWrap: 'on'
    });

    let breakpointDecorations = [];
    monacoEditor.onMouseDown((e) => {
        if (e.target.type === 2 && e.target.position) {
            const line = e.target.position.lineNumber;
            if (keyframeBreakpoints.has(line)) {
                keyframeBreakpoints.delete(line);
            } else {
                keyframeBreakpoints.add(line);
            }
            const decos = Array.from(keyframeBreakpoints).map((ln) => ({
                range: new monaco.Range(ln, 1, ln, 1),
                options: { glyphMarginClassName: 'manim-keyframe-breakpoint' }
            }));
            breakpointDecorations = monacoEditor.deltaDecorations(breakpointDecorations, decos);
        }
    });
    window.monacoEditor = monacoEditor;
    editorThemeObserver?.disconnect();
    editorThemeObserver=new MutationObserver(()=>monaco.editor.setTheme(document.documentElement.dataset.theme==='dark'?'vs-dark':'vs'));
    editorThemeObserver.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});

    // 绑定代码变化时的布局自动调整（Monaco 懒加载后补绑）
    if (typeof scheduleManimLayoutAdjust === 'function') {
        monacoEditor.getModel()?.onDidChangeContent(() => scheduleManimLayoutAdjust('code'));
    }

    // 3. 绑定快捷键 Ctrl+Enter 运行
    monacoEditor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, function() {
        runDevManim();
    });
}

// --- 运行逻辑（与动态计算共享全站渲染冷却）---
const RUN_BTN_ORIGINAL = '<i class="fa-solid fa-play"></i> 运行';

function updateRunButtonFromCooldown(left) {
    const btn = document.getElementById('btn-run-manim');
    if (!btn) return;
    if (left > 0) {
        btn.disabled = true;
        btn.style.opacity = '0.7';
        btn.innerHTML = `<i class="fa-regular fa-clock"></i> ${left}s`;
    } else {
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.innerHTML = RUN_BTN_ORIGINAL;
    }
}

let devRenderController=null;
export function stopDevRender(){devRenderController?.abort();devPreviewController?.abort();}
export async function runDevManim({signal} = {}) {
    if(devRenderController||devPreviewController)return false;
    if(!monacoEditor)return false;
    if(signal?.aborted)return false;
    const code=monacoEditor.getValue(),controller=new AbortController();devRenderController=controller;
    const cancel=()=>controller.abort();signal?.addEventListener('abort',cancel,{once:true});
    const btn=document.getElementById('btn-run-manim'),video=document.getElementById('dev-manim-video');
    const placeholder=document.getElementById('dev-manim-placeholder'),loading=document.getElementById('dev-manim-loading'),log=document.getElementById('dev-manim-log');
    let stop=document.getElementById('btn-stop-dev-render');
    if(!stop){stop=document.createElement('button');stop.id='btn-stop-dev-render';stop.className='ide-btn';stop.textContent='停止渲染';stop.onclick=stopDevRender;btn.after(stop);}
    btn.disabled=true;stop.hidden=false;loading.style.display='block';placeholder.style.display='none';video.style.display='none';log.textContent='';
    let success=false;
    try{
        const response=await fetch('/api/devtools/run_manim_stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code}),signal:controller.signal});
        await consumeEvents(response,event=>{
            if(event.type==='error')throw new Error(event.message||'渲染失败');
            if(event.message){log.textContent=(log.textContent+'\n'+event.message).slice(-24000);log.scrollTop=log.scrollHeight;}
            if(event.type==='complete'){
                if(!/^\/videos\/[a-f0-9-]+\.mp4$/.test(event.video_url))throw new Error('视频地址无效');
                if(event.repaired&&event.code&&monacoEditor?.getValue()===code){monacoEditor.pushUndoStop();monacoEditor.executeEdits('render-repair',[{range:monacoEditor.getModel().getFullModelRange(),text:event.code}]);monacoEditor.pushUndoStop();}
                hideKeyframeInVideoArea();video.src=event.video_url;video.style.display='block';success=true;
            }
        },controller.signal);
    }catch(error){log.textContent+='\n'+(error.name==='AbortError'?'已停止渲染。':error.message);}
    finally{signal?.removeEventListener('abort',cancel);loading.style.display='none';placeholder.style.display=success?'none':'block';btn.disabled=false;stop.hidden=true;devRenderController=null;}
    return success;
}

// 当前工作台脚本的最新视频文案摘要（仅前端存储，用于列表预览）
let currentVideoCopy = '';

/** 创作者：总结当前 Manim 脚本，生成视频文案（标题 + 简介 + 章节建议），结果以弹窗形式展示 */
export async function generateVideoCopy() {
    const code=monacoEditor?.getValue();if(!code?.trim())throw new Error('请先输入脚本');
    const dialog=document.createElement('dialog');dialog.className='studio-save-dialog';
    dialog.innerHTML='<h3>脚本说明</h3><p class="studio-summary-text" role="status">正在阅读脚本…</p><button>关闭</button>';
    document.body.append(dialog);dialog.showModal();dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();
    try{const res=await fetch('/api/devtools/generate_video_copy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});const data=await res.json();if(!res.ok||data.status!=='success')throw new Error(data.message||'生成失败');currentVideoCopy=data.copy;dialog.querySelector('p').textContent=data.copy;return true;}
    catch(error){dialog.querySelector('p').textContent=error.message;return false;}
}

/** 将当前视频文案与脚本 ID 关联存入 localStorage，供「我的脚本」和动画脚本库预览使用 */
export function saveCurrentVideoCopyForScript(scriptId) {
    if (!scriptId || !currentVideoCopy) return;
    try {
        const key = 'animation_script_video_copies';
        const raw = localStorage.getItem(key) || '{}';
        const map = JSON.parse(raw);
        map[String(scriptId)] = currentVideoCopy;
        localStorage.setItem(key, JSON.stringify(map));
    } catch (e) {
        console.warn('保存视频文案到 localStorage 失败', e);
    }
}

export function getVideoCopyForScript(scriptId) {
    try {
        const key = 'animation_script_video_copies';
        const raw = localStorage.getItem(key) || '{}';
        const map = JSON.parse(raw);
        return map && map[String(scriptId)] || '';
    } catch {
        return '';
    }
}

/** 将弹窗中展示的视频文案保存为当前脚本的关联文案（localStorage），便于列表里显示文案与时间 */
export function saveVideoCopyAsScriptNote() {
    if (workbenchScriptId == null) {
        if (typeof showToast === 'function') showToast('请先保存脚本到动画脚本库后再关联文案', 'info');
        return;
    }
    saveCurrentVideoCopyForScript(workbenchScriptId);
    toggleModal('video-copy-modal', false);
    if (typeof showToast === 'function') showToast('已保存为当前脚本文案，列表中将显示文案与时间', 'success');
    renderImportScripts();
}

/** 供 HTML 直接调用的关闭视频文案弹窗方法 */
export function closeVideoCopyModal() {
    toggleModal('video-copy-modal', false);
}

/** 从外部（如我的算式-动画脚本库）跳转到本工作台并填入代码，可选自动运行；支持 scriptId/note 以支持工作台保存 */
export async function openManimWorkbenchWithCode(code, options = {}) {
    workbenchScriptId=options.scriptId??null;workbenchScriptNote=options.note??'';
    const editor=await ensureManimEditor();editor.setValue(code||'');
    if(options.autoRun)return await runDevManim();
    return true;
}
export function openNewBlankScriptInWorkbench(){return openManimWorkbenchWithCode(MANIM_FRAMEWORK_SCRIPT);}

function initRenderCooldownListeners() {
    window.addEventListener('render-cooldown-tick', (e) => updateRunButtonFromCooldown(e.detail.left));
    window.addEventListener('render-cooldown-end', () => updateRunButtonFromCooldown(0));
}

// [修改] 渲染 Rainbow 库内容
function renderRainbowLib() {
    const container = document.getElementById('rainbow-content-container');
    if (!container || container.innerHTML.trim() !== "") return;

    const headerHtml = `
        <div class="rainbow-header">
            <h1 class="rainbow-title">${RAINBOW_LIB_INFO.title}</h1>
            <p class="rainbow-desc">${RAINBOW_LIB_INFO.description}</p>
            <a href="${RAINBOW_LIB_INFO.github}" target="_blank" class="rainbow-github-link">
                <i class="fa-brands fa-github"></i> View on GitHub
            </a>
        </div>
        <div class="rainbow-grid">
    `;

    const cardsHtml = RAINBOW_LIB_INFO.modules.map((mod, index) => {
        // [新增] 动态生成图片 HTML
        // 如果有图片，显示图片；否则不显示这个 div
        // 使用 onerror 处理器，如果图片加载失败（比如路径不对），自动隐藏该图片元素
        const imagePart = mod.image ? `
            <div class="rainbow-card-image">
                <img src="${mod.image}" alt="${mod.title}" onerror="this.style.display='none'">
            </div>
        ` : '';

        return `
        <div class="rainbow-card">
            <div class="card-top">
                <h3>${mod.title}</h3>
                <span class="card-badge">Extension</span>
            </div>
            
            <!-- 图片区域 -->
            ${imagePart}
            
            <p>${mod.desc}</p>
            
            <div class="code-preview">
                <pre><code class="language-python">${escapeHtml(mod.code)}</code></pre>
            </div>
            
            <button class="action-btn full-width" onclick="loadIntoWorkbench(${index})">
                <i class="fa-solid fa-flask"></i> 载入到工作台试用
            </button>
        </div>
        `;
    }).join('');

    const communityHtml = `
        <div class="rainbow-community-section">
            <h3 class="rainbow-community-title"><i class="fa-solid fa-code"></i> 我的可复用脚本</h3>
            <p class="rainbow-community-desc">在工作台保存动画脚本，回到脚本库阅读说明、载入代码并继续改编。</p>
            <button type="button" class="action-btn tertiary" data-rainbow-scripts>打开我的脚本库</button>
        </div>`;
    container.innerHTML = headerHtml + cardsHtml + '</div>' + communityHtml;
    container.querySelector('[data-rainbow-scripts]').onclick=async()=>{const G=await import('./site-graph.js');G.executeNodeAction(G.getNodeById('formulas-scripts'));};

    if(window.hljs) container.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
}

// [新增] 将代码载入 Monaco 并跳转
window.loadIntoWorkbench = function(index) {
    const code = RAINBOW_LIB_INFO.modules[index].code;

    // 1. 切换到 Manim 标签
    switchDevTool('manim');

    // 2. 等待切换完成（Monaco 初始化）后设置值
    setTimeout(() => {
        if (monacoEditor) {
            monacoEditor.setValue(code);
        } else {
            // 如果 Monaco 还没加载完，轮询一次
            const checkInit = setInterval(() => {
                if (monacoEditor) {
                    monacoEditor.setValue(code);
                    clearInterval(checkInit);
                }
            }, 100);
        }
    }, 100);
};

// 辅助：HTML 转义
function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// --- 导入面板：我的脚本 + Rainbow 样例 ---
function getCurrentUsername() {
    const userDisplay = document.getElementById('user-display');
    const usernameSpan = document.getElementById('username-span');
    if (userDisplay && userDisplay.style.display !== 'none' && usernameSpan) return usernameSpan.innerText;
    return null;
}

export function toggleImportPanel() {
    const panel = document.getElementById('manim-import-panel');
    const btn = document.getElementById('btn-manim-import');
    if (!panel) return;
    if (panel.style.display === 'flex') {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = 'flex';
    // 使用 fixed 定位并相对「导入」按钮贴齐，避免被父级 overflow 裁剪
    if (btn) {
        const r = btn.getBoundingClientRect();
        panel.style.position = 'fixed';
        panel.style.left = r.left + 'px';
        panel.style.top = (r.bottom + 6) + 'px';
        panel.style.right = 'auto';
        const maxH = window.innerHeight - r.bottom - 16;
        if (maxH < 320) panel.style.maxHeight = Math.max(200, maxH) + 'px';
        else panel.style.maxHeight = '360px';
    }
    const scriptsTab = panel.querySelector('.manim-import-tab[data-tab="scripts"]');
    const rainbowTab = panel.querySelector('.manim-import-tab[data-tab="rainbow"]');
    if (scriptsTab && scriptsTab.classList.contains('active')) {
        renderImportScripts();
    } else if (rainbowTab && rainbowTab.classList.contains('active')) {
        renderImportRainbow();
    }
    // 点击外部关闭
    const close = (e) => {
        if (!panel.contains(e.target) && !btn?.contains(e.target)) {
            panel.style.display = 'none';
            document.removeEventListener('click', close);
        }
    };
    setTimeout(() => document.addEventListener('click', close), 0);
}

function renderImportScripts() {
    const listEl = document.getElementById('manim-import-scripts');
    const rainbowEl = document.getElementById('manim-import-rainbow');
    if (!listEl || !rainbowEl) return;
    listEl.style.display = 'block';
    rainbowEl.style.display = 'none';
    const user = getCurrentUsername();
    if (!user) {
        listEl.innerHTML = '<p class="manim-import-msg" style="padding:1rem; font-size:0.85rem;">请先登录后在此选择已保存的脚本。</p>';
        return;
    }
    listEl.innerHTML = '<div class="empty-state" style="padding:1.5rem;"><i class="fa-solid fa-spinner fa-spin"></i><p>正在同步云端数据...</p></div>';
    fetch(`/api/animation_scripts/list?username=${encodeURIComponent(user)}`)
        .then(res => res.json())
        .then(data => {
            if (data.status !== 'success' || !data.data || data.data.length === 0) {
                listEl.innerHTML = '<p class="manim-import-msg" style="padding:1rem; font-size:0.85rem;">暂无保存的脚本，可前往「我的算式 → 动画脚本库」保存。</p>';
                return;
            }
            const marked = window.marked && typeof window.marked.parse === 'function' ? window.marked : null;
            const typesetMath = typeof window.typesetAgentMath === 'function' ? window.typesetAgentMath : null;
            listEl.innerHTML = '';
            data.data.forEach(s => {
                const note = (s.note || '未命名').replace(/</g, '&lt;').replace(/"/g, '&quot;');
                const created = s.created_at ? new Date(s.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : '';
                const videoCopy = getVideoCopyForScript(s.id);
                const metaText = videoCopy
                    ? (created ? created : '')
                    : (created ? '文案未生成 · ' + created : '');
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'import-item';
                btn.dataset.id = String(s.id);
                btn.title = note + (metaText ? ' · ' + metaText : '');
                btn.innerHTML = `<span class="import-item-note">${note}</span>`;
                if (videoCopy && marked) {
                    const preview = document.createElement('div');
                    preview.className = 'import-item-preview markdown-body';
                    const raw = marked.parse(videoCopy.slice(0, 1500));
                    preview.innerHTML = sanitizeMarkdownHtml(raw);
                    if (typesetMath) typesetMath(preview);
                    btn.appendChild(preview);
                }
                const small = document.createElement('small');
                small.className = 'import-item-meta';
                small.textContent = metaText || ('ID: ' + s.id + (created ? ' · ' + created : ''));
                btn.appendChild(small);
                btn.addEventListener('click', () => loadScriptIntoEditor(parseInt(btn.dataset.id, 10)));
                listEl.appendChild(btn);
            });
        })
        .catch(() => {
            listEl.innerHTML = '<p class="manim-import-msg manim-import-msg-error" style="padding:1rem; font-size:0.85rem;">加载失败</p>';
        });
}

function loadScriptIntoEditor(scriptId) {
    const user = getCurrentUsername();
    if (!user) return;
    fetch(`/api/animation_scripts/get?id=${scriptId}&username=${encodeURIComponent(user)}`)
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success' && data.data && data.data.code && monacoEditor) {
                monacoEditor.setValue(data.data.code);
                workbenchScriptId = scriptId;
                workbenchScriptNote = (data.data.note || '').trim();
                document.getElementById('manim-import-panel').style.display = 'none';
            }
        });
}

/** 打开脚本备注弹窗（与公式编辑窗口同款样式），用户填写后点保存再执行实际保存 */
export async function saveScriptDirect(note=workbenchScriptNote||'未命名动画') {
    const response=await fetch('/api/user/me',{credentials:'include'}),me=await response.json();
    if(!response.ok||!me.username){window.toggleAuthModal?.(true);throw new Error('请登录后保存脚本');}
    const code=monacoEditor?.getValue();if(!code?.trim())throw new Error('代码不能为空');
    const endpoint=workbenchScriptId?'/update':'/save';
    const res=await fetch('/api/animation_scripts'+endpoint,{method:workbenchScriptId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:workbenchScriptId,username:me.username,note,code})});
    const result=await res.json();if(!res.ok||result.status!=='success')throw new Error(result.message||'保存失败');
    workbenchScriptId=result.id||workbenchScriptId;workbenchScriptNote=note;
    window.dispatchEvent(new CustomEvent('formula-library-updated'));
    return workbenchScriptId;
}
export function saveScriptFromWorkbench() {
    const dialog=document.createElement('dialog');dialog.className='studio-save-dialog';
    dialog.innerHTML='<form><h3>保存到我的脚本</h3><label>脚本名称<input name="note" maxlength="200" required></label><p role="status"></p><div><button type="button">取消</button><button type="submit">保存脚本</button></div></form>';
    dialog.querySelector('input').value=workbenchScriptNote||'未命名动画';document.body.append(dialog);dialog.showModal();
    dialog.querySelector('[type=button]').onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove(),{once:true});
    dialog.querySelector('form').onsubmit=async event=>{event.preventDefault();const btn=dialog.querySelector('[type=submit]');btn.disabled=true;try{await saveScriptDirect(dialog.querySelector('input').value.trim());dialog.close();window.showToast?.('脚本已保存','success');}catch(error){dialog.querySelector('[role=status]').textContent=error.message;}finally{btn.disabled=false;}};
}

/** 关闭脚本备注弹窗 */
export function closeScriptNoteModal() {
    toggleModal('script-note-modal', false);
}

/** 从脚本备注弹窗确认并执行保存（与登录成功一致使用 showToast 提示，不用浏览器默认 alert） */
export async function confirmScriptNoteAndSave() {
    const inputEl = document.getElementById('script-note-input');
    const prefixEl = document.getElementById('script-note-prefix');
    const prefix = (prefixEl && prefixEl.style.display !== 'none' && prefixEl.textContent) ? prefixEl.textContent : '';
    const inputPart = (inputEl && inputEl.value != null) ? inputEl.value.trim() : '';
    const note = prefix + (inputPart || '未命名');
    if (window._scriptNoteModalSource === 'calculate') {
        closeScriptNoteModal();
        window._scriptNoteModalSource = null;
        window._scriptNoteModalPart = null;
        if (typeof window.submitCalcScriptNote === 'function') window.submitCalcScriptNote(note);
        return;
    }
    closeScriptNoteModal();

    const user = getCurrentUsername();
    if (!user) return;
    const code = monacoEditor ? monacoEditor.getValue() : '';
    if (!code || !code.trim()) return;

    try {
        if (workbenchScriptId != null) {
            const res = await fetch('/api/animation_scripts/update', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: workbenchScriptId, username: user, note, code })
            });
            const data = await res.json();
            if (data.status === 'success') {
                workbenchScriptNote = note;
                showToast('更新成功！', 'success');
                try {
                    const copyRes = await fetch('/api/devtools/generate_video_copy', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code })
                    });
                    const copyData = await copyRes.json();
                    if (copyData.status === 'success' && copyData.copy) {
                        currentVideoCopy = copyData.copy;
                        saveCurrentVideoCopyForScript(workbenchScriptId);
                        renderImportScripts();
                    }
                } catch (_) {}
            } else {
                showToast(data.message || '更新失败', 'error');
            }
        } else {
            const res = await fetch('/api/animation_scripts/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, note, code })
            });
            const data = await res.json();
            if (data.status === 'success' && data.id) {
                workbenchScriptId = data.id;
                workbenchScriptNote = note;
                showToast('保存成功！', 'success');
                renderImportScripts();
                try {
                    const copyRes = await fetch('/api/devtools/generate_video_copy', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code })
                    });
                    const copyData = await copyRes.json();
                    if (copyData.status === 'success' && copyData.copy) {
                        currentVideoCopy = copyData.copy;
                        saveCurrentVideoCopyForScript(data.id);
                        renderImportScripts();
                    }
                } catch (_) {}
            } else {
                showToast(data.message || '保存失败', 'error');
            }
        }
    } catch (e) {
        showToast('网络错误', 'error');
    }
}

function renderImportRainbow() {
    const listEl = document.getElementById('manim-import-rainbow');
    const scriptsEl = document.getElementById('manim-import-scripts');
    if (!listEl || !scriptsEl) return;
    listEl.style.display = 'block';
    scriptsEl.style.display = 'none';
    const modules = RAINBOW_LIB_INFO.modules || [];
    if (modules.length === 0) {
        listEl.innerHTML = '<p style="padding:1rem; color:#94a3b8;">暂无样例</p>';
        return;
    }
    listEl.innerHTML = modules.map((mod, i) => {
        const title = (mod.title || '').replace(/</g, '&lt;');
        const desc = (mod.desc || '').replace(/</g, '&lt;').substring(0, 60);
        return `<button type="button" class="import-item" data-rainbow-index="${i}">${title}<small>${desc}${desc.length >= 60 ? '…' : ''}</small></button>`;
    }).join('');
    listEl.querySelectorAll('.import-item').forEach(btn => {
        btn.addEventListener('click', () => {
            const i = parseInt(btn.dataset.rainbowIndex, 10);
            const code = RAINBOW_LIB_INFO.modules[i]?.code;
            if (code && monacoEditor) {
                monacoEditor.setValue(code);
                document.getElementById('manim-import-panel').style.display = 'none';
            }
        });
    });
}

export function switchImportTab(tab) {
    document.querySelectorAll('#manim-import-panel .manim-import-tab').forEach(t => t.classList.remove('active'));
    const btn = document.querySelector(`#manim-import-panel .manim-import-tab[data-tab="${tab}"]`);
    if (btn) btn.classList.add('active');
    if (tab === 'scripts') renderImportScripts();
    else renderImportRainbow();
}

