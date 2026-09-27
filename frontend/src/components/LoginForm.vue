<script setup lang="ts">
import { ref } from "vue";
import { ApiError } from "../api/http";

const props = defineProps<{
  submit: (username: string, password: string) => Promise<void>;
}>();

const username = ref("");
const password = ref("");
const error = ref("");
const pending = ref(false);

async function signIn(): Promise<void> {
  const normalized = username.value.trim();
  if (normalized.length < 1 || normalized.length > 64) {
    error.value = "Username must contain 1 to 64 characters.";
    return;
  }
  if (password.value.length < 1 || password.value.length > 128) {
    error.value = "Invalid username or password.";
    return;
  }
  pending.value = true;
  error.value = "";
  try {
    await props.submit(normalized, password.value);
  } catch (reason) {
    error.value = reason instanceof ApiError && reason.status === 429
      ? reason.detail
      : "Invalid username or password.";
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <section class="auth-card" data-testid="login-form" aria-labelledby="login-heading">
    <p class="brand-mark">DEEP / RESEARCH</p>
    <h1 id="login-heading">Sign in</h1>
    <p class="auth-lede">Continue to the private research workspace.</p>
    <form class="stack" @submit.prevent="signIn">
      <label for="login-username">Username</label>
      <input
        id="login-username"
        v-model="username"
        data-testid="login-username"
        name="username"
        autocomplete="username"
        maxlength="64"
        :disabled="pending"
      />
      <label for="login-password">Password</label>
      <input
        id="login-password"
        v-model="password"
        data-testid="login-password"
        name="password"
        type="password"
        autocomplete="current-password"
        maxlength="128"
        :disabled="pending"
      />
      <p v-if="error" class="error-text" role="alert">{{ error }}</p>
      <button class="primary" type="submit" :disabled="pending">
        {{ pending ? "Signing in…" : "Sign in" }}
      </button>
    </form>
  </section>
</template>