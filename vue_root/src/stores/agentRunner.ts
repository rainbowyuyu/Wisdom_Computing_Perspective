import { reactive, readonly, getCurrentInstance, onUnmounted } from "vue";
import type { AgentStep } from "../components/agent/useAgentChat";
import { router } from "../router";

export type AgentRunnerStatus = "idle" | "running" | "finished" | "error";

export interface AgentRunnerState {
  status: AgentRunnerStatus;
  steps: AgentStep[];
  index: number;
  error?: string;
}

const sectionToPath: Record<string, string> = {
  home: "/",
  agent: "/agent",
  detect: "/detect",
  "my-formulas": "/my-formulas",
  calculate: "/calculate",
  examples: "/examples",
  devtools: "/devtools",
  help: "/help",
};

const state = reactive<AgentRunnerState>({
  status: "idle",
  steps: [],
  index: 0,
  error: undefined,
});
let runId = 0;
let claim = "";
const handlers = new Map<string, (step: AgentStep) => Promise<void> | void>();

function normalizeSteps(raw: AgentStep[] | undefined | null): AgentStep[] {
  if (!raw || !Array.isArray(raw)) return [];
  return raw.filter((s) => !!s && typeof s.section === "string");
}

async function gotoSection(sectionId: string) {
  // settings 不是路由页：用全局设置弹窗（后续会 Vue 化）
  if (sectionId === "settings") {
    const g: any = window;
    if (typeof g.openSettings === "function") {
      g.openSettings();
    }
    return;
  }
  const path = sectionToPath[sectionId] ?? "/";
  await router.push(path);
}

export function useAgentRunnerStore() {
  function reset() {
    runId++;
    claim = "";
    state.status = "idle";
    state.steps = [];
    state.index = 0;
    state.error = undefined;
  }

  async function start(steps: AgentStep[]) {
    const normalized = normalizeSteps(steps);
    if (!normalized.length) return;
    runId++;
    claim = "";
    state.steps = normalized;
    state.index = normalized.findIndex(step => step.section !== "chat");
    state.error = undefined;
    state.status = "running";

    // 先跳转到第一个非 chat 的页面（若都是 chat，则直接结束）
    const first = state.steps.find((s) => s.section && s.section !== "chat");
    if (!first) {
      state.status = "finished";
      return;
    }
    await dispatch(first);
  }

  async function dispatch(step: AgentStep) {
    if (step.section === "settings") {
      await consumeIfCurrent("settings", async current => {
        const g: any = window;
        if (typeof g.openSettings !== "function") throw new Error("设置窗口尚未就绪");
        g.openSettings(current.settings_section);
        if (current.setting_key) {
          if (!g.Settings?.applySingleSetting) throw new Error("当前前端不支持自动修改设置，请手动调整。");
          g.Settings.applySingleSetting(current.setting_key, current.setting_value);
        }
      });
      return;
    }
    const samePage = router.currentRoute.value.path === sectionToPath[step.section];
    if (!sectionToPath[step.section]) { state.status = "error"; state.error = "不支持的工具页面：" + step.section; return; }
    await gotoSection(step.section);
    if (samePage && handlers.has(step.section)) await consumeIfCurrent(step.section, handlers.get(step.section)!);
  }

  function currentStep(): AgentStep | null {
    if (state.status !== "running") return null;
    if (state.index < 0 || state.index >= state.steps.length) return null;
    return state.steps[state.index] || null;
  }

  async function advance() {
    if (state.status !== "running") return;
    state.index += 1;

    // 跳过 chat 步骤
    while (state.index < state.steps.length) {
      const s = state.steps[state.index];
      if (s && s.section && s.section !== "chat") break;
      state.index += 1;
    }

    if (state.index >= state.steps.length) {
      state.status = "finished";
      return;
    }

    const next = state.steps[state.index];
    if (next?.section) {
      await dispatch(next);
    }
  }

  /** 页面侧调用：若当前轮到本页处理，则执行 handler，并推进到下一步 */
  async function consumeIfCurrent(sectionId: string, handler: (step: AgentStep) => Promise<void> | void) {
    handlers.set(sectionId, handler);
    if (getCurrentInstance()) onUnmounted(() => { if (handlers.get(sectionId) === handler) handlers.delete(sectionId); });
    const step = currentStep();
    if (!step) return false;
    if (step.section !== sectionId) return false;
    const token = `${runId}:${state.index}`;
    if (claim === token) return false;
    claim = token;
    try {
      await handler(step);
      if (token !== `${runId}:${state.index}` || state.status !== "running") return false;
      await advance();
      return true;
    } catch (e: any) {
      if (token !== `${runId}:${state.index}`) return false;
      state.status = "error";
      state.error = e?.message || String(e);
      return false;
    }
  }

  return {
    state: readonly(state),
    reset,
    start,
    currentStep,
    advance,
    consumeIfCurrent,
  };
}
