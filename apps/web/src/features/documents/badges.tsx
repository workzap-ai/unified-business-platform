"use client";

import { AlertTriangle, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/display";
import { Tooltip } from "@/components/ui/overlays";
import type { Quote } from "@/features/business/types";
import { validityState } from "./lib";

/** Where a document came from. PI-drafted documents are marked distinctly. */
export function SourceBadge({
  source,
  className,
}: {
  source: string;
  className?: string;
}) {
  if (source === "pi") {
    return (
      <Badge tone="pi" className={className}>
        <Bot aria-hidden="true" /> PI
      </Badge>
    );
  }
  if (source === "quote") {
    return (
      <Badge tone="outline" className={className}>
        From quote
      </Badge>
    );
  }
  return (
    <span className={cn("text-xs text-muted-foreground", className)}>
      Manual
    </span>
  );
}

export function ValidUntil({
  quote,
  className,
}: {
  quote: Pick<Quote, "valid_until" | "status">;
  className?: string;
}) {
  const state = validityState(quote);
  const text = formatDate(quote.valid_until);
  if (!state) return <span className={cn("tabular", className)}>{text}</span>;
  return (
    <Tooltip
      content={
        state === "expired"
          ? "Validity date has passed"
          : "Expires within 3 days"
      }
    >
      <span
        className={cn(
          "tabular inline-flex items-center gap-1 font-medium",
          state === "expired" ? "text-danger" : "text-warning",
          className,
        )}
      >
        <AlertTriangle className="size-3.5" aria-hidden="true" />
        {text}
        <span className="sr-only">
          {state === "expired" ? "(expired)" : "(expires soon)"}
        </span>
      </span>
    </Tooltip>
  );
}
