/**
 * Browser client for the Pi app API. Same-origin only (/api/v1/pi-app is proxied to the
 * shared API), so the HttpOnly `pi_session` cookie stays first-party. Mutations echo the
 * session-bound `pi_csrf` cookie. Server messages are shown only through `errorText`,
 * which uses the API's safe, customer-facing message.
 */

const BASE = "/api/v1/pi-app";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

function csrf(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)pi_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export async function api<T = unknown>(
  method: Method,
  path: string,
  body?: unknown,
  init?: {
    signal?: AbortSignal;
    query?: Record<string, string | number | boolean | undefined | null>;
    /** Uploads that are transcribed or read can take longer than a normal call. */
    timeoutMs?: number;
  },
): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [key, value] of Object.entries(init?.query ?? {})) {
    if (value !== undefined && value !== null && value !== "")
      url.searchParams.set(key, String(value));
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  const multipart = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !multipart)
    headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrf();
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    init?.timeoutMs ?? 30_000,
  );
  init?.signal?.addEventListener("abort", () => controller.abort());
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: "same-origin",
      body: multipart
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(
      0,
      "NETWORK",
      "We couldn't reach Pi. Check your connection and try again.",
    );
  } finally {
    clearTimeout(timeout);
  }
  if (response.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const error = (
      data as { error?: { code?: string; message?: string } } | null
    )?.error;
    throw new ApiError(
      response.status,
      error?.code ?? (response.status === 401 ? "UNAUTHENTICATED" : "ERROR"),
      friendly(response.status, error?.message),
    );
  }
  return data as T;
}

function friendly(status: number, message?: string): string {
  if (status === 401) return "Please sign in again.";
  if (status === 403)
    return "You don't have access to this. Ask your business owner.";
  if (status === 404) return "We couldn't find that. It may have been removed.";
  if (status === 429)
    return "That's a lot of requests. Please wait a moment and try again.";
  if (status >= 500 && !message)
    return "Something went wrong on our side. Please try again.";
  return message || "Something went wrong. Please try again.";
}

export function errorText(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Something went wrong. Please try again.";
}

export const get = <T>(
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
) => api<T>("GET", path, undefined, { query });
export const post = <T>(path: string, body?: unknown) =>
  api<T>("POST", path, body ?? {});
export const put = <T>(path: string, body?: unknown) =>
  api<T>("PUT", path, body ?? {});
export const patch = <T>(path: string, body?: unknown) =>
  api<T>("PATCH", path, body ?? {});
export const del = <T>(path: string) => api<T>("DELETE", path);
