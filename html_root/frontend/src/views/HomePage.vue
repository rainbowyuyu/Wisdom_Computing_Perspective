<template>
  <section id="home" class="section">
    <div class="hero-decoration">
      <div class="blob blob-1"></div>
      <div class="blob blob-2"></div>
    </div>

    <div class="hero">
      <h1 class="animate-text">
        让数学计算<br />
        <span class="text-gradient">看得见、摸得着</span>
      </h1>

      <p class="subtitle">
        融合 <b>数学公式识别（OCR）</b>、手写公式识别与 <b>Manim</b> 动态引擎。<br />
        将枯燥的公式转化为直观的数学动画与可视化过程，服务学生、老师与开发者。
      </p>

      <div class="hero-btns">
        <button class="cta-btn primary" @click="goSection('calculate')">
          <i class="fa-solid fa-wand-magic-sparkles"></i>
          开始分步解题
        </button>
        <button class="cta-btn secondary" @click="goSection('detect')">
          立即体验
          <i class="fa-solid fa-arrow-right"></i>
        </button>
        <button class="cta-btn secondary" @click="goSection('examples')">
          <i class="fa-solid fa-play"></i>
          观看演示
        </button>
      </div>

      <div class="hero-links">
        <span class="tutorial-link" @click="goSection('agent')">
          <i class="fa-solid fa-robot"></i>
          用一句话完成识别与动画
        </span>
        <span class="tutorial-link" @click="scrollToSelector('.site-graph-section')">
          <i class="fa-solid fa-diagram-project"></i>
          查看全站知识图谱
        </span>
        <span class="tutorial-link" @click="startTutorial">
          <i class="fa-regular fa-circle-question"></i>
          30 秒教程
        </span>
      </div>
    </div>

    <div
      class="agent-feature-strip"
      @click="goSection('agent')"
    >
      <div class="agent-feature-strip-inner">
        <span class="agent-feature-badge">NEW</span>
        <div class="agent-feature-strip-content">
          <h3>智能体</h3>
          <p>
            用自然语言描述需求，自动跳转并执行：识别公式、生成动画、打开 LaTeX / Manim 工作台等，一站调度全站能力。
          </p>
        </div>
        <i class="fa-solid fa-chevron-right agent-feature-arrow"></i>
      </div>
    </div>

    <section class="role-start-section site-graph-section" aria-labelledby="role-start-title">
      <div id="section-home-roles"></div>
      <div class="role-universe-bg" aria-hidden="true"></div>
      <div class="role-start-header">
        <span class="role-start-badge">
          <i class="fa-solid fa-diagram-project"></i>
          知识图谱
        </span>
        <h2 id="role-start-title">全站知识图谱</h2>
        <p class="role-start-subtitle">点击任意节点跳转功能，探索网站全部能力</p>
      </div>
      <RoleGraph3D />
      <div id="role-flow-panel" class="role-flow-panel">
        <div class="role-flow-panel-inner">
          <button
            type="button"
            class="role-flow-close"
            id="role-flow-back"
            aria-label="关闭"
          >
            <i class="fa-solid fa-xmark"></i>
          </button>
          <h3 id="role-flow-title">推荐路径</h3>
          <div id="role-flow-chain" class="role-flow-chain"></div>
          <p class="role-flow-hint">点击「进入」跳转到对应页面，逐步熟悉网站功能</p>
        </div>
      </div>
    </section>

    <div class="features-grid">
      <div class="feature-card" @click="goSection('agent')">
        <span class="feature-card-badge">推荐</span>
        <div class="feature-icon-box">
          <i class="fa-solid fa-robot"></i>
        </div>
        <h3>智能体 · AI 数学助手</h3>
        <p>
          用一句话调用全站功能：从数学公式识别、Manim 数学动画到矩阵与线性代数计算，一位
          AI 数学助手帮你完成整套流程。
        </p>
      </div>
      <div class="feature-card" @click="goSection('detect')">
        <div class="feature-icon-box">
          <i class="fa-solid fa-eye"></i>
        </div>
        <h3>视觉识别 · 数学 OCR</h3>
        <p>
          支持手写公式与图片上传，毫秒级精准完成数学公式识别与 LaTeX
          转换，复杂矩阵和推导过程也能一键提取。
        </p>
      </div>
      <div class="feature-card" @click="goSection('calculate')">
        <div class="feature-icon-box">
          <i class="fa-solid fa-wand-magic-sparkles"></i>
        </div>
        <h3>动态推演 · 数学可视化</h3>
        <p>
          基于 Python Manim
          引擎，像线性代数计算器一样实时演示矩阵变换、行列式展开与几何推导全过程。
        </p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";
import RoleGraph3D from "../components/home/RoleGraph3D.vue";

const router = useRouter();

type SectionId =
  | "home"
  | "agent"
  | "detect"
  | "my-formulas"
  | "calculate"
  | "examples"
  | "devtools"
  | "help";

const sectionToPath: Record<SectionId, string> = {
  home: "/",
  agent: "/agent",
  detect: "/detect",
  "my-formulas": "/my-formulas",
  calculate: "/calculate",
  examples: "/examples",
  devtools: "/devtools",
  help: "/help"
};

function goSection(id: SectionId) {
  const path = sectionToPath[id] ?? "/";
  router.push(path);
}

function scrollToSelector(selector: string) {
  const el = document.querySelector(selector);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function startTutorial() {
  (window as any).startTutorial?.();
}
</script>

