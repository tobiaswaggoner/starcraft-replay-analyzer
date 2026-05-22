<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "./api/client";

const health = ref<{ replay_dir: string | null } | null>(null);
onMounted(async () => {
  try { health.value = await api.health(); } catch { /* offline */ }
});
</script>

<template>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-dot" />
        <span>Replay Analyzer</span>
      </div>
      <router-link to="/matches" class="nav-link">
        <span>Matches</span>
      </router-link>
      <router-link to="/trends" class="nav-link">
        <span>Trends</span>
      </router-link>
      <router-link to="/targets" class="nav-link">
        <span>Targets</span>
      </router-link>
      <router-link to="/tags" class="nav-link">
        <span>Tags</span>
      </router-link>
      <router-link to="/settings" class="nav-link">
        <span>Settings</span>
      </router-link>
      <div class="sidebar-footer">
        <div v-if="health?.replay_dir">Watching folder</div>
        <div v-else>No replay folder set</div>
      </div>
    </aside>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>
