import { Bot } from "lucide-react";
import { Badge } from "@/components/ui/display";
import { humanize } from "@/lib/format";
import type { Lead, LeadStage } from "@/features/business/types";

export const STAGES: LeadStage[] = ["new", "qualified", "proposal", "won", "lost"];
export const OPEN_STAGES: LeadStage[] = ["new", "qualified", "proposal"];

export const STAGE_LABELS: Record<LeadStage, string> = {
  new: "New",
  qualified: "Qualified",
  proposal: "Proposal",
  won: "Won",
  lost: "Lost",
};

export const STAGE_DESCRIPTIONS: Record<LeadStage, string> = {
  new: "Just captured, not yet qualified",
  qualified: "Real need and budget confirmed",
  proposal: "Quote or proposal shared",
  won: "Closed and converted",
  lost: "Closed without a sale",
};

export const LEAD_SOURCE_LABELS: Record<Lead["source"], string> = {
  manual: "Manual",
  pi: "PI (WhatsApp)",
  website: "Website",
  referral: "Referral",
};

export const EDITABLE_SOURCES = ["manual", "website", "referral"] as const;

export function isStage(value: string): value is LeadStage {
  return (STAGES as string[]).includes(value);
}

export function stageLabel(stage: string) {
  return isStage(stage) ? STAGE_LABELS[stage] : humanize(stage);
}

export function LeadSourceBadge({ source, compact = false }: { source: Lead["source"]; compact?: boolean }) {
  if (source === "pi") {
    return (
      <Badge tone="pi">
        <Bot aria-hidden="true" /> {compact ? "PI" : "Captured by PI"}
      </Badge>
    );
  }
  return <Badge tone="outline">{LEAD_SOURCE_LABELS[source]}</Badge>;
}

/** Human-readable rendering of a free-form requirement value captured by PI. */
export function formatRequirement(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map(formatRequirement).join(", ");
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function requirementEntries(requirements: Record<string, unknown>) {
  return Object.entries(requirements).filter(([, v]) => v !== null && v !== undefined && v !== "");
}
