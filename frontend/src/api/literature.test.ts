import { afterEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "./http";
import { literatureApi } from "./literature";

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("literature API", () => {
  it("uploads FormData with Cookie and CSRF but no forced Content-Type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        document_id: "22222222-2222-4222-8222-222222222222",
        units_indexed: 2,
        metadata: { title: "Paper" },
      }, { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf");

    await literatureApi.uploadDocument(new File(["paper"], "paper.pdf"), { title: "Paper" });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(init.credentials).toBe("same-origin");
    expect(init.body).toBeInstanceOf(FormData);
    expect(headers.get("X-CSRF-Token")).toBe("csrf");
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("uses authenticated transport for search and delete", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(Response.json({ items: [] }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf");

    await literatureApi.searchLiterature("topic");
    await literatureApi.deleteDocument("doc/1");

    for (const [, rawInit] of fetchMock.mock.calls) {
      const init = rawInit as RequestInit;
      expect(init.credentials).toBe("same-origin");
      expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf");
    }
  });
});