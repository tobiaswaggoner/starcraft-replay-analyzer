<script setup lang="ts">
defineProps<{ race: string }>();
</script>

<template>
  <span class="race-pill" :class="`race-${race}`">
    <span class="race-dot" />{{ race }}
  </span>
</template>
