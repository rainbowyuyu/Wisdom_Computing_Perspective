// MathLive 界面中文化：设置 locale 并注入常用中文文案

function applyMathLiveLocale() {
    customElements.whenDefined('math-field').then(() => {
        const MFE = window.MathfieldElement || (document.querySelector('math-field')?.constructor);
        if (!MFE) return;
        try {
            if (MFE.locale !== undefined) MFE.locale = 'zh';
        } catch (_) {}
        if (MFE.strings && typeof MFE.strings === 'object') {
            const zh = (MFE.strings['zh'] = MFE.strings['zh'] || {});
            const tr = {
                'keyboard.tooltip.fraction': '分数',
                'keyboard.tooltip.sqrt': '根号',
                'keyboard.tooltip.superscript': '上标',
                'keyboard.tooltip.subscript': '下标',
                'keyboard.tooltip.undo': '撤销',
                'keyboard.tooltip.redo': '重做',
                'keyboard.tooltip.cut': '剪切',
                'keyboard.tooltip.copy': '复制',
                'keyboard.tooltip.paste': '粘贴',
                'keyboard.tooltip.select-all': '全选',
                'menu.keyboard': '虚拟键盘',
                'menu.edit': '编辑',
                'menu.cut': '剪切',
                'menu.copy': '复制',
                'menu.paste': '粘贴',
                'menu.select-all': '全选',
                'menu.undo': '撤销',
                'menu.redo': '重做',
            };
            Object.assign(zh, tr);
        }
    });
}

export function initMathLiveLocale() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyMathLiveLocale);
    } else {
        applyMathLiveLocale();
    }
}
