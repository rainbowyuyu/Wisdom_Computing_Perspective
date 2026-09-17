<template>
  <div class="app-root">
    <!-- 导航栏 -->
    <nav class="navbar">
      <div class="logo">
        <img src="/static/assets/智算视界_avatar.svg" alt="智算视界" width="80" />
        智算视界
      </div>

      <!-- 全站搜索（桌面端） -->
      <div id="nav-search-wrap" class="nav-search-wrap desktop-nav" style="margin-right: 8px">
        <i class="fa-solid fa-search nav-search-icon" aria-hidden="true" title="全站搜索"></i>
        <input
          v-model="navSearch"
          type="text"
          id="nav-search-input"
          class="nav-search-input"
          placeholder="搜索题解、课包、错题、案例…"
          maxlength="200"
          autocomplete="off"
        />
        <div id="nav-search-dropdown" class="nav-search-dropdown" style="display: none"></div>
      </div>

      <!-- 桌面端导航链接 -->
      <div class="nav-links desktop-nav">
        <button
          v-for="item in navItems"
          :key="item.id"
          class="nav-btn"
          :class="{ active: currentSection === item.id }"
          @click="setSection(item.id)"
        >
          <span v-if="item.icon" :class="item.icon"></span>
          {{ item.label }}
        </button>
        <button class="nav-btn" @click="openSettings()" title="系统设置">
          <i class="fa-solid fa-gear"></i>
        </button>
      </div>

      <!-- 移动端汉堡按钮 -->
      <button class="mobile-menu-btn" @click="toggleMobileMenu">
        <i class="fa-solid fa-bars"></i>
      </button>

      <div class="auth-buttons desktop-auth">
        <button v-if="!isLoggedIn" class="login-btn" @click="openAuthModal">登录 / 注册</button>
        <span
          id="user-display"
          class="header-user-display"
          v-show="isLoggedIn"
          style="display: inline-flex; align-items: center; gap: 6px"
        >
          <img
            id="header-user-avatar"
            class="header-user-avatar"
            :src="userAvatar"
            alt=""
            v-show="!!userAvatar"
            style="
              width: 28px;
              height: 28px;
              border-radius: 50%;
              object-fit: cover;
              cursor: pointer;
            "
            @click="openSettings('profile')"
            title="账户与资料"
          />
          <i
            class="fa-regular fa-user-circle header-user-icon"
            id="header-user-icon"
            style="cursor: pointer"
            @click="openSettings('profile')"
            title="账户与资料"
          ></i>
          <span id="username-span" class="header-username">{{ username }}</span>
          <i
            class="fa-solid fa-arrow-right-from-bracket header-logout-icon"
            style="cursor: pointer; margin-left: 10px"
            @click="logout"
            title="退出"
          ></i>
        </span>
      </div>
    </nav>

    <!-- 移动端全屏菜单 -->
    <div
      id="mobile-menu-overlay"
      class="mobile-menu-overlay"
      v-show="mobileMenuVisible"
      @click.self="toggleMobileMenu"
    >
      <div class="mobile-menu-content">
        <span class="close-mobile-menu" @click="toggleMobileMenu">&times;</span>

        <div class="mobile-nav-links">
          <button
            v-for="item in navItems"
            :key="item.id"
            @click="mobileNavClick(item.id)"
          >
            {{ item.label }}
          </button>
          <button @click="() => { openSettings(); toggleMobileMenu(); }">系统设置</button>
        </div>

        <div class="mobile-auth-section">
          <button class="login-btn full-width" @click="() => { openAuthModal(); toggleMobileMenu(); }">
            登录 / 注册
          </button>
        </div>
      </div>
    </div>

    <!-- 顶部更新消息：v0.4.4 -->
    <div class="agent-update-banner" id="agent-update-banner" v-show="showAgentBanner">
      <span class="agent-update-text">
        新功能：分步解题、教学课包与错题复习已打通，让学习与创作连起来
      </span>
      <a
        href="javascript:void(0)"
        class="agent-update-detail"
        title="查看更新详情（定位到 v0.4.4）"
        @click="openUpdateDoc"
      >
        v0.4.4 更新详情
      </a>
      <button
        type="button"
        class="agent-update-close"
        @click="closeAgentBanner"
        title="关闭"
        aria-label="关闭"
      >
        <i class="fa-solid fa-times"></i>
      </button>
    </div>

    <!-- 主体：使用路由视图承载各页面 -->
    <main class="container">
      <RouterView v-slot="{ Component }">
        <Transition name="fade-page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>

    <AppFooter />
    <FloatingPanel />
    <AuthDialog ref="authDialog" @signed-in="signedIn" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { getLegacyApp } from "./utils/legacy-bridge";
import AppFooter from "./components/layout/AppFooter.vue";
import FloatingPanel from "./components/layout/FloatingPanel.vue";
import AuthDialog from "./components/layout/AuthDialog.vue";
const authDialog=ref<InstanceType<typeof AuthDialog>|null>(null);
function signedIn(name:string){username.value=name;isLoggedIn.value=true;window.dispatchEvent(new CustomEvent('auth-state-change',{detail:{username:name}}));}

type SectionId =
  | "home"
  | "agent"
  | "detect"
  | "my-formulas"
  | "calculate"
  | "examples"
  | "devtools"
  | "help";

const navToPath: Record<SectionId, string> = {
  home: "/",
  agent: "/agent",
  detect: "/detect",
  "my-formulas": "/my-formulas",
  calculate: "/calculate",
  examples: "/examples",
  devtools: "/devtools",
  help: "/help"
};

const route = useRoute();
const router = useRouter();

const currentSection = computed<SectionId>(() => {
  const path = route.path;
  for (const [id, p] of Object.entries(navToPath)) {
    if (p === path) {
      return id as SectionId;
    }
  }
  return "home";
});

const navSearch = ref("");

const isLoggedIn = ref(false);
const username = ref("");
const userAvatar = ref("");

const mobileMenuVisible = ref(false);
const showAgentBanner = ref(localStorage.getItem("wisdom.release.dismissed")!=="0.4.4");

const navItems = [
  { id: "home", label: "首页" },
  { id: "agent", label: "智能体" },
  { id: "detect", label: "智能识别" },
  { id: "my-formulas", label: "我的算式" },
  { id: "calculate", label: "动态计算" },
  { id: "examples", label: "教学案例" },
  { id: "devtools", label: "开发者工具" },
  { id: "help", label: "帮助" }
] as const;

function setSection(id: (typeof navItems)[number]["id"]) {
  const path = navToPath[id] ?? "/";
  router.push(path);
}

function mobileNavClick(id: (typeof navItems)[number]["id"]) {
  setSection(id);
  mobileMenuVisible.value = false;
}

function toggleMobileMenu() {
  mobileMenuVisible.value = !mobileMenuVisible.value;
}

function openSettings(section?: string) {
  console.log("openSettings", section);
}

function openAuthModal() {
  authDialog.value?.show();
}

async function logout() {
  const response=await fetch('/api/logout',{method:'POST',credentials:'include'});
  if(response.ok){isLoggedIn.value=false;username.value='';window.dispatchEvent(new CustomEvent('auth-state-change',{detail:{username:null}}));window.dispatchEvent(new CustomEvent('formula-library-updated'));}
}

function closeAgentBanner() {
  showAgentBanner.value = false;
  localStorage.setItem("wisdom.release.dismissed","0.4.4");
}

function openUpdateDoc() {
  (window as any).openDoc?.("update.md","更新日志","update-v-0.4.4");
}

function scrollToSelector(selector: string) {
  const el = document.querySelector(selector);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function startTutorial() {
  console.log("start tutorial");
}

let disposeSiteSearch: (() => void) | undefined;
let appDisposed=false;
onUnmounted(()=>{appDisposed=true;disposeSiteSearch?.();});
onMounted(() => {
  const searchUrl='/static/js/site-search.js';
  import(/* @vite-ignore */ searchUrl).then(module=>{if(!appDisposed)disposeSiteSearch=module.initNavSearch();}).catch(()=>{});
  (window as any).toggleAuthModal=(show:boolean)=>{if(show)openAuthModal();};
  fetch('/api/user/me',{credentials:'include'}).then(r=>r.ok?r.json():null).then(data=>{if(data?.username)signedIn(data.username);}).catch(()=>{});
  // 将部分操作暴露给全局，以兼容旧代码中的 window.App 调用
  const app = getLegacyApp();
  app.__setCurrentSection = (id: string) => {
    const exists = navItems.find((item) => item.id === id);
    if (exists) {
      setSection(exists.id);
    }
  };
  app.__openSettings = openSettings;
  app.__toggleMobileMenu = toggleMobileMenu;
});
</script>

<style scoped>
.fade-page-enter-active,
.fade-page-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}

.fade-page-enter-from,
.fade-page-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.placeholder-section {
  padding: 2rem 1.5rem;
  border-radius: 16px;
  border: 1px dashed rgba(148, 163, 184, 0.6);
  background: radial-gradient(circle at top left, rgba(59, 130, 246, 0.14), transparent),
    radial-gradient(circle at bottom right, rgba(139, 92, 246, 0.14), transparent);
  color: #e5e7eb;
}

.placeholder-section h2 {
  margin-bottom: 0.5rem;
  font-size: 1.4rem;
}

.placeholder-section p {
  margin: 0;
  font-size: 0.95rem;
  color: #9ca3af;
}
</style>

<style>
/* 在 Vue 版本中，路由负责页面切换，不再用 active-section 控制显隐 */
.app-root .section {
  display: block;
}
</style>

