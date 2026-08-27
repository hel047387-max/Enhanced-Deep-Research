<script setup lang="ts">
import { computed, ref } from "vue";
import type { RunStatus } from "../types/research";

const props = defineProps<{ status: RunStatus; clarification: string | null }>();
const emit = defineEmits<{
  start: [query: string];
  resume: [answer: string];
  cancel: [];
}>();

const query = ref("");
const answer = ref("");
const running = computed(() => props.status === "running");

function submitStart() {
  const value = query.value.trim();
  if (value && !running.value) emit("start", value);
}

function submitAnswer() {
  const value = answer.value.trim();
  if (value) emit("resume", value);
}
</script>

<template>
  <section class="panel intake" aria-labelledby="research-heading">
    <p class="eyebrow">Research brief</p>
    <h2 id="research-heading">What should we investigate?</h2>
    <p class="lede">Ask a focused question. The workspace will show the plan, evidence, and review trail as it develops.</p>

    <form data-testid="start-research" class="stack" @submit.prevent="submitStart">
      <label for="research-query">Research question</label>
      <textarea
        id="research-query"
        v-model="query"
        data-testid="research-query"
        rows="4"
        placeholder="Compare two approaches, investigate a market, or explain a recent change…"
        :disabled="running"
      />
      <div class="actions">
        <button data-testid="start-submit" class="primary" type="submit" :disabled="!query.trim() || running">
          {{ running ? "Research in progress" : "Start research" }}
        </button>
        <button v-if="running" data-testid="cancel-research" class="secondary" type="button" @click="emit('cancel')">
          Cancel run
        </button>
      </div>
    </form>

    <form
      v-if="status === 'waiting_for_user' && clarification"
      data-testid="clarification-form"
      class="clarification stack"
      @submit.prevent="submitAnswer"
    >
      <p class="eyebrow">One clarification</p>
      <h3>{{ clarification }}</h3>
      <label for="clarification-answer">Your answer</label>
      <input id="clarification-answer" v-model="answer" data-testid="clarification-answer" autocomplete="off" />
      <button class="primary" type="submit" :disabled="!answer.trim()">Continue research</button>
    </form>
  </section>
</template>
