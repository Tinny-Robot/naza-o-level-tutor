/** Fetch wrapper for the FastAPI backend (loopback / Vite proxy only). */

/**
 * In Vite dev, use same-origin `/api` (proxied to 127.0.0.1:8010) so port-forwarded
 * browsers do not call :8010 on the client machine.
 * Override with VITE_API_BASE when needed.
 */
const DEFAULT_BASE = import.meta.env.DEV ? "/api" : "http://127.0.0.1:8010";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.trim() || DEFAULT_BASE;

export class ApiError extends Error {
  status: number;
  offline: boolean;

  constructor(message: string, opts?: { status?: number; offline?: boolean }) {
    super(message);
    this.name = "ApiError";
    this.status = opts?.status ?? 0;
    this.offline = opts?.offline ?? false;
  }
}

export const OFFLINE_ENGINE_MESSAGE =
  "Could not reach the tutor. Make sure the app is running.";

function assertSafeBase(base: string): void {
  // Same-origin relative base (Vite proxy) - always allowed in the desktop shell.
  if (base.startsWith("/")) {
    return;
  }
  let url: URL;
  try {
    url = new URL(base);
  } catch {
    throw new ApiError("Invalid API base URL.", { offline: true });
  }
  if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") {
    throw new ApiError("API base must be localhost only.", { offline: true });
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  assertSafeBase(API_BASE);
  const url = `${API_BASE.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(OFFLINE_ENGINE_MESSAGE, { offline: true, status: 0 });
  }

  if (!res.ok) {
    const offline = res.status >= 500 || res.status === 0;
    throw new ApiError(
      offline ? OFFLINE_ENGINE_MESSAGE : `Request failed (${res.status}).`,
      { status: res.status, offline },
    );
  }

  return (await res.json()) as T;
}
