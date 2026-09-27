import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, setCsrfToken, setUnauthorizedHandler } from "../api/http";
import { createAuthStoreForTest } from "./auth";

const owner = { user_id: "u1", username: "owner", role: "owner", csrf_token: "csrf" } as const;

afterEach(() => {
  setCsrfToken(null);
  setUnauthorizedHandler(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("auth store", () => {
  it("routes status to setup, login, or authenticated and restores /me", async () => {
    const setupApi = {
      getStatus: vi.fn().mockResolvedValue({ registration_open: true, authenticated: false }),
      getCurrent: vi.fn(), register: vi.fn(), login: vi.fn(), logout: vi.fn(),
    };
    const setup = createAuthStoreForTest(setupApi);
    await setup.check();
    expect(setup.state.value).toBe("setup");

    const loginApi = {
      ...setupApi,
      getStatus: vi.fn().mockResolvedValue({ registration_open: false, authenticated: false }),
    };
    const login = createAuthStoreForTest(loginApi);
    await login.check();
    expect(login.state.value).toBe("login");

    const restoredApi = {
      ...setupApi,
      getStatus: vi.fn().mockResolvedValue({ registration_open: false, authenticated: true }),
      getCurrent: vi.fn().mockResolvedValue(owner),
    };
    const restored = createAuthStoreForTest(restoredApi);
    await restored.check();
    expect(restoredApi.getCurrent).toHaveBeenCalledOnce();
    expect(restored.state.value).toBe("authenticated");
    expect(restored.owner.value?.username).toBe("owner");
  });

  it("sets the session after registration and clears it on logout", async () => {
    const api = {
      getStatus: vi.fn(), getCurrent: vi.fn(),
      register: vi.fn().mockResolvedValue(owner),
      login: vi.fn(), logout: vi.fn().mockResolvedValue(undefined),
    };
    const store = createAuthStoreForTest(api);

    await store.register("owner", "correct password");
    expect(store.state.value).toBe("authenticated");
    await store.logout();
    expect(store.state.value).toBe("login");
    expect(store.owner.value).toBeNull();
  });

  it("clears in-memory auth after one 401 callback and never uses browser storage", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const api = {
      getStatus: vi.fn(), getCurrent: vi.fn(),
      register: vi.fn().mockResolvedValue(owner), login: vi.fn(), logout: vi.fn(),
    };
    const store = createAuthStoreForTest(api);
    await store.register("owner", "correct password");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ detail: "Authentication required." }, { status: 401 })),
    );

    await apiFetch("/protected").catch(() => undefined);

    expect(store.state.value).toBe("login");
    expect(store.owner.value).toBeNull();
    expect(getItem).not.toHaveBeenCalled();
    expect(setItem).not.toHaveBeenCalled();
  });
});