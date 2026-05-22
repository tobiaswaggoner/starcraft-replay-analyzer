<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, type Tag, type TagCategory } from "../api/client";
import TagChip from "../components/TagChip.vue";
import TagVocabDialog from "../components/TagVocabDialog.vue";

const tags = ref<Tag[]>([]);
const loading = ref(false);
const editing = ref<Tag | null>(null);
const showDialog = ref(false);
const usageCounts = ref<Record<string, number>>({});

async function load() {
  loading.value = true;
  try {
    const [list, facets] = await Promise.all([api.listTagVocab(), api.facets()]);
    tags.value = list.items;
    usageCounts.value = Object.fromEntries(facets.tags.map((t) => [t.slug, t.usage_count]));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const byCategory = computed(() => {
  const order: TagCategory[] = ["strategy", "tech", "build", "tempo", "outcome"];
  const groups: { category: TagCategory; tags: Tag[] }[] = [];
  for (const cat of order) {
    const arr = tags.value.filter((t) => t.category === cat);
    if (arr.length) groups.push({ category: cat, tags: arr });
  }
  return groups;
});

function openCreate() {
  editing.value = null;
  showDialog.value = true;
}
function openEdit(t: Tag) {
  editing.value = t;
  showDialog.value = true;
}
async function onSave(v: Partial<Tag> & { slug: string; name: string; category: TagCategory }) {
  if (editing.value) {
    await api.updateTagVocab(editing.value.slug, v);
  } else {
    await api.createTagVocab(v);
  }
  showDialog.value = false;
  await load();
}
async function onDelete(t: Tag) {
  const uses = usageCounts.value[t.slug] || 0;
  const ok = window.confirm(
    uses > 0
      ? `"${t.name}" is currently used on ${uses} player(s). Deleting it removes those assignments. Continue?`
      : `Delete "${t.name}"?`,
  );
  if (!ok) return;
  await api.deleteTagVocab(t.slug);
  await load();
}
async function resetSeed() {
  if (!window.confirm("Re-import seed tags? System tags will be refreshed; user tags are kept.")) return;
  await api.resetSeedTags();
  await load();
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1 class="page-title">Tags</h1>
      <div class="page-sub">
        Vocabulary used for auto-tagging matches. Seeded from <code>tags_seed.yaml</code>;
        edit anything here — DB is the source of truth.
      </div>
    </div>
    <div style="display: flex; gap: 8px;">
      <button class="btn" @click="resetSeed">Reset seed</button>
      <button class="btn primary" @click="openCreate">+ New tag</button>
    </div>
  </div>

  <div v-if="loading" class="empty">Loading…</div>

  <div v-else>
    <div v-for="group in byCategory" :key="group.category" class="tag-group">
      <div class="tag-group-head">
        <span class="tag-group-name">{{ group.category }}</span>
        <span class="tag-group-count mono">{{ group.tags.length }} tags</span>
      </div>
      <div class="tag-vocab-grid">
        <div v-for="t in group.tags" :key="t.slug" class="tag-vocab-card">
          <div class="tag-vocab-head">
            <TagChip :name="t.name" :color="t.color" />
            <div class="tag-vocab-meta">
              <span v-if="t.created_by === 'user'" class="tag user-badge">USER</span>
              <span v-if="(usageCounts[t.slug] || 0) > 0" class="mono tag-vocab-uses">
                used {{ usageCounts[t.slug] }}×
              </span>
            </div>
          </div>
          <div class="tag-vocab-slug mono">{{ t.slug }}</div>
          <div class="tag-vocab-desc">{{ t.description ?? "—" }}</div>
          <div class="tag-vocab-foot">
            <div class="tag-vocab-races">
              <span v-if="t.applies_to_races">
                <span v-for="r in t.applies_to_races" :key="r" class="tag" style="margin-right: 4px;">{{ r }}</span>
              </span>
              <span v-else class="tag" style="opacity: 0.5;">any race</span>
            </div>
            <div style="display: flex; gap: 6px;">
              <button class="btn" @click="openEdit(t)">Edit</button>
              <button class="btn danger" @click="onDelete(t)">Delete</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <TagVocabDialog
    v-if="showDialog"
    :tag="editing"
    @save="onSave"
    @close="showDialog = false"
  />
</template>
