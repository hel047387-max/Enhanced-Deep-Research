const configuredBaseUrl = import.meta.env.VITE_BACKEND_URL?.trim().replace(/\/$/, "");

function backendBaseUrl(): string {
  if (configuredBaseUrl) return configuredBaseUrl;
  if (import.meta.env.DEV) return `http://${window.location.hostname}:8000`;
  return "";
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${backendBaseUrl()}/health`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return false;
    const body = (await response.json()) as { status?: unknown };
    return body.status === "ok";
  } catch {
    return false;
  }
}