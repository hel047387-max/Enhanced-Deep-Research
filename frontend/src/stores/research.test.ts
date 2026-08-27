import { describe, expect, it, vi } from "vitest";
import contractSequence from "../../../contracts/research-event-sequence.json";
import type {
  ResearchEvent,
  ResearchEventType,
  ResearchSnapshot,
  ResearchTaskWire,
} from "../types/research";
import {
  applyResearchEvent,
  initialResearchState,
  useResearchStore,
} from "./research";

function event(
  type: ResearchEventType,
  sequence: number,
  payload: Record<string, unknown>,
  runId = "run-1",
): ResearchEvent {
  return {
    type,
    run_id: runId,
    thread_id: "thread-1",
    sequence,
    timestamp: "2026-08-26T00:00:00Z",
    payload,
  } as ResearchEvent;
}

function task(taskId: string): ResearchTaskWire {
  return {
    task_id: taskId,
    title: `Task ${taskId}`,
    objective: `Objective ${taskId}`,
    completion_criteria: ["Supported conclusion"],
    search_queries: [`query ${taskId}`],
    status: "pending",
    current_round: 0,
    parent_task_id: null,
    gap_reason: null,
    error: null,
  };
}

function snapshot(overrides: Partial<ResearchSnapshot> = {}): ResearchSnapshot {
  return {
    run_id: "run-1",
    thread_id: "thread-1",
    status: "running",
    clarification: null,
    research_brief: null,
    tasks: {},
    sources: {},
    evidence: {},
    review: null,
    report: null,
    errors: [],
    ...overrides,
  };
}

describe("applyResearchEvent", () => {
  it("projects the shared backend event contract into complete UI state", () => {
    const state = (contractSequence as ResearchEvent[]).reduce(
      applyResearchEvent,
      initialResearchState(),
    );

    expect(state.status).toBe("completed");
    expect(state.researchBrief?.scope).toBe("Three evidence dimensions");
    expect(state.tasks["task-1"]?.title).toBe("Dimension 1");
    expect(state.sources["source-1"]?.domain).toBe("example.com");
    expect(state.evidence["evidence-1"]?.claim).toContain("supports");
    expect(state.review?.verdict).toBe("pass");
    expect(state.report).toContain("# Research report");
  });

  it("updates interleaved tasks and evidence by ID without replacing siblings", () => {
    let state = initialResearchState();
    state = applyResearchEvent(state, event("plan_created", 1, { task_count: 2, tasks: [task("a"), task("b")] }));
    state = applyResearchEvent(state, event("task_started", 2, { task_id: "b" }));
    state = applyResearchEvent(state, event("evidence_added", 3, {
      task_id: "b",
      round: 1,
      evidence_ids: ["e-b"],
      count: 1,
      sources: [{
        source_id: "s-b",
        url: "https://example.com/b",
        canonical_url: "https://example.com/b",
        title: "Source B",
        domain: "example.com",
        published_at: null,
        retrieved_at: "2026-08-26T00:00:00Z",
        content_hash: "hash",
        source_type: "web",
      }],
      evidence: [{
        evidence_id: "e-b",
        task_id: "b",
        source_id: "s-b",
        claim: "Claim B",
        excerpt: "Excerpt B",
        context: "Context B",
        relevance: "high",
        discovered_in_round: 1,
        citation_label: "B",
      }],
    }));
    state = applyResearchEvent(state, event("task_completed", 4, { task_id: "a", status: "completed", round: 1, queries_used: 1 }));

    expect(state.tasks.a.status).toBe("completed");
    expect(state.tasks.b.status).toBe("running");
    expect(state.evidence["e-b"]?.claim).toBe("Claim B");
    expect(state.sources["s-b"]?.url).toBe("https://example.com/b");
  });

  it("ignores duplicate, older, and stale-run events for the active run", () => {
    let state = applyResearchEvent(initialResearchState(), event("run_started", 2, {}));
    state = applyResearchEvent(state, event("task_started", 2, { task_id: "same-run" }));
    state = applyResearchEvent(state, event("task_started", 3, { task_id: "old-run" }, "run-old"));

    expect(state.progressEvents).toHaveLength(1);
    expect(state.tasks).toEqual({});
  });

  it("projects clarification and terminal error/done states", () => {
    let state = applyResearchEvent(initialResearchState(), event("run_started", 1, {}));
    state = applyResearchEvent(state, event("clarification_required", 2, { question: "Which market?" }));
    expect(state).toMatchObject({ status: "waiting_for_user", clarification: "Which market?" });

    state = applyResearchEvent(state, event("error", 3, {
      error_code: "research_failed",
      stage: "runtime",
      message: "Research failed safely.",
      task_id: null,
      retryable: false,
      attempt: 1,
      details: {},
    }));
    state = applyResearchEvent(state, event("done", 4, { status: "failed" }));

    expect(state.status).toBe("failed");
    expect(state.error).toBe("Research failed safely.");
  });

  it("handles every backend event type through the same transition function", () => {
    const contractPayload = (type: ResearchEventType): Record<string, unknown> =>
      contractSequence.find((item) => item.type === type)?.payload ?? {};
    const payloads: Array<[ResearchEventType, Record<string, unknown>]> = [
      ["run_started", {}],
      ["research_brief_created", contractPayload("research_brief_created")],
      ["plan_created", { task_count: 1, tasks: [task("a")] }],
      ["task_started", { task_id: "a" }],
      ["search_started", { task_id: "a", round: 1, query_count: 1 }],
      ["search_completed", { task_id: "a", round: 1, query_count: 1, result_count: 2, status: "completed" }],
      ["evidence_added", { task_id: "a", round: 1, evidence_ids: [], count: 0 }],
      ["gap_assessed", { task_id: "a", coverage: "partial", should_continue: true }],
      ["task_completed", { task_id: "a", status: "insufficient", round: 1, queries_used: 1 }],
      ["task_failed", { task_id: "a", status: "failed", round: 1, queries_used: 1, error_code: "search_failed" }],
      ["coverage_assessed", { task_count: 1 }],
      ["additional_tasks_created", { tasks: [task("b")], task_count: 1 }],
      ["draft_created", {}],
      ["review_completed", contractPayload("review_completed")],
      ["revision_started", {}],
      ["report_finalized", { report: "# Final" }],
      ["run_cancelled", { message: "Cancelled" }],
      ["clarification_required", { question: "Clarify" }],
      ["error", { error_code: "x", stage: "runtime", message: "Failed", task_id: null, retryable: false, attempt: 1, details: {} }],
      ["done", { status: "failed" }],
    ];
    const state = payloads.reduce(
      (current, [type, payload], index) => applyResearchEvent(current, event(type, index + 1, payload)),
      initialResearchState(),
    );

    expect(state.progressEvents.map((item) => item.type)).toEqual(payloads.map(([type]) => type));
    expect(state.tasks.b.title).toBe("Task b");
  });
});

describe("useResearchStore", () => {
  it("restores and normalizes the full backend snapshot", async () => {
    const api = {
      startResearch: vi.fn(),
      resumeResearch: vi.fn(),
      cancelResearch: vi.fn(),
      getSnapshot: vi.fn().mockResolvedValue(snapshot({
        clarification: "Which market?",
        status: "waiting_for_user",
        tasks: { a: task("a") },
      })),
    };
    const store = useResearchStore(api);

    await store.restore("thread-1");

    expect(store.state.value.status).toBe("waiting_for_user");
    expect(store.state.value.clarification).toBe("Which market?");
    expect(store.state.value.tasks.a.searchQueries).toEqual(["query a"]);
  });

  it("aborts the browser stream before requesting backend cancellation", async () => {
    const order: string[] = [];
    const api = {
      startResearch: vi.fn((_query, onEvent, signal: AbortSignal) => {
        onEvent(event("run_started", 1, {}));
        return new Promise<void>((resolve) => {
          signal.addEventListener("abort", () => {
            order.push("abort");
            resolve();
          }, { once: true });
        });
      }),
      resumeResearch: vi.fn(),
      cancelResearch: vi.fn(async () => { order.push("backend"); }),
      getSnapshot: vi.fn(),
    };
    const store = useResearchStore(api);
    const running = store.start("question");
    await Promise.resolve();

    await store.cancel();
    await running;

    expect(order).toEqual(["abort", "backend"]);
    expect(api.cancelResearch).toHaveBeenCalledWith("thread-1");
  });

  it("resumes the same thread with a new run while preserving its task projection", async () => {
    const api = {
      startResearch: vi.fn(),
      resumeResearch: vi.fn(async (_threadId, _answer, onEvent) => {
        onEvent(event("run_started", 1, {}, "run-2"));
      }),
      cancelResearch: vi.fn(),
      getSnapshot: vi.fn().mockResolvedValue(snapshot({
        clarification: "Which market?",
        status: "waiting_for_user",
        tasks: { a: task("a") },
      })),
    };
    const store = useResearchStore(api);
    await store.restore("thread-1");

    await store.resume("Global market");

    expect(api.resumeResearch).toHaveBeenCalledWith("thread-1", "Global market", expect.any(Function), expect.any(AbortSignal));
    expect(store.state.value).toMatchObject({ threadId: "thread-1", runId: "run-2", clarification: null });
    expect(store.state.value.tasks.a.title).toBe("Task a");
  });
});
