<template>
  <dialog ref="dialog" class="solution-reader auth-account-dialog" @close="closed">
    <header class="reader-header">
      <div><span class="reader-kicker">智算视界 · 账户</span><h3>{{ title }}</h3></div>
      <button type="button" aria-label="关闭" @click="dialog?.close()">×</button>
    </header>
    <form class="reader-body" @submit.prevent="submit">
      <p class="auth-account-intro">{{ intro }}</p>
      <label v-if="mode==='login' || mode==='register'">用户名<input v-model="username" autocomplete="username" required maxlength="64" /></label>
      <label v-if="mode!=='login'">邮箱<input v-model="email" type="email" autocomplete="email" required maxlength="254" :placeholder="maskedEmail ? '当前绑定：'+maskedEmail : '常用邮箱地址'" /></label>
      <label v-if="mode==='login' || (!codeSent && mode!=='verify')">图片验证码
        <div class="auth-captcha-row">
          <input v-model="captcha" aria-label="图片验证码" autocomplete="off" :required="mode==='login'" maxlength="8" />
          <button type="button" @click="refreshCaptcha" aria-label="刷新图片验证码"><img v-if="captchaUrl" :src="captchaUrl" alt="验证码" /></button>
        </div>
      </label>
      <label v-if="mode!=='login'">邮箱验证码
        <div class="auth-email-code">
          <input v-model="emailCode" aria-label="邮箱验证码" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" required />
          <button type="button" @click="sendCode" :disabled="busy || sending || remaining>0">{{ sending ? '发送中…' : remaining>0 ? remaining+' 秒后重发' : '获取验证码' }}</button>
        </div>
      </label>
      <label v-if="mode!=='verify'">{{ mode==='login' ? '密码' : '设置密码（至少 6 位）' }}
        <input v-model="password" type="password" :autocomplete="mode==='login' ? 'current-password' : 'new-password'" :minlength="mode==='login' ? 1 : 6" maxlength="72" required />
      </label>
      <label v-if="mode==='register' || mode==='forgot'">确认密码<input v-model="confirmation" type="password" autocomplete="new-password" minlength="6" maxlength="72" required /></label>
      <p class="auth-account-message" role="status" aria-live="polite">{{ message }}</p>
      <button type="submit" class="reader-primary" :disabled="busy || sending">{{ busy ? '正在处理…' : submitLabel }}</button>
      <div class="auth-secondary-actions">
        <template v-if="mode==='verify'"><button type="button" @click="signOut" :disabled="busy">退出当前账户</button><a href="https://github.com/rainbowyuyu" target="_blank" rel="noopener noreferrer">联系作者</a></template>
        <template v-else>
          <button v-if="mode==='login'" type="button" @click="switchMode('forgot')">忘记密码？</button>
          <button type="button" @click="switchMode(mode==='login' ? 'register' : 'login')">{{ mode==='login' ? '创建账户' : '返回登录' }}</button>
        </template>
      </div>
    </form>
  </dialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
type Mode = 'login'|'register'|'verify'|'forgot';
const emit=defineEmits<{signedIn:[username:string]}>();
const dialog=ref<HTMLDialogElement|null>(null), mode=ref<Mode>('login');
const username=ref(''), password=ref(''), confirmation=ref(''), email=ref(''), maskedEmail=ref('');
const emailCode=ref(''), captcha=ref(''), captchaUrl=ref(''), captchaId=ref(''), message=ref('');
const busy=ref(false), sending=ref(false), remaining=ref(0), codeSent=ref(false);
let captchaRun=0, timer:ReturnType<typeof setInterval>|undefined, operation=0;
let pendingVerification=false;
const title=computed(()=>({login:'登录账户',register:'创建账户',verify:'验证邮箱',forgot:'找回密码'}[mode.value]));
const submitLabel=computed(()=>({login:'登录',register:'验证并注册',verify:'验证并继续',forgot:'重置密码'}[mode.value]));
const intro=computed(()=>mode.value==='verify' ? '你的学习资料会保留。请先验证常用邮箱，再继续使用其他功能。'
  : mode.value==='forgot' ? '通过已验证的邮箱找回账户。旧账户若尚未绑定邮箱，请联系作者协助。'
  : mode.value==='register' ? '验证常用邮箱，保存你的学习进度，也方便找回密码。' : '继续你的题解、动画与学习笔记。');
function releaseCaptcha(){captchaRun++;if(captchaUrl.value)URL.revokeObjectURL(captchaUrl.value);captchaUrl.value='';}
function closed(){operation++;releaseCaptcha();password.value='';confirmation.value='';window.dispatchEvent(new Event('auth-dialog-closed'));}
async function refreshCaptcha(){
  const run=++captchaRun;
  captcha.value='';
  try {
    const response=await fetch('/api/captcha',{signal:AbortSignal.timeout(12000)});
    if(!response.ok)throw new Error();
    const blob=await response.blob();if(run!==captchaRun)return;
    if(captchaUrl.value)URL.revokeObjectURL(captchaUrl.value);
    captchaId.value=response.headers.get('X-Captcha-ID')||'';captchaUrl.value=URL.createObjectURL(blob);
  } catch {if(run===captchaRun)message.value='图片验证码加载失败，请点击图片重试。';}
}
function switchMode(next:Mode){
  operation++;mode.value=next;message.value='';password.value='';confirmation.value='';emailCode.value='';
  codeSent.value=false;if(next!=='verify')refreshCaptcha();
}
function show(){switchMode(pendingVerification?'verify':'login');if(!dialog.value?.open)dialog.value?.showModal();}
function showVerification(masked=''){
  pendingVerification=true;maskedEmail.value=masked;
  if(mode.value!=='verify')switchMode('verify');
  if(!dialog.value?.open)dialog.value?.showModal();
}
async function post(path:string,body:object){
  const response=await fetch(path,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body),signal:AbortSignal.timeout(45000)});
  const data=await response.json();
  if(!response.ok || data.status!=='success')throw new Error(data.message||'请检查填写内容后重试。');
  return data;
}
function startCooldown(){
  clearInterval(timer);const until=Date.now()+60000;remaining.value=60;
  timer=setInterval(()=>{remaining.value=Math.max(0,Math.ceil((until-Date.now())/1000));if(!remaining.value)clearInterval(timer);},500);
}
async function sendCode(){
  if(sending.value||remaining.value>0||busy.value)return;
  if(!email.value || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)){message.value='请填写有效的邮箱地址。';return;}
  if(mode.value!=='verify'&&!captcha.value){codeSent.value=false;message.value='请先填写图片验证码。';await refreshCaptcha();return;}
  sending.value=true;const run=operation;
  try {
    const purpose=mode.value==='forgot'?'reset':mode.value;
    const data=await post(purpose==='reset'?'/api/password/forgot/request':'/api/email/send-code',
      {email:email.value,purpose,captcha:captcha.value,captcha_id:captchaId.value});
    startCooldown();if(run!==operation)return;codeSent.value=true;message.value=data.message;
  } catch(e:any){if(run===operation)message.value=e.name==='TimeoutError'?'发送较慢，请稍后查收邮件或重试。':e.message;}
  finally{sending.value=false;if(run===operation && mode.value!=='verify')await refreshCaptcha();}
}
async function submit(){
  if(busy.value||sending.value)return;
  if((mode.value==='register'||mode.value==='forgot') && password.value!==confirmation.value){message.value='两次输入的密码不一致。';return;}
  busy.value=true;message.value='';const run=operation;
  try {
    if(mode.value==='verify'){
      await post('/api/email/verify',{email:email.value,code:emailCode.value});
      pendingVerification=false;window.location.reload();return;
    }
    if(mode.value==='forgot'){
      await post('/api/password/forgot/reset',{email:email.value,code:emailCode.value,new_password:password.value});
      pendingVerification=false;window.dispatchEvent(new CustomEvent('auth-state-change',{detail:{username:null}}));
      switchMode('login');message.value='密码已重置，请使用新密码登录。';return;
    }
    const registering=mode.value==='register';
    const data=await post(registering?'/api/register':'/api/login',
      {username:username.value,password:password.value,captcha:captcha.value,captcha_id:captchaId.value,email:email.value,email_code:emailCode.value});
    if(registering){switchMode('login');message.value='注册成功，请登录。';}
    else {
      emit('signedIn',data.username);
      if(data.email_verified===false)showVerification(data.email);
      else {pendingVerification=false;dialog.value?.close();window.dispatchEvent(new Event('formula-library-updated'));}
    }
  } catch(e:any){if(run===operation){message.value=e.name==='TimeoutError'?'请求超时，请稍后重试。':e.message;if(mode.value==='login')refreshCaptcha();}}
  finally{busy.value=false;}
}
async function signOut(){
  busy.value=true;
  try{await post('/api/logout',{});pendingVerification=false;window.location.reload();}
  catch(e:any){message.value=e.message;}
  finally{busy.value=false;}
}
defineExpose({show,showVerification});
onBeforeUnmount(()=>{operation++;releaseCaptcha();clearInterval(timer);});
</script>
