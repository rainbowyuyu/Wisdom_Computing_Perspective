<template>
  <section id="calculate" class="section">
    <h2 class="section-title">数学运算可视化</h2>
    <p class="section-subtitle">从问题到理解，让每一步推导清晰可见</p>
    <StepTutor />
  </section>
</template>

<script setup lang="ts">
import { onMounted, watch } from "vue";
import StepTutor from "../components/StepTutor.vue";
import { getTutor } from "../services/tutor";
import { useAgentRunnerStore } from "../stores/agentRunner";
const runner = useAgentRunnerStore();
onMounted(async () => {
  const pending = sessionStorage.getItem("pending_calc_latex");
  if (pending) {
    const tutor = await getTutor();
    tutor.prefillProblem(pending, sessionStorage.getItem("pending_calc_context") || "");
    sessionStorage.removeItem("pending_calc_latex");
    sessionStorage.removeItem("pending_calc_context");
  }
});
watch(() => [runner.state.status, runner.state.index, runner.state.steps], () => {
  runner.consumeIfCurrent("calculate", async (step) => {
    const tutor = await getTutor();
    if (step.formula) tutor.prefillProblem(step.formula);
    if (step.trigger === "generate") {
      const success = await tutor.solveProblem(step.formula || (window as any).StepTutor.getState().draftProblem, { autoRender: true });
      if (!success) throw new Error("解题未完成，请查看解题状态。");
    }
  });
}, { immediate: true, flush: "post" });
</script>
