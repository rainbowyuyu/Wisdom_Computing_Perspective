// MathLive 菜单优化：Select all 上移便于改颜色前全选；Cut/Copy/Paste 排在一起

const CLIPBOARD_IDS = ['cut', 'copy', 'paste'];
const SELECT_ALL_IDS = ['select-all', 'selectAll'];

function reorderMenuItems(menuItems) {
    if (!Array.isArray(menuItems) || menuItems.length === 0) return menuItems;
    const copy = [...menuItems];
    const byId = (id) => copy.find((item) => item.id === id);
    const clip = CLIPBOARD_IDS.map((id) => byId(id)).filter(Boolean);
    const selectAll = SELECT_ALL_IDS.map((id) => byId(id)).find(Boolean);
    const selectAllId = selectAll ? selectAll.id : null;
    const rest = copy.filter(
        (item) =>
            item.id !== selectAllId &&
            !CLIPBOARD_IDS.includes(item.id)
    );
    const divider = { type: 'divider' };
    const out = [];
    if (clip.length) out.push(...clip, divider);
    if (selectAll) out.push(selectAll, divider);
    out.push(...rest);
    return out;
}

function applyMenuToMathField(mf) {
    try {
        const current = mf.menuItems;
        if (!current || current.length === 0) return;
        const reordered = reorderMenuItems(current);
        if (reordered.length) mf.menuItems = reordered;
    } catch (e) {
        console.warn('MathLive menu reorder failed', e);
    }
}

function initMathLiveMenuForElement(mf) {
    if (!mf || !mf.menuItems) return;
    applyMenuToMathField(mf);
}

function initMathLiveMenu() {
    customElements.whenDefined('math-field').then(() => {
        document.querySelectorAll('math-field').forEach(initMathLiveMenuForElement);
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((m) => {
                m.addedNodes.forEach((node) => {
                    if (node.nodeType === 1) {
                        if (node.tagName === 'MATH-FIELD') initMathLiveMenuForElement(node);
                        node.querySelectorAll?.('math-field').forEach(initMathLiveMenuForElement);
                    }
                });
            });
        });
        observer.observe(document.body, { childList: true, subtree: true });
    });
}

export function initMathLiveMenuOnce() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMathLiveMenu);
    } else {
        initMathLiveMenu();
    }
}
