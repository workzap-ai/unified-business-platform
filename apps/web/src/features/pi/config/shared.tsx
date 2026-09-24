"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { humanize } from "@/lib/format";
import { isDemo } from "@/lib/data-mode";
import { Badge, Skeleton } from "@/components/ui/display";
import { Switch } from "@/components/ui/controls";
import type {
  AgentKey,
  HandoffReason,
  KnowledgeSource,
  ProviderName,
  ToolDefinition,
} from "../types";

/* Query keys --------------------------------------------------------------------------- */

export const piKeys = {
  agents: ["pi", "agents"] as const,
  agent: (id: string) => ["pi", "agents", "detail", id] as const,
  versions: (id: string) => ["pi", "agents", "versions", id] as const,
  tools: ["pi", "tools"] as const,
  connection: ["pi", "whatsapp", "connection"] as const,
  events: ["pi", "whatsapp", "events"] as const,
  sources: ["pi", "knowledge", "sources"] as const,
  documents: ["pi", "knowledge", "documents"] as const,
  document: (id: string) => ["pi", "knowledge", "document", id] as const,
  analytics: (range: number) => ["pi", "analytics", range] as const,
  settings: ["pi", "settings"] as const,
};

/* Vocabulary ----------------------------------------------------------------------------- */

export const AGENT_ORDER: AgentKey[] = [
  "router",
  "customer_memory",
  "support",
  "requirement",
  "sales_order",
  "handoff",
];

export const AGENT_LABELS: Record<AgentKey, string> = {
  router: "Router",
  customer_memory: "Customer & Memory",
  support: "Support",
  requirement: "Requirement",
  sales_order: "Sales & Order",
  handoff: "Handoff",
};

export const PROVIDER_LABELS: Record<ProviderName, string> = {
  openai: "OpenAI",
  gemini: "Gemini",
  groq: "Groq",
};

export const MODEL_ALIASES: {
  value: "fast" | "balanced" | "reasoning";
  label: string;
  description: string;
}[] = [
  {
    value: "fast",
    label: "Fast",
    description:
      "Lowest latency and cost. Best for routing, greetings and short factual answers.",
  },
  {
    value: "balanced",
    label: "Balanced",
    description:
      "Good quality at moderate latency. The default for most customer replies.",
  },
  {
    value: "reasoning",
    label: "Reasoning",
    description:
      "Slower and more expensive. Use for multi-step requirements and complex orders.",
  },
];

export const HANDOFF_REASON_LABELS: Record<HandoffReason, string> = {
  customer_request: "Customer asked for a person",
  low_confidence: "Low confidence",
  provider_failure: "AI provider failure",
  policy: "Policy rule",
  tool_failure: "Tool failure",
  complaint: "Complaint",
  sensitive: "Sensitive topic",
  manual: "Manual",
};

export const SOURCE_KIND_LABELS: Record<KnowledgeSource["kind"], string> = {
  company_info: "Company info",
  faq: "FAQ",
  policy: "Policy",
  catalog: "Catalog",
  approved_answer: "Approved answer",
  file: "File",
};

export const MUTATION_WARNING =
  "Changes business data — always requires customer confirmation or policy checks";

const ERROR_MESSAGES: Record<string, string> = {
  UNSUPPORTED_ENCODING:
    "The file encoding isn't supported. Save it as UTF-8 text.",
  MEDIA_TOO_LARGE: "The media file is larger than the allowed size.",
  PROCESSING_TIMEOUT: "Processing took too long and was stopped. Try again.",
  RECIPIENT_UNAVAILABLE:
    "The recipient can't receive messages right now (not on WhatsApp or outside the 24-hour window).",
  SIGNATURE_INVALID:
    "The webhook signature didn't match, so the event was rejected.",
  TOKEN_INVALID: "The access token was rejected. Enter a new token.",
  TOKEN_EXPIRED: "The access token has expired. Enter a new token.",
  RATE_LIMITED: "WhatsApp rate-limited this number. Messages will retry.",
  EMPTY_DOCUMENT: "The document has no readable text.",
  DOCUMENT_TOO_LARGE: "The document is larger than 1 MB.",
  rate_limit: "Provider rate limit",
  timeout: "Provider timeout",
  provider_unavailable: "Provider unavailable",
  all_providers_failed: "All providers failed",
  invalid_response: "Invalid provider response",
};

/** Operator-safe explanation of an error code. Never shows raw provider payloads. */
export function humanizeError(code: string | null | undefined) {
  if (!code) return "—";
  return ERROR_MESSAGES[code] ?? humanize(code.toLowerCase());
}

export function formatLatency(ms: number) {
  if (!ms) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

export function formatBytesKb(bytes: number) {
  return `${(bytes / 1024).toLocaleString("en-US", { maximumFractionDigits: 1 })} KB`;
}

/* Components ----------------------------------------------------------------------------- */

/** Secondary section tabs, styled like ModuleNav tabs. */
export function SubNav({
  label,
  items,
  className,
}: {
  label: string;
  items: { href: string; label: string; exact?: boolean }[];
  className?: string;
}) {
  const pathname = usePathname();
  const active = items
    .filter((i) =>
      i.exact
        ? pathname === i.href
        : pathname === i.href || pathname.startsWith(`${i.href}/`),
    )
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;
  return (
    <nav
      aria-label={label}
      className={cn(
        "scrollbar-thin mb-5 overflow-x-auto border-b border-border",
        className,
      )}
    >
      <ul className="flex min-w-max items-center gap-1">
        {items.map((item) => {
          const current = item.href === active;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "relative -mb-px flex h-9 items-center border-b-2 px-2.5 text-[13px] font-medium transition-colors",
                  current
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function CapabilityBadge({
  capability,
}: {
  capability: ToolDefinition["capability"];
}) {
  const tone = {
    read: "neutral",
    draft: "info",
    mutation: "warning",
    communication: "primary",
  } as const;
  return <Badge tone={tone[capability]}>{humanize(capability)}</Badge>;
}

/** Label + description + switch in one accessible row. */
export function ToggleRow({
  id,
  label,
  description,
  checked,
  onCheckedChange,
  disabled,
  className,
}: {
  id: string;
  label: React.ReactNode;
  description?: React.ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn("flex items-start justify-between gap-4 py-2.5", className)}
    >
      <div className="min-w-0">
        <label htmlFor={id} className="text-[13px] font-medium">
          {label}
        </label>
        {description && (
          <p
            id={`${id}-description`}
            className="mt-0.5 text-xs text-muted-foreground"
          >
            {description}
          </p>
        )}
      </div>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-describedby={description ? `${id}-description` : undefined}
      />
    </div>
  );
}

export function SampleDataNote({ className }: { className?: string }) {
  if (!isDemo) return null;
  return (
    <p
      className={cn(
        "flex items-center gap-1.5 text-xs text-muted-foreground",
        className,
      )}
    >
      <Info className="size-3.5" aria-hidden="true" />
      Figures shown in sample-data mode are illustrative.
    </p>
  );
}

export function CardsSkeleton({
  count = 6,
  className,
  itemClassName = "h-44",
}: {
  count?: number;
  className?: string;
  itemClassName?: string;
}) {
  return (
    <div
      className={cn("grid gap-3 md:grid-cols-2 xl:grid-cols-3", className)}
      aria-busy="true"
      aria-label="Loading"
    >
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} className={cn("rounded-xl", itemClassName)} />
      ))}
    </div>
  );
}

/** A small stat tile used inside cards. */
export function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "danger" | "warning" | "success";
}) {
  return (
    <div className="min-w-0">
      <p className="truncate text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          "tabular mt-0.5 truncate text-[13.5px] font-semibold",
          tone === "danger" && "text-danger",
          tone === "warning" && "text-warning",
          tone === "success" && "text-success",
        )}
      >
        {value}
      </p>
    </div>
  );
}
