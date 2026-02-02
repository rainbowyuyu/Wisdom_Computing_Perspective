// static/js/auth.js

import { toggleAuthModal } from './ui.js';
import * as Formulas from "./formulas.js";

let currentCaptchaId = '';

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
        if (newId) currentCaptchaId = newId;
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
        alert("请填写完整信息");
        return;
    }

    // 新增：隐私协议校验
    if (!agree) {
        alert("请阅读并同意服务协议与隐私政策");
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
                captcha_id: currentCaptchaId
            })
        });

        const data = await res.json();

        if(data.status === 'success') {
            toggleAuthModal(false);
            updateUserDisplay(data.username);

            if (Formulas && Formulas.loadMyFormulas) {
                Formulas.loadMyFormulas();
            }
            alert("登录成功！");
        }  else {
            alert(data.message || "登录失败");
            refreshCaptcha('login');
            document.getElementById('login-captcha').value = '';
        }
    } catch(e) {
        console.error(e);
        alert("网络错误");
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
        alert("请填写完整信息");
        return;
    }

    // 新增：密码一致性校验
    if (p !== pConfirm) {
        alert("两次输入的密码不一致，请重新输入");
        return;
    }

    // 新增：隐私协议校验
    if (!agree) {
        alert("请阅读并同意服务协议与隐私政策");
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
                captcha_id: currentCaptchaId
            })
        });

        const data = await res.json();

        if(data.status === 'success') {
            alert("注册成功，请登录");
            if(window.switchAuthMode) window.switchAuthMode('login');
            refreshCaptcha('login'); // 切换后刷新登录验证码
        } else {
            alert(data.message || "注册失败");
            refreshCaptcha('register');
            document.getElementById('reg-captcha').value = '';
        }
    } catch(e) {
        console.error(e);
        alert("网络错误");
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

// --- 登出 ---
// 需要挂载到 window，因为 HTML 中 onclick="logout()" 直接调用
window.logout = async function() {
    try {
        await fetch('/api/logout', { method: 'POST' });
        // 刷新页面以清除状态
        location.reload();
    } catch (e) {
        console.error("Logout failed", e);
        location.reload();
    }
}