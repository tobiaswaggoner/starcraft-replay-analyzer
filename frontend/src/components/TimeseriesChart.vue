<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, CanvasRenderer]);

const props = defineProps<{
  series: { name: string; color: string; data: [number, number][] }[];
  title?: string;
  yLabel?: string;
  maximizable?: boolean;
  heightCss?: string;
}>();
const emit = defineEmits<{ maximize: [] }>();

function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const option = computed(() => ({
  backgroundColor: "transparent",
  grid: { left: 50, right: 20, top: 28, bottom: 36 },
  legend: { top: 0, textStyle: { color: "#9aa3b6" }, itemGap: 18 },
  tooltip: {
    trigger: "axis",
    backgroundColor: "#161b25",
    borderColor: "#2e3849",
    textStyle: { color: "#e6e9ef" },
    axisPointer: { lineStyle: { color: "#2e3849" } },
    formatter: (params: any[]) => {
      const t = params[0]?.value?.[0] ?? 0;
      const lines = params
        .map((p) => `<span style="color:${p.color}">●</span> ${p.seriesName}: <b>${p.value[1]}</b>`)
        .join("<br/>");
      return `<div style="font-family:JetBrains Mono,monospace;color:#9aa3b6;margin-bottom:4px">${fmtTime(t)}</div>${lines}`;
    },
  },
  xAxis: {
    type: "value",
    axisLabel: {
      color: "#6b7388",
      formatter: (v: number) => fmtTime(v),
    },
    axisLine: { lineStyle: { color: "#232a39" } },
    splitLine: { show: false },
  },
  yAxis: {
    type: "value",
    name: props.yLabel,
    nameTextStyle: { color: "#6b7388", align: "left", padding: [0, 0, 0, -40] },
    axisLabel: { color: "#6b7388" },
    splitLine: { lineStyle: { color: "#1f2533" } },
  },
  series: props.series.map((s) => ({
    name: s.name,
    type: "line",
    showSymbol: false,
    smooth: 0.2,
    lineStyle: { color: s.color, width: 2 },
    itemStyle: { color: s.color },
    areaStyle: { color: s.color, opacity: 0.08 },
    data: s.data,
  })),
}));
</script>

<template>
  <div class="chart-card">
    <div class="chart-card-head">
      <h3 v-if="title">{{ title }}</h3>
      <button
        v-if="maximizable"
        class="chart-maximize"
        @click="emit('maximize')"
        aria-label="Maximize"
        title="Maximize"
      >⛶</button>
    </div>
    <v-chart class="echart" :style="heightCss ? { height: heightCss } : undefined" :option="option" autoresize />
  </div>
</template>
