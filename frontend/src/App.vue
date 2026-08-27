<script setup lang="ts">
import { onMounted, watch } from "vue";
import EvidencePanel from "./components/EvidencePanel.vue";
import ReportViewer from "./components/ReportViewer.vue";
import ResearchForm from "./components/ResearchForm.vue";
import ResearchPlan from "./components/ResearchPlan.vue";
import ReviewPanel from "./components/ReviewPanel.vue";
import TaskProgress from "./components/TaskProgress.vue";
import { useResearchStore, type ResearchStore } from "./stores/research";

const props = defineProps<{ store?: ResearchStore; initialThreadId?: string }>();
const store = props.store ?? useResearchStore();
const state = store.state;

onMounted(() => {
  const threadId = props.initialThreadId ?? new URLSearchParams(window.location.search).get("thread") ?? undefined;
  if (threadId) void store.restore(threadId);
});

watch(() => state.value.threadId, (threadId) => {
  if (!threadId) return;
  const url = new URL(window.location.href);
  if (url.searchParams.get("thread") === threadId) return;
  url.searchParams.set("thread", threadId);
  window.history.replaceState(null, "", url);
});
</script>

<template>
  <div class="app-shell">
    <header class="hero">
      <div>
        <p class="brand-mark">DEEP / RESEARCH</p>
        <h1>Evidence, not black boxes.</h1>
        <p>Follow the research plan from first question to cited report—without exposing private reasoning.</p>
      </div>
      <div class="run-status" :data-status="state.status">
        <span class="status-dot" aria-hidden="true" />
        <span>{{ state.status.replace('_', ' ') }}</span>
      </div>
    </header>

    <main>
      <p class="sr-only" aria-live="polite">Research status: {{ state.status.replace('_', ' ') }}</p>
      <p v-if="state.error" class="global-error" role="alert">{{ state.error }}</p>
      <ResearchForm
        :status="state.status"
        :clarification="state.clarification"
        @start="store.start"
        @resume="store.resume"
        @cancel="store.cancel"
      />
      <div class="workspace-grid">
        <div class="workspace-main">
          <ResearchPlan :brief="state.researchBrief" :tasks="state.tasks" />
          <TaskProgress :tasks="state.tasks" />
          <ReportViewer :markdown="state.report" />
        </div>
        <aside class="workspace-side" aria-label="Research evidence and review">
          <EvidencePanel :evidence="state.evidence" :sources="state.sources" :tasks="state.tasks" />
          <ReviewPanel :review="state.review" />
          <section v-if="state.progressEvents.length" class="panel event-summary" aria-labelledby="events-heading">
            <p class="eyebrow">Activity</p>
            <h2 id="events-heading">Latest progress</h2>
            <ol>
              <li v-for="item in state.progressEvents.slice(-6).reverse()" :key="`${item.run_id}-${item.sequence}`">
                <span>{{ item.type.replaceAll('_', ' ') }}</span><small>#{{ item.sequence }}</small>
              </li>
            </ol>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>
