"use client";

import Link from "next/link";
import {
  ArrowRight,
  Clock,
  PackageCheck,
  PackageOpen,
  Truck,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatMoney, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import type { Order } from "@/features/business/types";
import { documentsService, type OrderAction } from "./service";
import { SourceBadge } from "./badges";

type Lane = {
  status: Order["status"];
  title: string;
  description: string;
  next?: { action: OrderAction; label: string; icon: LucideIcon; done: string };
};

const LANES: Lane[] = [
  {
    status: "confirmed",
    title: "Confirmed",
    description: "Stock reserved, ready to pick",
    next: {
      action: "start_processing",
      label: "Start processing",
      icon: PackageOpen,
      done: "moved to processing",
    },
  },
  {
    status: "processing",
    title: "Processing",
    description: "Being picked and packed",
    next: {
      action: "ship",
      label: "Mark shipped",
      icon: Truck,
      done: "marked as shipped",
    },
  },
  {
    status: "shipped",
    title: "Shipped",
    description: "On the way to the customer",
    next: {
      action: "deliver",
      label: "Mark delivered",
      icon: PackageCheck,
      done: "marked as delivered",
    },
  },
  {
    status: "delivered",
    title: "Delivered",
    description: "Most recent deliveries",
  },
];

export function FulfillmentPage() {
  return (
    <RequirePermission permission="orders.read" area="fulfillment">
      <PageShell width="full">
        <div className="mx-auto max-w-[1400px]">
          <PageHeader
            title="Fulfillment"
            description="Move confirmed orders through processing, shipping and delivery."
          />
          <ModuleNav moduleKey="orders" />
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {LANES.map((lane) => (
              <LaneColumn key={lane.status} lane={lane} />
            ))}
          </div>
        </div>
      </PageShell>
    </RequirePermission>
  );
}

function LaneColumn({ lane }: { lane: Lane }) {
  const query = useScopedQuery(["orders", "list", "board", lane.status], () =>
    documentsService.orders({ status: lane.status, pageSize: 50 }),
  );
  const total = query.data?.total;
  const shown = query.data?.items.length ?? 0;
  return (
    <section
      aria-labelledby={`lane-${lane.status}`}
      className="flex min-w-0 flex-col rounded-xl border border-border bg-surface-muted/50"
    >
      <header className="flex items-start justify-between gap-2 px-3.5 pt-3 pb-2">
        <div className="min-w-0">
          <h2
            id={`lane-${lane.status}`}
            className="flex items-center gap-2 text-[13.5px] font-semibold"
          >
            <StatusBadge status={lane.status} label={lane.title} />
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {lane.description}
          </p>
        </div>
        <span className="tabular rounded-full bg-surface px-2 py-0.5 text-xs font-semibold text-foreground-secondary">
          {total ?? "–"}
        </span>
      </header>
      <div className="flex-1 space-y-2 px-2.5 pb-2.5">
        {query.isError ? (
          <div className="rounded-lg bg-surface">
            <ErrorState
              error={query.error}
              onRetry={() => void query.refetch()}
              compact
            />
          </div>
        ) : query.isPending ? (
          Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))
        ) : shown === 0 ? (
          <p className="rounded-lg border border-dashed border-border-strong px-3 py-8 text-center text-[13px] text-muted-foreground">
            No {lane.title.toLowerCase()} orders
          </p>
        ) : (
          <>
            <ul className="space-y-2">
              {query.data.items.map((order) => (
                <li key={order.id}>
                  <OrderCard order={order} lane={lane} />
                </li>
              ))}
            </ul>
            {total !== undefined && total > shown && (
              <Link
                href={`/orders?status=${lane.status}`}
                className="block rounded-md px-2 py-1.5 text-center text-xs font-medium text-primary hover:underline"
              >
                View all {total} in the list
              </Link>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function OrderCard({ order, lane }: { order: Order; lane: Lane }) {
  const { can } = useSession();
  const next = lane.next;
  const advance = useScopedMutation(
    (action: OrderAction) => documentsService.orderAction(order.id, action),
    {
      invalidate: [["orders"]],
      success: (o) => `${o.number} ${next?.done ?? "updated"}`,
    },
  );
  const since = order.confirmed_at ?? order.created_at;
  return (
    <article className="rounded-lg border border-border bg-surface p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <Link
          href={`/orders/${order.id}`}
          className="font-mono text-[13px] font-semibold hover:underline"
        >
          {order.number}
        </Link>
        <span className="tabular text-[13px] font-semibold">
          {formatMoney(order.total, order.currency)}
        </span>
      </div>
      <p className="mt-0.5 truncate text-[13px] text-foreground-secondary">
        {order.customer_name ?? "Unknown customer"}
      </p>
      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1" title={`Since ${since}`}>
          <Clock className="size-3" aria-hidden="true" /> {relativeTime(since)}
        </span>
        {order.source !== "manual" && <SourceBadge source={order.source} />}
      </div>
      <div
        className={cn("mt-3 flex items-center gap-2", !next && "justify-end")}
      >
        {next && can("orders.write") && (
          <Button
            size="xs"
            variant="secondary"
            className="flex-1"
            onClick={() => advance.mutate(next.action)}
            loading={advance.isPending}
            aria-label={`${next.label}: ${order.number}`}
          >
            <next.icon /> {next.label}
          </Button>
        )}
        <Button size="icon-xs" variant="ghost" asChild>
          <Link
            href={`/orders/${order.id}`}
            aria-label={`Open ${order.number}`}
          >
            <ArrowRight />
          </Link>
        </Button>
      </div>
    </article>
  );
}
