<script setup lang="ts">
import { computed, ref } from "vue";
import { api, type FacetTag, type PlayerTag } from "../api/client";
import TagChip from "./TagChip.vue";
import RacePill from "./RacePill.vue";

const props = defineProps<{
  playerId: number;
  playerName: string;
  playerRace: string;
  isHuman: boolean;
  result: string | null;
  tags: PlayerTag[];
  vocab: FacetTag[];
}>();

const emit = defineEmits<{ (e: "changed"): void }>();

const popoverFor = ref<string | null>(null);
const adding = ref(false);
const addSearch = ref("");

const sorted = computed(() =>
  [...props.tags].sort((a, b) => {
    if (a.source !== b.source) return a.source === "llm" ? -1 : 1;
    return (b.confidence ?? 0) - (a.confidence ?? 0);
  }),
);

const availableForAdd = computed(() => {
  const has = new Set(props.tags.map((t) => t.tag_slug));
  const q = addSearch.value.toLowerCase();
  return props.vocab.filter((t) => !has.has(t.slug) && (q === "" || t.name.toLowerCase().includes(q) || t.slug.includes(q)));
});

async function remove(t: PlayerTag) {
  await api.removePlayerTag(props.playerId, t.tag_slug, t.source);
  popoverFor.value = null;
  emit("changed");
}
async function addTag(slug: string) {
  await api.addPlayerTag(props.playerId, slug);
  adding.value = false;
  addSearch.value = "";
  emit("changed");
}
</script>

<template>
  <div class="player-tag-block">
    <div class="player-tag-head">
      <RacePill :race="playerRace" />
      <span class="player-tag-name">{{ playerName }}</span>
      <span v-if="!isHuman" class="tag" style="font-size: 9px;">AI</span>
      <span v-if="result" class="tag" :class="result === 'Win' ? 'win' : result === 'Loss' ? 'loss' : ''">{{ result }}</span>
    </div>

    <div class="player-tag-chips">
      <span v-for="t in sorted" :key="`${t.tag_slug}-${t.source}`" style="position: relative;">
        <TagChip
          :name="t.name"
          :color="t.color"
          :source="t.source"
          :confidence="t.confidence"
          :removable="true"
          clickable
          @click="popoverFor = popoverFor === `${t.tag_slug}-${t.source}` ? null : `${t.tag_slug}-${t.source}`"
          @remove="remove(t)"
        />
        <div v-if="popoverFor === `${t.tag_slug}-${t.source}`" class="tag-popover">
          <div class="tag-popover-head">
            <div class="tag-popover-name">{{ t.name }}</div>
            <div class="tag-popover-source">
              {{ t.source === "llm" ? `LLM (${t.model || "?"})` : "Manual" }}
              <span v-if="t.confidence != null" class="mono">· {{ Math.round(t.confidence * 100) }}%</span>
            </div>
          </div>
          <div v-if="t.reasoning" class="tag-popover-reasoning">{{ t.reasoning }}</div>
          <div v-else class="tag-popover-reasoning" style="opacity: 0.6;">No reasoning recorded.</div>
        </div>
      </span>

      <button v-if="!adding" class="add-tag-btn" @click="adding = true">+ tag</button>
      <span v-else class="add-tag-combo">
        <input
          v-model="addSearch"
          class="text-input"
          style="padding: 4px 8px; font-size: 12px; width: 160px;"
          placeholder="Search tags…"
          autofocus
          @keyup.escape="adding = false; addSearch = ''"
        />
        <div class="add-tag-dropdown">
          <div
            v-for="t in availableForAdd.slice(0, 12)"
            :key="t.slug"
            class="add-tag-option"
            @click="addTag(t.slug)"
          >
            <TagChip :name="t.name" :color="t.color" size="sm" />
            <span class="add-tag-cat mono">{{ t.category }}</span>
          </div>
          <div v-if="availableForAdd.length === 0" class="add-tag-empty">No matches</div>
        </div>
      </span>
    </div>
  </div>
</template>
