import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  cancelResearch,
  getSnapshot,
  getArchive,
  listArchives,
  searchMemory,
  parseSseStream,
  resumeResearch,
  startResearch,
} from "./research";
import { setCsrfToken } from "./http";
import type { ResearchEvent, ResearchSnapshot } from "../types/research";

function byteStream(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(chunk));
      controller.close();
    },
  });
}

function encodedChunks(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return byteStream(chunks.map((chunk) => encoder.encode(chunk)));
}

function eventJson(type: "done" | "run_started", sequence: number, payload = "{}") {
  return `{"type":"${type}","run_id":"r","thread_id":"t","sequence":${sequence},"timestamp":"2026-08-26T00:00:00Z","payload":${payload}}`;
}

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("parseSseStream", () => {
  it("preserves a multi-byte UTF-8 code point split between chunks", async () => {
    const bytes = new TextEncoder().encode(
      `data: ${eventJson("done", 1, '{"status":"completed","note":"研究"}')}\n\n`,
    );
    const marker = bytes.findIndex((byte) => byte >= 0xe0);
    const events: ResearchEvent[] = [];

    await parseSseStream(
      byteStream([bytes.slice(0, marker + 1), bytes.slice(marker + 1)]),
      (event) => events.push(event),
    );

    expect(events).toHaveLength(1);
    expect(events[0]?.payload).toMatchObject({ note: "研究" });
  });

  it("ignores malformed frames and continues with a valid terminal frame", async () => {
    const events: ResearchEvent[] = [];
    await parseSseStream(
      encodedChunks(`data: not-json\n\ndata: ${eventJson("done", 1, '{"status":"completed"}')}\n\n`),
      (event) => events.push(event),
    );

    expect(events.map((event) => event.type)).toEqual(["done"]);
  });

  it("stops after the first terminal event", async () => {
    const events: ResearchEvent[] = [];
    await parseSseStream(
      encodedChunks(
        `data: ${eventJson("done", 1, '{"status":"completed"}')}\n\n`,
        `data: ${eventJson("run_started", 2)}\n\n`,
      ),
      (event) => events.push(event),
    );

    expect(events.map((event) => event.type)).toEqual(["done"]);
  });

  it("cancels a pending stream when its AbortSignal fires", async () => {
    let cancelled = false;
    const stream = new ReadableStream<Uint8Array>({
      cancel() {
        cancelled = true;
      },
    });
    const controller = new AbortController();
    const parsing = parseSseStream(stream, () => undefined, controller.signal);

    controller.abort();
    await parsing;

    expect(cancelled).toBe(true);
  });
});

describe("research API", () => {
  it("posts start and resume bodies to their backend routes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(`data: ${eventJson("done", 1, '{"status":"completed"}')}\n\n`, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onEvent = vi.fn();
    const signal = new AbortController().signal;

    await startResearch("bounded agents", onEvent, signal);
    await resumeResearch("thread one", "2024–2026", onEvent, signal);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/research/stream",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ query: "bounded agents", use_memory: true, use_literature: false }), signal }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/research/thread%20one/resume/stream",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ answer: "2024–2026" }), signal }),
    );
  });

  it("sanitizes non-2xx API details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "<script>alert('x')</script> Invalid request\u0000" }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const error = await getSnapshot("thread-1").catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, detail: "alert('x') Invalid request" });
    expect((error as Error).message).not.toContain("<script>");
  });

  it("gets snapshots and sends explicit cancellation", async () => {
    const snapshot: ResearchSnapshot = {
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
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(Response.json(snapshot))
      .mockResolvedValueOnce(new Response(null, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getSnapshot("thread/1")).resolves.toEqual(snapshot);
    await cancelResearch("thread/1");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/research/thread%2F1", expect.objectContaining({ method: "GET" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/v1/research/thread%2F1/cancel", expect.objectContaining({ method: "POST" }));
  });
  it("uses authenticated transport for research and memory operations", async () => {
    const snapshot = {
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
    } satisfies ResearchSnapshot;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(`data: ${eventJson("done", 1, '{"status":"completed"}')}\n\n`),
      )
      .mockResolvedValueOnce(new Response(null, { status: 202 }))
      .mockResolvedValueOnce(Response.json(snapshot))
      .mockResolvedValueOnce(Response.json({ items: [] }))
      .mockResolvedValueOnce(Response.json({ thread_id: "thread-1" }))
      .mockResolvedValueOnce(Response.json({ researches: [], cards: [] }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf");

    await startResearch("question", vi.fn(), new AbortController().signal);
    await cancelResearch("thread-1");
    await getSnapshot("thread-1");
    await listArchives();
    await getArchive("thread-1");
    await searchMemory("topic");

    for (const [, rawInit] of fetchMock.mock.calls) {
      expect((rawInit as RequestInit).credentials).toBe("same-origin");
    }
    expect(new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).get("X-CSRF-Token")).toBe("csrf");
    expect(new Headers((fetchMock.mock.calls[1]?.[1] as RequestInit).headers).get("X-CSRF-Token")).toBe("csrf");
    expect(new Headers((fetchMock.mock.calls[2]?.[1] as RequestInit).headers).has("X-CSRF-Token")).toBe(false);
  });
});
