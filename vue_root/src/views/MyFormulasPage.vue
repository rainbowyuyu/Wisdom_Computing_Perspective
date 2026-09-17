<template>
  <section id="my-formulas" class="section">
    <h2 class="section-title">我的算式库</h2>
    <div class="container formulas-container" style="max-width: 1000px">
      <div class="formulas-sub-nav">
        <button
          type="button"
          class="formulas-sub-tab"
          :class="{ active: activeTab === 'formulas' }"
          @click="activeTab = 'formulas'"
        >
          算式库
        </button>
        <button
          type="button"
          class="formulas-sub-tab"
          :class="{ active: activeTab === 'scripts' }"
          @click="activeTab = 'scripts'"
        >
          动画脚本库
        </button>
        <button
          type="button"
          class="formulas-sub-tab"
          :class="{ active: activeTab === 'templates' }"
          @click="activeTab = 'templates'"
        >
          智能体模板
        </button>
      </div>

      <!-- 算式库面板（Vue 化渲染） -->
      <div
        v-show="activeTab === 'formulas'"
        class="formulas-panel glass-panel"
      >
        <div class="formulas-panel-header">
          <h3 class="formulas-panel-title">公式与题解</h3>
          <button
            class="action-btn secondary formulas-refresh-btn"
            :disabled="loading"
            @click="reload"
          >
            <i class="fa-solid fa-rotate"></i>
            {{ loading ? "加载中…" : "刷新列表" }}
          </button>
        </div>

        <div class="formula-grid">
          <div
            class="formula-card add-new-card"
            style="
              justify-content: center;
              align-items: center;
              border: 2px dashed #cbd5e1;
              cursor: pointer;
              min-height: 180px;
            "
            @click="goToDetect"
          >
            <div
              style="
                font-size: 2.5rem;
                color: var(--primary-color);
                margin-bottom: 0.5rem;
              "
            >
              <i class="fa-solid fa-circle-plus"></i>
            </div>
            <div
              style="
                font-size: 1rem;
                color: var(--text-secondary);
                font-weight: 600;
              "
            >
              新建算式
            </div>
          </div>

          <div
            v-if="loading"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <i class="fa-solid fa-spinner fa-spin"></i>
            <p>正在同步云端数据...</p>
          </div>
          <div
            v-else-if="error"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <p>{{ error }}</p>
          </div>
          <div
            v-else-if="isEmpty"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <p>暂无保存的算式，点击上方卡片去识别添加吧！</p>
          </div>

          <div
            v-for="f in items"
            :key="f.id"
            class="formula-card"
            :class="{ 'solution-card': f.solution_title }"
          >
            <template v-if="f.solution_title">
              <div class="solution-card-body"><span class="solution-card-kind"><i class="fa-solid fa-layer-group"></i> 分步题解</span><h3>{{ f.solution_title }}</h3><p>{{ f.latex }}</p><span class="solution-card-detail">{{ f.step_count }} 个步骤{{ f.video_url ? ' · 含动画' : '' }}</span></div>
              <div class="formula-meta"><button class="solution-card-open" @click="readSolution(f.id)">阅读题解 <i class="fa-solid fa-arrow-right"></i></button><button class="btn-icon delete" title="删除题解" @click="deleteSolution(f.id)"><i class="fa-regular fa-trash-can"></i></button></div>
            </template>
            <div v-else class="formula-preview" :data-formula-id="f.id">
              \\[ {{ f.latex }} \\]
            </div>
            <div v-if="!f.solution_title" class="formula-meta">
              <span class="formula-note" :title="f.note || '未命名'">
                {{ f.note || "未命名" }}
              </span>
              <button class="btn-icon" title="在可视化中使用" @click="useFormula(f.latex)"><i class="fa-solid fa-arrow-right"></i></button>
            </div>
          </div>
        </div>
      </div>

      <!-- 其余两个 Tab 暂时仍保留占位，后续按计划 Vue 化 -->
      <div
        v-show="activeTab === 'scripts'"
        class="formulas-panel glass-panel"
      >
        <div class="formulas-panel-header">
          <h3 class="formulas-panel-title">动画脚本库</h3>
          <button
            class="action-btn secondary formulas-refresh-btn"
            :disabled="scriptsLoading"
            @click="reloadScripts"
          >
            <i class="fa-solid fa-rotate"></i>
            {{ scriptsLoading ? "加载中…" : "刷新列表" }}
          </button>
        </div>

        <div class="formula-grid" id="animation-scripts-list">
          <div
            class="formula-card add-new-card"
            style="
              justify-content: center;
              align-items: center;
              border: 2px dashed #cbd5e1;
              cursor: pointer;
              min-height: 180px;
            "
            @click="goToCalc"
          >
            <div style="font-size: 2.5rem; color: var(--primary-color); margin-bottom: 0.5rem">
              <i class="fa-solid fa-circle-plus"></i>
            </div>
            <div style="font-size: 1rem; color: var(--text-secondary); font-weight: 600">
              去动态计算页生成并保存
            </div>
          </div>

          <div
            v-if="scriptsNeedLogin"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <i class="fa-solid fa-lock"></i>
            <p>请先登录以查看动画脚本库</p>
            <button class="action-btn" @click="toggleAuthModal(true)">立即登录</button>
          </div>
          <div
            v-else-if="scriptsLoading"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <i class="fa-solid fa-spinner fa-spin"></i>
            <p>正在同步云端数据...</p>
          </div>
          <div
            v-else-if="scriptsError"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <p>{{ scriptsError }}</p>
          </div>
          <div
            v-else-if="scripts.length === 0"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <p>暂无保存的脚本。你可以在「动态计算」生成后保存到脚本库。</p>
          </div>

          <div
            v-for="s in scripts"
            :key="s.id"
            class="formula-card"
          >
            <div
              class="formula-preview"
              style="font-size: 0.8rem; text-align: left; justify-content: flex-start; overflow: hidden; white-space: pre-wrap"
            >
              {{ (s.code_preview || s.code || '').slice(0, 160) }}
            </div>
            <div class="formula-meta">
              <span class="formula-note" :title="s.note || '未命名'">
                {{ s.note || "未命名" }}
              </span>
              <div class="formula-actions">
                <button class="btn-icon" title="在云端工作台编辑" @click="editScriptInDevtools(s.id)">
                  <i class="fa-solid fa-pen-to-square"></i>
                </button>
                <button class="btn-icon" title="在云端工作台运行" @click="runScriptInDevtools(s.id)">
                  <i class="fa-solid fa-play"></i>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-show="activeTab === 'templates'"
        class="formulas-panel glass-panel"
      >
        <div class="formulas-panel-header">
          <h3 class="formulas-panel-title">智能体模板</h3>
          <button
            class="action-btn secondary formulas-refresh-btn"
            :disabled="templatesLoading"
            @click="reloadTemplates"
          >
            <i class="fa-solid fa-rotate"></i>
            {{ templatesLoading ? "加载中…" : "刷新列表" }}
          </button>
        </div>

        <div class="formula-grid" id="formulas-agent-templates-list">
          <div
            v-if="templatesNeedLogin"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <i class="fa-solid fa-lock"></i>
            <p>请先登录以查看智能体模板</p>
            <button class="action-btn" @click="toggleAuthModal(true)">立即登录</button>
          </div>
          <div
            v-else-if="templatesLoading"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <i class="fa-solid fa-spinner fa-spin"></i>
            <p>正在同步云端数据...</p>
          </div>
          <div
            v-else-if="templatesError"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <p>{{ templatesError }}</p>
          </div>
          <div
            v-else-if="templates.length === 0"
            class="empty-state"
            style="grid-column: 1 / -1; padding-top: 1rem"
          >
            <p>暂无模板。你可以在智能体中把一段流程「存为模板」。</p>
          </div>

          <div
            v-for="t in templates"
            :key="t.id"
            class="formula-card"
          >
            <div class="formula-preview" style="font-size: 0.9rem; text-align: left; justify-content: flex-start">
              {{ t.name || ("模板#" + t.id) }}
            </div>
            <div class="formula-meta">
              <span class="formula-note" :title="t.name || '未命名'">
                {{ t.name || "未命名" }}
              </span>
              <div class="formula-actions">
                <button class="btn-icon" title="一键运行" @click="runTemplate(t.id)">
                  <i class="fa-solid fa-bolt"></i>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from "vue";
import { getTutor } from "../services/tutor";
import { useRouter } from "vue-router";
import { useFormulasStore } from "../composables/useFormulasStore";

type TabId = "formulas" | "scripts" | "templates";

const activeTab = ref<TabId>("formulas");
const router = useRouter();

const { items, loading, error, isEmpty, reload } = useFormulasStore();
watch(items, async()=>{
  await nextTick();
  const path='/static/js/math-text.js';const {renderFormula,textWithMath}=await import(/* @vite-ignore */ path);
  for(const item of items.value){
    const target=document.querySelector(`[data-formula-id="${item.id}"]`);
    if(target)renderFormula(target,item.latex);
  }
  document.querySelectorAll(".solution-card-body h3,.solution-card-body p").forEach(el=>textWithMath(el,el.textContent));
});
async function readSolution(id: number) {
  const path = '/static/js/solution-library.js';
  try { const library = await import(/* @vite-ignore */ path); await library.openSavedSolution(id); }
  catch (e: any) { error.value=e.message; }
}
async function deleteSolution(id: number) {
  const confirmed = (window as any).showConfirm ? await (window as any).showConfirm('删除这条题解？', '删除题解') : window.confirm('删除这条题解？');
  if (!confirmed) return;
  const path = '/static/js/solution-library.js';
  try { const library = await import(/* @vite-ignore */ path); await library.libraryRequest('/'+id,{method:'DELETE'}); window.dispatchEvent(new CustomEvent('formula-library-deleted',{detail:{id}})); await reload(); }
  catch (e: any) { error.value=e.message; }
}
async function useFormula(latex: string) { const tutor=await getTutor(); tutor.prefillProblem(latex); router.push('/calculate'); }

type ScriptItem = {
  id: number;
  note?: string | null;
  code?: string;
  code_preview?: string;
};

type TemplateItem = {
  id: number | string;
  name?: string | null;
  prompt?: string;
};

const scripts = ref<ScriptItem[]>([]);
const scriptsLoading = ref(false);
const scriptsError = ref("");
const scriptsNeedLogin = ref(false);

const templates = ref<TemplateItem[]>([]);
const templatesLoading = ref(false);
const templatesError = ref("");
const templatesNeedLogin = ref(false);

async function getMeUsername(): Promise<string | null> {
  try {
    const res = await fetch("/api/user/me", { credentials: "include" });
    const data = await res.json();
    if (data?.status === "success" && data.username) return String(data.username);
    return null;
  } catch (_) {
    return null;
  }
}

function toggleAuthModal(show: boolean) {
  (window as any).toggleAuthModal?.(show);
}

function goToDetect() {
  router.push("/detect");
}

function goToCalc() {
  router.push("/calculate");
}

async function reloadScripts() {
  scriptsLoading.value = true;
  scriptsError.value = "";
  scriptsNeedLogin.value = false;
  try {
    const user = await getMeUsername();
    if (!user) {
      scriptsNeedLogin.value = true;
      scripts.value = [];
      return;
    }
    const res = await fetch(
      `/api/animation_scripts/list?username=${encodeURIComponent(user)}`
    );
    const data = await res.json();
    if (data?.status === "success" && Array.isArray(data.data)) {
      scripts.value = data.data;
    } else {
      scriptsError.value = String(data?.message || "加载失败");
    }
  } catch (e: any) {
    scriptsError.value = e?.message || "网络错误";
  } finally {
    scriptsLoading.value = false;
  }
}

async function reloadTemplates() {
  templatesLoading.value = true;
  templatesError.value = "";
  templatesNeedLogin.value = false;
  try {
    const user = await getMeUsername();
    if (!user) {
      templatesNeedLogin.value = true;
      templates.value = [];
      return;
    }
    const res = await fetch(
      `/api/agent_templates/list?username=${encodeURIComponent(user)}`
    );
    const data = await res.json();
    if (data?.status === "success" && Array.isArray(data.data)) {
      templates.value = data.data;
    } else {
      templatesError.value = String(data?.message || "加载失败");
    }
  } catch (e: any) {
    templatesError.value = e?.message || "网络错误";
  } finally {
    templatesLoading.value = false;
  }
}

async function getScriptCodeById(id: number): Promise<string | null> {
  try {
    const user = await getMeUsername();
    if (!user) return null;
    const res = await fetch(
      `/api/animation_scripts/get?id=${id}&username=${encodeURIComponent(user)}`
    );
    const data = await res.json();
    if (data?.status === "success" && data.data?.code) return String(data.data.code);
    return null;
  } catch (_) {
    return null;
  }
}

async function editScriptInDevtools(id: number) {
  const code = await getScriptCodeById(id);
  if (!code) {
    (window as any).showToast?.("脚本加载失败", "error");
    return;
  }
  try {
    sessionStorage.setItem("pending_devtools_manim_code", code);
  } catch (_) {}
  router.push("/devtools");
  // Devtools 页将读取 pending_devtools_manim_code 并打开 manim
}

async function runScriptInDevtools(id: number) {
  const code = await getScriptCodeById(id);
  if (!code) {
    (window as any).showToast?.("脚本加载失败", "error");
    return;
  }
  try {
    sessionStorage.setItem("pending_devtools_manim_code", code);
    sessionStorage.setItem("pending_devtools_manim_autorun", "1");
  } catch (_) {}
  router.push("/devtools");
}

async function getTemplatePromptById(id: number | string): Promise<string | null> {
  try {
    const user = await getMeUsername();
    if (!user) return null;
    const res = await fetch(
      `/api/agent_templates/get?id=${id}&username=${encodeURIComponent(user)}`
    );
    const data = await res.json();
    if (data?.status === "success" && data.data?.prompt) return String(data.data.prompt);
    return null;
  } catch (_) {
    return null;
  }
}

async function runTemplate(id: number | string) {
  const prompt = await getTemplatePromptById(id);
  if (!prompt) {
    (window as any).showToast?.("模板加载失败", "error");
    return;
  }
  try {
    sessionStorage.setItem("pending_agent_prompt", prompt);
  } catch (_) {}
  router.push("/agent");
}

onMounted(() => {
  window.addEventListener('formula-library-updated', reload);
  reload();
  // 提前加载，减少切换 tab 的等待
  reloadScripts();
  reloadTemplates();
});
onBeforeUnmount(()=>window.removeEventListener('formula-library-updated',reload));
</script>
