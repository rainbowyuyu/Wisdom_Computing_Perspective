import {escapeText as esc} from './solution-visual.js';
import '/static/js/task-progress.js';

let current=null,refreshing=null,epoch=0,refreshTimer,accessError='';
export const AUTHOR_URL='https://github.com/rainbowyuyu';
const names={guest:'游客试用',member:'普通用户',vip:'VIP 用户',admin:'管理员'};
async function request(path,options={}){
    const response=await fetch(path,{credentials:'include',signal:AbortSignal.timeout(12000),...options});const data=await response.json();
    if(!response.ok)throw new Error(data.message||data.detail||'请求未完成，请稍后重试。');return data;
}
function mount(){
    const hero=document.querySelector('#home .hero');
    if(!hero||hero.querySelector('.account-access-card'))return;
    const card=document.createElement('section');card.className='account-access-card';card.setAttribute('aria-label','账户类型与额度');
    hero.append(card);render();
}
function accessSummary(){
    if(!current)return null;
    const guest=current.role==='guest';
    const quota=current.quotas?.[guest?'calculate':'all'];
    const unlimited=['vip','admin'].includes(current.role)&&quota?.limit===null;
    const known=unlimited||(Number.isFinite(quota?.limit)&&Number.isFinite(quota?.remaining));
    const short=!known?'额度待更新':unlimited?'额度不限':`${guest?'试用剩余':'今日剩余'} ${quota.remaining} / ${quota.limit}`;
    const description=!known?'暂时无法读取额度，请刷新重试。':guest?
        `计算试用剩余 ${quota.remaining} / ${quota.limit} 次 · 识图 ${current.quotas.recognize?.remaining??'—'} 次 · 助手 ${current.quotas.assistant?.remaining??'—'} 次`:
        unlimited?'不限个人每日使用次数 · 高峰期自动排队':`今日剩余 ${quota.remaining} / ${quota.limit} 次 · 每日 00:00（北京时间）恢复`;
    return {guest,quota,unlimited,known,short,description};
}
function render(){
    const summary=accessSummary();
    document.querySelectorAll('[data-account-header]').forEach(host=>{
        if(!current){
            host.setAttribute('aria-label',accessError?'账户权益读取失败':'正在读取账户权益');
            host.innerHTML=accessError?'<button type="button" class="access-retry" data-access-retry>额度读取失败 · 重试</button>':'<span class="access-loading">正在读取权限…</span>';
        }else{
            const role=current.can_manage?'主账号 · 管理员':names[current.role]||'账户';
            host.innerHTML=`<span class="access-mobile-name">${esc(current.username||'游客')}</span><button type="button" class="header-access-trigger" data-access-details aria-haspopup="dialog" aria-label="查看我的权限与申请方式"><span class="account-type ${esc(current.role)}">${esc(role)}</span><span class="header-quota ${summary.known&&!summary.unlimited&&summary.quota.remaining===0?'exhausted':''}" title="${esc(summary.description)}">${esc(summary.short)}</span><i class="fa-solid fa-chevron-down" aria-hidden="true"></i></button>${current.can_manage===true?'<button type="button" class="header-admin-link" data-access-admin title="进入用户管理页面"><i class="fa-solid fa-sliders" aria-hidden="true"></i> 管理中心</button>':''}`;
            host.setAttribute('aria-label',`${current.username||'游客'} · ${role} · ${summary.description}`);
        }
        if(current?.username && current.email_verified===false) {
            host.innerHTML='<button type="button" class="header-access-trigger" data-verify-email>'+(current.email_address?'邮箱待验证 · 点击完成验证':'尚未绑定邮箱 · 点击绑定')+'</button>';
        }
        bindAccessActions(host);
    });
    document.querySelectorAll('.account-access-card').forEach(card=>{
        if(!current){card.innerHTML=accessError?'<p>账户信息暂时无法读取</p><button type="button" data-access-retry>重新加载</button>':'<p>正在读取账户权益…</p>';bindAccessActions(card);return;}
        card.innerHTML=`<div class="access-card-main"><div class="access-card-identity"><span class="access-card-icon"><i class="fa-solid ${current.can_manage?'fa-shield-halved':summary.unlimited?'fa-crown':'fa-user-graduate'}" aria-hidden="true"></i></span><div><span class="account-type ${esc(current.role)}">${esc(current.can_manage?'主账号 · 管理员':names[current.role]||'账户')}</span><strong>${esc(current.username||'从一次尝试，开始理解数学')}</strong></div></div><p>${esc(summary.description)}</p><span class="access-card-caption">${current.can_manage?'用户权限、题目请求与管理记录，在一处查看。':summary.guest?'登录后可保存题解、整理错题与创建课包。':summary.unlimited?'解题、识图、动画与学习资料整理，随时继续。':'计算、识图、助手与动画共享每日额度；VIP 免个人每日次数限制。'}</span></div><div class="account-access-actions">${current.can_manage?'<button class="access-primary" type="button" data-access-admin><i class="fa-solid fa-sliders" aria-hidden="true"></i> 进入管理中心</button>':summary.guest?'<button class="access-primary" type="button" data-access-login>登录，保存我的学习</button>':`<a class="vip-contact access-primary" href="${AUTHOR_URL}" target="_blank" rel="noopener noreferrer"><i class="fa-brands fa-github" aria-hidden="true"></i> ${summary.unlimited?'联系作者':'联系作者 · 申请 VIP'} ↗</a>`}<button type="button" data-access-details aria-haspopup="dialog">${current.can_manage?'查看主账号权益':summary.guest?'查看试用与申请说明':'我的权益与申请说明'} <span aria-hidden="true">→</span></button>${summary.guest||current.can_manage?`<a class="vip-contact access-secondary" href="${AUTHOR_URL}" target="_blank" rel="noopener noreferrer">GitHub · 联系作者 ↗</a>`:''}</div>`;
        if(current?.username && current.email_verified===false) {
            const label=current.email_address?'邮箱待验证':'尚未绑定邮箱';
            const action=current.email_address?'验证邮箱':'绑定邮箱';
            card.innerHTML=`<div class="access-card-main"><strong>${esc(current.username)} · ${label}</strong><p>完成邮箱${current.email_address?'验证':'绑定'}后即可继续解题、保存笔记和使用其他功能。已有学习资料会保留。</p></div><div class="account-access-actions"><button type="button" class="access-primary" data-verify-email>${action}</button></div>`;
        }
        bindAccessActions(card);
    });
}
function bindAccessActions(host){
    host.querySelector('[data-verify-email]')?.addEventListener('click',()=>window.openEmailVerification?.(current?.email_address||''));
    host.querySelector('[data-access-details]')?.addEventListener('click',openAccessDetails);
    host.querySelector('[data-access-login]')?.addEventListener('click',()=>window.toggleAuthModal?.(true));
    host.querySelector('[data-access-admin]')?.addEventListener('click',openAdmin);
    host.querySelector('[data-access-retry]')?.addEventListener('click',refreshAccess);
}
export async function refreshAccess(){
    if(refreshing)return refreshing;
    const run=epoch;
    const pending=request('/api/account/access').then(data=>{
        if(run===epoch){current=data;accessError='';mount();render();}
        return run===epoch?data:null;
    }).catch(error=>{
        if(run===epoch){current=null;accessError=error.message;render();}
        return null;
    }).finally(()=>{if(refreshing===pending)refreshing=null;});
    refreshing=pending;
    return pending;
}

export function showAccessPrompt(message,code){
    let dialog=document.querySelector('.access-limit-dialog');if(dialog)return;
    dialog=document.createElement('dialog');dialog.className='access-limit-dialog';
    dialog.innerHTML=`<h3>${code==='daily_exhausted'?'今日额度已用完':'登录，继续你的学习'}</h3><p></p><div><button type="button" data-close>稍后再说</button>${code==='daily_exhausted'?'<button type="button" data-apply>查看 VIP 申请方式</button>':'<button type="button" data-login>登录 / 注册</button>'}</div>`;
    dialog.querySelector('p').textContent=message;
    dialog.querySelector('[data-apply]')?.addEventListener('click',()=>{dialog.close();openAccessDetails();});
    dialog.querySelector('[data-close]').onclick=()=>dialog.close();
    dialog.querySelector('[data-login]')?.addEventListener('click',()=>{dialog.close();window.toggleAuthModal?.(true);});
    dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();
}

export async function openAccessDetails(){
    try{
        const {showAccountDetails}=await import('./account-details.js');
        return await showAccountDetails();
    }catch{
        window.showToast?.('权益说明暂时无法打开，请刷新后重试。','error');
        return false;
    }
}
function openAdmin(){ document.querySelector('.account-details-dialog')?.close();window.showSection?.('admin'); }

// Observe API access decisions centrally so every existing tool displays the same
// login/upgrade dialog; do not consume or alter the caller's response stream.
const originalFetch=window.fetch.bind(window);
window.fetch=async(...args)=>{
    const response=await originalFetch(...args);
    const path=new URL(typeof args[0]==='string'?args[0]:args[0]?.url||String(args[0]),location.href);
    if(path.origin===location.origin&&path.pathname.startsWith('/api/')){
        const code=response.headers.get('X-Wisdom-Access');
        if(code==='email_verification_required')window.openEmailVerification?.(current?.email_address||'');
        if(['trial_exhausted','daily_exhausted'].includes(code)){
            try{const data=await response.clone().json();showAccessPrompt(data.message,code);}catch{}
        }
        if((args[1]?.method||'GET').toUpperCase()!=='GET'&&!path.pathname.startsWith('/api/admin/')){clearTimeout(refreshTimer);refreshTimer=setTimeout(refreshAccess,300);}
    }
    return response;
};
window.addEventListener('auth-state-change',()=>{epoch++;current=null;accessError='';refreshing=null;render();refreshAccess();});
window.addEventListener('focus',refreshAccess);
let mountQueued=false;
new MutationObserver(()=>{
    if(mountQueued)return;
    if(document.querySelector('.account-access-card')&&![...document.querySelectorAll('[data-account-header]')].some(el=>!el.childNodes.length))return;
    mountQueued=true;requestAnimationFrame(()=>{mountQueued=false;mount();if([...document.querySelectorAll('[data-account-header]')].some(el=>!el.childNodes.length))render();});
}).observe(document.documentElement,{childList:true,subtree:true});
mount();refreshAccess();
