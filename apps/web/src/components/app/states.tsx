"use client";

import type { LucideIcon } from "lucide-react";
import { AlertCircle, RefreshCw, SearchX, ShieldOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ApiError, errorMessage } from "@/services/api-client";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondary,
  className,
  compact = false,
  tone = "default",
}: {
  icon?: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  secondary?: React.ReactNode;
  className?: string;
  compact?: boolean;
  tone?: "default" | "pi";
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "px-4 py-8" : "px-6 py-14",
        className,
      )}
    >
      {Icon && (
        <div
          className={cn(
            "flex items-center justify-center rounded-xl",
            compact ? "size-9" : "size-11",
            tone === "pi"
              ? "bg-pi-soft text-pi"
              : "bg-surface-muted text-muted-foreground",
          )}
        >
          <Icon
            className={compact ? "size-4.5" : "size-5"}
            aria-hidden="true"
          />
        </div>
      )}
      <h3
        className={cn(
          "font-semibold",
          compact ? "mt-3 text-sm" : "mt-4 text-[15px]",
        )}
      >
        {title}
      </h3>
      {description && (
        <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}
      {(action || secondary) && (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          {action}
          {secondary}
        </div>
      )}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title,
  className,
  compact = false,
}: {
  error?: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
  compact?: boolean;
}) {
  const denied = error instanceof ApiError && error.status === 403;
  const missing = error instanceof ApiError && error.status === 404;
  const Icon = denied ? ShieldOff : missing ? SearchX : AlertCircle;
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "px-4 py-8" : "px-6 py-14",
        className,
      )}
    >
      <div className="flex size-10 items-center justify-center rounded-xl bg-danger-soft text-danger">
        <Icon className="size-5" aria-hidden="true" />
      </div>
      <h3 className="mt-3.5 text-[15px] font-semibold">
        {title ??
          (denied
            ? "Access restricted"
            : missing
              ? "Not found"
              : "Couldn't load this")}
      </h3>
      <p className="mt-1 max-w-sm text-[13px] text-muted-foreground">
        {denied
          ? "Your role doesn't allow viewing this. Ask an administrator if you need access."
          : missing
            ? "It may have been removed, or it belongs to another workspace."
            : errorMessage(
                error,
                "Something went wrong while loading. Please try again.",
              )}
      </p>
      {onRetry && !denied && !missing && (
        <Button
          variant="secondary"
          size="sm"
          className="mt-4"
          onClick={onRetry}
        >
          <RefreshCw /> Try again
        </Button>
      )}
    </div>
  );
}

export function InlineError({ message }: { message: string }) {
  return (
    <p
      role="alert"
      className="flex items-center gap-1.5 rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger"
    >
      <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}

export function Notice({
  tone = "info",
  icon: Icon,
  title,
  children,
  action,
  className,
}: {
  tone?: "info" | "warning" | "danger" | "success" | "pi" | "neutral";
  icon?: LucideIcon;
  title?: React.ReactNode;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  const tones = {
    info: "border-info/20 bg-info-soft text-info",
    warning: "border-warning/25 bg-warning-soft text-warning",
    danger: "border-danger/25 bg-danger-soft text-danger",
    success: "border-success/25 bg-success-soft text-success",
    pi: "border-pi/25 bg-pi-soft text-pi-soft-foreground",
    neutral: "border-border bg-surface-muted text-foreground-secondary",
  };
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-lg border px-3.5 py-3",
        tones[tone],
        className,
      )}
    >
      {Icon && <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
      <div className="min-w-0 flex-1 text-[13px]">
        {title && <p className="font-semibold">{title}</p>}
        {children && (
          <div className={cn("text-foreground-secondary", title && "mt-0.5")}>
            {children}
          </div>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
