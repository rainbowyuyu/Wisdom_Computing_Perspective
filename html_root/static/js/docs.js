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

    // 重置内容区域并显示 Loading (使用 CSS 类)
    contentEl.scrollTop = 0;
    contentEl.innerHTML = `
        <div class="docs-loading">
            <i class="fa-solid fa-spinner fa-spin"></i>
            <p>正在加载文档...</p>
        </div>
    `;

    // 2. 显示模态框
    toggleModal('docs-modal', true);

    try {
        // 3. 请求 Markdown 文件
        const res = await fetch(`docs/${fileName}?t=${new Date().getTime()}`);

        if (!res.ok) throw new Error(`File not found: ${fileName}`);

        const markdownText = await res.text();

        // 4. 转换为 HTML
        if (window.marked) {
            window.marked.use({
                gfm: true,
                breaks: true
            });

            const html = window.marked.parse(markdownText);
            contentEl.innerHTML = html;

            // 5. 代码高亮
            if (window.hljs) {
                contentEl.querySelectorAll('pre code').forEach((block) => {
                    window.hljs.highlightElement(block);
                });
            }

            // 6. 链接在新标签页打开
            contentEl.querySelectorAll('a').forEach(link => {
                link.setAttribute('target', '_blank');
                link.setAttribute('rel', 'noopener noreferrer');
            });

        } else {
            console.warn('Marked.js not loaded');
            contentEl.style.whiteSpace = 'pre-wrap';
            contentEl.innerText = markdownText;
        }

    } catch (e) {
        console.error(e);
        // 使用 CSS 类显示错误信息
        contentEl.innerHTML = `
            <div class="docs-error">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p class="error-title">文档加载失败</p>
                <p>无法获取文件 "${fileName}"</p>
                <button class="action-btn secondary" onclick="closeDocsModal()" style="margin-top: 1.5rem;">关闭</button>
            </div>
        `;
    }
}

export function closeDocsModal() {
    toggleModal('docs-modal', false);
}