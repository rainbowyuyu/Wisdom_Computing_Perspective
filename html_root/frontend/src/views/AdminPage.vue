<template>
  <section id="admin" class="section active-section"><div ref="host" data-admin-host></div></section>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
const host = ref<HTMLElement | null>(null);
let dispose: (() => void) | undefined;
let alive = true;
onMounted(async () => {
  try {
    const url = '/static/js/account-admin.js';
    const { mountAdmin } = await import(/* @vite-ignore */ url);
    if (alive && host.value) dispose = mountAdmin(host.value);
  } catch {
    if (alive && host.value) host.value.textContent = '用户管理页面加载失败，请刷新重试。';
  }
});
onBeforeUnmount(() => { alive = false; dispose?.(); });
</script>
