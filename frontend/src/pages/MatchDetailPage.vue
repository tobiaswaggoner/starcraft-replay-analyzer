<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  api, formatDate, formatDuration, formatMetric, metricLabel,
  shortenAIName, targetSummary, targetScopeChips, playerColor,
  categorizeBuildEvent, BUILD_CATEGORY_COLORS, BUILD_CATEGORY_LABELS,
  type MatchDetail, type FacetTag,
} from "../api/client";
import RacePill from "../components/RacePill.vue";
import ResultTag from "../components/ResultTag.vue";
import TimeseriesChart from "../components/TimeseriesChart.vue";
import ApmTimeChart from "../components/ApmTimeChart.vue";
import PlayerTagBlock from "../components/PlayerTagBlock.vue";

const props = defineProps<{ id: string }>();
const match = ref<MatchDetail | null>(null);
const vocab = ref<FacetTag[]>([]);
const retagging = ref(false);

async function load() {
  const [m, facets] = await Promise.all([api.getMatch(Number(props.id)), api.facets()]);
  match.value = m;
  vocab.value = facets.tags;
}

function chartLabel(p: { name: string; race: string }): string {
  return `${shortenAIName(p.name)} (${p.race[0] ?? "?"})`;
}
onMounted(load);
watch(() => props.id, load);

async function retag() {
  if (!match.value) return;
  retagging.value = true;
  try {
    await api.tagMatch(match.value.id, true);
    await load();
  } catch (e: any) {
    window.alert(`Tagging failed: ${e.message ?? e}`);
  } finally {
    retagging.value = false;
  }
}

async function tagFirstTime() {
  if (!match.value) return;
  retagging.value = true;
  try {
    await api.tagMatch(match.value.id, false);
    await load();
  } catch (e: any) {
    window.alert(`Tagging failed: ${e.message ?? e}`);
  } finally {
    retagging.value = false;
  }
}

const myPlayer = computed(() => {
  if (!match.value) return undefined;
  return (
    match.value.players.find((p) => p.is_me === 1) ??
    match.value.players.find((p) => p.is_human === 1)
  );
});

const workerSeries = computed(() => {
  if (!match.value) return [];
  return match.value.players.map((p) => ({
    name: chartLabel(p),
    color: playerColor(p.player_index),
    data: p.timeseries
      .filter((r) => r.workers !== null)
      .map((r) => [r.game_time_seconds, r.workers!] as [number, number]),
  }));
});

const supplySeries = computed(() => {
  if (!match.value) return [];
  return match.value.players.map((p) => ({
    name: chartLabel(p),
    color: playerColor(p.player_index),
    data: p.timeseries
      .filter((r) => r.supply_used !== null)
      .map((r) => [r.game_time_seconds, r.supply_used!] as [number, number]),
  }));
});

const armySeries = computed(() => {
  if (!match.value) return [];
  return match.value.players.map((p) => ({
    name: chartLabel(p),
    color: playerColor(p.player_index),
    data: p.timeseries
      .filter((r) => r.army_value !== null)
      .map((r) => [r.game_time_seconds, r.army_value!] as [number, number]),
  }));
});

const apmPlayers = computed(() => {
  if (!match.value) return [];
  return match.value.players
    .filter((p) => p.is_human === 1 && p.apm_minutes && p.apm_minutes.length > 0)
    .map((p) => ({
      name: chartLabel(p),
      color: playerColor(p.player_index),
      apm_minutes: p.apm_minutes,
    }));
});

const buildOrderCollapsed = ref(false);

const filteredBuildEvents = computed(() => {
  if (!myPlayer.value?.build_events) return [];
  // Skip the starting workers / units that sc2reader reports at second 0.
  return myPlayer.value.build_events
    .filter((e) => e.game_time_seconds > 0)
    .slice(0, 80);
});

const METRIC_ORDER = [
  "apm",
  "workers_at_4min",
  "workers_at_8min",
  "workers_peak",
  "supply_peak",
  "supply_blocked_seconds",
  "time_to_max_supply",
];

function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
</script>

<template>
  <div v-if="!match" class="empty">Loading…</div>
  <div v-else>
    <router-link to="/matches" class="nav-link" style="display:inline-flex; padding: 0; color: var(--text-muted); margin-bottom: 12px;">
      ← Back to matches
    </router-link>

    <div class="match-detail-header">
      <h1>
        <span v-for="(p, i) in match.players" :key="p.id">
          <RacePill :race="p.race" />
          <span style="color: var(--text-muted)"> {{ shortenAIName(p.name) }}</span>
          <span v-if="i < match.players.length - 1" style="color: var(--text-muted); margin: 0 10px;">vs</span>
        </span>
      </h1>
      <div class="meta">
        <span class="mode-tag" :class="`mode-${match.mode}`">{{ match.mode }}</span>
        <span class="dot">·</span><span>{{ match.game_format ?? match.player_count_label }}</span>
        <span class="dot">·</span><span>{{ match.map_name }}</span>
        <span class="dot">·</span><span>{{ formatDate(match.played_at) }}</span>
        <span class="dot">·</span><span class="mono">{{ formatDuration(match.duration_seconds) }}</span>
        <span v-if="match.matchup" class="dot">·</span><span v-if="match.matchup">{{ match.matchup }}</span>
        <span v-if="match.game_version" class="dot">·</span><span v-if="match.game_version">{{ match.game_version }}</span>
      </div>
      <div v-if="match.tagging_run?.match_summary" class="match-summary">
        <span class="match-summary-quote">“{{ match.tagging_run.match_summary }}”</span>
        <span class="match-summary-meta mono">— {{ match.tagging_run.model }}</span>
      </div>
    </div>

    <div class="match-tags-section">
      <div class="match-tags-head">
        <h2 class="section-title" style="margin: 0;">Tags</h2>
        <div style="display: flex; gap: 8px;">
          <button v-if="!match.tagging_run" class="btn primary" :disabled="retagging" @click="tagFirstTime">
            {{ retagging ? "Tagging…" : "Auto-tag" }}
          </button>
          <button v-else class="btn" :disabled="retagging" @click="retag">
            {{ retagging ? "Retagging…" : "Retag" }}
          </button>
        </div>
      </div>
      <div class="player-tag-blocks">
        <PlayerTagBlock
          v-for="p in match.players"
          :key="p.id"
          :player-id="p.id"
          :player-name="shortenAIName(p.name)"
          :player-race="p.race"
          :is-human="p.is_human === 1"
          :result="p.result"
          :tags="p.tags"
          :vocab="vocab"
          @changed="load"
        />
      </div>
    </div>

    <div class="players-grid">
      <div
        v-for="p in match.players"
        :key="p.id"
        class="player-card"
        :class="{ me: p.is_me === 1 }"
      >
        <div class="player-card-head">
          <div class="player-name">
            <RacePill :race="p.race" />
            <span>{{ shortenAIName(p.name) }}</span>
            <span v-if="p.is_human === 0" class="tag" style="font-size: 9px; padding: 1px 6px;">AI</span>
          </div>
          <ResultTag :result="p.result" />
        </div>
        <div class="metrics-grid">
          <div v-for="name in METRIC_ORDER" :key="name" class="metric">
            <div class="metric-label">{{ metricLabel(name) }}</div>
            <div class="metric-value">{{ formatMetric(name, p.metrics[name]) }}</div>
          </div>
        </div>
      </div>
    </div>

    <template v-if="match.target_evaluations.length > 0">
      <h2 class="section-title">Training targets</h2>
      <div class="target-eval-grid">
        <div
          v-for="ev in match.target_evaluations"
          :key="ev.target.id"
          class="target-eval"
          :class="{ pass: ev.pass === true, fail: ev.pass === false, na: ev.pass === null }"
        >
          <div class="target-eval-head">
            <div class="target-eval-icon">
              <span v-if="ev.pass === true">✓</span>
              <span v-else-if="ev.pass === false">✗</span>
              <span v-else>—</span>
            </div>
            <div class="target-eval-name">
              <div class="target-eval-title">{{ ev.target.name }}</div>
              <div class="target-eval-rule mono">{{ targetSummary(ev.target) }}</div>
            </div>
            <div class="target-eval-value mono">
              <div class="big">{{ ev.value !== null ? formatMetric(ev.target.metric_name, ev.value) : 'N/A' }}</div>
              <div v-if="ev.delta !== null" class="delta">
                {{ ev.delta >= 0 ? '+' : '' }}{{ formatMetric(ev.target.metric_name, ev.delta) }}
              </div>
            </div>
          </div>
          <div class="target-eval-scope">
            <span v-for="c in targetScopeChips(ev.target)" :key="c" class="tag">{{ c }}</span>
          </div>
        </div>
      </div>
    </template>

    <h2 class="section-title">Macro over time</h2>
    <div style="display: grid; gap: 16px; grid-template-columns: 1fr 1fr;">
      <TimeseriesChart title="Workers" :series="workerSeries" />
      <TimeseriesChart title="Supply used" :series="supplySeries" />
    </div>
    <div style="margin-top: 16px;">
      <TimeseriesChart title="Army value" :series="armySeries" />
    </div>
    <div v-if="apmPlayers.length > 0" style="margin-top: 16px;">
      <ApmTimeChart :players="apmPlayers" />
    </div>

    <div class="build-order-wrap">
      <div class="section-title-row">
        <h2 class="section-title" style="margin: 0;">
          Build order — {{ myPlayer ? shortenAIName(myPlayer.name) : '' }}
        </h2>
        <button class="collapse-btn" @click="buildOrderCollapsed = !buildOrderCollapsed">
          {{ buildOrderCollapsed ? "▶ Show" : "▼ Hide" }}
        </button>
      </div>
      <div v-show="!buildOrderCollapsed" class="build-order">
        <div v-if="filteredBuildEvents.length === 0" style="color: var(--text-muted); padding: 6px 0; font-size: 13px;">
          No build events after 00:00.
        </div>
        <div
          v-for="(ev, i) in filteredBuildEvents"
          :key="i"
          class="build-row"
        >
          <span
            class="build-cat-dot"
            :style="{ background: BUILD_CATEGORY_COLORS[categorizeBuildEvent(ev.event_type, ev.name)] }"
            :title="BUILD_CATEGORY_LABELS[categorizeBuildEvent(ev.event_type, ev.name)]"
          />
          <div class="build-time mono">{{ fmtTime(ev.game_time_seconds) }}</div>
          <div class="build-supply mono">{{ ev.supply ?? '' }}</div>
          <div class="build-name">{{ ev.name }}</div>
          <span
            class="build-cat-tag"
            :style="{
              color: BUILD_CATEGORY_COLORS[categorizeBuildEvent(ev.event_type, ev.name)],
              borderColor: BUILD_CATEGORY_COLORS[categorizeBuildEvent(ev.event_type, ev.name)] + '55',
            }"
          >
            {{ BUILD_CATEGORY_LABELS[categorizeBuildEvent(ev.event_type, ev.name)] }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
