<script setup lang="ts">
defineProps<{ result: string | null }>();
</script>

<template>
  <span v-if="result === 'Win'" class="tag win">Win</span>
  <span v-else-if="result === 'Loss'" class="tag loss">Loss</span>
  <span v-else class="tag">—</span>
</template>
