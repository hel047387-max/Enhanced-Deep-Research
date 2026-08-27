<script setup lang="ts">
import { computed } from "vue";
import type { ResearchBriefView, ResearchTaskView } from "../types/research";

const props = defineProps<{
  brief: ResearchBriefView | null;
  tasks: Record<string, ResearchTaskView>;
}>();
const orderedTasks = computed(() => Object.values(props.tasks));
</script>

<template>
  <section v-if="brief || orderedTasks.length" class="panel" aria-labelledby="plan-heading">
    <p class="eyebrow">Scope and strategy</p>
    <h2 id="plan-heading">Research plan</h2>
    <dl v-if="brief" class="brief-grid">
      <div><dt>Question</dt><dd>{{ brief.mainQuestion }}</dd></div>
      <div><dt>Scope</dt><dd>{{ brief.scope }}</dd></div>
      <div v-if="brief.timeRange"><dt>Time range</dt><dd>{{ brief.timeRange }}</dd></div>
      <div v-if="brief.comparisonDimensions.length"><dt>Compare</dt><dd>{{ brief.comparisonDimensions.join(", ") }}</dd></div>
    </dl>
    <ol v-if="orderedTasks.length" class="plan-list">
      <li v-for="task in orderedTasks" :key="task.taskId">
        <span class="status-dot" :data-status="task.status" aria-hidden="true" />
        <div><strong>{{ task.title }}</strong><p>{{ task.objective }}</p></div>
      </li>
    </ol>
  </section>
</template>
