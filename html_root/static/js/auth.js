// static/js/auth.js

import { toggleAuthModal } from './ui.js';
import * as Formulas from "./formulas.js";

let currentCaptchaId = '';

// ... (initAuth, refreshCaptcha 保持不变) ...

export function initAuth() {
    refreshCaptcha('login');
    refreshCaptcha('register');
}

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

// 登录处理
export async function handleLogin() {
    const u = document.getElementById('login-user').value;
    const p = document.getElementById('login-pass').value;
    const c = document.getElementById('login-captcha').value;

    if(!u || !p || !c) {
        alert("请填写完整信息");
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

            // --- 核心修复 & 移动端适配 ---

            // 1. 更新所有登录按钮（桌面+移动）为隐藏
            document.querySelectorAll('.login-btn').forEach(b => b.style.display = 'none');

            // 2. 更新桌面端显示
            const userDisplay = document.getElementById('user-display');
            const usernameSpan = document.getElementById('username-span');
            if (userDisplay && usernameSpan) {
                userDisplay.style.display = 'inline-block';
                usernameSpan.innerText = data.username;
            }

            // 3. 更新移动端菜单显示 (如果存在)
            const mobileAuthSection = document.querySelector('.mobile-auth-section');
            if (mobileAuthSection) {
                mobileAuthSection.innerHTML = `
                    <div style="font-weight:bold; color:var(--primary-color); margin-bottom:10px; font-size:1.1rem;">
                        <i class="fa-regular fa-user-circle"></i> ${data.username}
                    </div>
                    <button onclick="logout()" style="width:100%; padding:10px; background:white; border:1px solid #eee; border-radius:8px; color:#666;">
                        <i class="fa-solid fa-arrow-right-from-bracket"></i> 退出登录
                    </button>
                `;
            }

            // 4. 加载用户数据
            if (Formulas && Formulas.loadMyFormulas) {
                Formulas.loadMyFormulas();
            }

            alert("登录成功！");
        }  else {
            alert(data.message || "登录失败");
            // 关键：失败后必须刷新验证码，因为后端可能已经销毁了旧的，或者为了安全需要更换
            refreshCaptcha('login');
            // 清空输入框
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

// 注册处理
export async function handleRegister() {
    const u = document.getElementById('reg-user').value;
    const p = document.getElementById('reg-pass').value;
    const c = document.getElementById('reg-captcha').value;

    if(!u || !p || !c) {
        alert("请填写完整信息");
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