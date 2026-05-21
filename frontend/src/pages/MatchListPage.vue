<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useMatchesStore } from "../stores/matches";
import {
  formatDate, formatDuration, formatMetric,
  findMe, opponentsOf, shortenAIName,
  type Match,
} from "../api/client";
import RacePill from "../components/RacePill.vue";
import ResultTag from "../components/ResultTag.vue";

const store = useMatchesStore();
const router = useRouter();

onMounted(async () => {
  await Promise.all([store.loadFacets(), store.load()]);
});

const myFor = (m: Match) => findMe(m.players);
const opponentsFor = (m: Match) => opponentsOf(m.players, myFor(m));

function opponentLabel(m: Match): string {
  return opponentsFor(m).map((p) => shortenAIName(p.name)).join(", ");
}

const summaryStats = computed(() => {
  const total = store.items.length;
  let wins = 0;
  for (const m of store.items) {
    if (myFor(m)?.result === "Win") wins++;
  }
  return { total, wins, losses: total - wins, winrate: total ? (wins / total) * 100 : 0 };
});

function open(id: number) {
  router.push({ name: "match", params: { id } });
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1 class="page-title">Matches</h1>
      <div class="page-sub">
        {{ store.total }} replays
        <span v-if="summaryStats.total">
          · {{ summaryStats.wins }}W {{ summaryStats.losses }}L ·
          <span class="mono">{{ summaryStats.winrate.toFixed(0) }}%</span> winrate (shown)
        </span>
      </div>
    </div>
    <button class="btn primary" @click="store.scan()">Scan folder</button>
  </div>

  <div class="filters">
    <select class="filter-select" :value="store.filters.mode ?? ''"
            @change="store.setFilter('mode', ($event.target as HTMLSelectElement).value)">
      <option value="">All modes</option>
      <option v-for="m in store.facets.modes" :key="m" :value="m">{{ m }}</option>
    </select>
    <select class="filter-select" :value="store.filters.matchup ?? ''"
            @change="store.setFilter('matchup', ($event.target as HTMLSelectElement).value)">
      <option value="">All matchups</option>
      <option v-for="m in store.facets.matchups" :key="m" :value="m">{{ m }}</option>
    </select>
    <select class="filter-select" :value="store.filters.race ?? ''"
            @change="store.setFilter('race', ($event.target as HTMLSelectElement).value)">
      <option value="">My race: any</option>
      <option v-for="r in store.facets.races" :key="r" :value="r">{{ r }}</option>
    </select>
    <select class="filter-select" :value="store.filters.result ?? ''"
            @change="store.setFilter('result', ($event.target as HTMLSelectElement).value)">
      <option value="">Win/Loss: any</option>
      <option value="Win">Win</option>
      <option value="Loss">Loss</option>
    </select>
    <select class="filter-select" :value="store.filters.map_name ?? ''"
            @change="store.setFilter('map_name', ($event.target as HTMLSelectElement).value)">
      <option value="">All maps</option>
      <option v-for="m in store.facets.maps" :key="m" :value="m">{{ m }}</option>
    </select>
  </div>

  <div v-if="store.loading" class="empty">Loading…</div>

  <div v-else-if="store.items.length === 0" class="empty">
    <h2>No matches yet</h2>
    <div>Set <code>REPLAY_DIR</code> in <code>backend/.env</code>, then click <strong>Scan folder</strong>.</div>
  </div>

  <div v-else class="match-table">
    <div class="match-row header">
      <div>Date</div>
      <div>Versus</div>
      <div>Opponent</div>
      <div>Mode</div>
      <div>Result</div>
      <div>Map</div>
      <div>Duration</div>
      <div>APM</div>
    </div>
    <div v-for="m in store.items" :key="m.id" class="match-row" @click="open(m.id)">
      <div class="cell-date">{{ formatDate(m.played_at) }}</div>
      <div class="cell-vs-pills">
        <RacePill :race="myFor(m)?.race ?? '—'" />
        <span class="cell-vs">vs</span>
        <template v-if="opponentsFor(m).length === 1">
          <RacePill :race="opponentsFor(m)[0].race" />
        </template>
        <span v-else class="mono cell-num-muted">{{ m.player_count_label }}</span>
      </div>
      <div class="cell-opp" :title="opponentLabel(m)">{{ opponentLabel(m) || '—' }}</div>
      <div>
        <span class="mode-tag" :class="`mode-${m.mode}`">{{ m.mode }}</span>
      </div>
      <div><ResultTag :result="myFor(m)?.result ?? null" /></div>
      <div class="cell-map" :title="m.map_name">{{ m.map_name }}</div>
      <div class="cell-num">{{ formatDuration(m.duration_seconds) }}</div>
      <div class="cell-num">{{ formatMetric('apm', myFor(m)?.metrics?.apm) }}</div>
    </div>
  </div>
</template>
