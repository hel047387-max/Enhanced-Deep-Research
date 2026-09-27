<script setup lang="ts">
import { computed } from "vue";
import type { ResearchEventType, ResearchUIState } from "../types/research";
import ProgressBar from "./ProgressBar.vue";

const props = defineProps<{ state: ResearchUIState }>();

const progress = computed(() => {
  const { state } = props;
  if (state.status === "completed") {
    return { label: "Research completed", detail: "The final report is ready.", value: 100 };
  }
  if (state.status === "waiting_for_user") {
    return { label: "Waiting for clarification", detail: "Answer the clarification to continue.", value: 10 };
  }

  const eventTypes = new Set<ResearchEventType>(state.progressEvents.map((event) => event.type));
  let active = { label: "Starting research", detail: "Preparing the research brief.", value: 8 };

  if (state.researchBrief) {
    active = { label: "Planning research", detail: "Building the research task plan.", value: 20 };
  }

  const tasks = Object.values(state.tasks);
  if (tasks.length) {
    const finished = tasks.filter((task) =>
      ["completed", "insufficient", "failed"].includes(task.status),
    ).length;
    active = {
      label: `Researching ${finished}/${tasks.length} tasks`,
      detail: "Collecting and checking evidence.",
      value: 25 + Math.round((finished / tasks.length) * 55),
    };
  }

  if (eventTypes.has("coverage_assessed")) {
    active = { label: "Assessing coverage", detail: "Checking evidence coverage across tasks.", value: 82 };
  }
  if (eventTypes.has("draft_created")) {
    active = { label: "Reviewing draft", detail: "Checking claims and citations.", value: 85 };
  }
  if (eventTypes.has("review_completed")) {
    active = { label: "Review completed", detail: "Preparing the final report.", value: 90 };
  }
  if (eventTypes.has("revision_started")) {
    active = { label: "Revising report", detail: "Applying review findings.", value: 92 };
  }
  if (eventTypes.has("report_finalized") || state.report) {
    active = { label: "Finalizing report", detail: "Saving the report and research memory.", value: 96 };
  }

  if (state.status === "failed") return { ...active, label: "Research failed", detail: state.error ?? "The research run stopped." };
  if (state.status === "cancelled") return { ...active, label: "Research cancelled", detail: "The research run was cancelled." };
  return active;
});
</script>

<template>
  <ProgressBar
    v-if="state.status !== 'created'"
    class="research-progress"
    :label="progress.label"
    :detail="progress.detail"
    :value="progress.value"
  />
</template>