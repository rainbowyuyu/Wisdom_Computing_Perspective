import * as Settings from './settings.js';
import * as Profile from './profile.js';
import { toggleTheme } from './theme.js';
import { toggleModal, showToast } from './ui.js';

// Reuse the original dialog markup and storage, rather than maintaining a Vue copy.
let loading;
async function ensureSettings() {
    if (document.getElementById('settings-modal')) return;
    if (loading) return loading;
    loading = (async () => {
        const response = await fetch('/static/index.html', { signal: AbortSignal.timeout(10000) });
        if (!response.ok) throw new Error('设置界面加载失败，请稍后重试');
        const source = new DOMParser().parseFromString(await response.text(), 'text/html');
        const ids = ['settings-modal', 'change-username-modal', 'change-password-modal', 'change-email-modal'];
        const modals = ids.map(id => source.getElementById(id));
        if (modals.some(el => !el)) throw new Error('设置界面不完整，请刷新后重试');
        for (const modal of modals) {
            if (document.getElementById(modal.id)) continue;
            modal.setAttribute('role', 'dialog');modal.setAttribute('aria-modal', 'true');
            document.body.append(document.importNode(modal, true));
        }
        Object.assign(window, { Settings, Profile, toggleTheme, resetDefaults: Settings.resetDefaults,
            closeSettings: () => toggleModal('settings-modal', false) });
        const root = document.getElementById('settings-modal');
        root.addEventListener('keydown', event => {
            if (event.key === 'Escape') { event.stopPropagation();window.closeSettings(); }
        });
        root.addEventListener('click', event => { if (event.target === root) window.closeSettings(); });
        Settings.initSettings();Profile.initProfile();
        window.addEventListener('auth-state-change', () => { Settings.loadUserSettings();Profile.loadProfile(); });
        await Settings.loadUserSettings();
    })().finally(() => { loading = null; });
    return loading;
}

export async function openSettings(section) {
    try {
        await ensureSettings();Settings.openSettings(section);
        return true;
    } catch (error) {
        showToast(error.name === 'TimeoutError' ? '设置界面加载超时，请重试' : error.message, 'error');
        return false;
    }
}
