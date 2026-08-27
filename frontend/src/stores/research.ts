import { computed, shallowRef, type Ref } from "vue";
import * as researchApi from "../api/research";
import type { ResearchEventHandler } from "../api/research";
import type {
  EvidenceView, EvidenceWire, ResearchBriefView, ResearchBriefWire,
  ResearchEvent, ResearchSnapshot, ResearchTaskView, ResearchTaskWire,
  ResearchUIState, ReviewIssueView, ReviewIssueWire, ReviewView,
  ReviewResultWire, SourceView, SourceWire,
} from "../types/research";

export interface ResearchApiClient {
  startResearch(query: string, onEvent: ResearchEventHandler, signal: AbortSignal): Promise<void>;
  resumeResearch(threadId: string, answer: string, onEvent: ResearchEventHandler, signal: AbortSignal): Promise<void>;
  cancelResearch(threadId: string): Promise<void>;
  getSnapshot(threadId: string): Promise<ResearchSnapshot>;
}

export interface ResearchStore {
  state: Readonly<Ref<ResearchUIState>>;
  start(query: string): Promise<void>;
  resume(answer: string): Promise<void>;
  cancel(): Promise<void>;
  restore(threadId: string): Promise<void>;
}

const defaultApi: ResearchApiClient = researchApi;

export function initialResearchState(): ResearchUIState {
  return {
    threadId: null, runId: null, status: "created", clarification: null,
    researchBrief: null, tasks: {}, sources: {}, evidence: {}, review: null,
    report: "", progressEvents: [], error: null, lastSequence: 0,
  };
}

function taskFromWire(task: ResearchTaskWire): ResearchTaskView {
  return {
    taskId: task.task_id, title: task.title, objective: task.objective,
    completionCriteria: [...task.completion_criteria], searchQueries: [...task.search_queries],
    status: task.status, currentRound: task.current_round, parentTaskId: task.parent_task_id,
    gapReason: task.gap_reason, error: task.error,
  };
}

function sourceFromWire(source: SourceWire): SourceView {
  return {
    sourceId: source.source_id, url: source.url, title: source.title,
    domain: source.domain, publishedAt: source.published_at, sourceType: source.source_type,
  };
}

function evidenceFromWire(evidence: EvidenceWire): EvidenceView {
  return {
    evidenceId: evidence.evidence_id, taskId: evidence.task_id, sourceId: evidence.source_id,
    claim: evidence.claim, excerpt: evidence.excerpt, context: evidence.context,
    relevance: evidence.relevance, discoveredInRound: evidence.discovered_in_round,
    citationLabel: evidence.citation_label,
  };
}

function briefFromWire(brief: ResearchBriefWire): ResearchBriefView {
  return {
    mainQuestion: brief.main_question, scope: brief.scope, timeRange: brief.time_range,
    comparisonDimensions: [...brief.comparison_dimensions], expectedOutput: brief.expected_output,
    sourcePreferences: [...brief.source_preferences], assumptions: [...brief.assumptions],
    exclusions: [...brief.exclusions],
  };
}

function issueFromWire(issue: ReviewIssueWire): ReviewIssueView {
  return { sectionId: issue.section_id, paragraphId: issue.paragraph_id, evidenceId: issue.evidence_id, message: issue.message };
}

function reviewFromWire(review: ReviewResultWire): ReviewView {
  return {
    verdict: review.verdict, blockingIssues: review.blocking_issues.map(issueFromWire),
    unsupportedClaims: review.unsupported_claims.map(issueFromWire),
    conflictingEvidence: review.conflicting_evidence.map(issueFromWire),
    missingSections: [...review.missing_sections], revisionInstructions: [...review.revision_instructions],
    followUpTasks: review.follow_up_tasks.map(taskFromWire),
  };
}

function dictionary<TWire, TView>(records: Record<string, TWire>, convert: (item: TWire) => TView): Record<string, TView> {
  return Object.fromEntries(Object.entries(records).map(([id, item]) => [id, convert(item)]));
}

export function stateFromSnapshot(snapshot: ResearchSnapshot): ResearchUIState {
  return {
    threadId: snapshot.thread_id, runId: snapshot.run_id, status: snapshot.status,
    clarification: snapshot.clarification,
    researchBrief: snapshot.research_brief ? briefFromWire(snapshot.research_brief) : null,
    tasks: dictionary(snapshot.tasks, taskFromWire), sources: dictionary(snapshot.sources, sourceFromWire),
    evidence: dictionary(snapshot.evidence, evidenceFromWire),
    review: snapshot.review ? reviewFromWire(snapshot.review) : null,
    report: snapshot.report ?? "", progressEvents: [],
    error: snapshot.errors.at(-1)?.message ?? null, lastSequence: 0,
  };
}

function placeholderTask(taskId: string): ResearchTaskView {
  return {
    taskId, title: `Task ${taskId}`, objective: "Task details are available in the saved research state.",
    completionCriteria: [], searchQueries: [], status: "pending", currentRound: 0,
    parentTaskId: null, gapReason: null, error: null,
  };
}

function mergeWireTasks(current: Record<string, ResearchTaskView>, tasks?: ResearchTaskWire[]): Record<string, ResearchTaskView> {
  if (!tasks?.length) return current;
  const next = { ...current };
  for (const task of tasks) next[task.task_id] = taskFromWire(task);
  return next;
}

function updateTask(state: ResearchUIState, taskId: string, patch: Partial<ResearchTaskView>): ResearchUIState {
  const current = state.tasks[taskId] ?? placeholderTask(taskId);
  return { ...state, tasks: { ...state.tasks, [taskId]: { ...current, ...patch } } };
}

function emptyReview(verdict: ReviewView["verdict"]): ReviewView {
  return { verdict, blockingIssues: [], unsupportedClaims: [], conflictingEvidence: [], missingSections: [], revisionInstructions: [], followUpTasks: [] };
}

export function applyResearchEvent(current: ResearchUIState, event: ResearchEvent): ResearchUIState {
  if (current.runId !== null && event.run_id !== current.runId && event.type !== "run_started") return current;
  if (event.run_id === current.runId && event.sequence <= current.lastSequence) return current;

  const startsNewThread = event.type === "run_started" && current.threadId !== null && current.threadId !== event.thread_id;
  const prior = startsNewThread ? initialResearchState() : current;
  const state: ResearchUIState = {
    ...prior,
    threadId: event.thread_id,
    runId: event.run_id,
    lastSequence: event.sequence,
    progressEvents: [...prior.progressEvents, event],
  };

  switch (event.type) {
    case "run_started":
      return { ...state, status: "running", clarification: null, error: null };
    case "clarification_required":
      return { ...state, status: "waiting_for_user", clarification: event.payload.question };
    case "research_brief_created":
    case "coverage_assessed":
    case "draft_created":
      return state;
    case "plan_created":
      return { ...state, tasks: mergeWireTasks(state.tasks, event.payload.tasks) };
    case "task_started":
      return updateTask(state, event.payload.task_id, { status: "running" });
    case "search_started":
      return updateTask(state, event.payload.task_id, { status: "running", currentRound: event.payload.round });
    case "search_completed":
      return updateTask(state, event.payload.task_id, { currentRound: event.payload.round });
    case "evidence_added": {
      const sources = { ...state.sources };
      for (const source of event.payload.sources ?? []) sources[source.source_id] = sourceFromWire(source);
      const evidence = { ...state.evidence };
      for (const item of event.payload.evidence ?? []) evidence[item.evidence_id] = evidenceFromWire(item);
      return { ...updateTask(state, event.payload.task_id, { currentRound: event.payload.round }), sources, evidence };
    }
    case "gap_assessed":
      return updateTask(state, event.payload.task_id, {
        gapReason: event.payload.coverage === "sufficient" ? null : `Coverage is ${event.payload.coverage}.`,
      });
    case "task_completed":
      return updateTask(state, event.payload.task_id, { status: event.payload.status, currentRound: event.payload.round });
    case "task_failed":
      return updateTask(state, event.payload.task_id, { status: "failed", currentRound: event.payload.round, error: event.payload.error_code });
    case "additional_tasks_created":
      return { ...state, tasks: mergeWireTasks(state.tasks, event.payload.tasks) };
    case "review_completed":
      return event.payload.verdict ? { ...state, review: emptyReview(event.payload.verdict) } : state;
    case "revision_started":
      return { ...state, status: "running" };
    case "report_finalized":
      return { ...state, report: event.payload.report ?? state.report };
    case "run_cancelled":
      return { ...state, status: "cancelled", error: null };
    case "error":
      return { ...state, status: "failed", error: event.payload.message };
    case "done":
      return { ...state, status: event.payload.status };
    default: {
      const exhaustive: never = event;
      return exhaustive;
    }
  }
}

function localEvent(state: ResearchUIState, type: "run_cancelled" | "error", payload: Record<string, unknown>): ResearchEvent {
  return {
    type,
    run_id: state.runId ?? "client-run",
    thread_id: state.threadId ?? "client-thread",
    sequence: state.lastSequence + 1,
    timestamp: new Date().toISOString(),
    payload,
  } as ResearchEvent;
}

export function useResearchStore(api: ResearchApiClient = defaultApi): ResearchStore {
  const mutableState = shallowRef<ResearchUIState>(initialResearchState());
  const state = computed(() => mutableState.value);
  let controller: AbortController | null = null;
  const receive: ResearchEventHandler = (event) => {
    mutableState.value = applyResearchEvent(mutableState.value, event);
  };

  async function runStream(operation: (signal: AbortSignal) => Promise<void>): Promise<void> {
    controller?.abort();
    controller = new AbortController();
    const active = controller;
    try {
      await operation(active.signal);
    } catch (reason) {
      if (active.signal.aborted) return;
      const message = reason instanceof Error ? reason.message : "Research request failed.";
      mutableState.value = applyResearchEvent(mutableState.value, localEvent(mutableState.value, "error", {
        error_code: "client_request_failed",
        stage: "client",
        message,
        task_id: null,
        retryable: true,
        attempt: 1,
        details: {},
      }));
    } finally {
      if (controller === active) controller = null;
    }
  }

  async function start(query: string): Promise<void> {
    mutableState.value = initialResearchState();
    await runStream((signal) => api.startResearch(query, receive, signal));
  }

  async function resume(answer: string): Promise<void> {
    const threadId = mutableState.value.threadId;
    if (threadId === null) throw new Error("Cannot resume research without a thread ID.");
    await runStream((signal) => api.resumeResearch(threadId, answer, receive, signal));
  }

  async function cancel(): Promise<void> {
    const threadId = mutableState.value.threadId;
    controller?.abort();
    if (threadId === null) return;
    await api.cancelResearch(threadId);
    if (mutableState.value.threadId === threadId && mutableState.value.status !== "cancelled") {
      mutableState.value = applyResearchEvent(
        mutableState.value,
        localEvent(mutableState.value, "run_cancelled", { message: "Research was cancelled." }),
      );
    }
  }

  async function restore(threadId: string): Promise<void> {
    mutableState.value = stateFromSnapshot(await api.getSnapshot(threadId));
  }

  return { state, start, resume, cancel, restore };
}

type TestActionOverrides = {
  start?: (query: string) => unknown;
  resume?: (answer: string) => unknown;
  cancel?: () => unknown;
  restore?: (threadId: string) => unknown;
};

export function createResearchStoreForTest(
  actions: TestActionOverrides = {},
  stateOverrides: Partial<ResearchUIState> = {},
): ResearchStore {
  const state = shallowRef<ResearchUIState>({ ...initialResearchState(), ...stateOverrides });
  return {
    state: computed(() => state.value),
    start: async (query) => { await actions.start?.(query); },
    resume: async (answer) => { await actions.resume?.(answer); },
    cancel: async () => { await actions.cancel?.(); },
    restore: async (threadId) => { await actions.restore?.(threadId); },
  };
}
