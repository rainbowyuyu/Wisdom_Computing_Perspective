import { computed, reactive, toRefs } from "vue";

export interface FormulaItem {
  id: number;
  latex: string;
  note?: string | null;
  solution_title?: string | null;
  step_count?: number;
  video_url?: string | null;
}

interface FormulasState {
  items: FormulaItem[];
  loading: boolean;
  error: string | null;
}

export function useFormulasStore() {
  const state = reactive<FormulasState>({
    items: [],
    loading: false,
    error: null,
  });

  async function reload() {
    state.loading = true;
    state.error = null;
    try {
      const res = await fetch("/api/formulas/list/me", {
        method: "GET",
      });
      const data = await res.json();
      if(res.status===401){state.items=[];state.error='登录后可阅读已保存的算式、题解与动画。';return;}
      if (data.status === "success" && Array.isArray(data.data)) {
        state.items = data.data;
      } else {
        state.error = String(data.message ?? "加载失败");
      }
    } catch (e: any) {
      state.error = e?.message || "网络错误";
    } finally {
      state.loading = false;
    }
  }

  const isEmpty = computed(
    () => !state.loading && state.items.length === 0 && !state.error,
  );

  return {
    ...toRefs(state),
    isEmpty,
    reload,
  };
}

