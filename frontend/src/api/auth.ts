import { apiFetch } from "./http";

const ROOT = "/api/v1/auth";

export interface AuthStatus {
  registration_open: boolean;
  authenticated: boolean;
}

export interface AuthOwner {
  user_id: string;
  username: string;
  role: "owner";
  csrf_token: string;
}

async function json<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

export async function getAuthStatus(): Promise<AuthStatus> {
  return json<AuthStatus>(await apiFetch(`${ROOT}/status`));
}

export async function registerOwner(
  username: string,
  password: string,
): Promise<AuthOwner> {
  return json<AuthOwner>(
    await apiFetch(`${ROOT}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  );
}

export async function loginOwner(
  username: string,
  password: string,
): Promise<AuthOwner> {
  return json<AuthOwner>(
    await apiFetch(`${ROOT}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  );
}

export async function getCurrentOwner(): Promise<AuthOwner> {
  return json<AuthOwner>(await apiFetch(`${ROOT}/me`));
}

export async function logoutOwner(): Promise<void> {
  await apiFetch(`${ROOT}/logout`, { method: "POST" });
}