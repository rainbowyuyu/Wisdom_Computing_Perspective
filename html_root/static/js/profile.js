// 用户资料与账户安全：头像、昵称、修改用户名、修改密码
import { showToast, toggleModal } from './ui.js';

let currentUserAvatarUrl = null;
let emailChangeTimer = null;

function showHint(id, text, isError) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text || '';
        el.style.color = isError ? 'var(--error-color, #ef4444)' : 'var(--text-secondary)';
    }
}

/** 打开设置时加载资料区：未登录显示引导，已登录拉取并填充 */
export async function loadProfile() {
    const guest = document.getElementById('settings-profile-guest');
    const content = document.getElementById('settings-profile-content');
    if (!guest || !content) return;
    try {
        const res = await fetch('/api/user/me', { credentials: 'include' });
        // 401 是未登录的正常状态，静默处理
        if (res.status === 401 || !res.ok) {
            guest.style.display = 'block';
            content.style.display = 'none';
            return;
        }
        const me = await res.json();
        if (me.status !== 'success' || !me.username) {
            guest.style.display = 'block';
            content.style.display = 'none';
            return;
        }
        guest.style.display = 'none';
        content.style.display = 'block';

        // Unverified accounts can read /user/me but cannot access profile APIs yet.
        const profileRes = me.email_verified === false ? null : await fetch('/api/user/profile', { credentials: 'include' }).then(r => r.json());
        const profile = (profileRes?.status === 'success' && profileRes.profile) ? profileRes.profile : { username: me.username, avatar_url: null, nickname: null, email: me.email, email_address: me.email_address, email_verified: me.email_verified };

        const img = document.getElementById('profile-avatar-img');
        const placeholder = document.getElementById('profile-avatar-placeholder');
        if (profile.avatar_url) {
            img.src = profile.avatar_url;
            img.style.display = '';
            if (placeholder) placeholder.style.display = 'none';
        } else {
            img.removeAttribute('src');
            img.style.display = 'none';
            if (placeholder) placeholder.style.display = 'flex';
        }

        const nicknameEl = document.getElementById('profile-nickname');
        if (nicknameEl) nicknameEl.value = profile.nickname || '';

        const usernameDisplay = document.getElementById('profile-username-display');
        if (usernameDisplay) usernameDisplay.textContent = profile.username || me.username;

        const emailDisplay = document.getElementById('profile-email-display');
        if (emailDisplay) emailDisplay.textContent = profile.email || me.email || '暂未绑定';
        const emailStatus = document.getElementById('profile-email-status');
        if (emailStatus) {
            const verified = Boolean(profile.email_verified ?? me.email_verified);
            emailStatus.textContent = verified ? '已验证' : ((profile.email || me.email) ? '待验证' : '未绑定');
            emailStatus.classList.toggle('is-verified', verified);
            emailStatus.classList.toggle('is-pending', !verified);
        }
        const verifyButton = document.getElementById('profile-email-verify-btn');
        if (verifyButton) {
            verifyButton.dataset.email = profile.email_address || me.email_address || '';
            verifyButton.hidden = Boolean(profile.email_verified ?? me.email_verified);
        }

        currentUserAvatarUrl = profile.avatar_url || null;
        updateHeaderAvatar(profile.avatar_url || null);
    } catch (e) {
        guest.style.display = 'block';
        content.style.display = 'none';
    }
}

function setEmailHint(text, isError = false) {
    const el = document.getElementById('change-email-hint');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('is-error', Boolean(isError));
    el.classList.toggle('is-success', Boolean(text) && !isError);
}

/** 打开更换邮箱弹窗，验证码只发送到新邮箱。 */
export async function openChangeEmailModal() {
    const guest = document.getElementById('change-email-guest');
    const form = document.getElementById('change-email-form');
    const email = document.getElementById('change-email-new');
    const code = document.getElementById('change-email-code');
    if (email) email.value = '';
    if (code) code.value = '';
    setEmailHint('');
    try {
        const res = await fetch('/api/user/me', { credentials: 'include' });
        const me = await res.json().catch(() => ({}));
        const signedIn = res.ok && me.status === 'success' && me.username;
        if (guest) guest.style.display = signedIn ? 'none' : 'block';
        if (form) form.style.display = signedIn ? 'block' : 'none';
    } catch (_) {
        if (guest) guest.style.display = 'block';
        if (form) form.style.display = 'none';
    }
    toggleModal('change-email-modal', true);
}

export function closeChangeEmailModal() {
    toggleModal('change-email-modal', false);
    if (emailChangeTimer) { clearInterval(emailChangeTimer); emailChangeTimer = null; }
    const button = document.getElementById('btn-change-email-code');
    if (button) { button.disabled = false; button.textContent = '获取验证码'; }
}

export async function sendChangeEmailCode() {
    const email = (document.getElementById('change-email-new')?.value || '').trim();
    const button = document.getElementById('btn-change-email-code');
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        setEmailHint('请输入有效的新邮箱地址。', true);
        return;
    }
    if (emailChangeTimer) return;
    if (button) { button.disabled = true; button.textContent = '发送中…'; }
    setEmailHint('正在发送验证码…');
    try {
        const res = await fetch('/api/email/send-code', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, purpose: 'change_email' })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.status !== 'success') {
            setEmailHint(data.message || '验证码发送失败，请稍后重试。', true);
            if (button) { button.disabled = false; button.textContent = '获取验证码'; }
            return;
        }
        let remain = Math.max(30, Number(data.retry_after) || 60);
        setEmailHint(data.message || '验证码已发送，请查收新邮箱。');
        if (button) button.textContent = `${remain}s 后重发`;
        emailChangeTimer = setInterval(() => {
            remain -= 1;
            if (!button) return;
            if (remain <= 0) {
                clearInterval(emailChangeTimer); emailChangeTimer = null;
                button.disabled = false; button.textContent = '重新获取';
            } else button.textContent = `${remain}s 后重发`;
        }, 1000);
    } catch (_) {
        setEmailHint('网络连接失败，请稍后重试。', true);
        if (button) { button.disabled = false; button.textContent = '获取验证码'; }
    }
}

export async function submitChangeEmailModal() {
    const email = (document.getElementById('change-email-new')?.value || '').trim();
    const code = (document.getElementById('change-email-code')?.value || '').trim();
    const button = document.getElementById('btn-change-email-submit');
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        setEmailHint('请先填写有效的新邮箱地址。', true); return;
    }
    if (!/^\d{6}$/.test(code)) {
        setEmailHint('请输入 6 位邮箱验证码。', true); return;
    }
    if (button) { button.disabled = true; button.textContent = '验证中…'; }
    setEmailHint('正在确认邮箱归属…');
    try {
        const res = await fetch('/api/email/change', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, code })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.status !== 'success') {
            setEmailHint(data.message || '邮箱更换失败，请检查验证码。', true);
            return;
        }
        if (typeof showToast === 'function') showToast('邮箱已更新并完成验证', 'success');
        closeChangeEmailModal();
        await loadProfile();
        window.dispatchEvent(new CustomEvent('auth-state-change'));
    } catch (_) {
        setEmailHint('网络连接失败，请稍后重试。', true);
    } finally {
        if (button) { button.disabled = false; button.innerHTML = '<i class="fa-solid fa-check"></i> 验证并更换'; }
    }
}

/** 保存昵称（防抖或失焦时可选）；头像由上传接口直接更新 */
export function saveNickname() {
    const nicknameEl = document.getElementById('profile-nickname');
    if (!nicknameEl) return;
    const nickname = nicknameEl.value.trim().slice(0, 64);
    fetch('/api/user/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: nickname || null }),
        credentials: 'include'
    }).then(r => r.json()).then(data => {
        if (data.status === 'success' && typeof showToast === 'function') showToast('昵称已保存', 'success');
    }).catch(() => {});
}

/** 打开修改用户名独立弹窗（与登录/注册同风格） */
export async function openChangeUsernameModal() {
    const guest = document.getElementById('change-username-guest');
    const form = document.getElementById('change-username-form');
    const curEl = document.getElementById('change-un-current');
    const newEl = document.getElementById('change-un-new');
    const pwdEl = document.getElementById('change-un-password');
    const hintEl = document.getElementById('change-un-hint');
    if (newEl) newEl.value = '';
    if (pwdEl) pwdEl.value = '';
    if (hintEl) hintEl.textContent = '';
    try {
        const res = await fetch('/api/user/me', { credentials: 'include' });
        // 401 是未登录的正常状态，静默处理
        if (res.status === 401 || !res.ok) {
            if (guest) guest.style.display = 'block';
            if (form) form.style.display = 'none';
            return;
        }
        const me = await res.json();
        if (me.status !== 'success' || !me.username) {
            if (guest) guest.style.display = 'block';
            if (form) form.style.display = 'none';
        } else {
            if (guest) guest.style.display = 'none';
            if (form) form.style.display = 'block';
            if (curEl) curEl.textContent = me.username;
        }
    } catch (_) {
        if (guest) guest.style.display = 'block';
        if (form) form.style.display = 'none';
    }
    toggleModal('change-username-modal', true);
}

export function closeChangeUsernameModal() {
    toggleModal('change-username-modal', false);
}

export async function submitChangeUsernameModal() {
    const newUsername = (document.getElementById('change-un-new')?.value || '').trim();
    const password = document.getElementById('change-un-password')?.value || '';
    const hintEl = document.getElementById('change-un-hint');
    const setHint = (text, err) => {
        if (hintEl) {
            hintEl.textContent = text;
            hintEl.style.color = err ? 'var(--error-color, #ef4444)' : 'var(--text-secondary)';
        }
    };
    if (!newUsername) {
        setHint('请输入新用户名', true);
        return;
    }
    if (!password) {
        setHint('请输入当前密码', true);
        return;
    }
    setHint('提交中…', false);
    try {
        const res = await fetch('/api/user/username', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_username: newUsername, password }),
            credentials: 'include'
        });
        const data = await res.json();
        if (data.status === 'success') {
            if (typeof showToast === 'function') showToast('用户名已修改', 'success');
            if (document.getElementById('profile-username-display')) document.getElementById('profile-username-display').textContent = data.username;
            if (document.getElementById('username-span')) document.getElementById('username-span').textContent = data.username;
            closeChangeUsernameModal();
            loadProfile();
        } else {
            setHint(data.message || '修改失败', true);
        }
    } catch (_) {
        setHint('网络错误', true);
    }
}

/** 打开修改密码独立弹窗（登录页或设置内均可调用） */
export async function openChangePasswordModal() {
    const guest = document.getElementById('change-password-guest');
    const form = document.getElementById('change-password-form');
    const cur = document.getElementById('change-pw-current');
    const pw1 = document.getElementById('change-pw-new');
    const pw2 = document.getElementById('change-pw-confirm');
    const hint = document.getElementById('change-pw-hint');
    if (hint) hint.textContent = '';
    if (cur) cur.value = '';
    if (pw1) pw1.value = '';
    if (pw2) pw2.value = '';
    try {
        const res = await fetch('/api/user/me', { credentials: 'include' });
        // 401 是未登录的正常状态，静默处理
        if (res.status === 401 || !res.ok) {
            if (guest) guest.style.display = 'block';
            if (form) form.style.display = 'none';
            return;
        }
        const me = await res.json();
        if (me.status !== 'success' || !me.username) {
            if (guest) guest.style.display = 'block';
            if (form) form.style.display = 'none';
        } else {
            if (guest) guest.style.display = 'none';
            if (form) form.style.display = 'block';
        }
    } catch (_) {
        if (guest) guest.style.display = 'block';
        if (form) form.style.display = 'none';
    }
    toggleModal('change-password-modal', true);
}

export function closeChangePasswordModal() {
    toggleModal('change-password-modal', false);
}

export async function submitChangePasswordModal() {
    const current = document.getElementById('change-pw-current')?.value || '';
    const newPw = document.getElementById('change-pw-new')?.value || '';
    const confirm = document.getElementById('change-pw-confirm')?.value || '';
    const hintEl = document.getElementById('change-pw-hint');
    const setHint = (text, err) => {
        if (hintEl) {
            hintEl.textContent = text;
            hintEl.style.color = err ? 'var(--error-color, #ef4444)' : 'var(--text-secondary)';
        }
    };
    if (!current) {
        setHint('请输入当前密码', true);
        return;
    }
    if (newPw.length < 6) {
        setHint('新密码至少 6 位', true);
        return;
    }
    if (newPw !== confirm) {
        setHint('两次输入的新密码不一致', true);
        return;
    }
    setHint('提交中…', false);
    try {
        const res = await fetch('/api/user/password', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: current, new_password: newPw }),
            credentials: 'include'
        });
        const data = await res.json();
        if (data.status === 'success') {
            if (typeof showToast === 'function') showToast('密码已修改', 'success');
            closeChangePasswordModal();
        } else {
            setHint(data.message || '修改失败', true);
        }
    } catch (_) {
        setHint('网络错误', true);
    }
}

/** 供头部/移动端更新用户头像；有 url 时显示 img 并隐藏图标 */
export function updateHeaderAvatar(avatarUrl) {
    currentUserAvatarUrl = avatarUrl || null;
    const img = document.getElementById('header-user-avatar');
    const icon = document.getElementById('header-user-icon');
    if (img && icon) {
        if (avatarUrl) {
            img.src = avatarUrl;
            img.style.display = '';
            icon.style.display = 'none';
        } else {
            img.removeAttribute('src');
            img.style.display = 'none';
            icon.style.display = '';
        }
    }
}

/** 供智能体消息使用：返回当前用户头像 URL，无则 null */
export function getCurrentUserAvatarUrl() {
    return currentUserAvatarUrl || null;
}

/** 头像上传 */
function initAvatarUpload() {
    const input = document.getElementById('profile-avatar-input');
    const btn = document.querySelector('.profile-avatar-btn');
    if (!input || !btn) return;
    btn.addEventListener('click', () => input.click());
    input.addEventListener('change', async () => {
        const file = input.files?.[0];
        if (!file) return;
        const form = new FormData();
        form.append('file', file);
        try {
            const res = await fetch('/api/user/avatar', { method: 'POST', body: form, credentials: 'include' });
            const data = await res.json();
            if (data.status === 'success' && data.avatar_url) {
                currentUserAvatarUrl = data.avatar_url;
                updateHeaderAvatar(data.avatar_url);
                const img = document.getElementById('profile-avatar-img');
                const placeholder = document.getElementById('profile-avatar-placeholder');
                img.src = data.avatar_url;
                img.style.display = '';
                if (placeholder) placeholder.style.display = 'none';
                if (typeof showToast === 'function') showToast('头像已更新', 'success');
            } else {
                if (typeof showToast === 'function') showToast(data.message || '上传失败', 'error');
            }
        } catch (e) {
            if (typeof showToast === 'function') showToast('上传失败', 'error');
        }
        input.value = '';
    });
}

export function initProfile() {
    initAvatarUpload();
    const nicknameEl = document.getElementById('profile-nickname');
    if (nicknameEl) nicknameEl.addEventListener('blur', saveNickname);
}
