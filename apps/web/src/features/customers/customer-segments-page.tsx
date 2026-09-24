"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Archive, ArrowRight, Info, MessageCircle, Star, Tag, Users, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/format";
import { Skeleton } from "@/components/ui/display";
import { ModuleNav, PageHeader, PageShell, RequirePermission, SectionHeader } from "@/components/app/page";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { customersService } from "./service";

type Segment = {
  key: string;
  name: string;
  description: string;
  icon: LucideIcon;
  filter: { status?: string; tag?: string };
  tone?: string;
};

const BUILT_IN: Segment[] = [
  { key: "active", name: "All active", description: "Customers you can quote and sell to", icon: Users, filter: { status: "active" }, tone: "bg-success-soft text-success" },
  { key: "whatsapp", name: "WhatsApp", description: "Customers tagged whatsapp", icon: MessageCircle, filter: { tag: "whatsapp" }, tone: "bg-info-soft text-info" },
  { key: "vip", name: "VIP", description: "Customers tagged vip", icon: Star, filter: { tag: "vip" }, tone: "bg-warning-soft text-warning" },
  { key: "archived", name: "Archived", description: "Kept on record, hidden from pickers", icon: Archive, filter: { status: "archived" } },
];

function hrefFor(filter: Segment["filter"]) {
  const params = new URLSearchParams();
  if (filter.status) params.set("status", filter.status);
  if (filter.tag) params.set("tag", filter.tag);
  return `/customers?${params.toString()}`;
}

export function CustomerSegmentsPage() {
  return (
    <RequirePermission permission="customers.read" area="customers">
      <Segments />
    </RequirePermission>
  );
}

function Segments() {
  const sample = useScopedQuery(["customers", "list", { page: 1, pageSize: 100 }], () => customersService.list({ page: 1, pageSize: 100 }));

  const tagSegments: Segment[] = useMemo(() => {
    const counts = new Map<string, number>();
    sample.data?.items.forEach((c) => c.tags.forEach((t) => counts.set(t, (counts.get(t) ?? 0) + 1)));
    const builtInTags = new Set(BUILT_IN.map((s) => s.filter.tag).filter(Boolean));
    return [...counts.entries()]
      .filter(([tag]) => !builtInTags.has(tag))
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([tag]) => ({ key: `tag-${tag}`, name: tag, description: `Customers tagged ${tag}`, icon: Tag, filter: { tag } }));
  }, [sample.data]);

  return (
    <PageShell>
      <PageHeader title="Segments" description="Groups of customers you can open as a filtered list, based on status and tags." />
      <ModuleNav moduleKey="customers" />

      <Notice tone="neutral" icon={Info} className="mb-5">
        Segments are saved filters over customer tags and status. Add a tag to a customer (for example <span className="font-medium">vip</span>) and they
        join that segment automatically; remove it and they leave.
      </Notice>

      <SectionHeader title="Built-in segments" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {BUILT_IN.map((segment) => (
          <SegmentCard key={segment.key} segment={segment} />
        ))}
      </div>

      <SectionHeader
        className="mt-8"
        title="Tag segments"
        description={
          sample.data && sample.data.total > sample.data.items.length
            ? `Tags found on your ${sample.data.items.length} most recent customers.`
            : "One segment per tag used on your customers."
        }
      />
      {sample.isError ? (
        <div className="rounded-xl border border-border bg-surface">
          <ErrorState error={sample.error} onRetry={() => void sample.refetch()} compact />
        </div>
      ) : sample.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-[108px] rounded-xl" />
          ))}
        </div>
      ) : tagSegments.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-surface">
          <EmptyState
            compact
            icon={Tag}
            title="No tag segments yet"
            description="Tag customers from their record (Edit → Tags) to create segments such as wholesale, repeat or lahore."
          />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {tagSegments.map((segment) => (
            <SegmentCard key={segment.key} segment={segment} />
          ))}
        </div>
      )}
    </PageShell>
  );
}

function SegmentCard({ segment }: { segment: Segment }) {
  const count = useScopedQuery(["customers", "count", "segment", segment.filter], () => customersService.list({ ...segment.filter, pageSize: 1 }));
  const Icon = segment.icon;
  return (
    <Link
      href={hrefFor(segment.filter)}
      className="group flex h-full flex-col rounded-xl border border-border bg-surface p-4 shadow-sm transition-colors hover:border-border-strong focus-visible:outline-2 focus-visible:outline-ring"
    >
      <div className="flex items-start justify-between gap-3">
        <span className={cn("flex size-8 items-center justify-center rounded-lg", segment.tone ?? "bg-surface-muted text-muted-foreground")}>
          <Icon className="size-4" aria-hidden="true" />
        </span>
        {count.isPending ? (
          <Skeleton className="h-6 w-10" />
        ) : (
          <span className="tabular text-xl font-semibold tracking-tight" aria-label={count.data ? `${count.data.total} customers` : "Count unavailable"}>
            {count.data ? formatNumber(count.data.total) : "—"}
          </span>
        )}
      </div>
      <p className="mt-3 truncate text-[13.5px] font-semibold">{segment.name}</p>
      <p className="mt-0.5 flex-1 text-xs text-muted-foreground">{segment.description}</p>
      <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary">
        View customers <ArrowRight className="size-3 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
      </span>
    </Link>
  );
}
