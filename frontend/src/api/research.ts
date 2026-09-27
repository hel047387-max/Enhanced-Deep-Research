import { ApiError, apiFetch } from "./http";
export { ApiError } from "./http";
import type {
  ResearchEvent,
  ResearchEventType,
  ResearchSnapshot,
  ArchiveSummary,
  ArchiveDetail,
  MemorySearchResult,
} from "../types/research";

const API_ROOT = "/api/v1/research";
const TERMINAL_EVENTS = new Set<ResearchEventType>(["done", "error"]);
const EVENT_TYPES = new Set<ResearchEventType>([
  "run_started",
  "clarification_required",
  "research_brief_created",
  "plan_created",
  "memory_recalled",
  "memory_saved",
  "memory_save_failed",
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
  body: Record<string, string | boolean>,
  onEvent: ResearchEventHandler,
  signal: AbortSignal,
): Promise<void> {
  const response = await apiFetch(`${API_ROOT}${path}`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
  });
  if (response.body === null) throw new ApiError(502, "Research stream was unavailable.");
  await parseSseStream(response.body, onEvent, signal);
}

export function startResearch(
  query: string,
  onEvent: ResearchEventHandler,
  signal: AbortSignal,
  useMemory = true,
  useLiterature = false,
): Promise<void> {
  return streamRequest("/stream", { query, use_memory: useMemory, use_literature: useLiterature }, onEvent, signal);
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
  const response = await apiFetch(`${API_ROOT}/${encodeURIComponent(threadId)}/cancel`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
}

export async function getSnapshot(threadId: string): Promise<ResearchSnapshot> {
  const response = await apiFetch(`${API_ROOT}/${encodeURIComponent(threadId)}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return (await response.json()) as ResearchSnapshot;
}

const MEMORY_ROOT = "/api/v1/memories";

export async function listArchives(offset = 0): Promise<ArchiveSummary[]> {
  const response = await apiFetch(`${MEMORY_ROOT}/researches?limit=20&offset=${offset}`);
  const body = (await response.json()) as { items: ArchiveSummary[] };
  return body.items;
}

export async function getArchive(threadId: string): Promise<ArchiveDetail> {
  const response = await apiFetch(`${MEMORY_ROOT}/researches/${encodeURIComponent(threadId)}`);
  return (await response.json()) as ArchiveDetail;
}

export async function searchMemory(query: string): Promise<MemorySearchResult> {
  const response = await apiFetch(`${MEMORY_ROOT}/search?q=${encodeURIComponent(query)}`);
  return (await response.json()) as MemorySearchResult;
}
