<script setup lang="ts">
import { computed } from "vue";
import type { HistoricalResearchReference, ResearchBriefView, ResearchTaskView } from "../types/research";

const props = defineProps<{
  brief: ResearchBriefView | null;
  tasks: Record<string, ResearchTaskView>;
  memoryReferences?: HistoricalResearchReference[];
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
      <div v-if="brief.expectedOutput"><dt>Output</dt><dd>{{ brief.expectedOutput }}</dd></div>
      <div v-if="brief.sourcePreferences.length"><dt>Preferred sources</dt><dd>{{ brief.sourcePreferences.join(", ") }}</dd></div>
      <div v-if="brief.assumptions.length"><dt>Assumptions</dt><dd>{{ brief.assumptions.join(", ") }}</dd></div>
      <div v-if="brief.exclusions.length"><dt>Exclusions</dt><dd>{{ brief.exclusions.join(", ") }}</dd></div>
    </dl>
    <div v-if="memoryReferences?.length" class="memory-leads">
      <h3>Previous research to verify</h3>
      <p>These are planning leads. The report cites only evidence checked in this run.</p>
      <ul>
        <li v-for="item in memoryReferences" :key="item.thread_id">
          <strong>{{ item.question }}</strong> <small>{{ item.completed_at.slice(0, 10) }}</small>
          <p v-if="item.summary">{{ item.summary }}</p>
          <p v-if="item.limitations.length">Limitations: {{ item.limitations.join("; ") }}</p>
          <ul v-if="item.source_urls.length">
            <li v-for="url in item.source_urls" :key="url">
              <a :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</a>
            </li>
          </ul>
        </li>
      </ul>
    </div>
    <ol v-if="orderedTasks.length" class="plan-list">
      <li v-for="task in orderedTasks" :key="task.taskId">
        <span class="status-dot" :data-status="task.status" aria-hidden="true" />
        <div><strong>{{ task.title }}</strong><p>{{ task.objective }}</p></div>
      </li>
    </ol>
  </section>
</template>
