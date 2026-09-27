<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  label: string;
  detail?: string;
  value?: number;
}>();

const percentage = computed(() => props.value === undefined ? null : Math.round(props.value));
</script>

<template>
  <section
    class="progress-status"
    role="progressbar"
    :aria-label="label"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-valuenow="percentage ?? undefined"
  >
    <div class="progress-copy">
      <strong>{{ label }}</strong>
      <span v-if="percentage !== null">{{ percentage }}%</span>
    </div>
    <div class="progress-track" aria-hidden="true">
      <span
        class="progress-fill"
        :class="{ indeterminate: percentage === null }"
        :style="percentage === null ? undefined : { width: `${percentage}%` }"
      />
    </div>
    <small v-if="detail">{{ detail }}</small>
  </section>
</template>