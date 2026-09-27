export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`Request failed (${status}): ${detail}`);
    this.name = "ApiError";
  }
}

type UnauthorizedHandler = (() => void) | null;

let csrfToken: string | null = null;
let unauthorizedHandler: UnauthorizedHandler = null;
let unauthorizedNotified = false;
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
  if (token !== null) unauthorizedNotified = false;
}

export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler;
  unauthorizedNotified = false;
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

async function responseError(response: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    const body = (await response.json()) as { detail?: unknown };
    detail = body.detail;
  } catch {
    detail = undefined;
  }
  return new ApiError(response.status, sanitizeDetail(detail));
}

export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!SAFE_METHODS.has(method) && csrfToken !== null) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(input, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 401 && !unauthorizedNotified) {
    unauthorizedNotified = true;
    unauthorizedHandler?.();
  }
  if (!response.ok) throw await responseError(response);
  return response;
}