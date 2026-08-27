<script setup lang="ts">
import { computed } from "vue";
import type { ReviewView } from "../types/research";

const props = defineProps<{ review: ReviewView | null }>();
const issueGroups = computed(() => props.review ? [
  ["Blocking issues", props.review.blockingIssues],
  ["Unsupported claims", props.review.unsupportedClaims],
  ["Conflicting evidence", props.review.conflictingEvidence],
] as const : []);
</script>

<template>
  <section v-if="review" class="panel" aria-labelledby="review-heading">
    <p class="eyebrow">Quality gate</p>
    <div class="section-heading">
      <h2 id="review-heading">Review</h2>
      <span class="status-chip" :data-status="review.verdict">{{ review.verdict.replace('_', ' ') }}</span>
    </div>
    <template v-for="[label, issues] in issueGroups" :key="label">
      <div v-if="issues.length" class="review-group">
        <h3>{{ label }}</h3>
        <ul><li v-for="issue in issues" :key="`${issue.sectionId}-${issue.paragraphId}-${issue.message}`">{{ issue.message }}</li></ul>
      </div>
    </template>
    <div v-if="review.missingSections.length" class="review-group">
      <h3>Missing sections</h3><ul><li v-for="section in review.missingSections" :key="section">{{ section }}</li></ul>
    </div>
    <div v-if="review.revisionInstructions.length" class="review-group">
      <h3>Selected repair</h3><ul><li v-for="instruction in review.revisionInstructions" :key="instruction">{{ instruction }}</li></ul>
    </div>
  </section>
</template>
