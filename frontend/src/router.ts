import { createRouter, createWebHistory } from "vue-router";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/matches" },
    { path: "/matches", component: () => import("./pages/MatchListPage.vue"), name: "matches" },
    { path: "/matches/:id", component: () => import("./pages/MatchDetailPage.vue"), name: "match", props: true },
    { path: "/trends", component: () => import("./pages/TrendsPage.vue"), name: "trends" },
    { path: "/targets", component: () => import("./pages/TargetsPage.vue"), name: "targets" },
    { path: "/tags", component: () => import("./pages/TagsPage.vue"), name: "tags" },
    { path: "/settings", component: () => import("./pages/SettingsPage.vue"), name: "settings" },
  ],
});
