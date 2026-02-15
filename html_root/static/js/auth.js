// static/js/auth.js

import { toggleAuthModal, showToast } from './ui.js';
import * as Formulas from "./formulas.js";

// 登录、注册各自保存验证码 ID，避免并行刷新时互相覆盖导致第一次总报错
let currentCaptchaIdLogin = '';
let currentCaptchaIdRegister = '';

// 用户名查重：最近一次检查结果（用于禁用注册按钮）
let lastUsernameAvailable = null;
let usernameCheckDebounceTimer = 0;

// --- 初始化：检查服务端 Session ---
export async function initAuth() {
    refreshCaptcha('login');
    refreshCaptcha('register');

    // 修改：不再读取 localStorage，而是向后端询问 Session 状态
    try {
        const res = await fetch('/api/user/me');
        const data = await res.json();

        if (data.status === 'success' && data.username) {
            updateUserDisplay(data.username);
            // 预加载用户公式
            if (Formulas && Formulas.loadMyFormulas) {
                Formulas.loadMyFormulas();
            }
        }
    } catch (e) {
        console.log("Not logged in or session expired");
    }
    setupUsernameCheck();
}

/** 请求后端检查用户名是否可用 */
export async function checkUsername(username) {
    const raw = (username || '').trim();
    if (!raw) return { available: false };
    const res = await fetch(`/api/user/check-username?username=${encodeURIComponent(raw)}`);
    const data = await res.json();
    return { available: data.available === true };
}

function setUsernameHint(text, state) {
    const hint = document.getElementById('reg-username-hint');
    if (!hint) return;
    hint.textContent = text;
    hint.className = 'username-hint username-hint--' + (state || 'idle');
}

function setupUsernameCheck() {
    const input = document.getElementById('reg-user');
    const hint = document.getElementById('reg-username-hint');
    const submitBtn = document.getElementById('btn-reg-submit');
    if (!input || !hint) return;

    function doCheck() {
        const raw = input.value.trim();
        if (!raw) {
            lastUsernameAvailable = null;
            setUsernameHint('', 'idle');
            updateRegisterButtonState();
            return;
        }
        setUsernameHint('正在检查…', 'loading');
        lastUsernameAvailable = null;
        updateRegisterButtonState();
        checkUsername(raw).then(({ available }) => {
            lastUsernameAvailable = available;
            if (available) setUsernameHint('用户名可用', 'ok');
            else setUsernameHint('用户名已被占用', 'bad');
            updateRegisterButtonState();
        }).catch(() => {
            setUsernameHint('检查失败，请稍后再试', 'bad');
            lastUsernameAvailable = false;
            updateRegisterButtonState();
        });
    }

    function updateRegisterButtonState() {
        if (!submitBtn) return;
        if (lastUsernameAvailable === false) submitBtn.disabled = true;
        else submitBtn.disabled = false;
    }

    input.addEventListener('blur', () => doCheck());
    input.addEventListener('input', () => {
        const raw = input.value.trim();
        if (!raw) {
            setUsernameHint('', 'idle');
            lastUsernameAvailable = null;
            updateRegisterButtonState();
            if (usernameCheckDebounceTimer) clearTimeout(usernameCheckDebounceTimer);
            usernameCheckDebounceTimer = 0;
            return;
        }
        if (usernameCheckDebounceTimer) clearTimeout(usernameCheckDebounceTimer);
        usernameCheckDebounceTimer = setTimeout(doCheck, 400);
    });
}

/** 切换回注册 Tab 时清空用户名提示（由 main 在 switchAuthMode('register') 时调用） */
export function clearUsernameHint() {
    setUsernameHint('', 'idle');
    lastUsernameAvailable = null;
    const submitBtn = document.getElementById('btn-reg-submit');
    if (submitBtn) submitBtn.disabled = false;
}

// ... (refreshCaptcha 保持不变) ...
export async function refreshCaptcha(type) {
    const imgId = type === 'login' ? 'captcha-img-login' : 'captcha-img-reg';
    const imgEl = document.getElementById(imgId);
    if (!imgEl) return;
    imgEl.style.opacity = '0.5';
    try {
        const res = await fetch('/api/captcha');
        const newId = res.headers.get('X-Captcha-ID');
        if (type === 'login') {
            if (newId) currentCaptchaIdLogin = newId;
        } else {
            if (newId) currentCaptchaIdRegister = newId;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        imgEl.src = url;
    } catch (e) {
        console.error("Captcha error", e);
    } finally {
        imgEl.style.opacity = '1';
    }
}

// --- 登录处理 ---
export async function handleLogin() {
    const u = document.getElementById('login-user').value;
    const p = document.getElementById('login-pass').value;
    const c = document.getElementById('login-captcha').value;
    const agree = document.getElementById('login-agree').checked; // 获取复选框状态

    if(!u || !p || !c) {
        showToast("请填写完整信息", "error");
        return;
    }

    // 新增：隐私协议校验
    if (!agree) {
        showToast("请阅读并同意服务协议与隐私政策", "error");
        return;
    }

    const btn = document.getElementById('btn-login-submit');
    const originalText = btn.innerText;
    btn.innerText = "登录中...";
    btn.disabled = true;

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                username: u,
                password: p,
                captcha: c,
                captcha_id: currentCaptchaIdLogin
            })
        });

        const data = await res.json();

        if(data.status === 'success') {
            toggleAuthModal(false);
            updateUserDisplay(data.username);

            if (Formulas && Formulas.loadMyFormulas) {
                Formulas.loadMyFormulas();
            }
            showToast("登录成功！", "success");
        }  else {
            showToast(data.message || "登录失败", "error");
            refreshCaptcha('login');
            document.getElementById('login-captcha').value = '';
        }
    } catch(e) {
        console.error(e);
        showToast("网络错误", "error");
        refreshCaptcha('login');
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

// --- 注册处理 ---
export async function handleRegister() {
    const u = document.getElementById('reg-user').value;
    const p = document.getElementById('reg-pass').value;
    const pConfirm = document.getElementById('reg-pass-confirm').value; // 获取确认密码
    const c = document.getElementById('reg-captcha').value;
    const agree = document.getElementById('reg-agree').checked; // 获取复选框

    if(!u || !p || !pConfirm || !c) {
        showToast("请填写完整信息", "error");
        return;
    }

    // 新增：密码一致性校验
    if (p !== pConfirm) {
        showToast("两次输入的密码不一致，请重新输入", "error");
        return;
    }

    // 新增：隐私协议校验
    if (!agree) {
        showToast("请阅读并同意服务协议与隐私政策", "error");
        return;
    }

    const btn = document.getElementById('btn-reg-submit');
    const originalText = btn.innerText;
    btn.innerText = "注册中...";
    btn.disabled = true;

    try {
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                username: u,
                password: p,
                captcha: c,
                captcha_id: currentCaptchaIdRegister
            })
        });

        const data = await res.json();

        if(data.status === 'success') {
            showToast("注册成功，请登录", "success");
            if(window.switchAuthMode) window.switchAuthMode('login');
            refreshCaptcha('login'); // 切换后刷新登录验证码
        } else {
            showToast(data.message || "注册失败", "error");
            refreshCaptcha('register');
            document.getElementById('reg-captcha').value = '';
        }
    } catch(e) {
        console.error(e);
        showToast("网络错误", "error");
        refreshCaptcha('register');
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

// --- 辅助：更新 UI 显示用户名 ---
function updateUserDisplay(username) {
    // 1. 隐藏导航栏登录按钮
    document.querySelectorAll('.login-btn').forEach(b => b.style.display = 'none');

    // 2. 显示桌面端用户信息
    const userDisplay = document.getElementById('user-display');
    const usernameSpan = document.getElementById('username-span');
    if (userDisplay && usernameSpan) {
        userDisplay.style.display = 'inline-block';
        usernameSpan.innerText = username;
    }

    // 3. 更新移动端菜单
    const mobileAuthSection = document.querySelector('.mobile-auth-section');
    if (mobileAuthSection) {
        mobileAuthSection.innerHTML = `
            <div style="font-weight:bold; color:var(--text-inverse); margin-bottom:10px; font-size:1.1rem; text-align:center;">
                <i class="fa-regular fa-user-circle"></i> ${username}
            </div>
            <button onclick="logout()" style="width:100%; padding:10px; background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); border-radius:8px; color:var(--text-inverse);">
                <i class="fa-solid fa-arrow-right-from-bracket"></i> 退出登录
            </button>
        `;
    }
}

// --- 登出：调用接口清除服务端 session 与 cookie，再刷新 ---
export async function logout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
    } catch (e) {
        console.error("Logout failed", e);
    }
    location.reload();
}