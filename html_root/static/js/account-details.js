import {refreshAccess,AUTHOR_URL} from './account-access.js?v=20260919-access-1';
import {escapeText as esc} from './solution-visual.js';

export async function showAccountDetails(){
    const existing=document.querySelector('.account-details-dialog');if(existing){existing.focus();return;}
    const returnFocus=document.activeElement;
    const dialog=document.createElement('dialog');dialog.className='account-details-dialog';
    dialog.setAttribute('aria-labelledby','account-details-title');
    dialog.innerHTML='<header><div><span class="access-eyebrow">你的学习空间</span><h2 id="account-details-title">账户权益</h2></div><button type="button" data-close aria-label="关闭账户权益">×</button></header><div data-access-body role="status">正在读取最新权益…</div>';
    document.body.append(dialog);dialog.showModal();
    dialog.querySelector('[data-close]').onclick=()=>dialog.close();
    const invalidate=()=>dialog.close();window.addEventListener('auth-state-change',invalidate);
    dialog.addEventListener('close',()=>{window.removeEventListener('auth-state-change',invalidate);dialog.remove();if(returnFocus?.isConnected)returnFocus.focus();},{once:true});
    dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
    async function load(){
        const data=await refreshAccess();if(!dialog.isConnected)return;
        const body=dialog.querySelector('[data-access-body]');
        if(!data){body.innerHTML='<p>暂时无法读取权益，请稍后再试。</p><button type="button" data-reload>重新加载</button>';body.querySelector('button').onclick=load;return;}
        const owner=data.can_manage===true,guest=data.role==='guest';
        const quota=data.quotas?.[guest?'calculate':'all'];
        const unlimited=['vip','admin'].includes(data.role)&&quota?.limit===null;
        const known=Number.isFinite(quota?.remaining)&&Number.isFinite(quota?.limit);
        const label=owner?'主账号 · 管理员':({guest:'游客试用',member:'普通用户',vip:'VIP 用户',admin:'管理员身份'})[data.role]||'账户';
        const allowance=unlimited?'不限个人额度':known?`${quota.remaining} / ${quota.limit}`:'暂不可用';
        const progress=known&&quota.limit>0?Math.min(100,Math.max(0,quota.remaining/quota.limit*100)):0;
        const requestText=`你好，我希望申请 VIP / 咨询使用权限。\n智算视界用户名：${data.username||'请先登录并填写用户名'}\n使用场景：学习 / 教学 / 内容创作（请补充）\n希望使用的功能与需求：（请补充）`;
        body.removeAttribute('role');
        body.innerHTML=`<section class="access-entitlement"><div><span class="account-type ${esc(data.role)}">${esc(label)}</span><strong>${esc(data.username||'欢迎体验智算视界')}</strong></div><div class="access-quota-heading"><span>${guest?'计算试用剩余':unlimited?'当前使用额度':'今日剩余次数'}</span><b>${allowance}</b></div>${known?`<div class="access-quota-track" role="meter" aria-label="剩余次数" aria-valuemin="0" aria-valuemax="${Math.max(1,quota.limit)}" aria-valuenow="${quota.remaining}"><i style="width:${progress}%"></i></div>`:''}<p>${guest?'试用次数不会每日恢复；登录后使用账户额度。':unlimited?'个人每日次数不限，高峰时仍会排队，并遵守服务保护。':'计算、识图、助手及动画共享额度。每日北京时间 00:00 恢复。'}</p>${guest?`<div class="access-trial-quotas">${[['recognize','识图'],['assistant','助手'],['code','创作助手'],['render','动画']].map(([key,name])=>`<span>${name} <b>${data.quotas?.[key]?.remaining??'—'}</b> 次</span>`).join('')}</div>`:''}</section>
        <section class="access-benefits"><h3>你现在可以做什么</h3><ul><li><i class="fa-solid fa-check" aria-hidden="true"></i> 输入文字 / LaTeX 题目，分步解题与可视化</li><li><i class="fa-solid fa-check" aria-hidden="true"></i> ${guest?'体验识图、助手与动画；浏览典型例题':'识图、智能体拆题、分步动画与典型例题'}</li><li><i class="fa-solid ${guest?'fa-lock':'fa-check'}" aria-hidden="true"></i> ${guest?'登录后解锁账户保存、错题整理、课包创建':'保存题解、整理错题、创建课包与教学笔记'}</li>${owner?'<li><i class="fa-solid fa-shield-halved" aria-hidden="true"></i> 管理用户角色与额度、查看题目请求和管理记录</li>':''}</ul>${!owner?'<p>用户管理与请求记录仅对主账号 rainbow_yu 开放。VIP 或其他管理员身份不会开放管理后台；自定义 Python 渲染需要单独授权。</p>':''}</section>
        ${owner?'<section class="access-owner-action"><div><h3>管理中心</h3><p>查看用户提交的题目，调整角色与使用额度。</p></div><button type="button" class="access-primary" data-admin>进入管理中心 →</button></section>':`<section class="access-application"><span class="access-eyebrow">${unlimited?'需要更多支持':'想获得更多使用额度'}</span><h3>${unlimited?'联系作者，说明你的需求':'如何申请 VIP'}</h3><ol><li><b>确认账户</b><span>${guest?'先登录或注册，再提供本站用户名。':'向作者提供本站用户名：'+esc(data.username)}</span></li><li><b>说明用途</b><span>复制下方申请说明，填写学习或教学需求。</span></li><li><b>联系作者</b><span>前往 GitHub，通过作者公开的联系方式沟通。确认开通后，刷新权益即可。</span></li></ol><details class="access-application-template"><summary>查看申请说明</summary><pre>${esc(requestText)}</pre></details><div class="access-application-actions">${guest?'<button type="button" class="access-primary" data-login>登录 / 注册</button>':`<a href="${AUTHOR_URL}" target="_blank" rel="noopener noreferrer" class="access-primary"><i class="fa-brands fa-github" aria-hidden="true"></i> 前往 GitHub 联系作者 ↗</a>`}<button type="button" data-copy ${guest?'disabled':''}>复制申请说明</button></div><p>点击链接会打开 GitHub，本站不会自动提交申请。请勿提供密码或 API 密钥。</p></section>`}
        <footer><span data-copy-status role="status"></span><button type="button" data-reload>刷新权益</button><button type="button" data-help>查看帮助 →</button></footer>`;
        body.querySelector('[data-reload]').onclick=load;
        body.querySelector('[data-admin]')?.addEventListener('click',()=>{dialog.close();window.showSection?.('admin');});
        body.querySelector('[data-login]')?.addEventListener('click',()=>{dialog.close();window.toggleAuthModal?.(true);});
        body.querySelector('[data-help]').onclick=()=>{dialog.close();window.showSection?.('help');};
        body.querySelector('[data-copy]')?.addEventListener('click',async()=>{
            try{await navigator.clipboard.writeText(requestText);if(dialog.isConnected)body.querySelector('[data-copy-status]').textContent='申请说明已复制，补充用途后发送给作者。';}
            catch{if(dialog.isConnected){body.querySelector('.access-application-template').open=true;body.querySelector('[data-copy-status]').textContent='未能自动复制，请选中上方申请说明手动复制。';}}
        });
    }
    await load();
}
