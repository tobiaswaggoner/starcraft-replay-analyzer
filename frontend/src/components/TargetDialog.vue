<script setup lang="ts">
import { reactive, watch, onMounted } from "vue";
import { api, metricLabel, type Operator, type TrainingTarget, type TrainingTargetInput } from "../api/client";

const props = defineProps<{ target: TrainingTarget | null }>();
const emit = defineEmits<{ (e: "save", value: TrainingTargetInput): void; (e: "close"): void }>();

const form = reactive<TrainingTargetInput>({
  name: "",
  metric_name: "workers_at_4min",
  operator: ">=",
  threshold: 0,
  race: null,
  matchup: null,
  mode: null,
  enabled: true,
});

const metricNames = reactive<{ list: string[] }>({ list: [] });

onMounted(async () => {
  const m = await api.metrics();
  metricNames.list = m.metrics;
});

watch(
  () => props.target,
  (t) => {
    if (t) {
      Object.assign(form, {
        name: t.name,
        metric_name: t.metric_name,
        operator: t.operator,
        threshold: t.threshold,
        race: t.race,
        matchup: t.matchup,
        mode: t.mode,
        enabled: t.enabled,
      });
    } else {
      Object.assign(form, {
        name: "",
        metric_name: "workers_at_4min",
        operator: ">=" as Operator,
        threshold: 0,
        race: null,
        matchup: null,
        mode: null,
        enabled: true,
      });
    }
  },
  { immediate: true },
);

function submit() {
  if (!form.name.trim()) return;
  emit("save", { ...form, name: form.name.trim() });
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-head">
        <h2>{{ target ? "Edit target" : "New target" }}</h2>
        <button class="modal-close" @click="emit('close')" aria-label="Close">×</button>
      </div>
      <div class="modal-body">
        <label class="field">
          <div class="field-label">Name</div>
          <input v-model="form.name" class="text-input" placeholder="e.g. Workers @ 4:00 (ZvT)" />
        </label>

        <div class="row-2">
          <label class="field">
            <div class="field-label">Metric</div>
            <select v-model="form.metric_name" class="text-input">
              <option v-for="n in metricNames.list" :key="n" :value="n">{{ metricLabel(n) }}</option>
            </select>
          </label>
          <label class="field" style="max-width: 90px;">
            <div class="field-label">Operator</div>
            <select v-model="form.operator" class="text-input">
              <option value=">=">≥</option>
              <option value="<=">≤</option>
              <option value="==">=</option>
            </select>
          </label>
          <label class="field" style="max-width: 130px;">
            <div class="field-label">Threshold</div>
            <input v-model.number="form.threshold" type="number" step="any" class="text-input" />
          </label>
        </div>

        <div class="row-3">
          <label class="field">
            <div class="field-label">Race (mine)</div>
            <select v-model="form.race" class="text-input">
              <option :value="null">Any</option>
              <option value="Terran">Terran</option>
              <option value="Zerg">Zerg</option>
              <option value="Protoss">Protoss</option>
            </select>
          </label>
          <label class="field">
            <div class="field-label">Matchup</div>
            <input v-model="form.matchup" class="text-input" placeholder="e.g. TvZ" />
          </label>
          <label class="field">
            <div class="field-label">Mode</div>
            <select v-model="form.mode" class="text-input">
              <option :value="null">Any</option>
              <option value="PvP">PvP</option>
              <option value="PvAI">PvAI</option>
            </select>
          </label>
        </div>

        <label class="checkbox-row">
          <input type="checkbox" v-model="form.enabled" />
          <span>Enabled</span>
        </label>
      </div>
      <div class="modal-foot">
        <button class="btn" @click="emit('close')">Cancel</button>
        <button class="btn primary" :disabled="!form.name.trim()" @click="submit">
          {{ target ? "Save" : "Create" }}
        </button>
      </div>
    </div>
  </div>
</template>
