"use client";

import { useEffect, useId, useState } from "react";
import type { FieldError } from "react-hook-form";
import { AlertTriangle, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";

/** Label + control + help + error, wired for accessibility. */
export function FormField({
  label,
  htmlFor,
  required = false,
  help,
  error,
  children,
  className,
  optional = false,
}: {
  label: string;
  htmlFor?: string;
  required?: boolean;
  optional?: boolean;
  help?: React.ReactNode;
  error?: FieldError | string;
  children: React.ReactNode;
  className?: string;
}) {
  const message = typeof error === "string" ? error : error?.message;
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={htmlFor} className="flex items-center gap-1">
        {label}
        {required && <span className="text-danger" aria-hidden="true">*</span>}
        {optional && <span className="font-normal text-muted-foreground">(optional)</span>}
      </Label>
      {children}
      {message ? (
        <p id={htmlFor ? `${htmlFor}-error` : undefined} role="alert" className="text-xs font-medium text-danger">
          {message}
        </p>
      ) : help ? (
        <p id={htmlFor ? `${htmlFor}-help` : undefined} className="text-xs text-muted-foreground">
          {help}
        </p>
      ) : null}
    </div>
  );
}

export function FormSection({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("grid gap-x-8 gap-y-4 border-b border-border py-6 first:pt-0 last:border-0 lg:grid-cols-[240px_1fr]", className)}>
      <div>
        <h2 className="text-[14px] font-semibold">{title}</h2>
        {description && <p className="mt-1 text-[13px] text-muted-foreground">{description}</p>}
      </div>
      <div className="min-w-0 space-y-4">{children}</div>
    </section>
  );
}

export function FormActions({
  dirty,
  saving,
  onCancel,
  submitLabel = "Save",
  className,
  savedAt,
  extra,
}: {
  dirty?: boolean;
  saving?: boolean;
  onCancel?: () => void;
  submitLabel?: string;
  className?: string;
  savedAt?: number | null;
  extra?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "sticky bottom-0 z-10 -mx-4 mt-6 flex flex-wrap items-center justify-end gap-2 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8",
        className,
      )}
    >
      <span className="mr-auto flex items-center gap-1.5 text-[13px]" aria-live="polite">
        {dirty ? (
          <>
            <span className="size-2 rounded-full bg-warning" aria-hidden="true" />
            <span className="text-muted-foreground">Unsaved changes</span>
          </>
        ) : savedAt ? (
          <>
            <Check className="size-4 text-success" aria-hidden="true" />
            <span className="text-muted-foreground">Saved</span>
          </>
        ) : null}
      </span>
      {extra}
      {onCancel && (
        <Button type="button" variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      )}
      <Button type="submit" loading={saving} disabled={saving || dirty === false}>
        {submitLabel}
      </Button>
    </div>
  );
}

/** Warn before leaving a page with unsaved changes (browser navigation). */
export function useUnsavedChangesWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  consequences,
  confirmLabel = "Confirm",
  destructive = false,
  loading = false,
  onConfirm,
  requireText,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  consequences?: string[];
  confirmLabel?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  /** Type-to-confirm for irreversible actions. */
  requireText?: string;
}) {
  const [typed, setTyped] = useState("");
  const id = useId();
  useEffect(() => {
    if (!open) setTyped("");
  }, [open]);
  const blocked = requireText ? typed.trim() !== requireText : false;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader title={title} description={description} />
        {(consequences?.length || requireText) && (
          <DialogBody className="space-y-3">
            {consequences && consequences.length > 0 && (
              <ul className={cn("space-y-1.5 rounded-lg p-3 text-[13px]", destructive ? "bg-danger-soft" : "bg-surface-muted")}>
                {consequences.map((c) => (
                  <li key={c} className="flex gap-2">
                    <AlertTriangle className={cn("mt-0.5 size-3.5 shrink-0", destructive ? "text-danger" : "text-warning")} aria-hidden="true" />
                    <span className="text-foreground-secondary">{c}</span>
                  </li>
                ))}
              </ul>
            )}
            {requireText && (
              <div className="space-y-1.5">
                <label htmlFor={id} className="text-[13px]">
                  Type <span className="font-mono font-semibold">{requireText}</span> to confirm
                </label>
                <input
                  id={id}
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm focus-visible:border-ring focus-visible:outline-none"
                  autoComplete="off"
                />
              </div>
            )}
          </DialogBody>
        )}
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>
            Cancel
          </Button>
          <Button variant={destructive ? "danger" : "default"} onClick={onConfirm} loading={loading} disabled={blocked}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function Stepper({
  steps,
  current,
  onStep,
}: {
  steps: { key: string; label: string; description?: string }[];
  current: number;
  onStep?: (index: number) => void;
}) {
  return (
    <ol className="scrollbar-thin mb-6 flex items-center gap-2 overflow-x-auto" aria-label="Progress">
      {steps.map((step, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li key={step.key} className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              disabled={!onStep || index > current}
              onClick={() => onStep?.(index)}
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-full py-1 pr-3 pl-1 text-[13px] font-medium transition-colors",
                active ? "bg-primary-soft text-primary-soft-foreground" : done ? "text-foreground hover:bg-surface-muted" : "text-muted-foreground",
              )}
            >
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-full text-xs font-semibold",
                  active ? "bg-primary text-primary-foreground" : done ? "bg-success-soft text-success" : "bg-surface-muted text-muted-foreground",
                )}
              >
                {done ? <Check className="size-3.5" /> : index + 1}
              </span>
              {step.label}
            </button>
            {index < steps.length - 1 && <span className="h-px w-6 bg-border" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}
