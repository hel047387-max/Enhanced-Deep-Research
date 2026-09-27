<script setup lang="ts">
import { ref } from "vue";
import { ApiError } from "../api/http";

const props = defineProps<{
  submit: (username: string, password: string) => Promise<void>;
}>();

const username = ref("");
const password = ref("");
const confirmation = ref("");
const error = ref("");
const pending = ref(false);

function validationError(): string | null {
  const normalized = username.value.trim();
  if (normalized.length < 1 || normalized.length > 64) {
    return "Username must contain 1 to 64 characters.";
  }
  if (password.value.length < 12 || password.value.length > 128) {
    return "Password must contain 12 to 128 characters.";
  }
  if (password.value !== confirmation.value) return "Passwords do not match.";
  return null;
}

async function createOwner(): Promise<void> {
  const invalid = validationError();
  if (invalid !== null) {
    error.value = invalid;
    return;
  }
  pending.value = true;
  error.value = "";
  try {
    await props.submit(username.value.trim(), password.value);
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.detail : "Owner setup failed.";
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <section class="auth-card" data-testid="owner-setup" aria-labelledby="setup-heading">
    <p class="brand-mark">DEEP / RESEARCH</p>
    <h1 id="setup-heading">Create the owner account</h1>
    <p class="auth-lede">Set up the only account that can access this research workspace.</p>
    <form class="stack" @submit.prevent="createOwner">
      <label for="owner-username">Username</label>
      <input
        id="owner-username"
        v-model="username"
        data-testid="owner-username"
        name="username"
        autocomplete="username"
        maxlength="64"
        :disabled="pending"
      />
      <label for="owner-password">Password</label>
      <input
        id="owner-password"
        v-model="password"
        data-testid="owner-password"
        name="password"
        type="password"
        autocomplete="new-password"
        maxlength="128"
        :disabled="pending"
      />
      <small>Use 12 to 128 characters.</small>
      <label for="owner-confirm">Confirm password</label>
      <input
        id="owner-confirm"
        v-model="confirmation"
        data-testid="owner-confirm"
        name="password-confirmation"
        type="password"
        autocomplete="new-password"
        maxlength="128"
        :disabled="pending"
      />
      <p v-if="error" class="error-text" role="alert">{{ error }}</p>
      <button class="primary" type="submit" :disabled="pending">
        {{ pending ? "Creating account…" : "Create owner account" }}
      </button>
    </form>
  </section>
</template>