export type RunStatus =
  | "created"
  | "running"
  | "waiting_for_user"
  | "completed"
  | "failed"
  | "cancelled";

export type TaskStatus =
  | "pending"
  | "running"
  | "completed"
  | "insufficient"
  | "failed";

export type CoverageLevel = "sufficient" | "partial" | "insufficient";
export type Relevance = "high" | "medium" | "low";
export type ReviewVerdict = "pass" | "revise" | "research_gap";

export type ResearchEventType =
  | "run_started"
  | "clarification_required"
  | "research_brief_created"
  | "plan_created"
  | "task_started"
  | "search_started"
  | "search_completed"
  | "evidence_added"
  | "gap_assessed"
  | "task_completed"
  | "task_failed"
  | "coverage_assessed"
  | "additional_tasks_created"
  | "draft_created"
  | "review_completed"
  | "revision_started"
  | "report_finalized"
  | "run_cancelled"
  | "error"
  | "done";

export interface ResearchBriefWire {
  main_question: string;
  scope: string;
  time_range: string | null;
  comparison_dimensions: string[];
  expected_output: string;
  source_preferences: string[];
  assumptions: string[];
  exclusions: string[];
}

export interface ResearchTaskWire {
  task_id: string;
  title: string;
  objective: string;
  completion_criteria: string[];
  search_queries: string[];
  status: TaskStatus;
  current_round: number;
  parent_task_id: string | null;
  gap_reason: string | null;
  error: string | null;
}

export interface SourceWire {
  source_id: string;
  url: string;
  canonical_url: string;
  title: string;
  domain: string;
  published_at: string | null;
  retrieved_at: string;
  content_hash: string;
  source_type: "web" | "official" | "news";
}

export interface EvidenceWire {
  evidence_id: string;
  task_id: string;
  source_id: string;
  claim: string;
  excerpt: string;
  context: string;
  relevance: Relevance;
  discovered_in_round: number;
  citation_label: string;
}

export interface ReviewIssueWire {
  section_id: string | null;
  paragraph_id: string | null;
  evidence_id: string | null;
  message: string;
}

export interface ReviewResultWire {
  verdict: ReviewVerdict;
  blocking_issues: ReviewIssueWire[];
  unsupported_claims: ReviewIssueWire[];
  conflicting_evidence: ReviewIssueWire[];
  missing_sections: string[];
  revision_instructions: string[];
  follow_up_tasks: ResearchTaskWire[];
}

export interface ResearchErrorWire {
  error_code: string;
  stage: string;
  message: string;
  task_id: string | null;
  retryable: boolean;
  attempt: number;
  details: Record<string, string | number | boolean | null>;
}

export interface ResearchSnapshot {
  run_id: string;
  thread_id: string;
  status: RunStatus;
  clarification: string | null;
  research_brief: ResearchBriefWire | null;
  tasks: Record<string, ResearchTaskWire>;
  sources: Record<string, SourceWire>;
  evidence: Record<string, EvidenceWire>;
  review: ReviewResultWire | null;
  report: string | null;
  errors: ResearchErrorWire[];
}

export interface ResearchEventPayloads {
  run_started: Record<string, never>;
  clarification_required: { question: string };
  research_brief_created: { brief: ResearchBriefWire };
  plan_created: { task_count: number; tasks: ResearchTaskWire[] };
  task_started: { task_id: string };
  search_started: { task_id: string; round: number; query_count: number };
  search_completed: {
    task_id: string;
    round: number;
    query_count: number;
    result_count: number;
    status: "completed" | "failed";
  };
  evidence_added: {
    task_id: string;
    round: number;
    evidence_ids: string[];
    count: number;
    evidence: EvidenceWire[];
    sources: SourceWire[];
  };
  gap_assessed: {
    task_id: string;
    coverage: CoverageLevel;
    should_continue: boolean;
  };
  task_completed: {
    task_id: string;
    status: "completed" | "insufficient";
    round: number;
    queries_used: number;
  };
  task_failed: {
    task_id: string;
    status: "failed";
    round: number;
    queries_used: number;
    error_code: string;
  };
  coverage_assessed: { task_count: number };
  additional_tasks_created: { tasks?: ResearchTaskWire[]; task_count?: number };
  draft_created: Record<string, never>;
  review_completed:
    | { verdict: ReviewVerdict; review: ReviewResultWire }
    | { status: "incomplete" };
  revision_started: { after_research?: boolean };
  report_finalized: { report: string };
  run_cancelled: { message: string };
  error: ResearchErrorWire;
  done: { status: RunStatus };
}

export type ResearchEvent<K extends ResearchEventType = ResearchEventType> = {
  [T in K]: {
    type: T;
    run_id: string;
    thread_id: string;
    sequence: number;
    timestamp: string;
    payload: ResearchEventPayloads[T];
  };
}[K];

export interface ResearchBriefView {
  mainQuestion: string;
  scope: string;
  timeRange: string | null;
  comparisonDimensions: string[];
  expectedOutput: string;
  sourcePreferences: string[];
  assumptions: string[];
  exclusions: string[];
}

export interface ResearchTaskView {
  taskId: string;
  title: string;
  objective: string;
  completionCriteria: string[];
  status: TaskStatus;
  currentRound: number;
  searchQueries: string[];
  parentTaskId: string | null;
  gapReason: string | null;
  error: string | null;
}

export interface SourceView {
  sourceId: string;
  url: string;
  title: string;
  domain: string;
  publishedAt: string | null;
  sourceType: "web" | "official" | "news";
}

export interface EvidenceView {
  evidenceId: string;
  taskId: string;
  sourceId: string;
  claim: string;
  excerpt: string;
  context: string;
  relevance: Relevance;
  discoveredInRound: number;
  citationLabel: string;
}

export interface ReviewIssueView {
  sectionId: string | null;
  paragraphId: string | null;
  evidenceId: string | null;
  message: string;
}

export interface ReviewView {
  verdict: ReviewVerdict;
  blockingIssues: ReviewIssueView[];
  unsupportedClaims: ReviewIssueView[];
  conflictingEvidence: ReviewIssueView[];
  missingSections: string[];
  revisionInstructions: string[];
  followUpTasks: ResearchTaskView[];
}

export interface ResearchUIState {
  threadId: string | null;
  runId: string | null;
  status: RunStatus;
  clarification: string | null;
  researchBrief: ResearchBriefView | null;
  tasks: Record<string, ResearchTaskView>;
  sources: Record<string, SourceView>;
  evidence: Record<string, EvidenceView>;
  review: ReviewView | null;
  report: string;
  progressEvents: ResearchEvent[];
  error: string | null;
  lastSequence: number;
}
