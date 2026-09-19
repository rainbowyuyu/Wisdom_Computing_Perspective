import {openAccessDetails,refreshAccess,AUTHOR_URL} from './account-access.js?v=20260919-access-1';

export const FAQ=[
    ['access','在哪里查看自己的权限和剩余额度？','点击导航栏右上角的身份与额度，即可打开「账户权益」。游客显示计算及其他工具的试用余量；普通用户显示今日剩余 / 总额度；VIP 与管理员身份显示个人额度不限。首页权益卡也可查看说明。额度读取失败时可重试，不会把未知额度当作不限。'],
    ['vip','如何申请 VIP 或其他使用权限？',`先登录本站，打开「账户权益 → 如何申请 VIP」，复制申请说明，填写本站用户名、学习或教学场景和功能需求，再前往 <a href="${AUTHOR_URL}" target="_blank" rel="noopener noreferrer">作者 GitHub ↗</a>，通过作者公开的联系方式沟通。开通由主账号确认，之后点击「刷新权益」查看。打开 GitHub 或复制文字不代表已经提交申请；无需提供密码或 API 密钥。`],
    ['quota','试用次数、每日额度与 VIP 分别如何计算？','游客可试用 3 次计算，识图、助手等工具有各自的试用次数，具体余量以账户权益为准；试用不会每天恢复。普通用户的计算、识图、助手及动画共享每日额度，北京时间 00:00 恢复，个人或默认额度由主账号设置。VIP 和管理员免个人每日次数限制，仍遵守服务排队及资源保护。后台整题首次提交或手动继续计 1 次，子任务与自动动画不重复扣个人次数；同步解题与动画各为一次提交。开始执行后失败或取消不退次数。'],
    ['admin','管理员身份和管理中心有什么区别？','管理中心仅限主账号 <b>rainbow_yu</b>。它可以授予或取消 VIP / 管理员身份、调整额度、停用账户，以及查看题目请求和操作记录；主账号自身不能在页面降权、停用或更名。其他管理员身份免个人每日次数限制，但不能进入管理后台。主账号可从右上角「管理中心」、首页权益卡或本页快捷入口直接进入。'],
    ['requests','管理中心的用户请求记录包含什么？','记录提交的题目文字、账号、请求类型、处理状态、时间、耗时和浏览器 / 系统类别，可按题目或用户名、类型、状态和时间范围筛选。图片请求保存识别后的题面，不保留上传图片原文或完整脚本，常见凭据格式会脱敏。记录从功能启用后产生，管理页最多查询最近 90 天，仅主账号可读取；超期记录定期批量清理。HTTP 已接收不代表后台任务已完成，请以任务状态为准。'],
    ['solve','如何输入 LaTeX 并查看分步解题？','在「动态计算 → 开始一道新题」输入文字或 LaTeX，也可切换可视化公式输入。提交后选择步骤，查看推导与图形变化；按需生成 Manim 动画。解题结果的「更多」中可复制解答、导出笔记、加入错题或课包。登录后保存到「我的算式」，以后可继续阅读与生成动画。AI 推导请结合题目条件核对。'],
    ['tasks','一道复杂题目如何逐步完成？','每次只提交一道完整题目，同题的小问可以保留。复杂题可转交智能体拆解，当前题完成或停止后再开始下一道。互不依赖的子任务可并行，有依赖的步骤按顺序执行，服务繁忙时排队。可在智能体任务列表查看进度、停止任务，或只继续未完成部分；缺少条件时需要补充题面。切换页面不等于取消后台任务，服务重启后中断的任务可手动继续。'],
    ['animation','动画生成失败、排队或超时怎么办？','先查看题解与当前进度。适合自动修复的 Manim 错误会触发一次模型判断与修复，再尝试渲染；不是所有错误都能自动修复。仍失败时保留题目和已完成解答，可以重试或把复杂题拆成较小的部分。生成时间取决于题目、队列与服务资源，没有固定完成时间；VIP 也需遵守并发保护。'],
    ['progress','悬浮球的进度与知识图谱怎么用？','生成期间，智算星云悬浮球会显示海浪式任务进度；展开可查看任务状态并返回对应页面。星云车站的前后入口读取知识图谱连接，点击可直达工具。首页图谱支持搜索、缩放及功能跳转，权限受限的入口仍会进行身份校验。'],
    ['examples','典型例题、错题本和课包在哪里？','高中与大学典型例题位于「教学案例」，可直接阅读已有步骤或带入动态计算继续探索。登录后可将题解、动画和教学资料整理进课包；错题本支持保存、复习和回到解题流程。案例播放器可使用弹幕、时间点笔记等功能。保存的账户内容与当前浏览器的最近练习不同，重要结果请主动保存。'],
    ['ocr','识别结果不准确，或手写题目无法识别怎么办？','支持常见代数、矩阵及微积分表达式等，但光线、连笔与题目结构会影响识别准确性。每次只上传一道题，请裁剪掉相邻题目，保留本题题干、图形和小问。使用清晰 JPG / PNG 图片，保持字迹间距，图片不超过 5 MB。空白、模糊或多题图片会提示调整，不会把报错内容当成公式。识别后先核对完整题面、数字、上下标和条件，可分别编辑公式与完整题面；计算时以完整题面为准。有疑问的内容需要先补全并确认，再转入计算。'],
    ['creator','创作助手与自定义 Python 渲染有什么限制？','创作助手可辅助编写、修改 Manim 代码，阅读建议并确认后再应用。自定义 Python 渲染需要主账号或服务器单独配置的可信执行权限；VIP 或其他管理员身份不会自动获得该权限。普通用户仍可使用动态计算中的数据驱动分步动画。'],
    ['privacy','题目、隐私和使用费用如何处理？','本站是开源教育项目，工具使用受账户额度及服务资源限制，VIP 开通事宜请联系作者确认。保存的题解、错题与课包按账户隔离；用于故障排查和服务管理的题目请求记录仅主账号可见。请不要在题目中填写密码、密钥等敏感信息，详细规则见隐私政策。'],
];

export function mountHelpCenter(host){
    const events=new AbortController();let alive=true,version=0;
    host.innerHTML=`<section class="help-recent"><span class="access-eyebrow">最近新增 · 从这里了解</span><h3>清楚自己的权益，继续每一步探索。</h3><p>账户额度与申请说明、主账号管理、题目请求记录，以及更完整的分步学习流程。</p><div class="help-quick-actions"><button type="button" data-help-action="access"><i class="fa-solid fa-user-shield" aria-hidden="true"></i> 我的权益与申请</button><button type="button" data-help-action="admin" hidden><i class="fa-solid fa-sliders" aria-hidden="true"></i> 进入管理中心</button><button type="button" data-help-action="tour">新手引导 →</button><button type="button" data-help-action="guide">分步解题指南 →</button></div></section>
      <div class="help-search-bar"><div class="help-search-inner"><i class="fa-solid fa-magnifying-glass help-search-icon" aria-hidden="true"></i><input id="help-search-input" type="search" placeholder="搜索 VIP、额度、课包、动画失败…" aria-label="搜索帮助" autocomplete="off"></div><p class="help-search-hint" data-help-count aria-live="polite">选择问题，了解实际的使用方式。</p></div>
      <div class="help-faq-list">${FAQ.map(([id,q,a])=>`<details data-faq="${id}"><summary>${q}</summary><p>${a}</p></details>`).join('')}</div><p class="help-empty" hidden>没有找到匹配问题，试试“额度”“动画”或“课包”。</p><div class="help-footer-links"><button type="button" data-help-action="updates">完整更新日志</button><button type="button" data-help-action="privacy">隐私政策</button><a href="${AUTHOR_URL}" target="_blank" rel="noopener noreferrer">GitHub · 联系作者 ↗</a></div>`;
    const entries=[...host.querySelectorAll('[data-faq]')];
    host.querySelector('#help-search-input').addEventListener('input',event=>{
        const query=event.target.value.trim().toLowerCase();let count=0;
        entries.forEach(el=>{const match=el.textContent.toLowerCase().includes(query);el.hidden=!match;el.open=!!query&&match;if(match)count++;});
        host.querySelector('.help-empty').hidden=count!==0;
        host.querySelector('[data-help-count]').textContent=query?`找到 ${count} 条相关说明`:'选择问题，了解实际的使用方式。';
    },{signal:events.signal});
    host.addEventListener('click',async event=>{
        const action=event.target.closest('[data-help-action]')?.dataset.helpAction;if(!action)return;
        if(action==='access')return openAccessDetails();
        if(action==='tour')return window.startTutorial?.();
        if(action==='admin'){const data=await refreshAccess();if(alive&&data?.can_manage)window.showSection?.('admin');return;}
        const doc={guide:['step-tutor.md','分步解题指南'],updates:['update.md','更新日志'],privacy:['privacy.md','隐私政策']}[action];
        if(doc)window.openDoc?.(...doc);
    },{signal:events.signal});
    async function updateAccess(){
        const run=++version;host.querySelector('[data-help-action=admin]').hidden=true;
        const data=await refreshAccess();if(alive&&run===version)host.querySelector('[data-help-action=admin]').hidden=!data?.can_manage;
    }
    window.addEventListener('auth-state-change',updateAccess,{signal:events.signal});updateAccess();
    return ()=>{alive=false;events.abort();};
}
