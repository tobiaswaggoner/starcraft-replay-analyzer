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
import TagChip from "../components/TagChip.vue";

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

function topTags(m: Match, max = 3) {
  const me = myFor(m);
  if (!me || !me.tags) return [];
  return me.tags.slice(0, max);
}
function extraTagCount(m: Match, max = 3): number {
  const me = myFor(m);
  return Math.max(0, (me?.tags?.length ?? 0) - max);
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
    <select class="filter-select" :value="store.filters.game_format ?? ''"
            @change="store.setFilter('game_format', ($event.target as HTMLSelectElement).value)">
      <option value="">All formats</option>
      <option v-for="f in store.facets.game_formats" :key="f" :value="f">{{ f }}</option>
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
    <select class="filter-select" :value="store.filters.tag ?? ''"
            @change="store.setFilter('tag', ($event.target as HTMLSelectElement).value)">
      <option value="">All tags</option>
      <option v-for="t in store.facets.tags.filter(t => t.usage_count > 0)" :key="t.slug" :value="t.slug">
        {{ t.name }} ({{ t.usage_count }})
      </option>
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
      <div>Format</div>
      <div>Tags</div>
      <div>Result</div>
      <div>Map</div>
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
      </div>
      <div class="cell-opp" :title="opponentLabel(m)">{{ opponentLabel(m) || '—' }}</div>
      <div class="cell-format mono">{{ m.game_format ?? m.player_count_label }}</div>
      <div class="cell-tags">
        <TagChip v-for="t in topTags(m)" :key="t.tag_slug" :name="t.name" :color="t.color" size="sm" />
        <span v-if="extraTagCount(m) > 0" class="tag mono" style="font-size: 10px;">+{{ extraTagCount(m) }}</span>
      </div>
      <div><ResultTag :result="myFor(m)?.result ?? null" /></div>
      <div class="cell-map" :title="m.map_name">{{ m.map_name }}</div>
      <div class="cell-num">{{ formatMetric('apm', myFor(m)?.metrics?.apm) }}</div>
    </div>
  </div>
</template>
