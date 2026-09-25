"use client";

import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Bot,
  Calendar,
  Check,
  CheckCircle2,
  Copy,
  CreditCard,
  Fingerprint,
  HardDrive,
  KeyRound,
  Landmark,
  Mail,
  MessageCircle,
  ShieldAlert,
  ShoppingBag,
  Users,
  Workflow,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDateTime, relativeTime } from "@/lib/format";
import { isDemo } from "@/lib/data-mode";
import { Button, type ButtonProps } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import { Tooltip } from "@/components/ui/overlays";
import { ModuleNav, PageHeader, PageShell } from "@/components/app/page";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError } from "@/services/api-client";
import { integrationsService } from "./service";
import { formatLatency, maskHint, permissionReason } from "./lib";
import type { Category, CredentialState, TestResult } from "./types";

/* Page frame ----------------------------------------------------------------- */

export function IntegrationsFrame({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <PageShell>
      <PageHeader title={title} description={description} actions={actions} />
      <ModuleNav moduleKey="integrations" />
      {children}
    </PageShell>
  );
}

/* Status vocabulary ---------------------------------------------------------- */

type Tone = "success" | "warning" | "danger" | "info" | "neutral" | "primary";
/** Keys in the shared StatusBadge vocabulary that carry each tone. */
const TONE_KEY: Record<Tone, string> = {
  success: "success",
  warning: "pending",
  danger: "failure",
  info: "running",
  neutral: "draft",
  primary: "shipped",
};

const VALUE_TONES: Record<string, Tone> = {
  // connection status
  draft: "neutral",
  connecting: "info",
  connected: "success",
  degraded: "warning",
  expired: "warning",
  revoked: "neutral",
  disabled: "neutral",
  error: "danger",
  // health
  healthy: "success",
  failing: "danger",
  unknown: "neutral",
  // circuit
  closed: "success",
  open: "danger",
  half_open: "warning",
  // work + events
  pending: "neutral",
  running: "info",
  succeeded: "success",
  failed: "danger",
  dead_letter: "danger",
  cancelled: "neutral",
  paused: "warning",
  received: "neutral",
  queued: "neutral",
  processing: "info",
  processed: "success",
  ignored: "neutral",
  // availability
  available: "success",
  beta: "info",
  planned: "neutral",
  // modes
  production: "primary",
  sandbox: "warning",
  idle: "neutral",
  not_applicable: "neutral",
};

const VALUE_LABELS: Record<string, string> = {
  half_open: "Half-open",
  dead_letter: "Dead letter",
  not_applicable: "Not used",
  closed: "Closed",
  open: "Open",
};

export function valueLabel(value: string) {
  return (
    VALUE_LABELS[value] ??
    value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
  );
}

export function StateBadge({
  value,
  label,
  prefix,
  className,
}: {
  value: string;
  label?: string;
  prefix?: string;
  className?: string;
}) {
  const tone = VALUE_TONES[value] ?? "neutral";
  const text = label ?? valueLabel(value);
  return (
    <StatusBadge
      status={TONE_KEY[tone]}
      label={prefix ? `${prefix}: ${text}` : text}
      className={className}
    />
  );
}

export function CircuitBadge({ value }: { value: string }) {
  return (
    <Tooltip
      content={
        value === "closed"
          ? "Calls flow normally."
          : value === "open"
            ? "Calls are blocked after repeated failures; retried automatically later."
            : "A limited number of trial calls are allowed to check recovery."
      }
    >
      <span tabIndex={0} className="inline-flex rounded-full">
        <StateBadge value={value} prefix="Circuit" />
      </span>
    </Tooltip>
  );
}

/* Glyphs ---------------------------------------------------------------------- */

const CATEGORY_ICONS: Record<Category, LucideIcon> = {
  messaging: MessageCircle,
  ai: Bot,
  email: Mail,
  storage: HardDrive,
  payments: CreditCard,
  calendar: Calendar,
  accounting: Landmark,
  commerce: ShoppingBag,
  collaboration: Users,
  automation: Workflow,
  identity: Fingerprint,
};

export function categoryIcon(category: Category | undefined): LucideIcon {
  return (category && CATEGORY_ICONS[category]) || Workflow;
}

export function IntegrationGlyph({
  category,
  size = "md",
  className,
}: {
  category: Category | undefined;
  size?: "sm" | "md";
  className?: string;
}) {
  const Icon = CATEGORY_ICONS[category ?? "automation"] ?? Workflow;
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-lg border border-border bg-surface-muted text-muted-foreground",
        size === "sm" ? "size-7" : "size-9",
        className,
      )}
      aria-hidden="true"
    >
      <Icon className={size === "sm" ? "size-3.5" : "size-4.5"} />
    </span>
  );
}

/* Permission-aware button ----------------------------------------------------- */

/**
 * A button that stays visible but disabled (with the reason on hover/focus) when the
 * member lacks the permission or the action isn't valid in the current state.
 */
export function GatedButton({
  permission,
  blockedReason,
  children,
  ...props
}: ButtonProps & { permission?: string; blockedReason?: string | null }) {
  const { can } = useSession();
  const denied = permission ? !can(permission) : false;
  const reason = denied ? permissionReason(permission!) : blockedReason;
  if (!reason) return <Button {...props}>{children}</Button>;
  return (
    <Tooltip content={reason}>
      <span tabIndex={0} className="inline-flex rounded-md" aria-label={reason}>
        <Button {...props} disabled aria-disabled="true">
          {children}
        </Button>
      </span>
    </Tooltip>
  );
}

/* Secrets --------------------------------------------------------------------- */

export function CredentialHint({
  credential,
}: {
  credential: CredentialState;
}) {
  return credential.set ? (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
      <KeyRound className="size-3.5 text-success" aria-hidden="true" />
      {maskHint(credential.hint)}
    </span>
  ) : (
    <span className="text-xs font-medium text-danger">Not set</span>
  );
}

/** One-time reveal of a newly issued secret with copy support. */
export function SecretReveal({
  label,
  secret,
  onDone,
  doneLabel = "I've stored it safely",
}: {
  label: string;
  secret: string;
  onDone: () => void;
  doneLabel?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <div
      className="space-y-3 rounded-lg border border-warning/30 bg-warning-soft p-3.5"
      data-testid="secret-reveal"
    >
      <p className="flex items-start gap-2 text-[13px] font-semibold text-warning">
        <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        Copy this now. You won&apos;t see this again.
      </p>
      <div>
        <label
          htmlFor="revealed-secret"
          className="text-xs font-medium text-foreground-secondary"
        >
          {label}
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id="revealed-secret"
            readOnly
            value={secret}
            onFocus={(e) => e.currentTarget.select()}
            className="h-9 min-w-0 flex-1 rounded-md border border-border bg-surface px-2.5 font-mono text-xs"
            data-testid="revealed-secret"
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-9"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(secret);
                setCopied(true);
              } catch {
                setCopied(false);
              }
            }}
          >
            {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </div>
      <p className="text-xs text-foreground-secondary">
        Only a short hint is kept. If you lose it, rotate to issue a new one.
      </p>
      <Button type="button" size="sm" onClick={onDone}>
        {doneLabel}
      </Button>
    </div>
  );
}

/* Test result ----------------------------------------------------------------- */

export function TestResultPanel({ result }: { result: TestResult }) {
  return (
    <div
      role="status"
      data-testid="test-result"
      className={cn(
        "flex items-start gap-3 rounded-lg border px-3.5 py-3",
        result.ok
          ? "border-success/25 bg-success-soft"
          : "border-danger/25 bg-danger-soft",
      )}
    >
      {result.ok ? (
        <CheckCircle2
          className="mt-0.5 size-4 shrink-0 text-success"
          aria-hidden="true"
        />
      ) : (
        <XCircle
          className="mt-0.5 size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
      )}
      <div className="min-w-0 flex-1 text-[13px]">
        <p
          className={cn(
            "font-semibold",
            result.ok ? "text-success" : "text-danger",
          )}
        >
          {result.ok ? "Test passed" : "Test failed"}
          {isDemo && (
            <Badge tone="outline" className="ml-2 align-middle">
              Sample result
            </Badge>
          )}
        </p>
        <p className="mt-0.5 break-words text-foreground-secondary">
          {result.message}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Latency {formatLatency(result.latency_ms)} · status reported by
          server:{" "}
          <span className="font-medium">{valueLabel(result.status)}</span> ·{" "}
          <time
            dateTime={result.checked_at}
            title={formatDateTime(result.checked_at)}
          >
            {relativeTime(result.checked_at)}
          </time>
        </p>
      </div>
    </div>
  );
}

/* Time ------------------------------------------------------------------------ */

export function When({
  value,
  empty = "Never",
}: {
  value: string | null | undefined;
  empty?: string;
}) {
  if (!value) return <span className="text-muted-foreground">{empty}</span>;
  return (
    <time
      dateTime={value}
      title={formatDateTime(value)}
      className="whitespace-nowrap"
    >
      {relativeTime(value)}
    </time>
  );
}

/* Data hooks ------------------------------------------------------------------ */

export function useDefinitions() {
  return useScopedQuery(["integrations", "definitions"], () =>
    integrationsService.definitions(),
  );
}

/** Connection options for filters and name lookups (first 100). */
export function useConnectionIndex() {
  return useScopedQuery(["integrations", "connections", "index"], () =>
    integrationsService.connections({ pageSize: 100 }),
  );
}

/* Server validation ----------------------------------------------------------- */

/**
 * Map `error.details.fields` onto form fields. Keys like `config.url` or
 * `credentials.api_key` are resolved by `setError` (return false when unknown).
 */
export function applyServerFieldErrors(
  error: unknown,
  setError: (name: string, message: string) => boolean,
): { mapped: number; leftovers: string[] } {
  if (!(error instanceof ApiError)) return { mapped: 0, leftovers: [] };
  const leftovers: string[] = [];
  let mapped = 0;
  for (const [key, message] of Object.entries(error.fields)) {
    if (setError(key, message)) mapped += 1;
    else leftovers.push(message);
  }
  return { mapped, leftovers };
}

export function hasFieldErrors(error: unknown) {
  return error instanceof ApiError && Object.keys(error.fields).length > 0;
}
