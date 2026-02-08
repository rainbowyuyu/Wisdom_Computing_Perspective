// static/js/devtools.js

import { RAINBOW_LIB_INFO } from './rainbow_data.js';

// 全局变量保存编辑器实例
let monacoEditor = null;

// 1. 工具切换逻辑
export function switchDevTool(tool) {
    document.querySelectorAll('#devtools .tab-btn').forEach(btn => btn.classList.remove('active'));
    const btn = document.querySelector(`#devtools .tab-btn[onclick*="${tool}"]`);
    if(btn) btn.classList.add('active');

    const latexPanel = document.getElementById('dev-latex');
    const manimPanel = document.getElementById('dev-manim');
    const rainbowPanel = document.getElementById('dev-rainbow'); // [新增]

    // 隐藏所有
    latexPanel.style.display = 'none';
    manimPanel.style.display = 'none';
    if(rainbowPanel) rainbowPanel.style.display = 'none';

    if (tool === 'latex') {
        latexPanel.style.display = 'flex';
    } else if (tool === 'manim') {
        manimPanel.style.display = 'block';
        if (monacoEditor) {
            setTimeout(() => monacoEditor.layout(), 50);
        } else {
            loadMonaco();
        }
    } else if (tool === 'rainbow') {
        // [新增] 切换到 Rainbow 面板
        if(rainbowPanel) {
            rainbowPanel.style.display = 'block';
            renderRainbowLib(); // 渲染内容
        }
    }
}

// 2. 初始化入口
export function initDevTools() {
    initLatexTool();
    // Manim 工具改为懒加载，点击 Tab 时再初始化
}

// --- LaTeX 模块 (保持不变) ---
function initLatexTool() {
    const mf = document.getElementById('dev-latex-mathfield');
    const source = document.getElementById('dev-latex-source');
    const preview = document.getElementById('dev-latex-preview');

    if (mf) {
        // 初始同步
        updateLatexView(mf.getValue());

        mf.addEventListener('input', (e) => {
            updateLatexView(e.target.value);
        });
    }

    function updateLatexView(latex) {
        if(source) source.value = latex;
        if(preview) {
            preview.innerHTML = `\\[ ${latex} \\]`;
            if(window.MathJax) MathJax.typesetPromise([preview]).catch(e => {});
        }
    }
}

// 复制 LaTeX 源码
export function copyDevLatex() {
    const source = document.getElementById('dev-latex-source');
    if(source) {
        source.select();
        document.execCommand('copy');
        // 简单的视觉反馈
        const originalBg = source.style.backgroundColor;
        source.style.backgroundColor = '#dcfce7';
        setTimeout(() => source.style.backgroundColor = originalBg, 200);
    }
}

// --- Manim 模块 (Monaco Kernel) ---

// 1. 动态加载 Monaco (解决全局冲突的核心)
function loadMonaco() {
    // 如果已经加载过，直接初始化
    if (window.monaco) {
        initMonacoEditor();
        return;
    }

    // 防止重复注入
    if (document.getElementById('monaco-loader-script')) return;

    const loaderUrl = 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/loader.min.js';

    const script = document.createElement('script');
    script.id = 'monaco-loader-script';
    script.src = loaderUrl;

    script.onload = () => {
        // loader.js 加载完毕，此时 window.require 可用
        // 配置 Monaco 路径
        window.require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' }});

        // 加载编辑器核心
        window.require(['vs/editor/editor.main'], function() {
            initMonacoEditor();
        });
    };

    document.body.appendChild(script);
}

function initMonacoEditor() {
    const container = document.getElementById('monaco-container');
    if (!container) return;

    // 1. 注册 Manim 智能补全 (模拟 Pylance)
    monaco.languages.registerCompletionItemProvider('python', {
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
        value: defaultCode,
        language: 'python',
        theme: 'vs-dark', // 深色主题
        automaticLayout: true, // 自动响应 resize (性能开销稍大，但方便)
        fontSize: 14,
        fontFamily: "'JetBrains Mono', 'Consolas', 'Courier New', monospace",
        minimap: { enabled: false }, // 关闭缩略图，节省空间
        scrollBeyondLastLine: false,
        padding: { top: 15, bottom: 15 },
        lineNumbersMinChars: 3,
        glyphMargin: false,
        wordWrap: 'on'
    });

    // 3. 绑定快捷键 Ctrl+Enter 运行
    monacoEditor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, function() {
        runDevManim();
    });
}

// --- 运行逻辑 ---
let isCooldown = false;

export async function runDevManim() {
    if (isCooldown) {
        alert("请等待冷却时间结束");
        return;
    }

    // 必须确保编辑器已加载
    if (!monacoEditor) return;
    const code = monacoEditor.getValue();

    const btn = document.getElementById('btn-run-manim');
    const video = document.getElementById('dev-manim-video');
    const placeholder = document.getElementById('dev-manim-placeholder');
    const loading = document.getElementById('dev-manim-loading');

    // UI 锁定
    startCooldownTimer(30, btn);
    placeholder.style.display = 'none';
    video.style.display = 'none';
    loading.style.display = 'block';

    try {
        const res = await fetch('/api/devtools/run_manim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code })
        });

        const data = await res.json();

        if (data.status === 'success') {
            // 添加时间戳防止缓存
            video.src = `${data.video_url}?t=${new Date().getTime()}`;
            video.style.display = 'block';
        } else {
            alert("渲染报错:\n" + data.message);
            placeholder.style.display = 'block';
        }
    } catch (e) {
        console.error(e);
        alert("网络请求失败");
        placeholder.style.display = 'block';
    } finally {
        loading.style.display = 'none';
    }
}

function startCooldownTimer(seconds, btn) {
    isCooldown = true;
    let left = seconds;
    const originalContent = '<i class="fa-solid fa-play"></i> 运行脚本';

    btn.disabled = true;
    btn.style.opacity = '0.7';
    btn.innerHTML = `<i class="fa-regular fa-clock"></i> ${left}s`;

    const timer = setInterval(() => {
        left--;
        if (left <= 0) {
            clearInterval(timer);
            isCooldown = false;
            btn.disabled = false;
            btn.innerHTML = originalContent;
            btn.style.opacity = '1';
        } else {
            btn.innerHTML = `<i class="fa-regular fa-clock"></i> ${left}s`;
        }
    }, 1000);
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

    container.innerHTML = headerHtml + cardsHtml + '</div>';

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
