import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import OwnerSetup from "./OwnerSetup.vue";

describe("OwnerSetup", () => {
  it("blocks invalid boundaries and password mismatch", async () => {
    const submit = vi.fn();
    const wrapper = mount(OwnerSetup, { props: { submit } });

    await wrapper.get('[data-testid="owner-username"]').setValue(" ");
    await wrapper.get('[data-testid="owner-password"]').setValue("short");
    await wrapper.get('[data-testid="owner-confirm"]').setValue("different password");
    await wrapper.get("form").trigger("submit");

    expect(submit).not.toHaveBeenCalled();
    expect(wrapper.get('[role="alert"]').text()).toContain("Username");

    await wrapper.get('[data-testid="owner-username"]').setValue("x".repeat(65));
    await wrapper.get('[data-testid="owner-password"]').setValue("correct password");
    await wrapper.get('[data-testid="owner-confirm"]').setValue("another password");
    await wrapper.get("form").trigger("submit");
    expect(submit).not.toHaveBeenCalled();
  });

  it("submits a trimmed valid owner account", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    const wrapper = mount(OwnerSetup, { props: { submit } });

    await wrapper.get('[data-testid="owner-username"]').setValue("  owner  ");
    await wrapper.get('[data-testid="owner-password"]').setValue("correct password");
    await wrapper.get('[data-testid="owner-confirm"]').setValue("correct password");
    await wrapper.get("form").trigger("submit");

    expect(submit).toHaveBeenCalledWith("owner", "correct password");
  });
});