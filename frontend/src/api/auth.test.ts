import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getAuthStatus,
  getCurrentOwner,
  loginOwner,
  logoutOwner,
  registerOwner,
} from "./auth";
import { setCsrfToken } from "./http";

afterEach(() => {
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("auth API", () => {
  it("uses the public status, register, login and authenticated me routes", async () => {
    const owner = { user_id: "u1", username: "owner", role: "owner", csrf_token: "csrf" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(Response.json({ registration_open: true, authenticated: false }))
      .mockResolvedValueOnce(Response.json(owner, { status: 201 }))
      .mockResolvedValueOnce(Response.json(owner))
      .mockResolvedValueOnce(Response.json(owner));
    vi.stubGlobal("fetch", fetchMock);

    await getAuthStatus();
    await registerOwner("owner", "correct password");
    await loginOwner("owner", "correct password");
    await getCurrentOwner();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/auth/status",
      "/api/v1/auth/register",
      "/api/v1/auth/login",
      "/api/v1/auth/me",
    ]);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: "POST",
      body: JSON.stringify({ username: "owner", password: "correct password" }),
    });
  });

  it("sends logout through the authenticated transport", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf");

    await logoutOwner();

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/auth/logout");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf");
  });
});