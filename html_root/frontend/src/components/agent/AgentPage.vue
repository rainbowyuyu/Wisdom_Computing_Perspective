<template><section id="agent" class="section agent-section"><div ref="host" /></section></template>
<script setup lang="ts">
import { ref,onMounted,onBeforeUnmount } from 'vue';
import '../../services/tutor';
const host=ref<HTMLElement|null>(null);let dispose:(()=>void)|undefined;let alive=true;
defineProps<{active?:boolean}>();
onMounted(async()=>{const url='/static/js/agent-workspace.js';const module=await import(/* @vite-ignore */ url);if(alive&&host.value)dispose=module.mountAgent(host.value);});
onBeforeUnmount(()=>{alive=false;dispose?.();});
</script>
