import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import App from "./App.vue";
import { createResearchStoreForTest } from "./stores/research";

describe("App", () => {
  it("submits a non-empty research question and keeps blank input disabled", async () => {
    const start = vi.fn();
    const store = createResearchStoreForTest({ start });
    const wrapper = mount(App, { props: { store } });

    expect(wrapper.get('[data-testid="start-submit"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-testid="research-query"]').setValue("Compare bounded research agents");
    await wrapper.get('[data-testid="start-research"]').trigger("submit");

    expect(start).toHaveBeenCalledWith("Compare bounded research agents");
  });

  it("shows and submits clarification only while waiting for the user", async () => {
    const resume = vi.fn();
    const store = createResearchStoreForTest(
      { resume },
      { status: "waiting_for_user", clarification: "Which market?", threadId: "thread-1" },
    );
    const wrapper = mount(App, { props: { store } });

    expect(wrapper.get('[data-testid="clarification-form"]').text()).toContain("Which market?");
    await wrapper.get('[data-testid="clarification-answer"]').setValue("Global market");
    await wrapper.get('[data-testid="clarification-form"]').trigger("submit");

    expect(resume).toHaveBeenCalledWith("Global market");
  });

  it("offers cancellation during an active run", async () => {
    const cancel = vi.fn();
    const store = createResearchStoreForTest({ cancel }, { status: "running", runId: "run-1", threadId: "thread-1" });
    const wrapper = mount(App, { props: { store } });

    await wrapper.get('[data-testid="cancel-research"]').trigger("click");

    expect(cancel).toHaveBeenCalledOnce();
  });

  it("restores a provided thread snapshot when mounted", async () => {
    const restore = vi.fn();
    const store = createResearchStoreForTest({ restore });

    mount(App, { props: { store, initialThreadId: "thread-restore" } });
    await Promise.resolve();

    expect(restore).toHaveBeenCalledWith("thread-restore");
  });

  it("renders evidence links with safe external-link attributes", () => {
    const store = createResearchStoreForTest({}, {
      tasks: {
        a: {
          taskId: "a", title: "Market", objective: "Compare markets", completionCriteria: [],
          searchQueries: ["market"], status: "completed", currentRound: 1,
          parentTaskId: null, gapReason: null, error: null,
        },
      },
      sources: {
        s1: { sourceId: "s1", url: "https://example.com/report", title: "Market report", domain: "example.com", publishedAt: null, sourceType: "web" },
      },
      evidence: {
        e1: { evidenceId: "e1", taskId: "a", sourceId: "s1", claim: "A supported claim", excerpt: "Evidence excerpt", context: "Context", relevance: "high", discoveredInRound: 1, citationLabel: "1" },
      },
    });
    const wrapper = mount(App, { props: { store } });
    const link = wrapper.get('[data-testid="evidence-link"]');

    expect(link.attributes()).toMatchObject({ target: "_blank", rel: "noopener noreferrer", href: "https://example.com/report" });
  });

  it("sanitizes report Markdown before rendering it as HTML", () => {
    const store = createResearchStoreForTest({}, {
      status: "completed",
      report: "# Result\n<script>window.pwned = true</script><img src=x onerror=alert(1)> [bad](javascript:alert(1))",
    });
    const wrapper = mount(App, { props: { store } });
    const report = wrapper.get('[data-testid="report-html"]');

    expect(report.find("h1").text()).toBe("Result");
    expect(report.find("script").exists()).toBe(false);
    expect(report.html()).not.toContain("onerror");
    expect(report.find("a").exists()).toBe(false);
  });
});
