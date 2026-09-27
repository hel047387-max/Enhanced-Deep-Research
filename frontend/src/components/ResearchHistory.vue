<script setup lang="ts">
import { ref, watch } from "vue";
import { getArchive, listArchives, searchMemory } from "../api/research";
import type { ArchiveDetail, ArchiveSummary, MemorySearchResult } from "../types/research";
import ReportViewer from "./ReportViewer.vue";

const props = defineProps<{ refreshKey?: string | null }>();
const expanded = ref(false);
const query = ref("");
const items = ref<ArchiveSummary[]>([]);
const cards = ref<MemorySearchResult["cards"]>([]);
const hasMore = ref(false);
const selected = ref<ArchiveDetail | null>(null);
const error = ref("");

async function load() {
  try {
    error.value = "";
    if (query.value.trim()) {
      const found = await searchMemory(query.value.trim());
      items.value = found.researches;
      cards.value = found.cards;
      hasMore.value = false;
    } else {
      items.value = await listArchives();
      cards.value = [];
      hasMore.value = items.value.length === 20;
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Could not load research history.";
  }
}

async function loadMore() {
  try {
    const page = await listArchives(items.value.length);
    items.value = [...items.value, ...page];
    hasMore.value = page.length === 20;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Could not load more research.";
  }
}

async function openArchive(threadId: string) {
  try {
    selected.value = await getArchive(threadId);
    error.value = "";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Could not load the archive.";
  }
}

function toggle() {
  expanded.value = !expanded.value;
  if (expanded.value) void load();
}

watch(() => props.refreshKey, () => {
  if (expanded.value) void load();
});
</script>

<template>
  <section class="panel research-history" aria-labelledby="history-heading">
    <div class="history-header">
      <div><p class="eyebrow">Saved research</p><h2 id="history-heading">Research history</h2></div>
      <button type="button" class="secondary" @click="toggle">{{ expanded ? "Hide history" : "Browse history" }}</button>
    </div>
    <div v-if="expanded">
      <form class="history-search" @submit.prevent="load">
        <label for="history-query">Search previous research</label>
        <input id="history-query" v-model="query" placeholder="Topic or keyword" />
        <button type="submit" class="secondary">Search</button>
      </form>
      <p v-if="error" role="alert" class="global-error">{{ error }}</p>
      <ul class="history-list">
        <li v-for="item in items" :key="item.thread_id">
          <button type="button" class="history-link" @click="openArchive(item.thread_id)">
            {{ item.question }} <small>{{ item.completed_at.slice(0, 10) }}</small>
          </button>
        </li>
      </ul>
      <button v-if="hasMore" type="button" class="secondary" @click="loadMore">Load more research</button>
      <p v-if="!items.length && !error">No saved research matched.</p>
      <div v-if="cards.length" class="memory-cards">
        <h3>Related cards</h3>
        <ul><li v-for="card in cards" :key="card.card_id">{{ card.text }}</li></ul>
      </div>
      <div v-if="selected" class="history-detail">
        <h3>{{ selected.question }}</h3>
        <p>Completed {{ selected.completed_at.slice(0, 10) }}</p>
        <ReportViewer :markdown="selected.report" heading-id="history-report-heading" title="Archived report" />
        <h4>Limitations</h4>
        <ul><li v-for="limitation in selected.draft.limitations" :key="limitation">{{ limitation }}</li></ul>
        <h4>Archived evidence</h4>
        <ul>
          <li v-for="item in selected.evidence" :key="item.evidence_id">
            <strong>{{ item.claim }}</strong> — {{ item.excerpt }}
          </li>
        </ul>
        <h4>Sources</h4>
        <ul>
          <li v-for="source in selected.sources" :key="source.source_id">
            <a v-if="'canonical_url' in source" :href="source.canonical_url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a>
            <span v-else>{{ source.title }} · Page {{ source.page_start ?? '?' }}</span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
