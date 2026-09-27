<script setup lang="ts">
import { computed } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";

const props = withDefaults(defineProps<{ markdown: string; headingId?: string; title?: string }>(), {
  headingId: "report-heading", title: "Research report",
});

function safeMarkdown(markdown: string): string {
  const parsed = marked.parse(markdown) as string;
  const sanitized = DOMPurify.sanitize(parsed, {
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "img"],
    FORBID_ATTR: ["style"],
  });
  const template = document.createElement("template");
  template.innerHTML = sanitized;
  for (const anchor of template.content.querySelectorAll("a")) {
    const href = anchor.getAttribute("href");
    try {
      if (!href) throw new Error("missing link");
      const url = new URL(href);
      if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("unsafe link");
      anchor.setAttribute("target", "_blank");
      anchor.setAttribute("rel", "noopener noreferrer");
    } catch {
      anchor.removeAttribute("href");
      anchor.removeAttribute("target");
      anchor.removeAttribute("rel");
    }
  }
  return template.innerHTML;
}

const rendered = computed(() => safeMarkdown(props.markdown));
</script>

<template>
  <section v-if="markdown" class="panel report-panel"  :aria-labelledby="headingId">
    <p class="eyebrow">Final output</p>
    <h2 :id="headingId">{{ title }}</h2>
    <div data-testid="report-html" class="report-content" v-html="rendered" />
  </section>
</template>
