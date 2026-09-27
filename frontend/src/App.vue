<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import EvidencePanel from "./components/EvidencePanel.vue";
import InstallPrompt from "./components/InstallPrompt.vue";
import LiteraturePanel from "./components/LiteraturePanel.vue";
import ReportViewer from "./components/ReportViewer.vue";
import ResearchForm from "./components/ResearchForm.vue";
import ResearchHistory from "./components/ResearchHistory.vue";
import ResearchPlan from "./components/ResearchPlan.vue";
import ResearchProgress from "./components/ResearchProgress.vue";
import ReviewPanel from "./components/ReviewPanel.vue";
import TaskProgress from "./components/TaskProgress.vue";
import type { AuthStore } from "./stores/auth";
import { useResearchStore, type ResearchStore } from "./stores/research";

const props = defineProps<{ store?: ResearchStore; initialThreadId?: string; authStore?: AuthStore }>();
const store = props.store ?? useResearchStore();
const state = store.state;
const loggingOut = ref(false);

async function logout(): Promise<void> {
  if (!props.authStore || loggingOut.value) return;
  loggingOut.value = true;
  try {
    await props.authStore.logout();
  } finally {
    loggingOut.value = false;
  }
}

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
      <div class="header-actions">
        <div class="run-status" :data-status="state.status">
          <span class="status-dot" aria-hidden="true" />
          <span>{{ state.status.replace('_', ' ') }}</span>
        </div>
        <InstallPrompt />
        <button
          v-if="authStore"
          class="secondary compact"
          data-testid="logout"
          type="button"
          :disabled="loggingOut"
          @click="logout"
        >
          {{ loggingOut ? 'Signing out…' : 'Sign out' }}
        </button>
      </div>
    </header>

    <main>
      <p class="sr-only" aria-live="polite">Research status: {{ state.status.replace('_', ' ') }}</p>
      <p v-if="state.error" class="global-error" role="alert">{{ state.error }}</p>
      <p v-if="state.memoryStatus === 'failed'" class="global-error" role="alert">Memory save failed. The report is still available.</p>
      <p v-if="state.memoryWarning" class="global-error" role="alert">{{ state.memoryWarning }}</p>
      <ResearchProgress :state="state" />
      <ResearchForm
        :status="state.status"
        :clarification="state.clarification"
        @start="store.start"
        @resume="store.resume"
        @cancel="store.cancel"
      />
      <ResearchHistory :refresh-key="state.memoryStatus === 'saved' ? state.threadId : null" />
      <LiteraturePanel />
      <div class="workspace-grid">
        <div class="workspace-main">
          <ResearchPlan :brief="state.researchBrief" :tasks="state.tasks" :memory-references="state.memoryReferences" />
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
