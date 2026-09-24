"use client";

import { Check, CircleSlash } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/format";

export type FlowStep = {
  key: string;
  label: string;
  state: "done" | "current" | "upcoming";
  hint?: string;
  at?: string | null;
};

/** Status progression for a document. Terminal outcomes (cancelled, rejected…) show distinctly. */
export function StatusFlow({
  steps,
  terminal,
  orientation = "vertical",
  className,
}: {
  steps: FlowStep[];
  terminal?: { label: string; description?: string; at?: string | null } | null;
  orientation?: "vertical" | "horizontal";
  className?: string;
}) {
  const horizontal = orientation === "horizontal";
  return (
    <div className={className}>
      {terminal && (
        <div className="mb-3 flex items-start gap-2.5 rounded-lg border border-border bg-surface-muted px-3 py-2.5 text-[13px]">
          <CircleSlash className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0">
            <p className="font-semibold">{terminal.label}</p>
            {(terminal.description || terminal.at) && (
              <p className="text-xs text-muted-foreground">
                {terminal.description}
                {terminal.description && terminal.at ? " · " : ""}
                {terminal.at ? formatDateTime(terminal.at) : ""}
              </p>
            )}
          </div>
        </div>
      )}
      <ol
        aria-label="Status progression"
        className={cn(
          horizontal ? "grid grid-cols-1 gap-2 sm:flex sm:items-start sm:gap-0" : "space-y-0",
          terminal && "opacity-60",
        )}
      >
        {steps.map((step, index) => {
          const last = index === steps.length - 1;
          return (
            <li
              key={step.key}
              aria-current={step.state === "current" ? "step" : undefined}
              className={cn(
                "relative flex gap-3",
                horizontal ? "sm:flex-1 sm:flex-col sm:items-center sm:gap-1.5 sm:text-center" : "pb-4 last:pb-0",
              )}
            >
              {!last && (
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute bg-border",
                    horizontal
                      ? "top-7 bottom-[-8px] left-3 w-px sm:top-3 sm:right-[-50%] sm:bottom-auto sm:left-[50%] sm:h-px sm:w-auto"
                      : "top-7 bottom-0 left-3 w-px",
                    step.state === "done" && "bg-success/50",
                  )}
                />
              )}
              <span
                className={cn(
                  "relative z-[1] flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                  step.state === "done" && "border-transparent bg-success-soft text-success",
                  step.state === "current" && "border-primary bg-primary text-primary-foreground",
                  step.state === "upcoming" && "border-border bg-surface text-muted-foreground",
                )}
              >
                {step.state === "done" ? <Check className="size-3.5" aria-hidden="true" /> : index + 1}
              </span>
              <div className={cn("min-w-0 pt-0.5", horizontal && "sm:px-1 sm:pt-0")}>
                <p
                  className={cn(
                    "text-[13px] leading-tight",
                    step.state === "upcoming" ? "text-muted-foreground" : "font-medium",
                  )}
                >
                  {step.label}
                  <span className="sr-only">
                    {step.state === "done" ? " (completed)" : step.state === "current" ? " (current)" : " (upcoming)"}
                  </span>
                </p>
                {(step.hint || step.at) && (
                  <p className="mt-0.5 text-xs text-muted-foreground">{step.at ? formatDateTime(step.at) : step.hint}</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
