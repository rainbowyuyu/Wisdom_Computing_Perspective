// static/js/auth.js

import { toggleAuthModal } from './ui.js';
import * as Formulas from "./formulas.js";
import {loadMyFormulas} from "./formulas.js";

let currentCaptchaId = '';

// 初始化：绑定事件，加载验证码
export function initAuth() {
    refreshCaptcha('login');
    refreshCaptcha('register');
}

// 获取验证码图片
export async function refreshCaptcha(type) {
    const imgId = type === 'login' ? 'captcha-img-login' : 'captcha-img-reg';
    const imgEl = document.getElementById(imgId);

    if (!imgEl) return;

    // 设置 loading 状态
    imgEl.style.opacity = '0.5';

    try {
        const res = await fetch('/api/captcha');
        // 获取 Header 中的 ID
        const newId = res.headers.get('X-Captcha-ID');
        if (newId) currentCaptchaId = newId;

        // 获取图片 Blob
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
            // 更新 UI
            document.querySelector('.login-btn').style.display = 'none';
            document.getElementById('user-display').style.display = 'inline-block';
            document.getElementById('username-span').innerText = data.username;
            Formulas.loadMyFormulas()
            alert("登录成功！");
        } else {
            alert(data.message || "登录失败");
            refreshCaptcha('login'); // 失败刷新验证码
        }
    } catch(e) {
        console.error(e);
        alert("网络错误");
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
            // 切换到登录 Tab (需要 ui.js 暴露 switchAuthMode)
            if(window.switchAuthMode) window.switchAuthMode('login');
        } else {
            alert(data.message || "注册失败");
            refreshCaptcha('register');
        }
    } catch(e) {
        console.error(e);
        alert("网络错误");
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}