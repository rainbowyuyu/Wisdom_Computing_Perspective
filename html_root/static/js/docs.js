// static/js/docs.js

import { toggleModal } from './ui.js';

// 打开文档模态框并加载内容
export async function openDoc(fileName, title) {
    const modal = document.getElementById('docs-modal');
    const titleEl = document.getElementById('docs-title');
    const contentEl = document.getElementById('docs-content');

    if (!modal || !contentEl) return;

    // 1. 设置标题和 Loading 状态
    if (titleEl) titleEl.innerText = title;

    // 重置内容区域并显示 Loading
    contentEl.scrollTop = 0; // 滚回顶部
    contentEl.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 300px; color: var(--text-secondary);">
            <i class="fa-solid fa-spinner fa-spin" style="font-size: 2rem; margin-bottom: 1rem;"></i>
            <p>正在加载文档...</p>
        </div>
    `;

    // 2. 显示模态框
    toggleModal('docs-modal', true);

    try {
        // 3. 请求 Markdown 文件
        // 假设 main.py 中 app.mount("/docs", ...) 已配置
        const res = await fetch(`docs/${fileName}?t=${new Date().getTime()}`);

        if (!res.ok) throw new Error(`File not found: ${fileName}`);

        const markdownText = await res.text();

        // 4. 转换为 HTML (依赖 marked.js)
        if (window.marked) {
            // 配置 marked 选项以支持更丰富的 Markdown 语法
            // gfm: GitHub Flavored Markdown (表格、删除线等)
            // breaks: 允许回车换行
            window.marked.use({
                gfm: true,
                breaks: true
            });

            const html = window.marked.parse(markdownText);
            contentEl.innerHTML = html;

            // 5. 代码高亮 (依赖 highlight.js)
            // 只有当内容中有代码块时才执行
            if (window.hljs) {
                contentEl.querySelectorAll('pre code').forEach((block) => {
                    window.hljs.highlightElement(block);
                });
            }

            // 6. 额外处理：让链接在新标签页打开
            contentEl.querySelectorAll('a').forEach(link => {
                link.setAttribute('target', '_blank');
                link.setAttribute('rel', 'noopener noreferrer');
            });

        } else {
            // 如果 marked 未加载，降级显示纯文本，防止空白
            console.warn('Marked.js not loaded');
            contentEl.style.whiteSpace = 'pre-wrap';
            contentEl.innerText = markdownText;
        }

    } catch (e) {
        console.error(e);
        contentEl.innerHTML = `
            <div style="text-align: center; color: #ef4444; padding: 4rem 2rem;">
                <i class="fa-solid fa-triangle-exclamation" style="font-size: 2.5rem; margin-bottom: 1rem; opacity: 0.8;"></i>
                <p style="font-size: 1.1rem; font-weight: 600;">文档加载失败</p>
                <p style="font-size: 0.9rem; margin-top: 0.5rem;">无法获取文件 "${fileName}"</p>
                <button class="action-btn secondary" onclick="closeDocsModal()" style="margin-top: 1.5rem;">关闭</button>
            </div>
        `;
    }
}

export function closeDocsModal() {
    toggleModal('docs-modal', false);
}