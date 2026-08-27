<script setup lang="ts">
import { computed } from "vue";
import type { ResearchTaskView } from "../types/research";

const props = defineProps<{ tasks: Record<string, ResearchTaskView> }>();
const tasks = computed(() => Object.values(props.tasks));
const label = (status: ResearchTaskView["status"]) => status.replace("_", " ");
</script>

<template>
  <section v-if="tasks.length" class="panel" aria-labelledby="tasks-heading">
    <div class="section-heading">
      <div><p class="eyebrow">Live execution</p><h2 id="tasks-heading">Task progress</h2></div>
      <span class="count-chip">{{ tasks.filter((task) => task.status === 'completed').length }}/{{ tasks.length }} complete</span>
    </div>
    <div class="task-grid">
      <article v-for="task in tasks" :key="task.taskId" class="task-card">
        <header><h3>{{ task.title }}</h3><span class="status-chip" :data-status="task.status">{{ label(task.status) }}</span></header>
        <p>{{ task.objective }}</p>
        <p class="meta">Round {{ task.currentRound }} of 2</p>
        <ul v-if="task.searchQueries.length" class="query-list" aria-label="Search queries">
          <li v-for="query in task.searchQueries" :key="query">{{ query }}</li>
        </ul>
        <p v-if="task.gapReason" class="notice">{{ task.gapReason }}</p>
        <p v-if="task.error" class="error-text">{{ task.error }}</p>
      </article>
    </div>
  </section>
</template>
