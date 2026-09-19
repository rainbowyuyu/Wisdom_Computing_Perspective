<template>
  <section id="help" class="section">
    <h2 class="section-title">常见问题与指南</h2>
    <div ref="host" class="help-container" style="max-width:880px;margin:0 auto"><p role="status">正在加载帮助…</p></div>
  </section>
</template>
<script setup lang="ts">
import {onMounted,onBeforeUnmount,ref} from 'vue';
const host=ref<HTMLElement|null>(null);
let alive=true,dispose:(()=>void)|undefined;
onMounted(async()=>{
  try{
    const url='/static/js/help-center.js';
    const {mountHelpCenter}=await import(/* @vite-ignore */ url);
    if(alive&&host.value)dispose=mountHelpCenter(host.value);
  }catch{if(alive&&host.value)host.value.textContent='帮助内容暂时无法加载，请刷新重试。';}
});
onBeforeUnmount(()=>{alive=false;dispose?.();});
</script>
