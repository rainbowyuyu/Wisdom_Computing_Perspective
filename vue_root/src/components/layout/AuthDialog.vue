<template>
  <dialog ref="dialog" class="solution-reader auth-account-dialog" @close="closed">
    <header class="reader-header"><div><span class="reader-kicker">智算视界</span><h3>{{ registering ? '创建账户' : '登录账户' }}</h3></div><button type="button" aria-label="关闭" @click="dialog?.close()"><i class="fa-solid fa-xmark"></i></button></header>
    <form class="reader-body" @submit.prevent="submit">
      <p class="auth-account-intro">将公式、分步题解与动画保存在你的算式库。</p>
      <label>用户名<input v-model="username" autocomplete="username" required maxlength="64" /></label>
      <label>密码<input v-model="password" type="password" :autocomplete="registering ? 'new-password' : 'current-password'" required /></label>
      <label>验证码<div class="auth-captcha-row"><input v-model="captcha" autocomplete="off" required maxlength="8" /><button type="button" @click="refreshCaptcha" aria-label="刷新验证码"><img v-if="captchaUrl" :src="captchaUrl" alt="验证码" /></button></div></label>
      <p class="auth-account-message" role="status">{{ message }}</p>
      <button type="submit" class="reader-primary" :disabled="busy">{{ busy ? '请稍候…' : registering ? '创建账户' : '登录' }}</button>
      <button type="button" @click="switchMode">{{ registering ? '已有账户，去登录' : '还没有账户？注册' }}</button>
    </form>
  </dialog>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
const emit=defineEmits<{signedIn:[username:string]}>();
const dialog=ref<HTMLDialogElement|null>(null);
const username=ref(''),password=ref(''),captcha=ref(''),captchaUrl=ref(''),captchaId=ref(''),message=ref('');
const registering=ref(false),busy=ref(false);
let captchaRun=0;
function releaseCaptcha(){captchaRun++;if(captchaUrl.value)URL.revokeObjectURL(captchaUrl.value);captchaUrl.value='';}
function closed(){releaseCaptcha();window.dispatchEvent(new Event('auth-dialog-closed'));}
async function refreshCaptcha(){
  const run=++captchaRun;
  try{const response=await fetch('/api/captcha');if(!response.ok)throw new Error();const blob=await response.blob();if(run!==captchaRun)return;if(captchaUrl.value)URL.revokeObjectURL(captchaUrl.value);captchaId.value=response.headers.get('X-Captcha-ID')||'';captchaUrl.value=URL.createObjectURL(blob);captcha.value='';}
  catch{message.value='验证码加载失败，请点击重试。';}
}
function show(){message.value='';password.value='';dialog.value?.showModal();refreshCaptcha();}
function switchMode(){registering.value=!registering.value;message.value='';refreshCaptcha();}
async function submit(){
  if(busy.value)return;busy.value=true;message.value='';
  try{const response=await fetch(registering.value?'/api/register':'/api/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value,password:password.value,captcha:captcha.value,captcha_id:captchaId.value})});const data=await response.json();if(!response.ok||data.status!=='success')throw new Error(data.message||'操作失败，请重试。');
    if(registering.value){registering.value=false;message.value='注册成功，请登录。';await refreshCaptcha();}
    else{emit('signedIn',username.value);dialog.value?.close();window.dispatchEvent(new CustomEvent('formula-library-updated'));}
  }catch(e:any){message.value=e.message;await refreshCaptcha();}finally{busy.value=false;}
}
defineExpose({show});onBeforeUnmount(releaseCaptcha);
</script>
