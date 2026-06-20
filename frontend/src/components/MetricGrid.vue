<script setup>
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
});
</script>

<template>
  <div class="metric-row">
    <div v-for="item in items" :key="item.label" class="metric">
      <span>{{ item.label }}</span>
      <b>{{ item.value }}</b>
    </div>
  </div>
</template>
