import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import RootApp from "./RootApp.vue";

afterEach(() => vi.useRealTimers());

describe("RootApp", () => {
  it("waits for backend health before mounting the application", async () => {
    vi.useFakeTimers();
    const checkHealth = vi.fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    const wrapper = mount(RootApp, {
      props: { checkHealth, retryDelayMs: 10 },
      global: { stubs: { App: { template: '<div data-testid="app-ready" />' } } },
    });

    await flushPromises();
    expect(wrapper.get('[data-testid="backend-loading"]').text()).toContain("Waiting for backend");
    expect(wrapper.find('[data-testid="app-ready"]').exists()).toBe(false);

    await vi.advanceTimersByTimeAsync(10);
    await flushPromises();

    expect(wrapper.find('[data-testid="app-ready"]').exists()).toBe(true);
    expect(checkHealth).toHaveBeenCalledTimes(2);
  });
});