<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import AuthGate from "./components/AuthGate.vue";
import type { AuthStore } from "./stores/auth";
import { checkBackendHealth } from "./api/health";
import ProgressBar from "./components/ProgressBar.vue";

const props = withDefaults(defineProps<{
  checkHealth?: () => Promise<boolean>;
  retryDelayMs?: number;
  authStore?: AuthStore;
}>(), {
  checkHealth: checkBackendHealth,
  retryDelayMs: 1000,
});

const ready = ref(false);
const attempts = ref(0);
let retryTimer: number | undefined;
let mounted = true;

async function probeBackend() {
  attempts.value += 1;
  const healthy = await props.checkHealth();
  if (!mounted) return;
  if (healthy) {
    ready.value = true;
    return;
  }
  retryTimer = window.setTimeout(probeBackend, props.retryDelayMs);
}

onMounted(probeBackend);
onUnmounted(() => {
  mounted = false;
  if (retryTimer !== undefined) window.clearTimeout(retryTimer);
});
</script>

<template>
  <AuthGate v-if="ready" :store="authStore" />
  <main v-else class="startup-shell" data-testid="backend-loading">
    <div class="startup-card">
      <p class="brand-mark">DEEP / RESEARCH</p>
      <h1>Waiting for backend</h1>
      <ProgressBar
        label="Backend service is loading"
        :detail="`Health check ${attempts}. The page will open automatically when ready.`"
      />
    </div>
  </main>
</template>