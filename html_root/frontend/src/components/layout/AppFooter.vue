<template>
  <footer class="app-footer">
    <div class="footer-content">
      <div class="footer-brand">
        <h3>
          <img
            src="/static/assets/智算视界_avatar.svg"
            alt="Logo"
            width="32"
          />
          智算视界
        </h3>
        <p>
          基于 AI 视觉识别与 Manim 动态引擎的下一代数学可视化计算平台。致力于降低数学学习门槛，让抽象公式触手可及。
        </p>
        <div class="social-links">
          <a
            href="https://github.com/rainbowyuyu/Wisdom_Computing_Perspective"
            target="_blank"
            class="social-link"
            title="GitHub"
          >
            <i class="fa-brands fa-github" />
          </a>
          <a
            href="https://www.bilibili.com/video/BV1n3dGYJEEJ/"
            target="_blank"
            class="social-link"
            title="Bilibili"
          >
            <i class="fa-brands fa-bilibili" />
          </a>
          <a
            href="mailto:rainbowyu619@gmail.com"
            class="social-link"
            title="Email"
          >
            <i class="fa-solid fa-envelope" />
          </a>
        </div>
      </div>

      <div class="footer-column">
        <h4>产品功能</h4>
        <ul>
          <li>
            <a href="javascript:void(0)" @click.prevent="goSection('detect')">智能识别</a>
          </li>
          <li>
            <a href="javascript:void(0)" @click.prevent="goSection('calculate')">动态计算</a>
          </li>
          <li>
            <a href="javascript:void(0)" @click.prevent="goSection('examples')">教学案例库</a>
          </li>
          <li>
            <a href="javascript:void(0)" @click.prevent="goSection('agent')">智能体</a>
          </li>
        </ul>
      </div>

      <div class="footer-column">
        <h4>资源支持</h4>
        <ul>
          <li>
            <a href="javascript:void(0)" @click.prevent="goSection('help')">使用文档</a>
          </li>
          <li>
            <a href="javascript:void(0)" @click.prevent="openDoc('api_doc.md', 'API 文档')">API 文档</a>
          </li>
          <li>
            <a href="javascript:void(0)" @click.prevent="openDoc('terms.md', '服务协议')">服务协议</a>
          </li>
          <li>
            <a href="javascript:void(0)" @click.prevent="openDoc('update.md', '更新日志')">更新日志</a>
          </li>
        </ul>
      </div>

      <div class="footer-column">
        <h4>关于我们</h4>
        <ul>
          <li>
            <a
              href="https://github.com/rainbowyuyu/Wisdom_Computing_Perspective"
              target="_blank"
            >
              项目背景
            </a>
          </li>
          <li>
            <a
              href="https://github.com/rainbowyuyu/Wisdom_Computing_Perspective"
              target="_blank"
            >
              加入我们
            </a>
          </li>
          <li>
            <a
              href="https://github.com/rainbowyuyu/Wisdom_Computing_Perspective"
              target="_blank"
            >
              联系合作
            </a>
          </li>
          <li>
            <a
              href="javascript:void(0)"
              @click.prevent="openDoc('privacy.md', '隐私政策')"
            >
              隐私政策
            </a>
          </li>
        </ul>
      </div>

      <div class="footer-column">
        <h4>开发者工具</h4>
        <ul>
          <li>
            <a href="javascript:void(0)" @click.prevent="goDevtools('latex')">
              LaTeX 编辑器
            </a>
          </li>
          <li>
            <a href="javascript:void(0)" @click.prevent="goDevtools('manim')">
              Manim 工作台
            </a>
          </li>
          <li>
            <a href="javascript:void(0)" @click.prevent="goDevtools('rainbow')">
              rainbow鱼拓展库
            </a>
          </li>
        </ul>
      </div>
    </div>

    <div class="footer-bottom">
      <p>© 2026 智算视界 (Wisdom Computing Perspective) · All rights reserved.</p>
      <p>
        Author:
        <a
          href="https://github.com/rainbowyuyu"
          target="_blank"
          style="color: #94a3b8; text-decoration: none"
        >
          rainbow_yu
        </a>
        |
        <a
          href="https://beian.miit.gov.cn/"
          target="_blank"
          style="color: #94a3b8; text-decoration: none"
        >
          沪ICP备2025156088号-2
        </a>
      </p>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";

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
  router.push(sectionToPath[id] ?? "/");
}

function goDevtools(tool: "latex" | "manim" | "rainbow") {
  router.push("/devtools");
  (window as any).switchDevTool?.(tool);
}

function openDoc(file: string, title: string) {
  (window as any).openDoc?.(file, title);
}
</script>

