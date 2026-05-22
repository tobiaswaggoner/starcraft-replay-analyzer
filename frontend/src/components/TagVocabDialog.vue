<script setup lang="ts">
import { reactive, watch } from "vue";
import type { Tag, TagCategory } from "../api/client";

const props = defineProps<{ tag: Tag | null }>();
const emit = defineEmits<{
  (e: "save", value: Partial<Tag> & { slug: string; name: string; category: TagCategory }): void;
  (e: "close"): void;
}>();

const CATEGORIES: { value: TagCategory; label: string }[] = [
  { value: "strategy", label: "Strategy" },
  { value: "tech", label: "Tech" },
  { value: "build", label: "Build" },
  { value: "tempo", label: "Tempo" },
  { value: "outcome", label: "Outcome" },
];
const RACES = ["Terran", "Zerg", "Protoss"];

const form = reactive<{
  slug: string;
  name: string;
  category: TagCategory;
  description: string;
  applies_to_races: string[];
  color: string;
}>({
  slug: "",
  name: "",
  category: "strategy",
  description: "",
  applies_to_races: [],
  color: "",
});

watch(() => props.tag, (t) => {
  if (t) {
    Object.assign(form, {
      slug: t.slug,
      name: t.name,
      category: t.category,
      description: t.description ?? "",
      applies_to_races: t.applies_to_races ?? [],
      color: t.color ?? "",
    });
  } else {
    Object.assign(form, { slug: "", name: "", category: "strategy" as TagCategory, description: "", applies_to_races: [], color: "" });
  }
}, { immediate: true });

function toggleRace(r: string) {
  const i = form.applies_to_races.indexOf(r);
  if (i >= 0) form.applies_to_races.splice(i, 1);
  else form.applies_to_races.push(r);
}

function submit() {
  if (!form.name.trim()) return;
  if (!props.tag && !form.slug.trim()) return;
  emit("save", {
    slug: form.slug || form.name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    name: form.name.trim(),
    category: form.category,
    description: form.description.trim() || null,
    applies_to_races: form.applies_to_races.length ? form.applies_to_races : null,
    color: form.color || null,
  });
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-head">
        <h2>{{ tag ? `Edit tag · ${tag.slug}` : "New tag" }}</h2>
        <button class="modal-close" @click="emit('close')">×</button>
      </div>
      <div class="modal-body">
        <div class="row-2">
          <label class="field">
            <div class="field-label">Slug</div>
            <input
              v-model="form.slug"
              class="text-input mono"
              :disabled="!!tag"
              placeholder="lowercase-with-dashes"
            />
          </label>
          <label class="field">
            <div class="field-label">Name</div>
            <input v-model="form.name" class="text-input" placeholder="Display name" />
          </label>
        </div>

        <div class="row-2">
          <label class="field">
            <div class="field-label">Category</div>
            <select v-model="form.category" class="text-input">
              <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </label>
          <label class="field" style="max-width: 110px;">
            <div class="field-label">Color</div>
            <input v-model="form.color" class="text-input" type="color" />
          </label>
        </div>

        <label class="field">
          <div class="field-label">Description</div>
          <textarea v-model="form.description" class="text-input" rows="3"
                    placeholder="What does this tag mean? The LLM sees this." />
        </label>

        <div class="field">
          <div class="field-label">Applies to races (empty = any)</div>
          <div style="display: flex; gap: 8px;">
            <button
              v-for="r in RACES"
              :key="r"
              type="button"
              class="race-toggle"
              :class="{ active: form.applies_to_races.includes(r) }"
              @click="toggleRace(r)"
            >{{ r }}</button>
          </div>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn" @click="emit('close')">Cancel</button>
        <button class="btn primary" :disabled="!form.name.trim() || (!tag && !form.slug.trim())" @click="submit">
          {{ tag ? "Save" : "Create" }}
        </button>
      </div>
    </div>
  </div>
</template>
