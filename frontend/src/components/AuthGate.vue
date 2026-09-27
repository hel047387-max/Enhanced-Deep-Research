<script setup lang="ts">
import { onMounted, ref } from "vue";
import App from "../App.vue";
import { useAuthStore, type AuthStore } from "../stores/auth";
import LoginForm from "./LoginForm.vue";
import OwnerSetup from "./OwnerSetup.vue";
import ProgressBar from "./ProgressBar.vue";

const props = defineProps<{ store?: AuthStore }>();
const store = props.store ?? useAuthStore();
const checkError = ref("");

async function checkSession(): Promise<void> {
  checkError.value = "";
  try {
    await store.check();
  } catch {
    checkError.value = "Authentication status could not be loaded.";
  }
}

onMounted(checkSession);
</script>

<template>
  <main v-if="store.state.value === 'checking'" class="startup-shell" data-testid="auth-checking">
    <div class="startup-card">
      <p class="brand-mark">DEEP / RESEARCH</p>
      <h1>Checking session</h1>
      <ProgressBar label="Checking account access" />
      <p v-if="checkError" class="error-text" role="alert">{{ checkError }}</p>
      <button v-if="checkError" class="secondary" type="button" @click="checkSession">Retry</button>
    </div>
  </main>
  <main v-else-if="store.state.value === 'setup'" class="auth-shell">
    <OwnerSetup :submit="store.register" />
  </main>
  <main v-else-if="store.state.value === 'login'" class="auth-shell">
    <LoginForm :submit="store.login" />
  </main>
  <App v-else :auth-store="store" />
</template>