<template>
  <section id="help" class="section">
    <h2 class="section-title">常见问题与指南</h2>
    <div class="help-container" style="max-width: 800px; margin: 0 auto">
      <!-- 帮助内搜索：实时过滤下方问答 -->
      <div class="help-search-bar">
        <div class="help-search-inner">
          <i class="fa-solid fa-magnifying-glass help-search-icon"></i>
          <input
            id="help-search-input"
            type="search"
            placeholder="在帮助中搜索，例如：智能体 / 教学案例 / 动画超时…"
            autocomplete="off"
            v-model="query"
          />
        </div>
        <p class="help-search-hint">
          输入关键字后，将自动筛选下方问题，并展开包含该关键字的问答。
        </p>
      </div>

      <!-- 智能体入口 -->
      <div class="tutorial-banner agent-help-banner" @click="goToAgent">
        <div class="banner-icon">
          <i class="fa-solid fa-robot"></i>
        </div>
        <div class="banner-content">
          <h3>智能体</h3>
          <p>
            用自然语言描述需求，自动跳转到识别、计算或开发者工具并执行对应任务。
          </p>
        </div>
        <div class="banner-action">
          <i class="fa-solid fa-wand-magic-sparkles"></i>
          去使用
        </div>
      </div>

      <div class="tutorial-banner" @click="startTutorial">
        <div class="banner-icon">
          <i class="fa-solid fa-graduation-cap"></i>
        </div>
        <div class="banner-content">
          <h3>新手入门指南</h3>
          <p>点击这里开启交互式教学，30 秒掌握核心功能。</p>
        </div>
        <div class="banner-action">
          <i class="fa-solid fa-circle-play"></i>
          观看
        </div>
      </div>

      <details
        v-for="item in filteredFaq"
        :key="item.id"
        :open="item.shouldOpen"
      >
        <summary>{{ item.q }}</summary>
        <p v-html="item.a"></p>
      </details>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const query = ref("");

type FaqItem = { id: string; q: string; a: string };

const faq: FaqItem[] = [
  {
    id: "agent-role",
    q: "智能体 & 按角色快速开始怎么用？",
    a: `
      <b>智能体</b> 是本站的“一句话调度”入口。你只需用自然语言描述想做的事（或上传一张公式/题目图片），系统会理解意图并自动：
      <br />· 跳转到【智能识别 / 动态计算 / 开发者工具 / 我的算式 / 教学案例】等页面；
      <br />· 预填识别到的 LaTeX 公式，或填入 Manim 代码，必要时自动执行；
      <br />· 对整道题目先给出 <b>文字版解题步骤</b>，再生成可视化演示。
      <br /><br />
      <b>按角色快速开始</b> 位于首页 Hero 下方，提供 学生 / 教师 / 内容创作者 / 开发者 四种入口：
      <br />· 点击「用智能体执行」：为该角色预填推荐提示词，一键唤起智能体完成整条路径；
      <br />· 点击「观看操作流程」：不调用智能体，只通过交互式教程演示完整操作步骤。
    `,
  },
  {
    id: "handwriting",
    q: "系统支持哪些手写格式和数学内容？",
    a: `
      目前系统针对 <b>线性代数</b> 进行了深度优化。
      <br />✅ <b>完美支持：</b> 矩阵、行列式、基础代数运算、微积分符号（积分、极限）等。
      <br />💡 <b>建议：</b> 书写时保持字符间距，避免连笔；深色墨水 + 白纸效果最佳。
    `,
  },
  {
    id: "ocr-fix",
    q: "识别结果不准确怎么办？",
    a: `
      AI 识别可能受光线、角度或字迹影响。如果识别有误，无需重新上传，可以直接用内置 <b>双向编辑</b>：
      <br />1）<b>可视化修改：</b> 点击公式像在 Word 中一样修改；
      <br />2）<b>代码修改：</b> 在「查看源码」中修改 LaTeX，会实时同步。
    `,
  },
  {
    id: "upload",
    q: "上传图片有什么要求？",
    a: `
      支持 JPG/PNG。建议图片清晰、光线均匀、无阴影遮挡；尽量让公式位于中心，背景干净（避免格纹/复杂背景）。
    `,
  },
];

const filteredFaq = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) {
    return faq.map((x, idx) => ({ ...x, shouldOpen: idx === 0 }));
  }
  return faq
    .filter((x) => (x.q + " " + x.a).toLowerCase().includes(q))
    .map((x) => ({ ...x, shouldOpen: true }));
});

function goToAgent() {
  router.push("/agent");
}

function startTutorial() {
  (window as any).startTutorial?.();
}
</script>
