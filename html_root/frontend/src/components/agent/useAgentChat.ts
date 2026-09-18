import { ref, computed } from "vue";
import { useAgentRunnerStore } from "../../stores/agentRunner";

export type AgentRole = "user" | "assistant";

export interface AgentMessage {
  role: AgentRole;
  /** 渲染用 HTML（纯文本会在组件中转义） */
  html: string;
  /** 原始文本（用于继续上下文） */
  raw?: string;
  /** 后端返回的完整数据，便于“重新执行”等扩展 */
  data?: any;
}

export interface AgentStep {
  section: string;
  reply?: string;
  devtool?: string;
  devtool_action?: string;
  action?: string;
  trigger?: "recognize" | "generate";
  save_to_formulas?: boolean;
  operation?: string;
  examples_filter?: string;
  settings_section?: string;
  setting_key?: string;
  setting_value?: unknown;
  formula?: string;
  fill_manim_code?: string;
}

export interface AgentExecuteResponse {
  status: "success" | "error";
  message?: string;
  prompt?: string;
  steps?: AgentStep[];
  isError?: boolean;
  image_base64?: string | null;
}

function escapeHtml(s: string): string {
  if (!s) return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 基于原版 agent.js 的 LaTeX 清洗逻辑的精简版 */
function sanitizeLatexForMathlive(latex: string | undefined | null): string {
  if (latex == null || typeof latex !== "string") return "";
  let s = latex
    .trim()
    .replace(/^```(?:latex)?\s*/g, "")
    .replace(/\s*```\s*$/g, "")
    .replace(/^\\\[\s]*/g, "")
    .replace(/\s*\\\]\s*$/g, "")
    .replace(/^\$\$\s*/g, "")
    .replace(/\s*\$\$\s*$/g, "")
    .replace(/^\\\(\s*/g, "")
    .replace(/\s*\\\)\s*$/g, "")
    .replace(/\\\(/g, "")
    .replace(/\\\)/g, "")
    .replace(/\\\\/g, "\\")
    .replace(/\\n/g, " ")
    .replace(/\r\n?|\n/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return s;
}

// steps 的“跨页执行”交给 agentRunnerStore（避免智能体直接操作其它页面 DOM）

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

  const messages = ref<AgentMessage[]>([]);
  const loading = ref(false);
  const attachedImage = ref<File | null>(null);
  const imagePreviewUrl = ref<string | null>(null);
  const sidebarCollapsed = ref(false);
let activeRequest: AbortController | null = null;
let requestVersion = 0;

export function useAgentChat() {
  const runner = useAgentRunnerStore();


  const hasMessages = computed(() => messages.value.length > 0);

  function setSidebarCollapsed(v: boolean) {
    sidebarCollapsed.value = v;
  }

  function setAttachedImage(file: File | null) {
    attachedImage.value = file;
    if (imagePreviewUrl.value) {
      URL.revokeObjectURL(imagePreviewUrl.value);
      imagePreviewUrl.value = null;
    }
    if (file) {
      imagePreviewUrl.value = URL.createObjectURL(file);
    }
  }

  function clearChat() {
    requestVersion++;
    activeRequest?.abort();
    activeRequest = null;
    loading.value = false;
    messages.value = [];
  }

  function appendUserMessage(text: string) {
    messages.value.push({
      role: "user",
      html: escapeHtml(text),
      raw: text,
    });
  }

  function appendAssistantRawHtml(html: string, data?: any) {
    messages.value.push({
      role: "assistant",
      html,
      raw: html,
      data,
    });
  }

  function getLastContext() {
    let lastUser = "";
    let lastAssistant = "";
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i];
      if (m.role === "assistant") {
        lastAssistant = (m.raw || m.html || "").slice(0, 280);
        if (i > 0 && messages.value[i - 1].role === "user") {
          const u = messages.value[i - 1];
          lastUser = (u.raw || u.html || "").slice(0, 280);
        }
        break;
      }
    }
    return {
      last_user_message: lastUser || undefined,
      last_assistant_message: lastAssistant || undefined,
    };
  }

  async function execute(promptInput: string) {
    if (loading.value) return;
    const g: any = window;
    // 登录检查依旧走旧逻辑，避免与现有鉴权重复实现
    if (typeof g.getCurrentUser === "function" && !g.getCurrentUser()) {
      if (typeof g.toggleAuthModal === "function") {
        g.toggleAuthModal(true);
      }
      return;
    }

    const trimmed = (promptInput || "").trim();
    const file = attachedImage.value;

    if (!trimmed && !file) {
      if (typeof g.showToast === "function") {
        g.showToast("请输入需求描述或上传图片", "error");
      }
      return;
    }

    let prompt = trimmed;
    if (!prompt && file) {
      prompt = "请根据这张图片的内容进行操作（识别、解题或生成演示）。";
    }

    let imageBase64: string | null = null;
    if (file) {
      try {
        imageBase64 = await fileToBase64(file);
      } catch (e) {
        if (typeof g.showToast === "function") {
          g.showToast("图片读取失败", "error");
        }
        return;
      }
    }

    const ctx = getLastContext();
    const version = ++requestVersion;
    activeRequest = new AbortController();
    appendUserMessage(prompt);
    loading.value = true;

    // loading 占位
    appendAssistantRawHtml(
      `<div class="agent-loading-dots"><span></span><span></span><span></span></div>`
    );

    try {
      const res = await fetch("/api/agent/execute", {
        method: "POST",
        signal: activeRequest.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          image_base64: imageBase64,
          ...ctx,
        }),
      });
      if (!res.ok) throw new Error(`请求失败（${res.status}）`);
      const data: AgentExecuteResponse = await res.json();
      if (version !== requestVersion) return;

      // 替换 loading
      messages.value.pop();

      if (data.status === "success") {
        const steps = Array.isArray(data.steps) ? data.steps : [];
        const first = steps[0];
        const isChatOnly =
          steps.length === 1 && first?.section === "chat" && first.reply;

        if (isChatOnly && first?.reply) {
          // 简化处理：直接展示文本；如需 markdown，可在组件中统一处理
          appendAssistantRawHtml(escapeHtml(first.reply), data);
        } else {
          const replyText =
            first?.reply ||
            steps.find((s) => s.reply && s.reply.trim())?.reply ||
            "";
          if (replyText) {
            appendAssistantRawHtml(escapeHtml(replyText), data);
          } else {
            appendAssistantRawHtml(
              "已生成执行计划，将依次调用对应工具。",
              data
            );
          }

          // 有工具调用时，延时执行站内跳转与填充
          if (steps.length > 0) {
            if (typeof g.showToast === "function") {
              g.showToast("即将跳转并调用工具，请稍候…", "info");
            }
            await delay(150);
            await runner.start(steps);
          }
        }
      } else {
        appendAssistantRawHtml(
          `<p class="agent-error">${escapeHtml(
            data.message || "执行失败"
          )}</p>`,
          { isError: true, prompt, image_base64: imageBase64 }
        );
      }
    } catch (e: any) {
      if (version !== requestVersion || e?.name === "AbortError") return;
      messages.value.pop();
      appendAssistantRawHtml(
        `<p class="agent-error">网络错误：${escapeHtml(
          e?.message || "请稍后重试"
        )}</p>`,
        { isError: true, prompt, image_base64: imageBase64 }
      );
    } finally {
      if (version === requestVersion) {
      activeRequest = null;
      loading.value = false;
      // 发送后清空图片
      setAttachedImage(null);
      }
    }
  }

  return {
    messages,
    loading,
    attachedImage,
    imagePreviewUrl,
    sidebarCollapsed,
    hasMessages,
    setSidebarCollapsed,
    setAttachedImage,
    clearChat,
    execute,
  };
}

