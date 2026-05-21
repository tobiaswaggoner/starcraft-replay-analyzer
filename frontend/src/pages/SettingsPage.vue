<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api/client";

const health = ref<{ ok: boolean; replay_dir: string | null; db_path: string } | null>(null);
const scanResult = ref<{ seen: number; new: number; errors: number } | null>(null);
const scanning = ref(false);
const recomputing = ref(false);
const recomputeResult = ref<{ players: number; metrics: string[]; elapsed_seconds: number } | null>(null);

async function load() {
  health.value = await api.health();
}
onMounted(load);

async function rescan() {
  scanning.value = true;
  try {
    scanResult.value = await api.scan();
  } finally {
    scanning.value = false;
  }
}

async function recompute() {
  recomputing.value = true;
  try {
    recomputeResult.value = await api.recompute();
  } finally {
    recomputing.value = false;
  }
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1 class="page-title">Settings</h1>
      <div class="page-sub">Edit <code>backend/.env</code> and restart the backend to change these.</div>
    </div>
  </div>

  <div class="card" style="margin-bottom: 16px;">
    <div style="display: grid; grid-template-columns: 200px 1fr; gap: 12px 16px;">
      <div style="color: var(--text-muted)">Replay folder</div>
      <div class="mono">{{ health?.replay_dir ?? '— not configured' }}</div>
      <div style="color: var(--text-muted)">Database</div>
      <div class="mono">{{ health?.db_path ?? '—' }}</div>
    </div>
  </div>

  <div class="card">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px;">
      <div>
        <div style="font-weight: 600">Re-scan folder</div>
        <div style="color: var(--text-muted); font-size: 13px;">
          Walks the replay folder and ingests every <code>.SC2Replay</code> not yet in the DB. Safe to re-run.
        </div>
      </div>
      <button class="btn primary" :disabled="scanning" @click="rescan">
        {{ scanning ? "Scanning…" : "Scan now" }}
      </button>
    </div>
    <div v-if="scanResult" class="mono" style="margin-top: 14px; color: var(--text-dim);">
      Saw {{ scanResult.seen }} files · {{ scanResult.new }} new · {{ scanResult.errors }} errors
    </div>
  </div>

  <div class="card" style="margin-top: 16px;">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px;">
      <div>
        <div style="font-weight: 600">Recompute metrics</div>
        <div style="color: var(--text-muted); font-size: 13px;">
          Re-evaluate all metric functions on existing matches using stored timeseries data.
          Use this after adding a new metric or fixing one. No replays are re-parsed.
        </div>
      </div>
      <button class="btn" :disabled="recomputing" @click="recompute">
        {{ recomputing ? "Recomputing…" : "Recompute now" }}
      </button>
    </div>
    <div v-if="recomputeResult" class="mono" style="margin-top: 14px; color: var(--text-dim);">
      {{ recomputeResult.players }} players · {{ recomputeResult.metrics.length }} metrics ·
      {{ recomputeResult.elapsed_seconds.toFixed(2) }}s
    </div>
  </div>
</template>
