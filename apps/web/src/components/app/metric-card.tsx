import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/display";

export function MetricCard({
  label,
  value,
  icon: Icon,
  change,
  detail,
  href,
  tone = "default",
  loading = false,
  className,
  children,
}: {
  label: string;
  value: React.ReactNode;
  icon?: LucideIcon;
  /** Relative change vs a comparison period, e.g. 0.12 for +12%. */
  change?: { value: number | null; label?: string; goodWhen?: "up" | "down" };
  detail?: React.ReactNode;
  href?: string;
  tone?: "default" | "warning" | "danger" | "pi" | "success";
  loading?: boolean;
  className?: string;
  children?: React.ReactNode;
}) {
  const accent = {
    default: "text-muted-foreground",
    warning: "text-warning",
    danger: "text-danger",
    pi: "text-pi",
    success: "text-success",
  }[tone];
  const body = (
    <div
      className={cn(
        "group relative flex h-full flex-col rounded-xl border border-border bg-surface p-3.5 shadow-sm transition-colors",
        href && "hover:border-border-strong",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-[12.5px] font-medium text-muted-foreground">{label}</p>
        {Icon && <Icon className={cn("size-4 shrink-0", accent)} aria-hidden="true" />}
      </div>
      {loading ? (
        <Skeleton className="mt-2.5 h-7 w-24" />
      ) : (
        <p className="tabular mt-1.5 truncate text-[22px] leading-tight font-semibold tracking-tight">
          {value}
        </p>
      )}
      <div className="mt-auto flex min-h-5 items-center gap-2 pt-1.5 text-xs text-muted-foreground">
        {change && change.value !== null && !loading && <Change {...change} value={change.value} />}
        {detail && !loading && <span className="truncate">{detail}</span>}
      </div>
      {children}
    </div>
  );
  return href ? (
    <Link href={href} className="block h-full rounded-xl focus-visible:outline-2 focus-visible:outline-ring">
      {body}
    </Link>
  ) : (
    body
  );
}

function Change({
  value,
  label,
  goodWhen = "up",
}: {
  value: number;
  label?: string;
  goodWhen?: "up" | "down";
}) {
  const flat = Math.abs(value) < 0.005;
  const up = value > 0;
  const good = flat ? null : up === (goodWhen === "up");
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-0.5 font-semibold",
        good === null ? "text-muted-foreground" : good ? "text-success" : "text-danger",
      )}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {flat ? "0%" : `${Math.abs(value * 100).toFixed(value > 9.99 ? 0 : 1)}%`}
      {label && <span className="font-normal text-muted-foreground">{label}</span>}
    </span>
  );
}

export function MetricGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4", className)}>
      {children}
    </div>
  );
}
