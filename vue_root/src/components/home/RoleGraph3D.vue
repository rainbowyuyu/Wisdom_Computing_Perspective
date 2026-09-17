<template>
  <div class="role-graph-wrap">
    <div id="role-graph-3d" class="role-graph-3d"></div>
    <p class="role-graph-hint">左键旋转 · 右键平移 · 滚轮缩放</p>
    <div class="role-graph-controls" aria-label="图谱控制">
      <button type="button" id="role-graph-zoom-in" title="放大">
        <i class="fa-solid fa-plus"></i>
      </button>
      <button type="button" id="role-graph-zoom-out" title="缩小">
        <i class="fa-solid fa-minus"></i>
      </button>
      <button type="button" id="role-graph-reset" title="还原视图">
        <i class="fa-solid fa-rotate-left"></i>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";

let timer: number | null = null;
let dispose: (() => void) | undefined;
let attempts = 0;

function tryInit(): boolean {
  const g: any = window;
  const rg = g.RoleGraph;
  if (rg && typeof rg.initRoleGraph === "function") {
    dispose = rg.initRoleGraph();
    return true;
  }
  return false;
}

onMounted(() => {
  if (tryInit()) return;
  timer = window.setInterval(() => {
    attempts++;
    if ((tryInit() || attempts > 40) && timer != null) {
      clearInterval(timer);
      timer = null;
    }
  }, 300);
});

onUnmounted(() => {
  if (timer != null) {
    clearInterval(timer);
    timer = null;
  }
  dispose?.();
  // 清理容器中的后备内容
  const el = document.getElementById("role-graph-3d");
  if (el) el.innerHTML = "";
});
</script>
