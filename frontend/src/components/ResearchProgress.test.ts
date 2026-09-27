import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { initialResearchState } from "../stores/research";
import ResearchProgress from "./ResearchProgress.vue";

function task(status: "pending" | "running" | "completed" | "insufficient" | "failed") {
  return {
    taskId: crypto.randomUUID(), title: "Task", objective: "Research",
    completionCriteria: [], status, currentRound: 1, searchQueries: [],
    parentTaskId: null, gapReason: null, error: null,
  };
}

describe("ResearchProgress", () => {
  it("derives research progress from terminal task counts", () => {
    const state = initialResearchState();
    state.status = "running";
    state.tasks = {
      a: task("completed"), b: task("insufficient"),
      c: task("running"), d: task("pending"),
    };

    const wrapper = mount(ResearchProgress, { props: { state } });

    expect(wrapper.text()).toContain("Researching 2/4 tasks");
    expect(wrapper.get('[role="progressbar"]').attributes("aria-valuenow")).toBe("53");
  });

  it("shows one hundred percent for completed research", () => {
    const state = initialResearchState();
    state.status = "completed";

    const wrapper = mount(ResearchProgress, { props: { state } });

    expect(wrapper.text()).toContain("Research completed");
    expect(wrapper.get('[role="progressbar"]').attributes("aria-valuenow")).toBe("100");
  });
});