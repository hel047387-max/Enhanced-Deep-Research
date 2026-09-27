import { computed, shallowRef, type Ref } from "vue";
import * as authApi from "../api/auth";
import type { AuthOwner, AuthStatus } from "../api/auth";
import { setCsrfToken, setUnauthorizedHandler } from "../api/http";

export type AuthState = "checking" | "setup" | "login" | "authenticated";

export interface AuthApiClient {
  getStatus(): Promise<AuthStatus>;
  getCurrent(): Promise<AuthOwner>;
  register(username: string, password: string): Promise<AuthOwner>;
  login(username: string, password: string): Promise<AuthOwner>;
  logout(): Promise<void>;
}

export interface AuthStore {
  state: Readonly<Ref<AuthState>>;
  owner: Readonly<Ref<AuthOwner | null>>;
  check(): Promise<void>;
  register(username: string, password: string): Promise<void>;
  login(username: string, password: string): Promise<void>;
  logout(): Promise<void>;
}

const defaultApi: AuthApiClient = {
  getStatus: authApi.getAuthStatus,
  getCurrent: authApi.getCurrentOwner,
  register: authApi.registerOwner,
  login: authApi.loginOwner,
  logout: authApi.logoutOwner,
};

function createAuthStore(api: AuthApiClient): AuthStore {
  const mutableState = shallowRef<AuthState>("checking");
  const mutableOwner = shallowRef<AuthOwner | null>(null);

  function clearSession(): void {
    mutableOwner.value = null;
    mutableState.value = "login";
    setCsrfToken(null);
  }

  function setSession(owner: AuthOwner): void {
    mutableOwner.value = owner;
    mutableState.value = "authenticated";
    setCsrfToken(owner.csrf_token);
  }

  setUnauthorizedHandler(clearSession);

  async function check(): Promise<void> {
    mutableState.value = "checking";
    const status = await api.getStatus();
    if (status.authenticated) {
      setSession(await api.getCurrent());
    } else {
      mutableOwner.value = null;
      setCsrfToken(null);
      mutableState.value = status.registration_open ? "setup" : "login";
    }
  }

  async function register(username: string, password: string): Promise<void> {
    setSession(await api.register(username, password));
  }

  async function login(username: string, password: string): Promise<void> {
    setSession(await api.login(username, password));
  }

  async function logout(): Promise<void> {
    try {
      await api.logout();
    } finally {
      clearSession();
    }
  }

  return {
    state: computed(() => mutableState.value),
    owner: computed(() => mutableOwner.value),
    check,
    register,
    login,
    logout,
  };
}

let singleton: AuthStore | null = null;

export function useAuthStore(): AuthStore {
  singleton ??= createAuthStore(defaultApi);
  return singleton;
}

export function createAuthStoreForTest(api: AuthApiClient): AuthStore {
  return createAuthStore(api);
}