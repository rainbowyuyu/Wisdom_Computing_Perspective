import {mountRequestRecords} from './admin-requests.js';
import {escapeText as esc} from './solution-visual.js';
import {refreshAccess, AUTHOR_URL} from './account-access.js?v=20260919-access-1';

const names={member:'普通用户',vip:'VIP 用户',admin:'管理员'};
function auditDescription(raw){
    let data=raw;
    if(typeof data==='string'){try{data=JSON.parse(data);}catch{return '已记录账户设置变更';}}
    if(!data||typeof data!=='object')return '已记录账户设置变更';
    const parts=[];
    if(data.role)parts.push('用户类型：'+(names[data.role]||'账户'));
    if('daily_limit' in data)parts.push(data.daily_limit===null?'每日额度跟随默认值':`每日额度 ${data.daily_limit} 次`);
    if('disabled' in data)parts.push(data.disabled?'停用账户':'账户可正常使用');
    if(data.reset_today)parts.push('重置今日用量');
    if(data.contact_email)parts.push('备用联系邮箱：'+data.contact_email);
    return parts.join(' · ')||'已记录账户设置变更';
}

// Each page visit owns its requests and listeners. Navigating away or changing
// accounts cancels the entire visit so a late response cannot restore private data.
export function mountAdmin(host){
    let alive=true,controller;
    function notice(message,login=false){
        host.innerHTML=`<div class="account-admin-page admin-gate"><span class="admin-eyebrow">智算视界 · 管理中心</span><h1>用户管理</h1><p role="status">${esc(message)}</p><div><button type="button" data-home>返回首页</button>${login?'<button type="button" data-login>登录管理员账户</button>':'<button type="button" data-retry>重新加载</button>'}</div></div>`;
        host.querySelector('[data-home]').onclick=()=>window.showSection?.('home');
        host.querySelector('[data-login]')?.addEventListener('click',()=>window.toggleAuthModal?.(true));
        host.querySelector('[data-retry]')?.addEventListener('click',start);
    }
    async function start(){
        controller?.abort();host.onsubmit=null;
        const visit=new AbortController();controller=visit;
        const active=()=>alive&&!visit.signal.aborted;
        const request=async(path,options={})=>{
            const response=await fetch(path,{credentials:'include',...options,signal:AbortSignal.any([visit.signal,AbortSignal.timeout(15000)])});
            const data=await response.json();
            visit.signal.throwIfAborted();
            if(!response.ok){
                if([401,403].includes(response.status)){
                    notice('当前账户没有管理权限，请使用管理员账户登录。',true);
                    visit.abort();refreshAccess();
                }
                throw new Error(data.message||data.detail||'请求未完成，请稍后重试。');
            }
            return data;
        };
        host.innerHTML='<div class="account-admin-page admin-gate" role="status">正在验证管理权限…</div>';
        try{
            const access=await request('/api/account/access');
            if(!active())return;
            if(access.can_manage!==true){notice('管理后台仅限主账号 rainbow_yu 使用。',true);return;}
        }catch(error){if(active())notice(error.name==='TimeoutError'?'读取超时，请重新加载。':error.message);return;}
        host.innerHTML=`<div class="account-admin-page">
          <header class="admin-page-heading"><div><span class="admin-eyebrow">智算视界 · 管理中心</span><h1>用户管理</h1><p>主账号专属 · 管理用户权限，了解题目处理情况。</p></div><button type="button" data-home><i class="fa-solid fa-arrow-left" aria-hidden="true"></i> 返回首页</button></header>
          <div class="admin-overview"><div><span>当前筛选用户</span><strong data-total>—</strong><small>支持按用户名查找</small></div><div><span>普通用户每日额度</span><strong><b data-default>—</b><em> 次 / 天</em></strong><small>北京时间每日 00:00 恢复</small></div><div><span>VIP 与管理员</span><strong>不限个人额度</strong><small>系统仍提供并发与服务保护</small></div></div>
          <details class="admin-settings-panel"><summary><span><i class="fa-solid fa-sliders" aria-hidden="true"></i> 默认额度与联系设置</span><span>编辑设置</span></summary><form class="access-settings"><label>普通用户每日默认额度<input name="daily_limit" type="number" min="0" max="10000" required></label><label>备用联系邮箱<input name="contact_email" type="email" maxlength="254" required></label><button class="admin-primary">保存默认设置</button></form><p class="access-admin-note">联系作者入口前往 <a href="${AUTHOR_URL}" target="_blank" rel="noopener noreferrer">GitHub ↗</a>。每日额度覆盖计算、识图、助手及动画请求；后台整题首次提交计 1 次。个人额度留空时跟随默认值，设为 0 则暂停当日额度。</p></details>
          <section class="admin-users-panel" aria-label="用户列表"><div class="admin-users-heading"><h2>账户与权限</h2><form class="access-search"><input name="q" type="search" placeholder="搜索用户名…" aria-label="搜索用户名" maxlength="80"><button type="submit">搜索</button><button type="button" data-refresh aria-label="刷新用户列表"><i class="fa-solid fa-rotate-right" aria-hidden="true"></i></button></form></div>
          <p data-status role="status" aria-live="polite"></p><button type="button" data-retry hidden>重新加载用户</button><div class="access-user-list" aria-busy="true"></div><footer class="admin-pagination"><span data-page></span><div><button type="button" data-prev disabled>上一页</button><button type="button" data-next disabled>下一页</button></div></footer></section>
          <section class="admin-requests-panel"></section>
          <section class="admin-audit-panel"><div class="admin-users-heading"><div><h2>管理记录</h2><p>查看最近的权限与额度调整。</p></div><button type="button" data-audit>读取最近记录</button></div><div data-audit-list aria-live="polite"></div></section>
        </div>`;
        const $=s=>host.querySelector(s);
        const feedback=(message,error=false)=>{if(active()){$('[data-status]').textContent=message;$('[data-status]').classList.toggle('is-error',error);}};
        let page=1,query='',version=0,total=0,settingsLoaded=false;
        async function load(){
            const run=++version;feedback('正在读取用户…');
            $('[data-retry]').hidden=true;$('.access-user-list').setAttribute('aria-busy','true');
            $('[data-prev]').disabled=true;$('[data-next]').disabled=true;
            try{
                const data=await request(`/api/admin/users?page=${page}&q=${encodeURIComponent(query)}`);
                if(!active()||run!==version)return false;
                total=data.total;
                if(page>1&&page>Math.ceil(total/20)){page=Math.max(1,Math.ceil(total/20));return load();}
                $('[data-total]').textContent=total;$('[data-default]').textContent=data.settings.daily_limit;
                if(!settingsLoaded){$('.access-settings [name=daily_limit]').value=data.settings.daily_limit;$('.access-settings [name=contact_email]').value=data.settings.contact_email;settingsLoaded=true;}
                $('.access-user-list').innerHTML=data.items.map(user=>{
                    const unlimited=['admin','vip'].includes(user.role);
                    const limit=user.daily_limit??data.settings.daily_limit;
                    return `<form class="access-user" data-id="${Number(user.id)}"><div class="access-user-identity"><span class="admin-user-avatar" aria-hidden="true">${esc([...user.username][0]||'U')}</span><div><strong>${esc(user.username)}</strong><small><span class="account-type ${esc(user.role)}">${esc(names[user.role]||'账户')}</span>${user.disabled?'已停用':unlimited?'不限个人额度':`今日剩余 ${Math.max(0,limit-user.used)} / ${limit} 次`}</small><small>${esc(user.email||"未绑定邮箱")} · ${user.email_verified?"已验证":"待验证"}</small></div></div>${user.username==='rainbow_yu'?'<span class="admin-protected"><i class="fa-solid fa-shield-halved" aria-hidden="true"></i> 主账号 · 受保护</span>':`<label>用户类型<select name="role"><option value="admin" ${user.role==='admin'?'selected':''}>管理员</option><option value="member" ${user.role==='member'?'selected':''}>普通用户</option><option value="vip" ${user.role==='vip'?'selected':''}>VIP 用户</option></select></label><label title="VIP 不受个人额度限制；此设置在普通用户身份下生效">个人每日额度<input name="daily_limit" type="number" min="0" max="10000" placeholder="默认 ${data.settings.daily_limit}" value="${user.daily_limit??''}"></label><div class="access-user-switches"><label class="access-check"><input name="disabled" type="checkbox" ${user.disabled?'checked':''}>停用账户</label><label class="access-check"><input name="reset_today" type="checkbox">重置今日用量</label></div><button class="admin-primary" type="submit">保存</button>`}</form>`;
                }).join('')||'<div class="admin-empty">没有找到匹配的用户，试试其他用户名。</div>';
                $('[data-page]').textContent=`第 ${page} / ${Math.max(1,Math.ceil(total/20))} 页 · 共 ${total} 人`;
                $('[data-prev]').disabled=page===1;$('[data-next]').disabled=page*20>=total;feedback('');
                return true;
            }catch(error){
                if(active()&&run===version){$('.access-user-list').replaceChildren();feedback(error.name==='TimeoutError'?'用户列表读取超时，请重试。':error.message,true);$('[data-retry]').hidden=false;}
                return false;
            }finally{if(active()&&run===version)$('.access-user-list').setAttribute('aria-busy','false');}
        }
        host.onsubmit=async event=>{
            event.preventDefault();const form=event.target;
            if(form.classList.contains('access-search')){page=1;query=form.elements.q.value.trim();await load();return;}
            if(!form.matches('.access-settings,.access-user')||form.dataset.saving)return;
            feedback('正在保存…');
            form.dataset.saving='true';const button=form.querySelector('button');button.disabled=true;button.textContent='保存中…';
            try{
                const data=Object.fromEntries(new FormData(form));data.daily_limit=data.daily_limit===''?null:Number(data.daily_limit);
                const isUser=form.classList.contains('access-user');
                if(isUser){data.disabled=form.elements.disabled.checked;data.reset_today=form.elements.reset_today.checked;}
                await request(isUser?'/api/admin/users/'+form.dataset.id:'/api/admin/access-settings',{method:isUser?'PATCH':'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
                if(!active())return;
                settingsLoaded=false;
                if(await load())feedback('已保存，后续请求立即使用新权限。');
                refreshAccess();
            }catch(error){feedback(error.message,true);}
            finally{if(active()){delete form.dataset.saving;button.disabled=false;button.textContent=form.classList.contains('access-user')?'保存':'保存默认设置';}}
        };
        $('[data-home]').onclick=()=>window.showSection?.('home');
        $('[data-prev]').onclick=()=>{page--;load();};$('[data-next]').onclick=()=>{page++;load();};
        $('[data-refresh]').onclick=()=>load();$('[data-retry]').onclick=()=>load();
        $('[data-audit]').onclick=async event=>{
            const button=event.currentTarget;button.disabled=true;button.textContent='正在读取…';
            try{
                const data=await request('/api/admin/access-audit');if(!active())return;
                const actions={update_user:'调整用户权限',update_settings:'调整默认设置'};
                $('[data-audit-list]').innerHTML=data.items.map(item=>`<article><div><strong>${esc(actions[item.action]||'账户设置变更')}</strong><time>${esc(item.created_at)}</time></div><p>操作人 #${esc(String(item.actor_id??'—'))} · ${item.target_id==null?'全站设置':'用户 #'+esc(String(item.target_id))}</p><small>${esc(auditDescription(item.details))}</small></article>`).join('')||'<p class="admin-empty">暂无管理记录</p>';
            }catch(error){if(active())$('[data-audit-list]').textContent=error.message;}
            finally{if(active()){button.disabled=false;button.textContent='刷新管理记录';}}
        };
        load();
        mountRequestRecords($('.admin-requests-panel'),request,active);
    }
    window.addEventListener('auth-state-change',start);start();
    return ()=>{alive=false;controller?.abort();window.removeEventListener('auth-state-change',start);host.onsubmit=null;host.replaceChildren();};
}
