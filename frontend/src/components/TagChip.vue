<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{
  name: string;
  color?: string | null;
  source?: "llm" | "manual" | null;
  confidence?: number | null;
  size?: "sm" | "md";
  removable?: boolean;
  clickable?: boolean;
}>(), { size: "md" });

const emit = defineEmits<{ (e: "remove"): void; (e: "click"): void }>();

const bg = computed(() => props.color || "#9aa3b6");

function colorWithAlpha(hex: string, alpha: number): string {
  const m = hex.replace("#", "").match(/.{2}/g);
  if (!m) return hex;
  const [r, g, b] = m.map((c) => parseInt(c, 16));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
</script>

<template>
  <span
    class="tag-chip"
    :class="[`tag-chip-${size}`, { clickable }]"
    :style="{
      background: colorWithAlpha(bg, 0.14),
      borderColor: colorWithAlpha(bg, 0.45),
      color: bg,
    }"
    @click="emit('click')"
  >
    <span v-if="source === 'manual'" class="tag-chip-source" title="Manual">✎</span>
    <span class="tag-chip-name">{{ name }}</span>
    <span v-if="confidence != null && size !== 'sm'" class="tag-chip-conf mono">
      {{ Math.round(confidence * 100) }}
    </span>
    <button
      v-if="removable"
      class="tag-chip-x"
      @click.stop="emit('remove')"
      aria-label="Remove"
    >×</button>
  </span>
</template>
