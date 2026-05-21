<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, TooltipComponent, MarkLineComponent, DataZoomComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { api, metricLabel, formatDate, type TrendPoint } from "../api/client";
import { useMatchesStore } from "../stores/matches";

use([LineChart, ScatterChart, GridComponent, TooltipComponent, MarkLineComponent, DataZoomComponent, CanvasRenderer]);

const TWO_MONTHS_MS = 60 * 24 * 60 * 60 * 1000;

const metricNames = ref<string[]>([]);
const selected = ref<string>("workers_at_8min");
const points = ref<TrendPoint[]>([]);
const matchup = ref<string>("");
const race = ref<string>("");
const store = useMatchesStore();

async function load() {
  const data = await api.trend(selected.value, {
    matchup: matchup.value || undefined,
    race: race.value || undefined,
  });
  points.value = data.points;
}

onMounted(async () => {
  const m = await api.metrics();
  metricNames.value = m.metrics;
  await store.loadFacets();
  await load();
});

watch([selected, matchup, race], load);

const option = () => {
  const data = points.value
    .filter((p) => p.value !== null)
    .map((p) => ({
      value: [new Date(p.played_at).getTime(), p.value],
      result: p.result,
      map: p.map_name,
      matchup: p.matchup,
    }));

  const avg = data.length ? data.reduce((s, d) => s + (d.value[1] as number), 0) / data.length : 0;

  // Default zoom window: last 2 months, but never narrower than the available data.
  const now = Date.now();
  const lastPoint = data.length ? (data[data.length - 1].value[0] as number) : now;
  const firstPoint = data.length ? (data[0].value[0] as number) : now - TWO_MONTHS_MS;
  const defaultStart = Math.max(firstPoint, lastPoint - TWO_MONTHS_MS);
  const defaultEnd = lastPoint;

  return {
    backgroundColor: "transparent",
    grid: { left: 56, right: 24, top: 28, bottom: 70 },
    tooltip: {
      trigger: "item",
      backgroundColor: "#161b25",
      borderColor: "#2e3849",
      textStyle: { color: "#e6e9ef" },
      formatter: (p: any) => {
        const d = new Date(p.value[0]);
        return `<div style="color:#9aa3b6">${d.toLocaleString()}</div>
          <div style="margin-top:4px"><b>${p.value[1]}</b> · ${p.data.result ?? '—'}</div>
          <div style="color:#9aa3b6">${p.data.map} · ${p.data.matchup ?? ''}</div>`;
      },
    },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: "#232a39" } },
      axisLabel: { color: "#6b7388" },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#6b7388" },
      splitLine: { lineStyle: { color: "#1f2533" } },
    },
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: 0,
        startValue: defaultStart,
        endValue: defaultEnd,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
      },
      {
        type: "slider",
        xAxisIndex: 0,
        startValue: defaultStart,
        endValue: defaultEnd,
        height: 24,
        bottom: 18,
        borderColor: "transparent",
        backgroundColor: "rgba(35, 42, 57, 0.45)",
        fillerColor: "rgba(110, 162, 255, 0.18)",
        handleStyle: { color: "#6ea2ff", borderColor: "#6ea2ff" },
        moveHandleStyle: { color: "#6ea2ff" },
        emphasis: { handleStyle: { color: "#8fb6ff", borderColor: "#8fb6ff" } },
        dataBackground: {
          lineStyle: { color: "#2e3849" },
          areaStyle: { color: "rgba(110, 162, 255, 0.08)" },
        },
        selectedDataBackground: {
          lineStyle: { color: "#6ea2ff" },
          areaStyle: { color: "rgba(110, 162, 255, 0.18)" },
        },
        labelFormatter: (_v: number, str: string) => {
          // ECharts gives an ISO-ish string; show just the date portion.
          const d = new Date(str);
          return isNaN(d.valueOf()) ? str : d.toLocaleDateString();
        },
        textStyle: { color: "#9aa3b6" },
      },
    ],
    series: [
      {
        name: selected.value,
        type: "scatter",
        symbolSize: 9,
        data,
        itemStyle: {
          color: (params: any) =>
            params.data.result === "Win" ? "#4ade80" : params.data.result === "Loss" ? "#f87171" : "#6ea2ff",
        },
        markLine: {
          symbol: "none",
          lineStyle: { color: "#6ea2ff", type: "dashed", opacity: 0.5 },
          label: { color: "#9aa3b6", formatter: `avg ${avg.toFixed(1)}` },
          data: [{ yAxis: avg }],
        },
      },
    ],
  };
};
</script>

<template>
  <div class="page-header">
    <div>
      <h1 class="page-title">Trends</h1>
      <div class="page-sub">How your metrics evolve over time. Green = Win, red = Loss.</div>
    </div>
  </div>

  <div class="filters">
    <select class="filter-select" v-model="selected">
      <option v-for="n in metricNames" :key="n" :value="n">{{ metricLabel(n) }}</option>
    </select>
    <select class="filter-select" v-model="matchup">
      <option value="">All matchups</option>
      <option v-for="m in store.facets.matchups" :key="m" :value="m">{{ m }}</option>
    </select>
    <select class="filter-select" v-model="race">
      <option value="">My race: any</option>
      <option v-for="r in store.facets.races" :key="r" :value="r">{{ r }}</option>
    </select>
  </div>

  <div v-if="points.length === 0" class="empty">
    <h2>No data yet</h2>
    <div>Ingest some replays and tag yourself in <code>backend/.env</code> via <code>MY_PLAYER_NAMES</code>.</div>
  </div>

  <div v-else class="chart-card">
    <h3>{{ metricLabel(selected) }} — {{ points.length }} matches</h3>
    <v-chart class="echart" style="height: 460px" :option="option()" autoresize />
    <div class="chart-hint">Drag the slider, scroll to zoom, or drag on the plot to pan.</div>
  </div>
</template>
