// Compatibility entry points for the static site's navigation and saved templates.
import { mountAgent, prefillAgent, executeAgent, stopAgent } from './agent-workspace.js';
export function initAgent(){const host=document.getElementById('agent');if(host&&!host.dataset.workspaceMounted){host.dataset.workspaceMounted='true';mountAgent(host);}}
export function refreshAgentGate(){} // Authentication is checked against the server before execution.
export const prefillAndShow=prefillAgent;
export const execute=executeAgent;
export function startRoleFlow(role){prefillAgent(({student:'请帮我分步解答一道题：',teacher:'请帮我制作一段课堂数学演示：',creator:'请帮我编写一段 Manim 动画：',developer:'打开 Manim 开发者工作台'})[role]||'');}
export function reExecuteLastMessage(){const request=window.AgentWorkspace?.getState().lastRequest;if(request)executeAgent(request.prompt,request.image_base64);}
export function openTemplatesModal(){window.showSection?.('my-formulas');window.Formulas?.switchFormulasSubTab?.('templates');}
export async function runTemplateById(id){
    const me=await fetch('/api/user/me').then(r=>r.json());if(!me.username){window.toggleAuthModal?.(true);return;}
    const result=await fetch('/api/agent_templates/get?id='+Number(id)+'&username='+encodeURIComponent(me.username)).then(r=>r.json());
    if(result.status==='success'&&result.data?.prompt){prefillAgent(result.data.prompt);await executeAgent(result.data.prompt);}
    else window.showToast?.(result.message||'模板读取失败','error');
}
window.Agent={...window.Agent,initAgent,execute,prefillAndShow,startRoleFlow,reExecuteLastMessage,openTemplatesModal,runTemplateById,stop:stopAgent};
