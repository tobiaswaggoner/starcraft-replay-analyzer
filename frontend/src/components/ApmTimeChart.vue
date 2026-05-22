<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent, MarkPointComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, GridComponent, TooltipComponent, LegendComponent, MarkPointComponent, CanvasRenderer]);

interface ChartPlayer {
  name: string;
  color: string;
  apm_minutes: { minute: number; apm: number }[];
}

const props = defineProps<{
  players: ChartPlayer[];
  windowMinutes?: number;
}>();

function rollingMean(values: number[], window: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    out.push(slice.reduce((a, b) => a + b, 0) / slice.length);
  }
  return out;
}

function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  return `${m}:00`;
}

const option = computed(() => {
  const win = props.windowMinutes ?? 3;
  const series: any[] = [];
  for (const p of props.players) {
    if (!p.apm_minutes?.length) continue;
    const raw = p.apm_minutes.map((r) => [r.minute * 60, r.apm] as [number, number]);
    const apmValues = p.apm_minutes.map((r) => r.apm);
    const smoothed = rollingMean(apmValues, win);
    const smoothData = p.apm_minutes.map(
      (r, i) => [r.minute * 60, Math.round(smoothed[i] * 10) / 10] as [number, number],
    );
    series.push({
      name: `${p.name} · raw`,
      type: "line",
      showSymbol: false,
      smooth: false,
      lineStyle: { color: p.color, width: 1, type: "dashed", opacity: 0.4 },
      itemStyle: { color: p.color, opacity: 0.4 },
      data: raw,
      z: 1,
    });
    const lastPoint = smoothData[smoothData.length - 1];
    series.push({
      name: `${p.name} · ${win}-min avg`,
      type: "line",
      showSymbol: false,
      smooth: 0.3,
      lineStyle: { color: p.color, width: 2.5 },
      itemStyle: { color: p.color },
      areaStyle: { color: p.color, opacity: 0.08 },
      data: smoothData,
      z: 2,
      markPoint: lastPoint
        ? {
            symbol: "circle",
            symbolSize: 11,
            label: { show: false },
            itemStyle: { color: p.color, borderColor: "#0a0d12", borderWidth: 2 },
            data: [{ coord: lastPoint }],
          }
        : undefined,
    });
  }
  return {
    backgroundColor: "transparent",
    grid: { left: 50, right: 24, top: 36, bottom: 32 },
    legend: { top: 0, textStyle: { color: "#9aa3b6" }, itemGap: 14 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#161b25",
      borderColor: "#2e3849",
      textStyle: { color: "#e6e9ef" },
      axisPointer: { lineStyle: { color: "#2e3849" } },
      formatter: (params: any[]) => {
        const t = params[0]?.value?.[0] ?? 0;
        const lines = params
          .map((p: any) => `<span style="color:${p.color}">●</span> ${p.seriesName}: <b>${p.value[1]}</b>`)
          .join("<br/>");
        return `<div style="font-family:JetBrains Mono,monospace;color:#9aa3b6;margin-bottom:4px">min ${Math.floor(t / 60)}</div>${lines}`;
      },
    },
    xAxis: {
      type: "value",
      axisLabel: { color: "#6b7388", formatter: (v: number) => fmtTime(v) },
      axisLine: { lineStyle: { color: "#232a39" } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      name: "APM",
      nameTextStyle: { color: "#6b7388" },
      axisLabel: { color: "#6b7388" },
      splitLine: { lineStyle: { color: "#1f2533" } },
    },
    series,
  };
});
</script>

<template>
  <div class="chart-card">
    <h3>APM over time</h3>
    <v-chart class="echart" :option="option" autoresize />
  </div>
</template>
