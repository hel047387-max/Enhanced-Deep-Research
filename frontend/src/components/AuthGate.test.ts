import { mount } from "@vue/test-utils";
import { computed, nextTick, ref } from "vue";
import { describe, expect, it, vi } from "vitest";
import AuthGate from "./AuthGate.vue";
import type { AuthState, AuthStore } from "../stores/auth";

function fakeStore(initial: AuthState): AuthStore & { mutableState: ReturnType<typeof ref<AuthState>> } {
  const mutableState = ref<AuthState>(initial);
  return {
    mutableState,
    state: computed(() => mutableState.value),
    owner: computed(() => initial === "authenticated" ? {
      user_id: "u1", username: "owner", role: "owner", csrf_token: "csrf",
    } : null),
    check: vi.fn().mockResolvedValue(undefined),
    register: vi.fn().mockResolvedValue(undefined),
    login: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn().mockResolvedValue(undefined),
  };
}

describe("AuthGate", () => {
  it.each([
    ["setup", "owner-setup"],
    ["login", "login-form"],
    ["authenticated", "protected-app"],
  ] as const)("renders only the %s screen", async (state, testId) => {
    const store = fakeStore(state);
    const wrapper = mount(AuthGate, {
      props: { store },
      global: { stubs: { App: { template: '<div data-testid="protected-app" />' } } },
    });
    await nextTick();

    expect(store.check).toHaveBeenCalledOnce();
    expect(wrapper.find(`[data-testid="${testId}"]`).exists()).toBe(true);
  });

  it("unmounts protected work after a simulated 401", async () => {
    const store = fakeStore("authenticated");
    const wrapper = mount(AuthGate, {
      props: { store },
      global: {
        stubs: {
          App: { template: '<div><div data-testid="research"/><div data-testid="history"/><div data-testid="literature"/></div>' },
        },
      },
    });
    expect(wrapper.find('[data-testid="research"]').exists()).toBe(true);

    store.mutableState.value = "login";
    await nextTick();

    expect(wrapper.find('[data-testid="research"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="history"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="literature"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="login-form"]').exists()).toBe(true);
  });
});