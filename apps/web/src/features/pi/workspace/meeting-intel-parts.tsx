"use client";

import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Small presentational pieces for the meeting screens. No data, no fetching. */

type Tone = "neutral" | "success" | "warning" | "danger" | "pi";

const TILE: Record<Tone, string> = {
  neutral: "bg-surface-muted text-foreground-secondary",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  pi: "bg-pi-soft text-pi-soft-foreground",
};

export function StatTile({
  icon: Icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  tone?: Tone;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3">
      <span
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-lg",
          TILE[tone],
        )}
        aria-hidden="true"
      >
        <Icon className="size-4.5" />
      </span>
      <div className="min-w-0">
        <p className="text-[22px] leading-6 font-semibold tabular-nums">
          {value}
        </p>
        <p className="truncate text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

/** The tone a meeting's status badge takes: what needs a person is amber, trouble is red. */
export function statusTone(
  status: string,
): "pi" | "warning" | "danger" | "success" {
  if (status === "failed") return "danger";
  if (status === "review") return "warning";
  if (status === "approved") return "success";
  return "pi";
}

export function IconTile({
  icon: Icon,
  tone = "pi",
}: {
  icon: ComponentType<{ className?: string }>;
  tone?: Tone;
}) {
  return (
    <span
      className={cn(
        "grid size-10 shrink-0 place-items-center rounded-xl",
        TILE[tone],
      )}
      aria-hidden="true"
    >
      <Icon className="size-5" />
    </span>
  );
}

export function SkeletonRows({ count = 3 }: { count?: number }) {
  return (
    <ul className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }, (_, n) => (
        <li
          key={n}
          className="h-[68px] animate-pulse rounded-xl border border-border bg-surface-sunken motion-reduce:animate-none"
        />
      ))}
    </ul>
  );
}

export function ReviewProgress({
  done,
  total,
}: {
  done: number;
  total: number;
}) {
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3">
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-medium">
          {done} of {total} reviewed
        </span>
        <span className="text-muted-foreground tabular-nums">{percent}%</span>
      </div>
      <div
        role="progressbar"
        aria-label="Insights reviewed"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        className="h-1.5 overflow-hidden rounded-full bg-surface-sunken"
      >
        <div
          className="h-full rounded-full bg-success transition-[width] duration-300 motion-reduce:transition-none"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

export function GroupHeading({
  title,
  hint,
  count,
}: {
  title: string;
  hint: string;
  count: number;
}) {
  return (
    <div className="mb-2 flex flex-wrap items-baseline gap-x-2">
      <h3 className="text-[13px] font-semibold">{title}</h3>
      <span className="rounded-full bg-surface-muted px-1.5 text-[11px] text-muted-foreground tabular-nums">
        {count}
      </span>
      <span className="text-xs text-muted-foreground">{hint}</span>
    </div>
  );
}

const AVATAR = [
  "bg-pi-soft text-pi-soft-foreground",
  "bg-info-soft text-info",
  "bg-warning-soft text-warning",
  "bg-success-soft text-success",
];

/** A speaker's initial in a coloured disc; the same speaker always gets the same colour. */
export function SpeakerAvatar({
  name,
  index,
}: {
  name: string;
  index: number;
}) {
  return (
    <span
      className={cn(
        "grid size-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold",
        AVATAR[index % AVATAR.length],
      )}
      aria-hidden="true"
    >
      {(name.trim()[0] ?? "?").toUpperCase()}
    </span>
  );
}

export function Accent({
  tone,
  children,
}: {
  tone: "success" | "pi";
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "border-l-[3px] pl-3",
        tone === "success" ? "border-success" : "border-pi",
      )}
    >
      {children}
    </div>
  );
}
