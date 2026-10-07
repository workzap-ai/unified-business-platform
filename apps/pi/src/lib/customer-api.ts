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

const SIGN_IN_CODES =
  /^(SECOND_STEP_|SIGN_IN_|FACE_|TOO_MANY_|NO_FINGERPRINT|PASSKEY_)/;

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
  method: "GET" | "POST" | "PUT" | "DELETE",
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
    const detail = (
      data as { error?: { code?: string; message?: string } } | null
    )?.error;
    // Sign-in steps explain themselves (tries left, sign in again): keep their words.
    const own = detail?.code && SIGN_IN_CODES.test(detail.code);
    throw new ApiError(
      response.status,
      detail?.code ?? (response.status === 401 ? "UNAUTHENTICATED" : "ERROR"),
      own && detail?.message
        ? detail.message
        : friendly(response.status, detail?.message),
    );
  }
  return data as T;
}

export const customerDelete = async (path: string) =>
  json<void>(await request("DELETE", path));

export const customerGet = async <T>(path: string) =>
  json<T>(await request("GET", path));

export const customerPost = async <T>(path: string, body?: unknown) =>
  json<T>(await request("POST", path, body ?? {}));

export const customerPut = async <T>(path: string, body: unknown) =>
  json<T>(await request("PUT", path, body));

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
  /** pi's one line about where things stand (better than the last raw message). */
  headline: string;
  preview: string;
  with_team: boolean;
  /** False until pi has read the newest messages in this chat. */
  issues_fresh: boolean;
  issues_open: number;
  issues_total: number;
  counts: RequestCounts;
  waiting_on_other_until: string | null;
  issues: CustomerIssue[];
  links: IssueLink[];
};

/** Every number on the dashboard counts requests, in these buckets. */
export type RequestCounts = {
  waiting_on_you: number;
  waiting_on_other: number;
  waiting_on_us: number;
  done: number;
  paused: number;
};

export type Stage =
  | "noted"
  | "need_answer"
  | "on_it"
  | "solution_ready"
  | "building"
  | "live"
  | "paused"
  | "closed";

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
  stage: Stage;
  ball_with: "client" | "team" | "pi" | "none";
  /** The one question waiting for the customer, when it's their turn. */
  open_question: string;
  /** The customer's own words; the title is pi's clean version. */
  original_words: string;
  summary: string;
  next_step: string;
  next_step_owner: "you" | "team" | "pi" | "none";
  waiting_since: string | null;
  waiting_on_other_until: string | null;
  /** When the team said it would update, if it's their turn. */
  next_update_by: string | null;
  overdue: boolean;
  /** Journey steps done out of 7; null when paused or closed. */
  journey_steps: number | null;
  /** The business department handling it, e.g. "Finance". */
  department_name?: string;
  area?: string;
  data_objects?: string[];
  urgency?: number;
  impact?: number;
  root_cause?: string;
  solution_outline?: string;
  outcome?: string;
  /** Requests sharing one id would be solved by one system. */
  solution_id?: string;
  /** How many other requests it is linked to. */
  linked?: number;
};

/** A real connection pi found between two of the customer's requests. */
export type IssueLink = {
  a: number;
  b: number;
  a_title: string;
  b_title: string;
  type: "shared_data" | "same_cause" | "depends_on" | "part_of";
  reason: string;
  benefit: string;
  confidence: number;
};

export type CustomerPrefs = {
  language: "auto" | "en" | "roman_ur" | "ur" | "ar";
  last_seen_at: string | null;
};

export type CustomerShareLink = {
  id: string;
  conversation_id: string | null;
  expires_at: string;
  views: number;
  created_at: string;
  token?: string;
};

export type SharedView = {
  expires_at: string;
  businesses: {
    business: string;
    counts: RequestCounts;
    links?: IssueLink[];
    issues: Pick<
      CustomerIssue,
      | "title"
      | "category"
      | "stage"
      | "ball_with"
      | "summary"
      | "next_step"
      | "next_step_owner"
      | "open_question"
      | "next_update_by"
      | "waiting_on_other_until"
      | "journey_steps"
      | "area"
      | "urgency"
      | "impact"
      | "solution_id"
      | "linked"
    >[];
  }[];
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
  waiting_on_other_until: string | null;
  issues: {
    at: string;
    headline?: string;
    issues: CustomerIssue[];
    links?: IssueLink[];
  } | null;
};

export type CustomerIssues = {
  available: boolean;
  at: string | null;
  headline?: string;
  issues: CustomerIssue[];
  links?: IssueLink[];
};
