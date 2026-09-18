<template><section id="examples" class="section" ref="host"><p role="status">正在加载教学工作台…</p></section></template>
<script setup lang="ts">
import { ref,onMounted,onBeforeUnmount } from 'vue';
const host=ref<HTMLElement|null>(null);let alive=true;let dispose:(()=>void)|undefined;
onMounted(async()=>{try{const url='/static/js/examples.js';const module=await import(/* @vite-ignore */ url);if(alive&&host.value){dispose=await module.mountExamples(host.value);if(!alive)dispose?.();}}catch(error){if(host.value)host.value.textContent='教学工作台加载失败，请刷新后重试。';}});
onBeforeUnmount(()=>{alive=false;dispose?.();});
</script>
