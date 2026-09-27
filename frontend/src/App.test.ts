import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import App from "./App.vue";
import { createResearchStoreForTest, useResearchStore } from "./stores/research";

describe("App", () => {
  it("submits a non-empty research question and keeps blank input disabled", async () => {
    const start = vi.fn();
    const store = createResearchStoreForTest({ start });
    const wrapper = mount(App, { props: { store } });

    expect(wrapper.get('[data-testid="start-submit"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-testid="research-query"]').setValue("Compare bounded research agents");
    await wrapper.get('[data-testid="start-research"]').trigger("submit");

    expect(start).toHaveBeenCalledWith("Compare bounded research agents", true, false);
  });

  it("can start without recalling previous research", async () => {
    const start = vi.fn();
    const wrapper = mount(App, { props: { store: createResearchStoreForTest({ start }) } });

    await wrapper.get('[data-testid="use-memory"]').setValue(false);
    await wrapper.get('[data-testid="research-query"]').setValue("A fresh study");
    await wrapper.get('[data-testid="start-research"]').trigger("submit");

    expect(start).toHaveBeenCalledWith("A fresh study", false, false);
  });

  it("can search indexed literature during research", async () => {
    const start = vi.fn();
    const wrapper = mount(App, { props: { store: createResearchStoreForTest({ start }) } });

    await wrapper.get('[data-testid="use-literature"]').setValue(true);
    await wrapper.get('[data-testid="research-query"]').setValue("Use my papers");
    await wrapper.get('[data-testid="start-research"]').trigger("submit");

    expect(start).toHaveBeenCalledWith("Use my papers", true, true);
  });
  it("becomes busy immediately and ignores a second start while the first request is pending", async () => {
    const pending: Array<() => void> = [];
    const api = {
      startResearch: vi.fn(() => new Promise<void>((resolve) => pending.push(resolve))),
      resumeResearch: vi.fn(),
      cancelResearch: vi.fn(),
      getSnapshot: vi.fn(),
    };
    const store = useResearchStore(api);
    const wrapper = mount(App, { props: { store } });
    await wrapper.get('[data-testid="research-query"]').setValue("Research once");

    await wrapper.get('[data-testid="start-research"]').trigger("submit");
    await wrapper.get('[data-testid="start-research"]').trigger("submit");

    expect(wrapper.get('[data-testid="research-query"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-testid="start-submit"]').text()).toBe("Research in progress");
    expect(api.startResearch).toHaveBeenCalledOnce();
    pending.forEach((resolve) => resolve());
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
        s1: { sourceId: "s1", sourceKind: "web", url: "https://example.com/report", title: "Market report", domain: "example.com", publishedAt: null, sourceType: "web" },
      },
      evidence: {
        e1: { evidenceId: "e1", taskId: "a", sourceId: "s1", claim: "A supported claim", excerpt: "Evidence excerpt", context: "Context", relevance: "high", discoveredInRound: 1, citationLabel: "1" },
      },
    });
    const wrapper = mount(App, { props: { store } });
    const link = wrapper.get('[data-testid="evidence-link"]');

    expect(link.attributes()).toMatchObject({ target: "_blank", rel: "noopener noreferrer", href: "https://example.com/report" });
  });

  it("shows all non-empty research brief fields", () => {
    const store = createResearchStoreForTest({}, {
      researchBrief: {
        mainQuestion: "Which approach wins?",
        scope: "Global enterprise market",
        timeRange: "2024–2026",
        comparisonDimensions: ["Cost", "Reliability"],
        expectedOutput: "Decision memo",
        sourcePreferences: ["Official documentation"],
        assumptions: ["Stable pricing"],
        exclusions: ["Consumer market"],
      },
    });
    const wrapper = mount(App, { props: { store } });

    expect(wrapper.text()).toContain("Decision memo");
    expect(wrapper.text()).toContain("Official documentation");
    expect(wrapper.text()).toContain("Stable pricing");
    expect(wrapper.text()).toContain("Consumer market");
  });

  it("shows reviewer follow-up task title, objective, and status", () => {
    const followUpTask = {
      taskId: "follow-up", title: "Resolve pricing gap", objective: "Find current official pricing",
      completionCriteria: ["Official source"], searchQueries: ["pricing"], status: "pending" as const,
      currentRound: 0, parentTaskId: "a", gapReason: "Pricing is stale", error: null,
    };
    const store = createResearchStoreForTest({}, {
      review: {
        verdict: "research_gap", blockingIssues: [], unsupportedClaims: [], conflictingEvidence: [],
        missingSections: [], revisionInstructions: [], followUpTasks: [followUpTask],
      },
    });
    const wrapper = mount(App, { props: { store } });

    expect(wrapper.text()).toContain("Resolve pricing gap");
    expect(wrapper.text()).toContain("Find current official pricing");
    expect(wrapper.text()).toContain("pending");
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
