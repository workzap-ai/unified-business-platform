/**
 * Fetch helper for the public, token-authenticated pay-by-link pages
 * (apps/pi/src/app/pay/...). Unlike every other screen in this app, these pages have
 * no session: there is no `pi_csrf` cookie to echo on a mutation, and the single-use
 * token in the URL is the only credential the API checks (see
 * app/modules/pi_saas/pay_links.py on the backend). This mirrors the JSON/error-shape
 * conventions of `api()` in `./api` minus the CSRF header and cookie dependency, so
 * `ApiError`/`errorText` from `./api` still work unchanged against it.
 */

import { ApiError } from "./api";

const BASE = "/api/v1/pi-app";

type Method = "GET" | "POST";

async function publicApi<T = unknown>(
  method: Method,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const multipart = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !multipart)
    headers["Content-Type"] = "application/json";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers,
      body: multipart
        ? (body as FormData)
        : body === undefined
          ? undefined
          : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(
      0,
      "NETWORK",
      "We couldn't reach pi. Check your connection and try again.",
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
      error?.code ?? "ERROR",
      friendly(response.status, error?.message),
    );
  }
  return data as T;
}

function friendly(status: number, message?: string): string {
  if (status === 404)
    return "This link isn't valid. It may have expired or already been used.";
  if (status === 429)
    return "That's a lot of attempts. Please wait a while and try again.";
  if (status >= 500 && !message)
    return "Something went wrong on our side. Please try again.";
  return message || "Something went wrong. Please try again.";
}

export const publicGet = <T>(path: string) => publicApi<T>("GET", path);
export const publicPost = <T>(path: string, body?: unknown) =>
  publicApi<T>("POST", path, body ?? {});
