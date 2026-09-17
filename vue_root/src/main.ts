import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router";

const app = createApp(App);

app.use(router);

// 为了与旧站点的全局函数兼容，这里先挂载一些占位函数，
// 在 Vue 内部会用路由与状态真正实现这些行为。
(window as any).App = (window as any).App || {};

const sectionToPath: Record<string, string> = {
  home: "/",
  agent: "/agent",
  detect: "/detect",
  "my-formulas": "/my-formulas",
  calculate: "/calculate",
  examples: "/examples",
  devtools: "/devtools",
  help: "/help"
};

(window as any).showSection = (sectionId: string) => {
  const targetPath = sectionToPath[sectionId] ?? "/";
  if (router) {
    router.push(targetPath);
  } else if ((window as any).App.__setCurrentSection) {
    (window as any).App.__setCurrentSection(sectionId);
  }
};

(window as any).openSettings = (...args: unknown[]) => {
  (window as any).App.__openSettings && (window as any).App.__openSettings(...args);
};

(window as any).toggleMobileMenu = () => {
  (window as any).App.__toggleMobileMenu &&
    (window as any).App.__toggleMobileMenu();
};

app.mount("#app");


const graphBootstrapUrl = "/static/js/role-graph-bootstrap.js";
import(/* @vite-ignore */ graphBootstrapUrl).catch(error => console.warn("图谱加载失败", error));

const docsUrl="/static/js/docs.js?v=20260917-release-044";
import(/* @vite-ignore */ docsUrl).catch(error=>console.warn("文档组件加载失败",error));
