<template><div ref="host" /></template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from "vue";
import { getTutor } from "../services/tutor";
const host = ref<HTMLElement | null>(null);
let dispose: (() => void) | undefined;
let alive = true;
onMounted(async () => {
  try {
    const tutor = await getTutor();
    if (alive && host.value) dispose = tutor.mountTutor(host.value);
  } catch {
    if (host.value) host.value.textContent = "分步解题组件加载失败，请确认后端服务已启动并刷新。";
  }
});
onBeforeUnmount(() => { alive = false; dispose?.(); });
</script>
