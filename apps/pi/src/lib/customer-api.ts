/**
 * Browser client for PI Customer (/api/v1/pi-app/customer-portal). It uses the
 * customer's own signed cookie, never a business session; changes echo the
 * `pi_customer_csrf` cookie.
 */

import { ApiError } from "@/lib/api";

const BASE = "/api/v1/pi-app/customer-portal";

function csrf(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)pi_customer_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function friendly(status: number, message?: string): string {
  if (status === 401) return "Please sign in again.";
  if (status === 403) return "Please refresh the page and try again.";
  if (status === 404) return "We couldn't find that.";
  if (status === 429)
    return message || "Too many tries. Please wait a few minutes.";
  if (status >= 500 && !message)
    return "Something went wrong on our side. Please try again.";
  return message || "Something went wrong. Please try again.";
}

async function request(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrf();
  try {
    return await fetch(BASE + path, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(45_000),
    });
  } catch {
    throw new ApiError(
      0,
      "NETWORK",
      "We couldn't connect. Check your internet and try again.",
    );
  }
}

async function json<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (data as { error?: { message?: string } } | null)?.error;
    throw new ApiError(
      response.status,
      response.status === 401 ? "UNAUTHENTICATED" : "ERROR",
      friendly(response.status, detail?.message),
    );
  }
  return data as T;
}

export const customerGet = async <T>(path: string) =>
  json<T>(await request("GET", path));

export const customerPost = async <T>(path: string, body?: unknown) =>
  json<T>(await request("POST", path, body ?? {}));

export async function customerFile(path: string): Promise<Blob> {
  const response = await request("GET", path);
  if (!response.ok) await json(response);
  return response.blob();
}

export type CustomerMe = { phone: string; expires_at: number };

export type CustomerConversationItem = {
  id: string;
  business: string;
  business_phone: string;
  whatsapp_link: string;
  status: "open" | "closed";
  last_message_at: string;
  preview: string;
  with_team: boolean;
  issues_open: number;
  issues_total: number;
  issues_by_status?: { open: number; with_team: number; resolved: number };
  issues_preview: Pick<
    CustomerIssue,
    "title" | "status" | "category" | "department_name"
  >[];
};

export type CustomerMessage = {
  id: string;
  from: "you" | "assistant" | "team" | "business";
  type: string;
  body: string;
  transcript: string | null;
  has_media: boolean;
  status: string | null;
  at: string;
};

export type CustomerIssue = {
  title: string;
  category:
    | "inquiry"
    | "order"
    | "booking"
    | "payment"
    | "complaint"
    | "support"
    | "other";
  status: "open" | "with_team" | "resolved";
  summary: string;
  next_step: string;
  /** The business department handling it, e.g. "Finance". */
  department_name?: string;
};

export type CustomerRequest = {
  kind: "ticket" | "task";
  title: string;
  status: "with_team" | "resolved";
  note: string;
  at: string;
};

export type CustomerConversationDetail = {
  id: string;
  business: string;
  business_phone: string;
  whatsapp_link: string;
  status: "open" | "closed";
  with_team: boolean;
  last_message_at: string;
  messages: CustomerMessage[];
  requests: CustomerRequest[];
  issues: { at: string; issues: CustomerIssue[] } | null;
};

export type CustomerIssues = {
  available: boolean;
  at: string | null;
  issues: CustomerIssue[];
};
