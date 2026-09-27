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
  | "memory_recalled"
  | "memory_saved"
  | "memory_save_failed"
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

export interface WebSourceWire {
  source_id: string;
  source_kind?: "web";
  url: string;
  canonical_url: string;
  title: string;
  domain: string;
  published_at: string | null;
  retrieved_at: string;
  content_hash: string;
  source_type: "web" | "official" | "news";
}

export interface LiteratureSourceWire {
  source_id: string;
  source_kind: "literature";
  document_id: string;
  unit_id: string;
  title: string;
  authors: string[];
  publication_year: number | null;
  doi: string | null;
  heading_path: string[];
  page_start: number | null;
  page_end: number | null;
  retrieved_at: string;
}

export type SourceWire = WebSourceWire | LiteratureSourceWire;

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
  memory_status?: "saved" | "failed" | null;
  memory_references?: HistoricalResearchReference[];
  memory_warning?: string | null;
  errors: ResearchErrorWire[];
}

export interface ResearchEventPayloads {
  run_started: Record<string, never>;
  clarification_required: { question: string };
  research_brief_created: { brief: ResearchBriefWire };
  plan_created: { task_count: number; tasks: ResearchTaskWire[] };
  memory_recalled: { researches: HistoricalResearchReference[]; warning?: string };
  memory_saved: { status: "saved" };
  memory_save_failed: { status: "failed"; message: string };
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

export interface HistoricalResearchReference {
  thread_id: string;
  question: string;
  completed_at: string;
  summary: string;
  limitations: string[];
  source_urls: string[];
}

export interface ArchiveSummary {
  thread_id: string;
  run_id?: string;
  question: string;
  completed_at: string;
  archive_status?: string;
}

export interface ArchiveDetail extends ArchiveSummary {
  brief: ResearchBriefWire;
  draft: { title: string; limitations: string[] };
  report: string;
  sources: SourceWire[];
  evidence: EvidenceWire[];
  cards: Array<{ card_id: string; card_type: string; text: string; evidence_ids: string[] }>;
}

export interface MemorySearchResult {
  researches: ArchiveSummary[];
  cards: Array<{ card_id: string; thread_id: string; card_type: string; text: string }>;
}

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
  sourceKind: "web" | "literature";
  url: string | null;
  title: string;
  domain: string | null;
  publishedAt: string | null;
  sourceType: "web" | "official" | "news" | "literature";
  authors?: string[];
  headingPath?: string[];
  pageStart?: number | null;
  pageEnd?: number | null;
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
  memoryStatus: "saved" | "failed" | null;
  memoryReferences: HistoricalResearchReference[];
  memoryWarning: string | null;
  progressEvents: ResearchEvent[];
  error: string | null;
  lastSequence: number;
}
