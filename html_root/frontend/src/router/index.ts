import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  { path: "/admin", name: "admin", component: () => import("../views/AdminPage.vue") },
  { path: "/home", redirect: "/" },
  {
    path: "/",
    name: "home",
    component: () => import("../views/HomePage.vue")
  },
  {
    path: "/agent",
    name: "agent",
    component: () => import("../views/AgentPage.vue")
  },
  {
    path: "/detect",
    name: "detect",
    component: () => import("../views/DetectPage.vue")
  },
  {
    path: "/my-formulas",
    name: "my-formulas",
    component: () => import("../views/MyFormulasPage.vue")
  },
  {
    path: "/calculate",
    name: "calculate",
    component: () => import("../views/CalculatePage.vue")
  },
  {
    path: "/examples",
    name: "examples",
    component: () => import("../views/ExamplesPage.vue")
  },
  {
    path: "/devtools",
    name: "devtools",
    component: () => import("../views/DevtoolsPage.vue")
  },
  {
    path: "/help",
    name: "help",
    component: () => import("../views/HelpPage.vue")
  }
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition || { top: 0, left: 0 };
  }
});

