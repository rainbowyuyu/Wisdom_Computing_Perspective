// static/js/auth.js

import { toggleAuthModal, showToast } from './ui.js';
import * as Formulas from "./formulas.js";
import * as Settings from "./settings.js";
import { escapeText } from './solution-visual.js';

// 登录、注册各自保存验证码 ID，避免并行刷新时互相覆盖导致第一次总报错
let currentCaptchaIdLogin = '';
let currentCaptchaIdRegister = '';
let currentCaptchaIdForgot = '';
const captchaRuns={};

// 用户名查重：最近一次检查结果（用于禁用注册按钮）
let lastUsernameAvailable = null;
let usernameCheckDebounceTimer = 0;

// --- 初始化：检查服务端 Session ---
export async function initAuth() {
    setupUsernameCheck();
    refreshCaptcha('login');
    refreshCaptcha('register');
    refreshCaptcha('forgot');

    // 修改：不再读取 localStorage，而是向后端询问 Session 状态
    try {
        const res = await fetch('/api/user/me', { credentials: 'include' });
        
        // 401 是未登录的正常状态，不需要显示错误
        if (res.status === 401) {
            // 用户未登录，静默处理
            return;
        }
        
        // 其他错误状态也静默处理
        if (!res.ok) {
            return;
        }
        
        const data = await res.json();

        if (data.status === 'success' && data.username) {
            if(data.email_verified===false){
                updateUserDisplay(data.username,null,false);
                openEmailVerification(data.email_address || data.email);
                return;
            }
            const profileRes = await fetch('/api/user/profile', { credentials: 'include' }).then(r => r.json()).catch(() => ({}));
            const avatarUrl = (profileRes.status === 'success' && profileRes.profile && profileRes.profile.avatar_url) ? profileRes.profile.avatar_url : null;
            updateUserDisplay(data.username, avatarUrl);
            if (window.Profile && typeof window.Profile.updateHeaderAvatar === 'function') {
                window.Profile.updateHeaderAvatar(avatarUrl);
            }
            // 预加载用户公式
            if (Formulas && Formulas.loadMyFormulas) {
                Formulas.loadMyFormulas();
            }
        }
    } catch (e) {
        // 网络错误或其他异常，静默处理（未登录是正常状态）
        // 不输出错误日志，避免控制台噪音
    }
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

// 简单密码强度打分：仅提示，不做限制
function calculatePasswordScore(pw) {
    if (!pw) return 0;
    let score = 0;
    if (pw.length >= 6) score += 1;
    if (pw.length >= 10) score += 1;
    if (/[A-Z]/.test(pw)) score += 1;
    if (/[0-9]/.test(pw)) score += 1;
    if (/[^A-Za-z0-9]/.test(pw)) score += 1;
    return score;
}

function updatePasswordStrength(pw) {
    const meter = document.getElementById('password-strength-meter');
    const bar = meter ? meter.querySelector('.password-strength-bar') : null;
    const textEl = document.getElementById('password-strength-text');
    if (!meter || !bar || !textEl) return;
    meter.classList.remove('password-strength--weak', 'password-strength--medium', 'password-strength--strong');
    if (!pw) {
        bar.style.width = '0%';
        textEl.textContent = '';
        return;
    }
    const score = calculatePasswordScore(pw);
    if (score <= 2) {
        meter.classList.add('password-strength--weak');
        textEl.textContent = '密码强度：较弱（建议包含大小写、数字和符号）';
    } else if (score <= 4) {
        meter.classList.add('password-strength--medium');
        textEl.textContent = '密码强度：中等（可以再增强一些复杂度）';
    } else {
        meter.classList.add('password-strength--strong');
        textEl.textContent = '密码强度：较强';
    }
}

// 注册表单密码强度监听
document.addEventListener('DOMContentLoaded', () => {
    const passInput = document.getElementById('reg-pass');
    if (passInput) {
        passInput.addEventListener('input', () => {
            updatePasswordStrength(passInput.value || '');
        });
    }
});

/** 切换回注册 Tab 时清空用户名提示（由 main 在 switchAuthMode('register') 时调用） */
export function clearUsernameHint() {
    setUsernameHint('', 'idle');
    lastUsernameAvailable = null;
    const submitBtn = document.getElementById('btn-reg-submit');
    if (submitBtn) submitBtn.disabled = false;
}

// ... (refreshCaptcha 保持不变) ...
export async function refreshCaptcha(type) {
    const imgId = type === 'login' ? 'captcha-img-login' : type === 'forgot' ? 'captcha-img-forgot' : 'captcha-img-reg';
    const imgEl = document.getElementById(imgId);
    if (!imgEl) return;
    const run=captchaRuns[type]=(captchaRuns[type]||0)+1;
    imgEl.style.opacity = '0.5';
    try {
        const res = await fetch('/api/captcha',{signal:AbortSignal.timeout(12000)});
        if(!res.ok)throw new Error('captcha');
        const blob = await res.blob();
        if(captchaRuns[type]!==run)return;
        const newId = res.headers.get('X-Captcha-ID');
        if (type === 'login') { if (newId) currentCaptchaIdLogin = newId; }
        else if (type === 'forgot') { if (newId) currentCaptchaIdForgot = newId; }
        else { if (newId) currentCaptchaIdRegister = newId; }
        if(imgEl.src.startsWith('blob:'))URL.revokeObjectURL(imgEl.src);
        const url = URL.createObjectURL(blob);
        imgEl.src = url;
    } catch (e) {
        console.error("Captcha error", e);
    } finally {
        if(captchaRuns[type]===run)imgEl.style.opacity = '1';
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
            signal: AbortSignal.timeout(45000),
            body: JSON.stringify({
                username: u,
                password: p,
                captcha: c,
                captcha_id: currentCaptchaIdLogin
            })
        });

        const data = await res.json();

        if(data.status === 'success') {
            if(data.email_verified===false){
                updateUserDisplay(data.username,null,false);
                openEmailVerification(data.email_address || data.email);
                return;
            }
            toggleAuthModal(false);
            let avatarUrl = null;
            try {
                const profileRes = await fetch('/api/user/profile', { credentials: 'include' }).then(r => r.json());
                if (profileRes.status === 'success' && profileRes.profile && profileRes.profile.avatar_url) {
                    avatarUrl = profileRes.profile.avatar_url;
                }
            } catch (_) {}
            updateUserDisplay(data.username, avatarUrl);
            if (window.Profile && typeof window.Profile.updateHeaderAvatar === 'function') {
                window.Profile.updateHeaderAvatar(avatarUrl);
            }

            if (Formulas && Formulas.loadMyFormulas) {
                Formulas.loadMyFormulas();
            }
            if (Settings && Settings.loadUserSettings) {
                Settings.loadUserSettings();
            }
            showToast("登录成功！", "success");
            window.dispatchEvent(new CustomEvent('auth-success'));
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
    const email = document.getElementById('reg-email').value.trim();
    const emailCode = document.getElementById('reg-email-code').value.trim();
    const c = document.getElementById('reg-captcha').value;
    const agree = document.getElementById('reg-agree').checked; // 获取复选框

    if(!u || !p || !pConfirm || !email || !emailCode) {
        showToast("请填写完整信息", "error");
        return;
    }

    // 新增：密码一致性校验
    if (p !== pConfirm || p.length<6) {
        showToast("密码至少 6 位，且两次输入需一致", "error");
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
            signal: AbortSignal.timeout(45000),
            body: JSON.stringify({
                username: u,
                password: p,
                email,
                email_code: emailCode,
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

/** 获取当前登录用户名，未登录返回 null（供智能体等模块判断） */
export function getCurrentUser() {
    const userDisplay = document.getElementById('user-display');
    const usernameSpan = document.getElementById('username-span');
    if (!userDisplay || userDisplay.style.display === 'none' || !usernameSpan) return null;
    const name = (usernameSpan.innerText || '').trim();
    return name || null;
}

// --- 辅助：更新 UI 显示用户名与头像 ---
function updateUserDisplay(username, avatarUrl, email_verified=true) {
    // 1. 隐藏导航栏登录按钮
    document.querySelectorAll('.login-btn').forEach(b => b.style.display = 'none');

    // 2. 显示桌面端用户信息（头像有则显示 img，无则显示图标）
    const userDisplay = document.getElementById('user-display');
    const usernameSpan = document.getElementById('username-span');
    const headerAvatar = document.getElementById('header-user-avatar');
    const headerIcon = document.getElementById('header-user-icon');
    if (userDisplay && usernameSpan) {
        userDisplay.style.display = 'inline-flex';
        usernameSpan.innerText = username;
        if (headerAvatar && headerIcon) {
            if (avatarUrl) {
                headerAvatar.src = avatarUrl;
                headerAvatar.style.display = '';
                headerIcon.style.display = 'none';
            } else {
                headerAvatar.removeAttribute('src');
                headerAvatar.style.display = 'none';
                headerIcon.style.display = '';
            }
        }
    }

    // 3. 更新移动端菜单（有头像则显示头像）；用户名与登出按钮使用 --text-main 保证在浅/深色遮罩下都清晰可见
    const mobileAuthSection = document.querySelector('.mobile-auth-section');
    if (mobileAuthSection) {
        const avatarHtml = avatarUrl
            ? `<img src="${avatarUrl.replace(/"/g, '&quot;')}" alt="" style="width:32px; height:32px; border-radius:50%; object-fit:cover; vertical-align:middle; margin-right:8px;">`
            : '<i class="fa-regular fa-user-circle" style="margin-right:8px;"></i>';
        mobileAuthSection.innerHTML = `
            <div class="mobile-menu-username" onclick="openSettings('profile'); toggleMobileMenu();">
                ${avatarHtml} <span class="mobile-menu-username-text">${escapeText(username)}</span>
            </div>
            <button class="mobile-menu-logout-btn" onclick="logout()">
                <i class="fa-solid fa-arrow-right-from-bracket"></i> 退出登录
            </button>
        `;
    }
    if (window.Profile && typeof window.Profile.updateHeaderAvatar === 'function') {
        window.Profile.updateHeaderAvatar(avatarUrl || null);
    }
    window.dispatchEvent(new CustomEvent('auth-state-change', { detail: { username, avatarUrl, email_verified } }));
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


export function openEmailVerification(emailAddress='') {
    const modal=document.getElementById('auth-modal');
    if(!modal)return;
    // Access errors can arrive together. Reopening must preserve input and cooldown.
    if(modal.dataset.requiresVerify==='true') {
        toggleAuthModal(true);
        return;
    }
    modal.dataset.requiresVerify='true';
    const input=document.getElementById('verify-email');
    const usableEmail = emailAddress && !String(emailAddress).includes('*') ? String(emailAddress) : '';
    const hasBoundEmail = Boolean(emailAddress);
    const title = document.getElementById('verify-email-title');
    const hint = document.getElementById('verify-email-hint');
    const codeButton = document.getElementById('btn-verify-code');
    if (title) title.textContent = hasBoundEmail ? '验证邮箱' : '绑定邮箱';
    if (hint) hint.textContent = hasBoundEmail
        ? '你的学习资料会保留。请填写当前绑定邮箱并获取验证码，验证后继续使用。'
        : '你的学习资料会保留。当前账户还未绑定邮箱，请填写常用邮箱并获取验证码，完成绑定后继续使用。';
    if (codeButton && !codeButton.disabled) codeButton.textContent = hasBoundEmail ? '获取验证码' : '发送绑定验证码';
    if(input) {
        input.value = usableEmail;
        input.placeholder = hasBoundEmail ? (usableEmail ? '当前绑定邮箱' : '当前绑定：'+emailAddress) : '请输入常用邮箱地址';
    }
    // This form must work before verification: never request gated profile APIs here.
    toggleAuthModal(true);
}

function authNotice(form, message, failed=false) {
    const status=document.querySelector('#'+form+' [role=status]');
    if(status){status.textContent=message;status.classList.toggle('auth-error',failed);}
    else showToast(message,failed?'error':'success');
}
async function accountPost(path,body){
    const res=await fetch(path,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body),signal:AbortSignal.timeout(45000)});
    const data=await res.json();
    if(!res.ok || data.status!=='success')throw new Error(data.message||'请检查填写内容后重试。');
    return data;
}
function cooldown(button){
    const until=Date.now()+60000, label=button.textContent;
    button.dataset.cooldown='true';button.disabled=true;
    const tick=()=>{
        const seconds=Math.max(0,Math.ceil((until-Date.now())/1000));
        button.textContent=seconds+' 秒后重发';
        if(!seconds){clearInterval(timer);delete button.dataset.cooldown;button.disabled=false;button.textContent=label;}
    };
    const timer=setInterval(tick,500);tick();
}
async function sendCode(purpose,prefix,form,buttonId,captchaId){
    const button=document.getElementById(buttonId);
    if(button.disabled)return;
    const email=document.getElementById(prefix+'-email').value.trim();
    const captcha=document.getElementById(prefix+'-captcha')?.value.trim();
    if(!email || (purpose!=='verify'&&!captcha)){authNotice(form,'请先填写邮箱'+(purpose==='verify'?'地址。':'和图片验证码。'),true);return;}
    const label=button.textContent;button.disabled=true;button.textContent='发送中…';
    try{
        const data=await accountPost(purpose==='reset'?'/api/password/forgot/request':'/api/email/send-code',
            {email,purpose,captcha,captcha_id:captchaId});
        authNotice(form,data.message+' 邮件可能在垃圾箱中。');
        button.textContent=label;cooldown(button);
    }catch(e){authNotice(form,e.name==='TimeoutError'?'发送较慢，请稍后查收邮件或重试。':e.message,true);}
    finally{
        if(!button.dataset.cooldown){button.disabled=false;button.textContent=label;}
        if(purpose!=='verify'){
            await refreshCaptcha(purpose==='reset'?'forgot':'register');
            document.getElementById(prefix+'-captcha').value='';
        }
    }
}
export function sendRegisterEmailCode(){return sendCode('register','reg','register-form','btn-reg-email-code',currentCaptchaIdRegister);}
export function sendForgotCode(){return sendCode('reset','forgot','forgot-form','btn-forgot-code',currentCaptchaIdForgot);}
export function sendVerifyEmailCode(){return sendCode('verify','verify','email-verify-form','btn-verify-code','');}

export async function resetForgotPassword(){
    const button=document.getElementById('btn-reset-password');if(button.disabled)return;
    const email=document.getElementById('forgot-email').value.trim(), code=document.getElementById('forgot-email-code').value.trim();
    const password=document.getElementById('forgot-new-pass').value, confirm=document.getElementById('forgot-new-pass-confirm').value;
    if(!email || !code || password.length<6 || password!==confirm){authNotice('forgot-form','请填写邮箱验证码，确认两次密码一致且至少 6 位。',true);return;}
    button.disabled=true;button.textContent='正在重置…';
    try{
        await accountPost('/api/password/forgot/reset',{email,code,new_password:password});
        document.getElementById('forgot-form').reset();
        window.switchAuthMode?.('login');showToast('密码已重置，请使用新密码登录。','success');
    }catch(e){authNotice('forgot-form',e.name==='TimeoutError'?'请求超时，请稍后重试。':e.message,true);}
    finally{button.disabled=false;button.textContent='重置密码';}
}
export async function verifyCurrentEmail(){
    const button=document.getElementById('btn-verify-submit');if(button.disabled)return;
    const email=document.getElementById('verify-email').value.trim(),code=document.getElementById('verify-email-code').value.trim();
    if(!email||!code){authNotice('email-verify-form','请输入邮箱和验证码。',true);return;}
    button.disabled=true;button.textContent='正在验证…';
    try{await accountPost('/api/email/verify',{email,code});location.reload();}
    catch(e){authNotice('email-verify-form',e.name==='TimeoutError'?'请求超时，请稍后重试。':e.message,true);}
    finally{button.disabled=false;button.textContent='验证并继续';}
}
