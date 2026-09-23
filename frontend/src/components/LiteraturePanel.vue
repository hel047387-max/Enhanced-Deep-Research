<script setup lang="ts">
import { ref } from "vue";
import { literatureApi, type LiteratureApiClient } from "../api/literature";
import type { LiteratureAnswer, LiteratureSearchItem } from "../types/literature";

const props = defineProps<{ api?: LiteratureApiClient }>();
const client = props.api ?? literatureApi;
const file = ref<File | null>(null);
const title = ref("");
const authors = ref("");
const tags = ref("");
const question = ref("");
const results = ref<LiteratureSearchItem[]>([]);
const answer = ref<LiteratureAnswer | null>(null);
const uploadMessage = ref("");
const busy = ref<"upload" | "search" | "answer" | "delete" | null>(null);
const error = ref("");

function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  if (file.value && !title.value) title.value = file.value.name.replace(/\.[^.]+$/, "");
}

function values(input: string): string[] {
  return input.split(",").map((value) => value.trim()).filter(Boolean);
}

async function upload() {
  if (!file.value || busy.value) return;
  busy.value = "upload";
  error.value = "";
  try {
    const result = await client.uploadDocument(file.value, {
      title: title.value.trim() || file.value.name,
      authors: values(authors.value),
      tags: values(tags.value),
    });
    uploadMessage.value = `${result.units_indexed} searchable units indexed.`;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Document upload failed.";
  } finally {
    busy.value = null;
  }
}

async function search() {
  const query = question.value.trim();
  if (!query || busy.value) return;
  busy.value = "search";
  error.value = "";
  answer.value = null;
  try {
    results.value = (await client.searchLiterature(query)).items;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Literature search failed.";
  } finally {
    busy.value = null;
  }
}

async function ask() {
  const query = question.value.trim();
  if (!query || busy.value) return;
  busy.value = "answer";
  error.value = "";
  results.value = [];
  try {
    answer.value = await client.answerLiterature(query);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Literature answering failed.";
  } finally {
    busy.value = null;
  }
}

async function remove(documentId: string) {
  if (busy.value) return;
  busy.value = "delete";
  error.value = "";
  try {
    await client.deleteDocument(documentId);
    results.value = results.value.filter((item) => item.document_id !== documentId);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "Document deletion failed.";
  } finally {
    busy.value = null;
  }
}

function pages(start: number | null, end: number | null): string {
  if (start === null) return "Pages unavailable";
  return end !== null && end !== start ? `Pages ${start}–${end}` : `Page ${start}`;
}
</script>

<template>
  <section class="panel literature-panel" aria-labelledby="literature-heading">
    <div class="section-heading">
      <div><p class="eyebrow">Local knowledge</p><h2 id="literature-heading">Literature library</h2></div>
      <span class="count-chip">Qdrant</span>
    </div>

    <div class="literature-grid">
      <div class="stack">
        <h3>Index a document</h3>
        <input type="file" accept=".pdf,.docx,.md,.markdown,.html,.htm,.txt" @change="selectFile" />
        <input v-model="title" aria-label="Document title" placeholder="Title" />
        <input v-model="authors" aria-label="Document authors" placeholder="Authors, comma separated" />
        <input v-model="tags" aria-label="Document tags" placeholder="Tags, comma separated" />
        <button data-action="upload" class="secondary" :disabled="!file || busy !== null" @click="upload">
          {{ busy === "upload" ? "Indexing…" : "Upload and index" }}
        </button>
        <p v-if="uploadMessage" class="notice">{{ uploadMessage }}</p>
      </div>

      <div class="stack">
        <h3>Search or ask</h3>
        <textarea v-model="question" data-field="question" rows="3" placeholder="Search the indexed literature" />
        <div class="actions">
          <button data-action="search" class="secondary" :disabled="!question.trim() || busy !== null" @click="search">Search</button>
          <button data-action="answer" class="primary" :disabled="!question.trim() || busy !== null" @click="ask">Answer with citations</button>
        </div>
        <p v-if="error" class="error-text" role="alert">{{ error }}</p>
      </div>
    </div>

    <div v-if="results.length" class="literature-results">
      <article v-for="item in results" :key="item.unit_id" class="literature-result">
        <div><strong>{{ item.title }}</strong><small>{{ item.heading_path.join(' › ') || 'No section' }} · {{ pages(item.page_start, item.page_end) }}</small></div>
        <p>{{ item.text }}</p>
        <button class="secondary compact" :disabled="busy !== null" @click="remove(item.document_id)">Delete document</button>
      </article>
    </div>

    <div v-if="answer" class="literature-answer">
      <p>{{ answer.answer }}</p>
      <ol>
        <li v-for="citation in answer.citations" :key="citation.unit_id">
          <strong>{{ citation.title }}</strong>
          <span>{{ citation.heading_path.join(' › ') }} · {{ pages(citation.page_start, citation.page_end) }}</span>
        </li>
      </ol>
    </div>
  </section>
</template>