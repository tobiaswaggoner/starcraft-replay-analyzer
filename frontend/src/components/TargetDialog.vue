<script setup lang="ts">
import { computed, reactive, ref, watch, onMounted } from "vue";
import { api, metricLabel, type Operator, type TrainingTarget, type TrainingTargetInput, type FacetTag } from "../api/client";

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
  game_format: null,
  opponent_race: null,
  tags: null,
  enabled: true,
});

const metricNames = reactive<{ list: string[] }>({ list: [] });
const gameFormats = ref<string[]>([]);
const tagVocab = ref<FacetTag[]>([]);
const tagSearch = ref("");
const tagDropdownOpen = ref(false);

onMounted(async () => {
  const [m, facets] = await Promise.all([api.metrics(), api.facets()]);
  metricNames.list = m.metrics;
  gameFormats.value = facets.game_formats;
  tagVocab.value = facets.tags;
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
        game_format: t.game_format,
        opponent_race: t.opponent_race,
        tags: t.tags ? [...t.tags] : null,
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
        game_format: null,
        opponent_race: null,
        tags: null,
        enabled: true,
      });
    }
  },
  { immediate: true },
);

const selectedTagSet = computed(() => new Set(form.tags ?? []));
const filteredVocab = computed(() => {
  const q = tagSearch.value.trim().toLowerCase();
  return tagVocab.value
    .filter((t) => !selectedTagSet.value.has(t.slug))
    .filter((t) => q === "" || t.name.toLowerCase().includes(q) || t.slug.includes(q))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name));
});

function addTag(slug: string) {
  form.tags = [...(form.tags ?? []), slug];
  tagSearch.value = "";
}
function removeTag(slug: string) {
  form.tags = (form.tags ?? []).filter((s) => s !== slug);
  if (form.tags.length === 0) form.tags = null;
}

function tagDisplay(slug: string): string {
  const t = tagVocab.value.find((x) => x.slug === slug);
  return t?.name ?? slug;
}

function closeDropdownLater() {
  // Delay so clicks on dropdown items register before blur closes it.
  window.setTimeout(() => { tagDropdownOpen.value = false; }, 150);
}

function submit() {
  if (!form.name.trim()) return;
  emit("save", {
    ...form,
    name: form.name.trim(),
    matchup: form.matchup?.trim() || null,
    tags: form.tags && form.tags.length ? form.tags : null,
  });
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
          <input v-model="form.name" class="text-input" placeholder="e.g. Workers @ 4:00 (Macro)" />
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

        <div class="field-section-label">Scope (all conditions AND-combined)</div>

        <div class="row-3">
          <label class="field">
            <div class="field-label">My race</div>
            <select v-model="form.race" class="text-input">
              <option :value="null">Any</option>
              <option value="Terran">Terran</option>
              <option value="Zerg">Zerg</option>
              <option value="Protoss">Protoss</option>
            </select>
          </label>
          <label class="field">
            <div class="field-label">Opponent race (1v1 only)</div>
            <select v-model="form.opponent_race" class="text-input">
              <option :value="null">Any</option>
              <option value="Terran">Terran</option>
              <option value="Zerg">Zerg</option>
              <option value="Protoss">Protoss</option>
            </select>
          </label>
          <label class="field">
            <div class="field-label">Format</div>
            <select v-model="form.game_format" class="text-input">
              <option :value="null">Any</option>
              <option v-for="f in gameFormats" :key="f" :value="f">{{ f }}</option>
            </select>
          </label>
        </div>

        <div class="row-2">
          <label class="field">
            <div class="field-label">Mode</div>
            <select v-model="form.mode" class="text-input">
              <option :value="null">Any</option>
              <option value="PvP">PvP</option>
              <option value="PvAI">PvAI</option>
            </select>
          </label>
          <label class="field">
            <div class="field-label">Matchup (legacy)</div>
            <input v-model="form.matchup" class="text-input" placeholder="e.g. TvZ (optional)" />
          </label>
        </div>

        <div class="field">
          <div class="field-label">Required tags (target only applies when ALL are present on my player)</div>
          <div class="tag-multi">
            <span v-for="slug in form.tags ?? []" :key="slug" class="tag-pill">
              {{ tagDisplay(slug) }}
              <button type="button" class="tag-pill-x" @click="removeTag(slug)" aria-label="Remove">×</button>
            </span>
            <span v-if="!form.tags?.length" class="tag-pill-placeholder">Any (no tags required)</span>
          </div>
          <div class="tag-combo">
            <input
              v-model="tagSearch"
              class="text-input"
              placeholder="Add tag…"
              @focus="tagDropdownOpen = true"
              @blur="closeDropdownLater"
            />
            <div v-if="tagDropdownOpen && filteredVocab.length" class="tag-combo-dropdown">
              <div
                v-for="t in filteredVocab"
                :key="t.slug"
                class="tag-combo-option"
                @mousedown.prevent="addTag(t.slug)"
              >
                <span class="tag-combo-name">{{ t.name }}</span>
                <span class="tag-combo-cat mono">{{ t.category }}</span>
              </div>
            </div>
          </div>
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
