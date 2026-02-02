// static/js/devtools.js

// 1. 工具切换逻辑
export function switchDevTool(tool) {
    document.querySelectorAll('#devtools .tab-btn').forEach(btn => btn.classList.remove('active'));
    const btn = document.querySelector(`#devtools .tab-btn[onclick*="${tool}"]`);
    if(btn) btn.classList.add('active');

    const latexPanel = document.getElementById('dev-latex');
    const manimPanel = document.getElementById('dev-manim');

    if (tool === 'latex') {
        latexPanel.style.display = 'flex';
        manimPanel.style.display = 'none';
    } else {
        latexPanel.style.display = 'none';
        manimPanel.style.display = 'block'; // 注意 Manim 面板容器已有 flex 布局

        // 切换回 Manim 面板时，强制刷新一次高亮和滚动位置，防止错位
        const input = document.getElementById('dev-manim-input');
        if (input) {
            updateHighlight(input.value);
            syncScroll(input);
        }
    }
}

// 2. 初始化入口
export function initDevTools() {
    initLatexTool();
    initManimTool();
}

// --- LaTeX 模块 ---
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

// --- Manim 模块 (核心修复部分) ---

// 独立的更新高亮函数 (供内部和全局调用)
function updateHighlight(code) {
    const highlight = document.getElementById('dev-manim-highlight');
    if (!highlight) return;

    // 1. 转义 HTML 字符，防止标签被解析
    let escaped = code
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // 2. 处理末尾换行
    // 如果 textarea 以换行结尾，pre 必须加一个空格占位，否则高度会少一行导致错位
    if (code.endsWith("\n")) {
        escaped += " ";
    }

    // 3. 更新 Pre 内容
    // 关键修复：直接在 innerHTML 中设置 style="font-family:inherit"，
    // 强迫 highlight.js 生成的 code 标签继承外层样式，防止字体不一致。
    highlight.innerHTML = `<code class="language-python" style="font-family:inherit; font-size:inherit; line-height:inherit; padding:0; background:transparent;">${escaped}</code>`;

    // 4. 触发高亮
    if (window.hljs) {
        const codeBlock = highlight.querySelector('code');
        if (codeBlock) hljs.highlightElement(codeBlock);
    }
}

// 独立的滚动同步函数
function syncScroll(element) {
    const highlight = document.getElementById('dev-manim-highlight');
    if(highlight && element) {
        highlight.scrollTop = element.scrollTop;
        highlight.scrollLeft = element.scrollLeft;
    }
}

function initManimTool() {
    const defaultCode = `from manim import *

class GenScene(Scene):
    def construct(self):
        # 创建一个圆形
        circle = Circle(radius=2, color=BLUE)
        
        # 创建标题文字
        title = Text("Hello Manim", font_size=48)
        title.next_to(circle, UP)
        
        # 播放动画
        self.play(Create(circle))
        self.play(Write(title))
        self.wait(1)
`;

    const input = document.getElementById('dev-manim-input');
    const highlight = document.getElementById('dev-manim-highlight');

    if(input && highlight) {
        // 1. 初始化内容
        input.value = defaultCode;
        updateHighlight(input.value);

        // 2. 绑定输入事件 (实时高亮)
        input.addEventListener('input', () => {
            updateHighlight(input.value);
            syncScroll(input);
        });

        // 3. 绑定滚动事件 (同步视图)
        input.addEventListener('scroll', () => syncScroll(input));

        // 4. 绑定快捷键 (Tab 缩进 & 运行)
        input.addEventListener('keydown', (e) => handleKeyDown(e, input));
    }

    function handleKeyDown(e, input) {
        // Ctrl + Enter 运行
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            runDevManim();
        }

        // Tab 键处理 (插入4个空格)
        if (e.key === 'Tab') {
            e.preventDefault();
            const start = input.selectionStart;
            const end = input.selectionEnd;

            // 插入空格
            const spaces = "    ";
            input.value = input.value.substring(0, start) + spaces + input.value.substring(end);

            // 移动光标
            input.selectionStart = input.selectionEnd = start + spaces.length;

            // 更新高亮 (必须手动触发，因为 js 修改 value 不会触发 input 事件)
            updateHighlight(input.value);
        }
    }
}

// 挂载全局辅助函数 (供 HTML 中的 oninput 调用，虽然我们已经用 addEventListener 绑定了，但为了兼容性保留)
window.syncScroll = syncScroll;
window.highlightCode = (el) => updateHighlight(el.value);


// --- 运行逻辑 ---
let isCooldown = false;

export async function runDevManim() {
    if (isCooldown) {
        alert("请等待冷却时间结束");
        return;
    }

    const codeInput = document.getElementById('dev-manim-input');
    if (!codeInput) return;
    const code = codeInput.value;

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
    const originalContent = btn.innerHTML; // 保存原始按钮 HTML (包含图标)

    btn.disabled = true;
    btn.style.opacity = '0.7';
    // 立即更新一次状态
    btn.innerHTML = `<i class="fa-regular fa-clock"></i> ${left}s`;

    const timer = setInterval(() => {
        left--;
        if (left <= 0) {
            clearInterval(timer);
            isCooldown = false;
            btn.disabled = false;
            btn.innerHTML = originalContent; // 恢复原始按钮
            btn.style.opacity = '1';
        } else {
            btn.innerHTML = `<i class="fa-regular fa-clock"></i> ${left}s`;
        }
    }, 1000);
}