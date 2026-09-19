import {textWithMath} from './math-text.js';
import {escapeText as esc} from './solution-visual.js';

const features={calculate:'分步计算',recognize:'图片识别',assistant:'智能体',task:'后台拆题',code:'创作助手',render:'动画渲染'};
const statuses={processing:'处理中',completed:'已完成',failed:'失败',rejected:'已拦截',cancelled:'已取消',interrupted:'已中断',handoff:'转交智能体',partial:'部分完成',needs_information:'待补充条件',queued:'排队中',planning:'拆解中',running:'执行中',blocked:'等待前置任务'};
function timeText(value){
    if(!value)return '—';
    const date=new Date(value.replace(' ','T')+(/[zZ]|[+-]\d\d:\d\d$/.test(value)?'':'Z'));
    return Number.isNaN(date.getTime())?'—':date.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
}
export function mountRequestRecords(host,request,active){
    host.innerHTML=`<div class="admin-users-heading"><div><h2>用户请求记录</h2><p>查看题目与处理情况 · 时间为北京时间 · 最近 90 天</p></div><button type="button" data-requests-refresh>刷新记录</button></div>
    <form class="request-filters"><input name="q" type="search" maxlength="200" placeholder="搜索用户名或题目" aria-label="搜索用户名或题目"><select name="feature" aria-label="请求类型"><option value="">所有类型</option>${Object.entries(features).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select><select name="status" aria-label="处理状态"><option value="">所有状态</option>${Object.entries(statuses).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select><select name="days" aria-label="时间范围"><option value="7">最近 7 天</option><option value="30">最近 30 天</option><option value="90">最近 90 天</option></select><button>筛选</button></form>
    <p class="request-record-notice">记录从本次更新起产生。图片仅保存识别出的题目文字；代码请求不保存脚本和凭据。管理员身份的授予不开放管理后台，后台仅限 rainbow_yu。</p>
    <p data-requests-status role="status" aria-live="polite"></p><div data-requests-list></div><footer class="admin-pagination"><span data-requests-page></span><div><button type="button" data-requests-prev disabled>上一页</button><button type="button" data-requests-next disabled>下一页</button></div></footer><div data-request-detail></div>`;
    const $=s=>host.querySelector(s);let page=1,version=0,detailVersion=0;
    async function load(){
        const run=++version;++detailVersion;$('[data-request-detail]').replaceChildren();
        $('[data-requests-status]').textContent='正在读取请求记录…';
        $('[data-requests-list]').setAttribute('aria-busy','true');
        $('[data-requests-prev]').disabled=true;$('[data-requests-next]').disabled=true;
        try{
            const params=new URLSearchParams(new FormData($('.request-filters')));params.set('page',page);
            const data=await request('/api/admin/requests?'+params);
            if(!active()||run!==version)return;
            if(page>1&&page>Math.ceil(data.total/20)){page=Math.max(1,Math.ceil(data.total/20));return load();}
            $('[data-requests-list]').innerHTML=data.items.map(item=>`<article class="request-record"><div class="request-record-meta"><strong>${esc(item.username||'游客')}</strong><span>${esc(features[item.feature]||item.feature)}</span><span class="request-state ${esc(item.status)}">${esc(statuses[item.status]||item.status)}</span><time>${esc(timeText(item.created_at))}</time></div><p class="request-preview">${esc(item.preview|| (item.has_image?'图片题目，暂无识别结果':'未保存文本内容'))}</p><div class="request-record-bottom"><small>${esc(item.device||'—')} · ${item.duration_ms==null?'处理中':(item.duration_ms/1000).toFixed(1)+' 秒'}${item.http_status?' · HTTP '+Number(item.http_status):''}</small><button type="button" data-request-id="${esc(item.id)}">查看详情</button></div></article>`).join('')||'<p class="admin-empty">当前条件下暂无请求记录。新提交的题目会出现在这里。</p>';
            $('[data-requests-page]').textContent=`第 ${page} / ${Math.max(1,Math.ceil(data.total/20))} 页 · 共 ${data.total} 条`;
            $('[data-requests-prev]').disabled=page===1;$('[data-requests-next]').disabled=page*20>=data.total;
            const health=data.recording||{};
            $('[data-requests-status]').textContent=health.dropped||health.failed?'部分请求记录写入失败，请检查数据库；解题服务仍可使用。':health.pending?'部分记录正在保存，可稍后刷新。':'';
        }catch(error){if(active()&&run===version){$('[data-requests-list]').replaceChildren();$('[data-requests-status]').textContent=error.message+' 可点击“刷新记录”重试。';}}
        finally{if(active()&&run===version)$('[data-requests-list]').setAttribute('aria-busy','false');}
    }
    $('.request-filters').onsubmit=event=>{event.preventDefault();event.stopPropagation();page=1;load();};
    $('[data-requests-refresh]').onclick=()=>load();
    $('[data-requests-prev]').onclick=()=>{page--;load();};$('[data-requests-next]').onclick=()=>{page++;load();};
    host.addEventListener('click',async event=>{
        const button=event.target.closest('[data-request-id]');if(!button)return;
        const run=++detailVersion;button.disabled=true;
        try{
            const {item}=await request('/api/admin/requests/'+encodeURIComponent(button.dataset.requestId));
            if(!active()||run!==detailVersion)return;
            const detail=$('[data-request-detail]');
            detail.innerHTML=`<section class="request-detail-card"><div class="admin-users-heading"><h3>请求详情</h3><button type="button" data-close-detail>收起详情</button></div><p>${esc(item.username||'游客')} · ${esc(features[item.feature]||item.feature)} · ${esc(statuses[item.status]||item.status)}</p><dl><dt>提交时间</dt><dd>${esc(timeText(item.created_at))}</dd><dt>用户 ID</dt><dd>${item.owner_id==null?'游客':Number(item.owner_id)}</dd><dt>请求编号</dt><dd>${esc(item.id)}</dd><dt>请求入口</dt><dd>${esc(item.endpoint)}</dd>${item.job_id?`<dt>后台任务编号</dt><dd>${esc(item.job_id)}</dd>`:''}</dl><h4>题目 / 用户输入</h4><div class="request-problem"></div>${item.content_truncated?'<p>题目较长，仅保留前 12,000 字。</p>':''}<p>图片附件：${item.has_image?'有（不保留图片原文）':'无'}</p></section>`;
            textWithMath(detail.querySelector('.request-problem'),item.problem||'此请求没有可保存的题目文字。');
            detail.querySelector('[data-close-detail]').onclick=()=>{++detailVersion;detail.replaceChildren();button.focus();};
            detail.scrollIntoView({behavior:'smooth',block:'start'});
        }catch(error){if(active()&&run===detailVersion)$('[data-requests-status]').textContent=error.message;}
        finally{if(active())button.disabled=false;}
    });
    load();
}
