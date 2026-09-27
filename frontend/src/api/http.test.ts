import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiFetch,
  setCsrfToken,
  setUnauthorizedHandler,
} from "./http";

afterEach(() => {
  setCsrfToken(null);
  setUnauthorizedHandler(null);
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("sends same-origin credentials and CSRF only for unsafe methods", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-value");

    await apiFetch("/read");
    await apiFetch("/write", { method: "POST", body: "{}" });

    const readInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const writeInit = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(readInit.credentials).toBe("same-origin");
    expect(new Headers(readInit.headers).has("X-CSRF-Token")).toBe(false);
    expect(writeInit.credentials).toBe("same-origin");
    expect(new Headers(writeInit.headers).get("X-CSRF-Token")).toBe("csrf-value");
  });

  it("does not force a multipart Content-Type boundary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-value");
    const body = new FormData();
    body.append("file", new File(["paper"], "paper.pdf"));

    await apiFetch("/upload", { method: "POST", body });

    const headers = new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers);
    expect(headers.has("Content-Type")).toBe(false);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-value");
  });

  it("sanitizes backend error details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          { detail: "<script>bad()</script> Invalid\u0000 request" },
          { status: 422 },
        ),
      ),
    );

    const error = await apiFetch("/bad").catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, detail: "bad() Invalid request" });
  });

  it("notifies the unauthorized handler once for repeated 401 responses", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ detail: "Authentication required." }, { status: 401 })),
    );

    await apiFetch("/one").catch(() => undefined);
    await apiFetch("/two").catch(() => undefined);

    expect(handler).toHaveBeenCalledTimes(1);
  });
});