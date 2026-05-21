<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  api, formatDate, formatDuration, formatMetric, metricLabel,
  shortenAIName, targetSummary, targetScopeChips, type MatchDetail,
} from "../api/client";
import RacePill from "../components/RacePill.vue";
import ResultTag from "../components/ResultTag.vue";
import TimeseriesChart from "../components/TimeseriesChart.vue";

const props = defineProps<{ id: string }>();
const match = ref<MatchDetail | null>(null);

const RACE_COLOR: Record<string, string> = {
  Terran: "#5aa9ff",
  Zerg: "#b45cff",
  Protoss: "#f1c83b",
};

async function load() {
  match.value = await api.getMatch(Number(props.id));
}
onMounted(load);
watch(() => props.id, load);

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
    name: p.name,
    color: RACE_COLOR[p.race] ?? "#6ea2ff",
    data: p.timeseries
      .filter((r) => r.workers !== null)
      .map((r) => [r.game_time_seconds, r.workers!] as [number, number]),
  }));
});

const supplySeries = computed(() => {
  if (!match.value) return [];
  return match.value.players.map((p) => ({
    name: p.name,
    color: RACE_COLOR[p.race] ?? "#6ea2ff",
    data: p.timeseries
      .filter((r) => r.supply_used !== null)
      .map((r) => [r.game_time_seconds, r.supply_used!] as [number, number]),
  }));
});

const armySeries = computed(() => {
  if (!match.value) return [];
  return match.value.players.map((p) => ({
    name: p.name,
    color: RACE_COLOR[p.race] ?? "#6ea2ff",
    data: p.timeseries
      .filter((r) => r.army_value !== null)
      .map((r) => [r.game_time_seconds, r.army_value!] as [number, number]),
  }));
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
        <span class="dot">·</span><span>{{ match.player_count_label }}</span>
        <span class="dot">·</span><span>{{ match.map_name }}</span>
        <span class="dot">·</span><span>{{ formatDate(match.played_at) }}</span>
        <span class="dot">·</span><span class="mono">{{ formatDuration(match.duration_seconds) }}</span>
        <span v-if="match.matchup" class="dot">·</span><span v-if="match.matchup">{{ match.matchup }}</span>
        <span v-if="match.game_version" class="dot">·</span><span v-if="match.game_version">{{ match.game_version }}</span>
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

    <h2 class="section-title">Build order — {{ myPlayer?.name }}</h2>
    <div class="build-order">
      <div
        v-for="(ev, i) in myPlayer?.build_events.slice(0, 60) ?? []"
        :key="i"
        class="build-row"
      >
        <div class="build-time">{{ fmtTime(ev.game_time_seconds) }}</div>
        <div class="build-supply">{{ ev.supply ?? '' }}</div>
        <div class="build-name">{{ ev.name }}</div>
        <div class="build-type">{{ ev.event_type }}</div>
      </div>
    </div>
  </div>
</template>
