<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useTargetsStore } from "../stores/targets";
import TargetDialog from "../components/TargetDialog.vue";
import {
  targetScopeChips, targetSummary,
  type TrainingTarget, type TrainingTargetInput,
} from "../api/client";

const store = useTargetsStore();
const editing = ref<TrainingTarget | null>(null);
const showDialog = ref(false);

onMounted(() => store.load());

function openCreate() {
  editing.value = null;
  showDialog.value = true;
}

function openEdit(t: TrainingTarget) {
  editing.value = t;
  showDialog.value = true;
}

async function onSave(v: TrainingTargetInput) {
  if (editing.value) {
    await store.update(editing.value.id, v);
  } else {
    await store.create(v);
  }
  showDialog.value = false;
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1 class="page-title">Training targets</h1>
      <div class="page-sub">
        Define goals like "workers @ 4:00 ≥ 35". Applicable targets are evaluated on every match
        and shown on the match detail. Pass-rate trends coming.
      </div>
    </div>
    <button class="btn primary" @click="openCreate">+ New target</button>
  </div>

  <div v-if="store.loading" class="empty">Loading…</div>

  <div v-else-if="store.items.length === 0" class="empty">
    <h2>No targets yet</h2>
    <div>Click <strong>+ New target</strong> to define your first training goal.</div>
  </div>

  <div v-else class="target-list">
    <div v-for="t in store.items" :key="t.id" class="target-card" :class="{ disabled: !t.enabled }">
      <div class="target-main">
        <div class="target-name">{{ t.name }}</div>
        <div class="target-summary mono">{{ targetSummary(t) }}</div>
        <div class="target-scope">
          <span v-for="c in targetScopeChips(t)" :key="c" class="tag">{{ c }}</span>
        </div>
      </div>
      <div class="target-actions">
        <label class="toggle">
          <input type="checkbox" :checked="t.enabled" @change="store.toggleEnabled(t)" />
          <span class="toggle-track"><span class="toggle-thumb" /></span>
        </label>
        <button class="btn" @click="openEdit(t)">Edit</button>
        <button class="btn danger" @click="store.remove(t.id)">Delete</button>
      </div>
    </div>
  </div>

  <TargetDialog
    v-if="showDialog"
    :target="editing"
    @save="onSave"
    @close="showDialog = false"
  />
</template>
