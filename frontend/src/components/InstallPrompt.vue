<script setup lang="ts">
import { onMounted, onUnmounted, shallowRef } from "vue";

const deferred = shallowRef<BeforeInstallPromptEvent | null>(null);

function capturePrompt(event: Event): void {
  const promptEvent = event as BeforeInstallPromptEvent;
  promptEvent.preventDefault();
  deferred.value = promptEvent;
}

function installed(): void {
  deferred.value = null;
}

async function install(): Promise<void> {
  const promptEvent = deferred.value;
  if (promptEvent === null) return;
  deferred.value = null;
  await promptEvent.prompt();
  await promptEvent.userChoice;
}

onMounted(() => {
  window.addEventListener("beforeinstallprompt", capturePrompt);
  window.addEventListener("appinstalled", installed);
});

onUnmounted(() => {
  window.removeEventListener("beforeinstallprompt", capturePrompt);
  window.removeEventListener("appinstalled", installed);
});
</script>

<template>
  <button
    v-if="deferred"
    class="secondary compact"
    data-testid="install-app"
    type="button"
    @click="install"
  >
    Install app
  </button>
</template>