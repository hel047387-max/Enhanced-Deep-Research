import type {
  ResearchEvent,
  ResearchEventType,
  ResearchSnapshot,
} from "../types/research";

const API_ROOT = "/api/v1/research";
const TERMINAL_EVENTS = new Set<ResearchEventType>(["done", "error"]);
const EVENT_TYPES = new Set<ResearchEventType>([
  "run_started",
  "clarification_required",
  "research_brief_created",
  "plan_created",
  "task_started",
  "search_started",
  "search_completed",
  "evidence_added",
  "gap_assessed",
  "task_completed",
  "task_failed",
  "coverage_assessed",
  "additional_tasks_created",
  "draft_created",
  "review_completed",
  "revision_started",
  "report_finalized",
  "run_cancelled",
  "error",
  "done",
]);

export type ResearchEventHandler = (event: ResearchEvent) => void;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`Request failed (${status}): ${detail}`);
    this.name = "ApiError";
  }
}

function sanitizeDetail(value: unknown): string {
  if (typeof value !== "string") return "Request failed.";
  const clean = value
    .replace(/<[^>]*>/g, "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 300);
  return clean || "Request failed.";
}

async function apiError(response: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    const body = (await response.json()) as { detail?: unknown };
    detail = body.detail;
  } catch {
    detail = undefined;
  }
  return new ApiError(response.status, sanitizeDetail(detail));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isResearchEvent(value: unknown): value is ResearchEvent {
  if (!isRecord(value)) return false;
  return (
    typeof value.type === "string" &&
    EVENT_TYPES.has(value.type as ResearchEventType) &&
    typeof value.run_id === "string" &&
    value.run_id.length > 0 &&
    typeof value.thread_id === "string" &&
    value.thread_id.length > 0 &&
    Number.isInteger(value.sequence) &&
    (value.sequence as number) >= 1 &&
    typeof value.timestamp === "string" &&
    isRecord(value.payload)
  );
}

function parseFrame(frame: string): ResearchEvent | null {
  const data = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) return null;
  try {
    const candidate: unknown = JSON.parse(data);
    return isResearchEvent(candidate) ? candidate : null;
  } catch {
    return null;
  }
}

export async function parseSseStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: ResearchEventHandler,
  signal?: AbortSignal,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let terminal = false;
  const abort = () => {
    void reader.cancel().catch(() => undefined);
  };

  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  try {
    while (!signal?.aborted && !terminal) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = parseFrame(frame);
        if (event === null) continue;
        onEvent(event);
        if (TERMINAL_EVENTS.has(event.type)) {
          terminal = true;
          break;
        }
      }
    }

    if (!signal?.aborted && !terminal) {
      buffer += decoder.decode();
      const event = parseFrame(buffer);
      if (event !== null) onEvent(event);
    }
  } finally {
    signal?.removeEventListener("abort", abort);
    if (terminal) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

async function streamRequest(
  path: string,
  body: Record<string, string>,
  onEvent: ResearchEventHandler,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_ROOT}${path}`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw await apiError(response);
  if (response.body === null) throw new ApiError(502, "Research stream was unavailable.");
  await parseSseStream(response.body, onEvent, signal);
}

export function startResearch(
  query: string,
  onEvent: ResearchEventHandler,
  signal: AbortSignal,
): Promise<void> {
  return streamRequest("/stream", { query }, onEvent, signal);
}

export function resumeResearch(
  threadId: string,
  answer: string,
  onEvent: ResearchEventHandler,
  signal: AbortSignal,
): Promise<void> {
  return streamRequest(`/${encodeURIComponent(threadId)}/resume/stream`, { answer }, onEvent, signal);
}

export async function cancelResearch(threadId: string): Promise<void> {
  const response = await fetch(`${API_ROOT}/${encodeURIComponent(threadId)}/cancel`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw await apiError(response);
}

export async function getSnapshot(threadId: string): Promise<ResearchSnapshot> {
  const response = await fetch(`${API_ROOT}/${encodeURIComponent(threadId)}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as ResearchSnapshot;
}
