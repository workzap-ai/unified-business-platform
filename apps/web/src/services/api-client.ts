import { z } from "zod";

/**
 * Single typed HTTP client for the platform API. Components never call fetch directly;
 * feature services wrap this and TanStack Query hooks wrap the services.
 *
 * The browser talks to a same-origin /api/v1 path proxied to the API by Next (see
 * next.config.ts), so the HttpOnly session cookie is first-party. Unsafe methods echo
 * the session-bound CSRF cookie in X-CSRF-Token.
 */

const errorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    request_id: z.string(),
    details: z.record(z.string(), z.unknown()).optional(),
  }),
});

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public requestId?: string,
    public serverMessage?: string,
    public fields: Record<string, string> = {},
  ) {
    super("The request could not be completed.");
    this.name = "ApiError";
  }
}

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1"
).replace(/\/$/, "");
export const CSRF_COOKIE = "platform_csrf";

let expectedWorkspace: { tenant: string; environment: string } | null = null;
export function bindApiWorkspace(
  tenant: string | undefined,
  environment: string | undefined,
) {
  expectedWorkspace = tenant && environment ? { tenant, environment } : null;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type Query = Record<string, string | number | boolean | null | undefined>;

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

export function buildPath(path: string, query?: Query): string {
  if (!path.startsWith("/") || path.startsWith("//"))
    throw new Error("Expected an API-relative path");
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export async function apiRequest<T>(
  method: Method,
  path: string,
  schema: z.ZodType<T> | null,
  options: {
    body?: unknown;
    query?: Query;
    signal?: AbortSignal;
    /** Override for slow, one-off operations such as provisioning a workspace. */
    timeoutMs?: number;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const multipart =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  if (expectedWorkspace && !path.startsWith("/auth/")) {
    headers["X-Workspace-Tenant"] = expectedWorkspace.tenant;
    headers["X-Workspace-Environment"] = expectedWorkspace.environment;
  }
  if (options.body !== undefined && !multipart)
    headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  const timeout = AbortSignal.timeout(options.timeoutMs ?? 30_000);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${buildPath(path, options.query)}`, {
      method,
      credentials: "include",
      cache: "no-store",
      headers,
      body: multipart
        ? (options.body as FormData)
        : options.body === undefined
          ? undefined
          : JSON.stringify(options.body),
      signal: options.signal
        ? AbortSignal.any([options.signal, timeout])
        : timeout,
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError(
      0,
      timeout.aborted ? "REQUEST_TIMEOUT" : "NETWORK_UNAVAILABLE",
    );
  }
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const parsed = errorSchema.safeParse(body);
    const fields = parsed.success
      ? ((parsed.data.error.details?.fields as
          Record<string, string> | undefined) ?? {})
      : {};
    throw new ApiError(
      response.status,
      parsed.success
        ? parsed.data.error.code
        : response.status >= 500
          ? "SERVICE_UNAVAILABLE"
          : "REQUEST_FAILED",
      response.headers.get("x-request-id") ?? undefined,
      parsed.success ? parsed.data.error.message : undefined,
      fields,
    );
  }
  return schema ? schema.parse(body) : (body as T);
}

export function apiGet<T>(
  path: string,
  schema: z.ZodType<T>,
  signal?: AbortSignal,
) {
  return apiRequest("GET", path, schema, { signal });
}

/** Operator-safe message: fixed server messages for business rules, generic otherwise. */
export function errorMessage(
  error: unknown,
  fallback = "Something went wrong. Please try again.",
) {
  if (error instanceof ApiError) {
    if (error.code === "NETWORK_UNAVAILABLE")
      return "We couldn’t connect to the service. Check your connection and try again.";
    if (error.code === "REQUEST_TIMEOUT")
      return "The service took too long to respond. Refresh before trying again.";
    if (
      error.code === "SERVICE_UNAVAILABLE" ||
      [502, 503, 504].includes(error.status)
    )
      return "The service is temporarily unavailable. Please try again shortly.";
    if (error.status === 401) return "Your session has ended. Sign in again.";
    if (error.status === 403) return "You don't have permission to do that.";
    if (error.status === 404) return "That record could not be found.";
    if (error.status === 429) return "Too many attempts. Please wait a moment.";
    if ([409, 422].includes(error.status) && error.serverMessage)
      return error.serverMessage;
    if (error.status >= 500)
      return "The service had a problem. Please try again shortly.";
  }
  if (error instanceof DemoError || error instanceof ServiceNotConnectedError)
    return error.message;
  return fallback;
}

/** Raised by demo adapters to mirror a server-side business rule. */
export class DemoError extends Error {}

/** A product capability whose backend API is not deployed in this environment yet. */
export class ServiceNotConnectedError extends Error {
  constructor(public service: string) {
    super(
      `${service} isn't connected in this environment yet. Its backend is deployed in a later phase.`,
    );
    this.name = "ServiceNotConnectedError";
  }
}

export const pageSchema = <T extends z.ZodTypeAny>(item: T) =>
  z.object({
    items: z.array(item),
    total: z.number().int().nonnegative(),
    page: z.number().int().positive(),
    page_size: z.number().int().positive(),
  });

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export const decimal = z
  .union([z.string(), z.number()])
  .transform((v) => String(v));
