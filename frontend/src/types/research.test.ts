import { describe, expect, it } from "vitest";
import type { ResearchEvent } from "./research";

describe("ResearchEvent", () => {
  it("accepts the exact shared event envelope", () => {
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
