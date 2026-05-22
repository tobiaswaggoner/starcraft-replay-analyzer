<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api, type AppSettings } from "../api/client";

const health = ref<{ ok: boolean; replay_dir: string | null; db_path: string } | null>(null);
const settings = ref<AppSettings | null>(null);
const scanResult = ref<{ seen: number; new: number; errors: number } | null>(null);
const scanning = ref(false);
const recomputing = ref(false);
const recomputeResult = ref<{ players: number; metrics: string[]; elapsed_seconds: number } | null>(null);
const reparsingApm = ref(false);
const reparseApmResult = ref<{ matches: number; updated_players: number; skipped_missing_files: number; errors: number; elapsed_seconds: number } | null>(null);

const newApiKey = ref("");
const savingKey = ref(false);
const testing = ref(false);
const testResult = ref<{ ok: boolean; model: string; response?: string; error?: string } | null>(null);

const batchTagging = ref(false);
const batchResult = ref<{ candidates: number; tagged: number; errors: any[] } | null>(null);
const resetting = ref(false);
const resetResult = ref<{ deleted_llm_tags: number; deleted_runs: number } | null>(null);

async function loadAll() {
  health.value = await api.health();
  settings.value = await api.getSettings();
}
onMounted(loadAll);

async function rescan() {
  scanning.value = true;
  try { scanResult.value = await api.scan(); } finally { scanning.value = false; }
}
async function recompute() {
  recomputing.value = true;
  try { recomputeResult.value = await api.recompute(); } finally { recomputing.value = false; }
}

async function reparseApm() {
  reparsingApm.value = true;
  try { reparseApmResult.value = await api.reparseApm(); } finally { reparsingApm.value = false; }
}

async function saveKey() {
  if (!newApiKey.value.trim()) return;
  savingKey.value = true;
  try {
    settings.value = await api.patchSettings({ openrouter_api_key: newApiKey.value.trim() });
    newApiKey.value = "";
  } finally { savingKey.value = false; }
}

async function clearKey() {
  settings.value = await api.patchSettings({ openrouter_api_key: "" });
}

async function changeModel(e: Event) {
  const v = (e.target as HTMLSelectElement).value;
  settings.value = await api.patchSettings({ tagging_model: v });
}

async function toggleAutoTag(e: Event) {
  const v = (e.target as HTMLInputElement).checked;
  settings.value = await api.patchSettings({ auto_tag_on_ingest: v });
}

async function testConnection() {
  testing.value = true;
  testResult.value = null;
  try { testResult.value = await api.testConnection(); } finally { testing.value = false; }
}

async function runBatchTagging() {
  batchTagging.value = true;
  batchResult.value = null;
  try { batchResult.value = await api.runBatchTagging(); } finally { batchTagging.value = false; }
}

async function resetLlmTags() {
  if (!window.confirm("Delete every LLM-generated tag and clear tagging history? Manual tags will be kept.")) return;
  resetting.value = true;
  resetResult.value = null;
  try { resetResult.value = await api.resetLlmTags(); } finally { resetting.value = false; }
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1 class="page-title">Settings</h1>
      <div class="page-sub">
        File-level config lives in <code>backend/.env</code> (replay folder, DB path).
        Everything else here is persisted in the DB.
      </div>
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

  <h2 class="section-title" style="margin-top: 8px;">LLM tagging</h2>

  <div class="card" style="margin-bottom: 12px;">
    <div class="field-row">
      <div class="field" style="flex: 2;">
        <div class="field-label">OpenRouter API key</div>
        <div v-if="settings?.openrouter_api_key_set" class="key-set">
          <span class="mono">{{ settings.openrouter_api_key_masked }}</span>
          <button class="btn danger" @click="clearKey">Clear</button>
        </div>
        <div v-else style="display: flex; gap: 8px;">
          <input
            v-model="newApiKey"
            type="password"
            class="text-input"
            placeholder="sk-or-…"
            @keyup.enter="saveKey"
          />
          <button class="btn primary" :disabled="savingKey || !newApiKey.trim()" @click="saveKey">
            {{ savingKey ? "Saving…" : "Save" }}
          </button>
        </div>
      </div>
    </div>

    <div class="field-row" style="margin-top: 12px;">
      <div class="field" style="flex: 1;">
        <div class="field-label">Tagging model</div>
        <select class="text-input" :value="settings?.tagging_model ?? ''" @change="changeModel">
          <option v-for="m in settings?.available_models ?? []" :key="m.id" :value="m.id">
            {{ m.label }} · {{ m.tier }}
          </option>
        </select>
      </div>
      <label class="checkbox-row" style="margin-top: 22px;">
        <input
          type="checkbox"
          :checked="settings?.auto_tag_on_ingest ?? true"
          @change="toggleAutoTag"
        />
        <span>Auto-tag new matches on ingest</span>
      </label>
    </div>

    <div style="margin-top: 14px; display: flex; gap: 8px; align-items: center;">
      <button class="btn" :disabled="!settings?.openrouter_api_key_set || testing" @click="testConnection">
        {{ testing ? "Testing…" : "Test connection" }}
      </button>
      <span v-if="testResult?.ok" class="tag win">OK — {{ testResult.response }}</span>
      <span v-else-if="testResult && !testResult.ok" class="tag loss" :title="testResult.error">
        Failed: {{ testResult.error?.slice(0, 80) }}
      </span>
    </div>
  </div>

  <div class="card" style="margin-bottom: 16px;">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px;">
      <div>
        <div style="font-weight: 600">Tag all untagged matches</div>
        <div style="color: var(--text-muted); font-size: 13px;">
          Backfill: send every match without a tagging run to the LLM. Skips already-tagged matches.
        </div>
      </div>
      <button class="btn primary" :disabled="batchTagging || !settings?.openrouter_api_key_set" @click="runBatchTagging">
        {{ batchTagging ? "Tagging…" : "Run batch tagging" }}
      </button>
    </div>
    <div v-if="batchResult" class="mono" style="margin-top: 14px; color: var(--text-dim);">
      {{ batchResult.candidates }} candidates · {{ batchResult.tagged }} tagged · {{ batchResult.errors.length }} errors
    </div>
  </div>

  <div class="card" style="margin-bottom: 16px;">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px;">
      <div>
        <div style="font-weight: 600">Reset all LLM tags</div>
        <div style="color: var(--text-muted); font-size: 13px;">
          Drop every auto-generated tag and clear tagging history. Manual tags you
          assigned stay untouched. Useful after refining the tag vocabulary or
          changing the model — afterwards run <em>Tag all untagged</em> to regenerate.
        </div>
      </div>
      <button class="btn danger" :disabled="resetting" @click="resetLlmTags">
        {{ resetting ? "Resetting…" : "Reset LLM tags" }}
      </button>
    </div>
    <div v-if="resetResult" class="mono" style="margin-top: 14px; color: var(--text-dim);">
      Deleted {{ resetResult.deleted_llm_tags }} LLM tags · {{ resetResult.deleted_runs }} tagging runs
    </div>
  </div>

  <h2 class="section-title" style="margin-top: 8px;">Ingest</h2>

  <div class="card" style="margin-bottom: 16px;">
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

  <div class="card">
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

  <div class="card" style="margin-top: 16px;">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px;">
      <div>
        <div style="font-weight: 600">Re-parse replays (APM)</div>
        <div style="color: var(--text-muted); font-size: 13px;">
          Re-open every <code>.SC2Replay</code> file and refresh just the APM metric.
          Use this once after upgrading the parser. Tags and other data are untouched.
        </div>
      </div>
      <button class="btn" :disabled="reparsingApm" @click="reparseApm">
        {{ reparsingApm ? "Re-parsing…" : "Re-parse APM" }}
      </button>
    </div>
    <div v-if="reparseApmResult" class="mono" style="margin-top: 14px; color: var(--text-dim);">
      {{ reparseApmResult.matches }} matches · {{ reparseApmResult.updated_players }} player APMs updated ·
      {{ reparseApmResult.skipped_missing_files }} skipped · {{ reparseApmResult.errors }} errors ·
      {{ reparseApmResult.elapsed_seconds.toFixed(2) }}s
    </div>
  </div>
</template>
