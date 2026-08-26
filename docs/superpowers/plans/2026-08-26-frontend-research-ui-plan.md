# Frontend Research UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Vue single-page interface that starts/resumes/cancels research, projects typed SSE events into deterministic UI state, and explains plans, tasks, evidence, review, and the final report.

**Architecture:** A typed API client parses POST-based SSE into `ResearchEvent`. One pure `applyResearchEvent` reducer owns all state transitions; Vue components receive state and emit user intent without duplicating transport or Agent logic.

**Tech Stack:** Vue 3, TypeScript 5, Vite, Vitest, Vue Test Utils, jsdom, marked, DOMPurify

**Spec:** `docs/superpowers/specs/2026-08-26-deep-research-agent-design.md`

## Global Constraints

- Complete the backend API/streaming/persistence plan first.
- Frontend renders observable decisions and outputs, never hidden chain-of-thought.
- The SSE client supports POST, UTF-8 chunk boundaries, AbortSignal, terminal events, and malformed-event isolation.
- `threadId` identifies snapshot/resume; `runId` identifies the active stream.
- Page refresh restores from `GET /api/v1/research/{thread_id}`.
- Cancellation sends both AbortController abort and the explicit backend cancel request.
- No Pinia, router, authentication, event replay, or administration UI in the MVP.
- Markdown is sanitized before rendering.

---

## File map

- `frontend/package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`: build and test foundation.
- `frontend/src/types/research.ts`: exact API/event/UI types.
- `frontend/src/api/research.ts`: stream parser and snapshot/resume/cancel calls.
- `frontend/src/stores/research.ts`: reactive store wrapper around pure event reducer.
- `frontend/src/components/*.vue`: focused workflow views.
- `frontend/src/App.vue`: composition only.
- `frontend/src/**/*.test.ts`: reducer, parser, component, and workflow tests.

### Task 1: TypeScript/Vue test foundation and shared contracts

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/tsconfig.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/index.html`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/types/research.ts`
- Create: `frontend/src/types/research.test.ts`

**Interfaces:**
- Consumes: backend event envelope and snapshot schema.
- Produces: discriminated `ResearchEvent`, `ResearchSnapshot`, `ResearchTaskView`, `EvidenceView`, and `ResearchUIState` types.

- [ ] **Step 1: Configure package scripts and write a failing type fixture test**

```typescript
import { describe, expect, it } from "vitest";
import type { ResearchEvent } from "./research";

describe("ResearchEvent", () => {
  it("accepts the shared event envelope", () => {
    const event: ResearchEvent = {
      type: "run_started",
      run_id: "run-1",
      thread_id: "thread-1",
      sequence: 1,
      timestamp: "2026-08-26T00:00:00Z",
      payload: {},
    };
    expect(event.sequence).toBe(1);
  });
});
```

Add scripts `dev`, `build`, `test`, and `test:run`. Add runtime dependencies `vue`, `marked`, and `dompurify`; development dependencies include Vite, TypeScript, `vue-tsc`, Vitest, jsdom, Vue Test Utils, and Vue Vite plugin.

- [ ] **Step 2: Run tests and type checking**

Run: `cd frontend && npm install && npm run test:run && npm run build`

Expected: FAIL because the shared types and Vue entrypoint are empty.

- [ ] **Step 3: Define exact event and state contracts**

```typescript
export type RunStatus = "created" | "running" | "waiting_for_user" | "completed" | "failed" | "cancelled";
export type TaskStatus = "pending" | "running" | "completed" | "insufficient" | "failed";

export interface ResearchEvent<T extends Record<string, unknown> = Record<string, unknown>> {
  type: string;
  run_id: string;
  thread_id: string;
  sequence: number;
  timestamp: string;
  payload: T;
}

export interface ResearchTaskView {
  taskId: string;
  title: string;
  objective: string;
  status: TaskStatus;
  currentRound: number;
  searchQueries: string[];
  gapReason: string | null;
  error: string | null;
}

export interface EvidenceView {
  evidenceId: string;
  taskId: string;
  sourceId: string;
  claim: string;
  excerpt: string;
  relevance: "high" | "medium" | "low";
  sourceTitle: string;
  sourceUrl: string;
}

export interface ResearchUIState {
  threadId: string | null;
  runId: string | null;
  status: RunStatus;
  clarification: string | null;
  researchBrief: Record<string, unknown> | null;
  tasks: Record<string, ResearchTaskView>;
  evidence: Record<string, EvidenceView>;
  review: Record<string, unknown> | null;
  report: string;
  progressEvents: ResearchEvent[];
  error: string | null;
}
```

- [ ] **Step 4: Run tests and build**

Run: `cd frontend && npm run test:run && npm run build`

Expected: PASS.

- [ ] **Step 5: Commit frontend foundation**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src/main.ts frontend/src/types
git commit -m "chore: configure typed Vue frontend"
```

### Task 2: POST SSE parser and API client

**Files:**
- Modify: `frontend/src/api/research.ts`
- Create: `frontend/src/api/research.test.ts`

**Interfaces:**
- Consumes: API base URL, query/answer, thread ID, AbortSignal.
- Produces: `startResearch`, `resumeResearch`, `cancelResearch`, `getSnapshot`, and `parseSseStream`.

- [ ] **Step 1: Write failing split-chunk and malformed-event tests**

```typescript
import { describe, expect, it } from "vitest";
import { parseSseStream } from "./research";

function stream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
}

describe("parseSseStream", () => {
  it("parses an event split across UTF-8 chunks", async () => {
    const events = [];
    await parseSseStream(stream(["data: {\"type\":\"done\",", "\"run_id\":\"r\",\"thread_id\":\"t\",\"sequence\":1,\"timestamp\":\"x\",\"payload\":{}}\n\n"]), (event) => events.push(event));
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("done");
  });

  it("ignores malformed frames and continues", async () => {
    const events = [];
    await parseSseStream(stream(["data: not-json\n\ndata: {\"type\":\"done\",\"run_id\":\"r\",\"thread_id\":\"t\",\"sequence\":1,\"timestamp\":\"x\",\"payload\":{}}\n\n"]), (event) => events.push(event));
    expect(events.map((event) => event.type)).toEqual(["done"]);
  });
});
```

- [ ] **Step 2: Run parser tests**

Run: `cd frontend && npm run test:run -- src/api/research.test.ts`

Expected: FAIL because parser functions do not exist.

- [ ] **Step 3: Implement stream parsing and API operations**

Use `TextDecoder("utf-8")`, buffer until `\n\n`, parse only lines beginning with `data:`, and flush the decoder on end. Validate envelope keys before invoking the callback. `startResearch` POSTs `/api/v1/research/stream`; `resumeResearch` POSTs `/{threadId}/resume/stream`; both set `Accept: text/event-stream`. `cancelResearch` POSTs `/{threadId}/cancel`; `getSnapshot` GETs `/{threadId}`.

Throw an `ApiError` containing status and sanitized response detail for non-2xx responses. Treat `done` and `error` as terminal stream events.

- [ ] **Step 4: Run parser tests and type checking**

Run: `cd frontend && npm run test:run -- src/api/research.test.ts && npm run build`

Expected: PASS.

- [ ] **Step 5: Commit the API client**

```bash
git add frontend/src/api/research.ts frontend/src/api/research.test.ts
git commit -m "feat: add resilient research SSE client"
```

### Task 3: Pure event reducer and reactive store

**Files:**
- Modify: `frontend/src/stores/research.ts`
- Create: `frontend/src/stores/research.test.ts`

**Interfaces:**
- Consumes: `ResearchUIState`, `ResearchEvent`, API client functions.
- Produces: `initialResearchState`, `applyResearchEvent`, and `useResearchStore` actions `start`, `resume`, `cancel`, and `restore`.

- [ ] **Step 1: Write failing interleaved-task reducer tests**

```typescript
import { describe, expect, it } from "vitest";
import { applyResearchEvent, initialResearchState } from "./research";
import type { ResearchEvent, ResearchTaskView } from "../types/research";


function event(type: string, sequence: number, payload: Record<string, unknown>): ResearchEvent {
  return { type, run_id: "run-1", thread_id: "thread-1", sequence, timestamp: "2026-08-26T00:00:00Z", payload };
}


function task(taskId: string): ResearchTaskView {
  return { taskId, title: taskId, objective: "objective", status: "pending", currentRound: 0, searchQueries: ["query"], gapReason: null, error: null };
}

describe("applyResearchEvent", () => {
  it("updates interleaved tasks by ID without replacing siblings", () => {
    let state = initialResearchState();
    state = applyResearchEvent(state, event("plan_created", 1, { tasks: [task("a"), task("b")] }));
    state = applyResearchEvent(state, event("task_started", 2, { task_id: "b", current_round: 1 }));
    state = applyResearchEvent(state, event("task_completed", 3, { task_id: "a" }));
    expect(state.tasks.a.status).toBe("completed");
    expect(state.tasks.b.status).toBe("running");
  });

  it("ignores duplicate or older sequence numbers", () => {
    let state = applyResearchEvent(initialResearchState(), event("run_started", 2, {}));
    const duplicate = applyResearchEvent(state, event("run_started", 2, {}));
    expect(duplicate.progressEvents).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run store tests**

Run: `cd frontend && npm run test:run -- src/stores/research.test.ts`

Expected: FAIL.

- [ ] **Step 3: Implement immutable reducer and lightweight store**

Clone only the dictionary branch changed by each event. Keep the highest sequence for the active run and ignore older/duplicate events. Map every approved backend event to a named transition. `useResearchStore` wraps a Vue `reactive` state and funnels all events through the reducer; it never modifies task/evidence dictionaries directly.

On `start`, clear previous UI state and create one AbortController. On `resume`, preserve the thread projection but clear the clarification and attach the new run. On `cancel`, abort first, then call the cancel endpoint. On `restore`, replace the projection from the snapshot response.

- [ ] **Step 4: Run store and parser suites**

Run: `cd frontend && npm run test:run -- src/stores/research.test.ts src/api/research.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit deterministic frontend state**

```bash
git add frontend/src/stores/research.ts frontend/src/stores/research.test.ts
git commit -m "feat: project research events into UI state"
```

### Task 4: Workflow components and App composition

**Files:**
- Modify: `frontend/src/components/ResearchForm.vue`
- Modify: `frontend/src/components/ResearchPlan.vue`
- Modify: `frontend/src/components/TaskProgress.vue`
- Modify: `frontend/src/components/EvidencePanel.vue`
- Modify: `frontend/src/components/ReviewPanel.vue`
- Modify: `frontend/src/components/ReportViewer.vue`
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/App.test.ts`
- Create: `frontend/src/style.css`

**Interfaces:**
- Consumes: store refs/actions and typed view models.
- Produces: accessible research form, clarification form, task/evidence/review panels, safe Markdown report, progress summary, and cancellation control.

- [ ] **Step 1: Write failing component workflow tests**

```typescript
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import App from "./App.vue";
import { createResearchStoreForTest } from "./stores/research";

describe("App", () => {
  it("submits a non-empty research question", async () => {
    const start = vi.fn();
    const store = createResearchStoreForTest({ start });
    const wrapper = mount(App, { props: { store } });
    await wrapper.get('[data-testid="research-query"]').setValue("Compare bounded research agents");
    await wrapper.get('[data-testid="start-research"]').trigger("submit");
    expect(start).toHaveBeenCalledWith("Compare bounded research agents");
  });

  it("shows clarification form only while waiting for user", () => {
    const store = createResearchStoreForTest({}, { status: "waiting_for_user", clarification: "Which market?" });
    const wrapper = mount(App, { props: { store } });
    expect(wrapper.get('[data-testid="clarification-form"]').text()).toContain("Which market?");
  });
});
```

- [ ] **Step 2: Run component tests**

Run: `cd frontend && npm run test:run -- src/App.test.ts`

Expected: FAIL because App and components are empty.

- [ ] **Step 3: Implement focused components and safe report rendering**

ResearchForm emits `start`, `resume`, and `cancel`; disable start for blank input and disable duplicate submissions while running. ResearchPlan renders brief fields and ordered tasks. TaskProgress displays status, current round, queries, gap reason, and errors. EvidencePanel groups evidence by task and links sources with `target="_blank" rel="noopener noreferrer"`. ReviewPanel renders verdict and actionable issues without hidden reasoning. ReportViewer uses `marked.parse`, sanitizes with DOMPurify, and never renders raw HTML before sanitization.

Export `ResearchStore` and `createResearchStoreForTest(actionOverrides, stateOverrides)` from the store module. `App` accepts an optional `store: ResearchStore` prop and otherwise constructs the production store, which lets component tests inject deterministic actions without module mocking. App composes components and obtains all mutations through store actions. Add visible focus styles, semantic headings, labels, live-region status text, responsive layout, and no animation dependency.

- [ ] **Step 4: Run the full frontend verification**

Run: `cd frontend && npm run test:run && npm run build`

Expected: all Vitest tests PASS and `vue-tsc`/Vite build succeeds.

- [ ] **Step 5: Commit the research UI**

```bash
git add frontend/src/App.vue frontend/src/App.test.ts frontend/src/components frontend/src/style.css
git commit -m "feat: build observable research workflow UI"
```

## Plan completion gate

Run:

```bash
cd frontend
npm run test:run
npm run build
```

Then start the fake-backed backend and frontend and manually verify: initial question, one clarification, concurrent task updates, evidence links, Reviewer state, cancellation, refresh snapshot restoration, and sanitized final report. Do not begin evaluation/hardening until automated checks and this smoke test pass.
