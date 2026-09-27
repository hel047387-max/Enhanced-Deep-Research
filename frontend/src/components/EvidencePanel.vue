<script setup lang="ts">
import { computed } from "vue";
import type { EvidenceView, ResearchTaskView, SourceView } from "../types/research";

const props = defineProps<{
  evidence: Record<string, EvidenceView>;
  sources: Record<string, SourceView>;
  tasks: Record<string, ResearchTaskView>;
}>();

const groups = computed(() => {
  const grouped = new Map<string, EvidenceView[]>();
  for (const item of Object.values(props.evidence)) {
    grouped.set(item.taskId, [...(grouped.get(item.taskId) ?? []), item]);
  }
  return [...grouped.entries()].map(([taskId, items]) => ({
    taskId,
    title: props.tasks[taskId]?.title ?? `Task ${taskId}`,
    items,
  }));
});

function safeExternalUrl(value: string | null): string | null {
  try {
    if (value === null) return null;
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}
</script>

<template>
  <section v-if="groups.length" class="panel" aria-labelledby="evidence-heading">
    <div class="section-heading">
      <div><p class="eyebrow">Grounding</p><h2 id="evidence-heading">Evidence</h2></div>
      <span class="count-chip">{{ Object.keys(evidence).length }} items</span>
    </div>
    <div v-for="group in groups" :key="group.taskId" class="evidence-group">
      <h3>{{ group.title }}</h3>
      <article v-for="item in group.items" :key="item.evidenceId" class="evidence-card">
        <div class="evidence-topline"><span class="relevance">{{ item.relevance }}</span><span>Round {{ item.discoveredInRound }}</span></div>
        <p class="claim">{{ item.claim }}</p>
        <blockquote>{{ item.excerpt }}</blockquote>
        <template v-if="sources[item.sourceId]">
          <a
            v-if="safeExternalUrl(sources[item.sourceId].url)"
            data-testid="evidence-link"
            :href="safeExternalUrl(sources[item.sourceId].url) ?? undefined"
            target="_blank"
            rel="noopener noreferrer"
          >{{ sources[item.sourceId].title }}</a>
          <span v-else>{{ sources[item.sourceId].title }}<small v-if="sources[item.sourceId].sourceKind === 'literature'"> · {{ sources[item.sourceId].headingPath?.join(' › ') }} · Page {{ sources[item.sourceId].pageStart ?? '?' }}</small></span>
        </template>
      </article>
    </div>
  </section>
</template>
