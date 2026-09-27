import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import LoginForm from "./LoginForm.vue";

describe("LoginForm", () => {
  it("blocks empty and oversized usernames", async () => {
    const submit = vi.fn();
    const wrapper = mount(LoginForm, { props: { submit } });

    await wrapper.get("form").trigger("submit");
    await wrapper.get('[data-testid="login-username"]').setValue("x".repeat(65));
    await wrapper.get('[data-testid="login-password"]').setValue("password");
    await wrapper.get("form").trigger("submit");

    expect(submit).not.toHaveBeenCalled();
    expect(wrapper.get('[role="alert"]').text()).toContain("Username");
  });

  it("shows one generic message for credential failures", async () => {
    const submit = vi.fn().mockRejectedValue(new Error("owner does not exist"));
    const wrapper = mount(LoginForm, { props: { submit } });

    await wrapper.get('[data-testid="login-username"]').setValue("owner");
    await wrapper.get('[data-testid="login-password"]').setValue("wrong password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toBe("Invalid username or password.");
    expect(wrapper.text()).not.toContain("does not exist");
  });
});