import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { describe, expect, it, vi } from "vitest";
import InstallPrompt from "./InstallPrompt.vue";

function installEvent(outcome: "accepted" | "dismissed" = "accepted") {
  return Object.assign(new Event("beforeinstallprompt"), {
    preventDefault: vi.fn(),
    prompt: vi.fn().mockResolvedValue(undefined),
    userChoice: Promise.resolve({ outcome, platform: "web" }),
  }) as BeforeInstallPromptEvent;
}

describe("InstallPrompt", () => {
  it("is hidden until the browser offers installation and prompts once", async () => {
    const wrapper = mount(InstallPrompt);
    expect(wrapper.find('[data-testid="install-app"]').exists()).toBe(false);
    const event = installEvent();

    window.dispatchEvent(event);
    await nextTick();
    const button = wrapper.get('[data-testid="install-app"]');
    await button.trigger("click");
    await Promise.resolve();
    await nextTick();

    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(event.prompt).toHaveBeenCalledOnce();
    expect(wrapper.find('[data-testid="install-app"]').exists()).toBe(false);
  });

  it("hides when the appinstalled event fires", async () => {
    const wrapper = mount(InstallPrompt);
    window.dispatchEvent(installEvent("dismissed"));
    await nextTick();
    expect(wrapper.find('[data-testid="install-app"]').exists()).toBe(true);

    window.dispatchEvent(new Event("appinstalled"));
    await nextTick();

    expect(wrapper.find('[data-testid="install-app"]').exists()).toBe(false);
  });
});