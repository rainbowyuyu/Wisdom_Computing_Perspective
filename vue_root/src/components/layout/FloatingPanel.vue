<template>
  <aside id="knowledge-panel" class="glass-panel knowledge-panel-global knowledge-panel-wrapper" style="position:fixed;right:24px;bottom:24px;width:320px;padding:1.1rem;border-radius:1rem;z-index:1300">
    <button id="knowledge-panel-close-btn" type="button" class="knowledge-panel-close-btn" aria-label="收起智算星云">×</button>
    <div id="knowledge-panel-bubble" style="display:none;width:100%;height:100%;align-items:center;justify-content:center">
      <img src="/static/assets/智算视界_avatar.svg" alt="" class="knowledge-bubble-logo" style="width:44px;height:44px" draggable="false">
    </div>
    <div id="knowledge-panel-content" class="knowledge-panel-content-scroll">
      <div id="knowledge-panel-header"><h3 id="knowledge-panel-title">智算星云</h3><p id="knowledge-panel-subtitle">快捷入口与解题任务</p></div>
      <div id="knowledge-panel-metro" class="knowledge-metro-wrap" />
      <div id="knowledge-panel-body" class="knowledge-panel-body knowledge-panel-body-scroll">
        <div id="knowledge-panel-dynamic" hidden><div id="knowledge-panel-dynamic-stats"/><div id="knowledge-progress-list"/><div id="knowledge-cloud"/></div>
        <div id="knowledge-panel-static"/>
      </div>
    </div>
  </aside>
</template>
<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { getTutor } from "../../services/tutor";
const route = useRoute();
let refresh: ((section: string) => void) | undefined;
onMounted(async () => {
  await getTutor();
  const floatingUrl = "/static/js/floating-panel.js?v=20260917-nebula-math-7";
  const knowledgeUrl = "/static/js/knowledge-panel.js?v=20260917-ecosystem-6";
  const floating = await import(/* @vite-ignore */ floatingUrl);
  floating.initFloatingPanel();
  const knowledge = await import(/* @vite-ignore */ knowledgeUrl);
  refresh = knowledge.refreshKnowledgePanel;
  refresh?.(route.path.slice(1) || "home");
});
watch(() => route.path, path => refresh?.(path.slice(1) || "home"));
</script>
