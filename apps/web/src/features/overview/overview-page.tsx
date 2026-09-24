"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Blocks,
  Bot,
  ChevronRight,
  FileText,
  IdCard,
  Receipt,
  ShoppingCart,
  Stamp,
  UserPlus,
  Users,
  Wallet,
  Warehouse,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  formatMoney,
  formatNumber,
  humanize,
  relativeTime,
} from "@/lib/format";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui/display";
import { Button } from "@/components/ui/button";
import { PageShell } from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ChartCard } from "@/components/app/charts";
import { ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { reportsService } from "@/features/reports/service";
import { documentsService } from "@/features/documents/service";
import { billingService } from "@/features/billing/service";
import { piService } from "@/features/pi/service";
import { productsService } from "@/features/products/service";
import type { Metric } from "@/features/business/types";

function greeting() {
  const hour = new Date().getHours();
  return hour < 12
    ? "Good morning"
    : hour < 17
      ? "Good afternoon"
      : "Good evening";
}

function change(metric: Metric | null) {
  if (!metric || metric.previous === undefined || metric.previous === null)
    return undefined;
  const prev = Number(metric.previous);
  if (!prev) return undefined;
  return {
    value: (Number(metric.value) - prev) / prev,
    label: "vs last month",
  };
}

const ACTIVITY_LABELS: Record<string, string> = {
  "order.confirm": "confirmed an order",
  "order.draft_created": "drafted an order",
  "payment.recorded": "recorded a payment",
  "customer.created": "added a customer",
  "quote.created": "created a quote",
  "inventory.adjusted": "adjusted stock",
};

export function OverviewPage() {
  const { session, can } = useSession();
  const overview = useScopedQuery(["overview"], () =>
    reportsService.overview(),
  );
  const revenue = useScopedQuery(
    ["reports", "revenue", 12],
    () => reportsService.revenue(12),
    { enabled: can("reports.read") && can("billing.read") },
  );
  const orders = useScopedQuery(
    ["reports", "orders", 30],
    () => reportsService.orders(30),
    { enabled: can("reports.read") && can("orders.read") },
  );
  const products = useScopedQuery(["products"], () => productsService.list());
  const piEnabled =
    Boolean(
      products.data?.find((p) => p.key === "pi" && p.environment_enabled),
    ) && can("pi.read");
  const pi = useScopedQuery(["pi", "overview"], () => piService.overview(), {
    enabled: piEnabled,
  });
  const approvals = useScopedQuery(
    ["quotes", "count", "pending_approval"],
    () => documentsService.quotes({ status: "pending_approval", pageSize: 1 }),
    { enabled: can("quotes.read") },
  );
  const drafts = useScopedQuery(
    ["orders", "count", "draft"],
    () => documentsService.orders({ status: "draft", pageSize: 1 }),
    { enabled: can("orders.read") },
  );
  const overdue = useScopedQuery(
    ["invoices", "count", "overdue"],
    () => billingService.invoices({ overdue: true, pageSize: 1 }),
    { enabled: can("billing.read") },
  );

  const data = overview.data;
  const currency = data?.currency ?? "USD";
  const loading = overview.isPending;
  const firstName = session?.user.display_name.split(" ")[0] ?? "there";
  const empty =
    data &&
    !loading &&
    Number(data.customers?.value ?? 0) === 0 &&
    Number(data.orders?.value ?? 0) === 0;

  const attention: {
    label: string;
    count: number | undefined;
    href: string;
    icon: LucideIcon;
    tone: string;
    show: boolean;
  }[] = [
    {
      label: "Quotes awaiting approval",
      count: approvals.data?.total,
      href: "/quotes/approvals",
      icon: Stamp,
      tone: "text-warning bg-warning-soft",
      show: can("quotes.read"),
    },
    {
      label: "Overdue invoices",
      count: overdue.data?.total,
      href: "/billing/invoices?overdue=true",
      icon: Receipt,
      tone: "text-danger bg-danger-soft",
      show: can("billing.read"),
    },
    {
      label: "Items low on stock",
      count: data?.inventory_alerts
        ? Number(data.inventory_alerts.value)
        : undefined,
      href: "/inventory/stock?low_only=true",
      icon: Warehouse,
      tone: "text-warning bg-warning-soft",
      show: can("inventory.read"),
    },
    {
      label: "Open PI handoffs",
      count: pi.data?.open_handoffs,
      href: "/pi/handoffs/open",
      icon: Bot,
      tone: "text-pi bg-pi-soft",
      show: piEnabled,
    },
    {
      label: "Draft orders to confirm",
      count: drafts.data?.total,
      href: "/orders?status=draft",
      icon: ShoppingCart,
      tone: "text-info bg-info-soft",
      show: can("orders.read"),
    },
  ];

  const quickActions: {
    label: string;
    href: string;
    icon: LucideIcon;
    permission: string;
  }[] = [
    {
      label: "Add customer",
      href: "/customers/new",
      icon: UserPlus,
      permission: "customers.write",
    },
    {
      label: "Create quote",
      href: "/quotes/new",
      icon: FileText,
      permission: "quotes.write",
    },
    {
      label: "Create order",
      href: "/orders/new",
      icon: ShoppingCart,
      permission: "orders.write",
    },
    {
      label: "Record payment",
      href: "/billing/invoices?status=issued",
      icon: Wallet,
      permission: "billing.write",
    },
    {
      label: "Adjust stock",
      href: "/inventory/stock",
      icon: Warehouse,
      permission: "inventory.adjust",
    },
    {
      label: "Open PI inbox",
      href: "/pi/inbox",
      icon: Bot,
      permission: "pi.read",
    },
  ];

  if (overview.isError) {
    return (
      <PageShell>
        <ErrorState
          error={overview.error}
          onRetry={() => void overview.refetch()}
        />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[13px] text-muted-foreground">
            {new Date().toLocaleDateString("en-US", {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </p>
          <h1 className="mt-0.5 text-xl font-semibold tracking-tight sm:text-[22px]">
            {greeting()}, {firstName}
          </h1>
          <p className="mt-1 text-[13.5px] text-muted-foreground">
            Here’s what’s happening across{" "}
            {session?.tenant?.name ?? "your workspace"} today.
          </p>
        </div>
      </header>

      {empty && (
        <Card className="mb-5 overflow-hidden">
          <div className="grid gap-6 p-5 md:grid-cols-[1.3fr_1fr] md:p-6">
            <div>
              <Badge tone="primary">Getting started</Badge>
              <h2 className="mt-3 text-lg font-semibold tracking-tight">
                Set up your workspace
              </h2>
              <p className="mt-1.5 max-w-lg text-[13.5px] text-muted-foreground">
                This environment has no business data yet. Add customers and
                products, then connect WhatsApp so PI can start answering with
                your real catalog and stock.
              </p>
            </div>
            <ol className="space-y-2 text-[13px]">
              {[
                ["Add your products and prices", "/catalog/products/new"],
                ["Create a stock location", "/inventory/locations"],
                ["Add your first customer", "/customers/new"],
                ["Install and connect PI", "/settings/products"],
              ].map(([label, href], i) => (
                <li key={href}>
                  <Link
                    href={href!}
                    className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5 hover:bg-surface-muted"
                  >
                    <span className="flex size-6 items-center justify-center rounded-full bg-surface-muted text-xs font-semibold">
                      {i + 1}
                    </span>
                    <span className="flex-1 font-medium">{label}</span>
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </Link>
                </li>
              ))}
            </ol>
          </div>
        </Card>
      )}

      <MetricGrid className="xl:grid-cols-4">
        {(can("billing.read") || loading) && (
          <MetricCard
            label="Revenue (collected)"
            icon={Wallet}
            loading={loading}
            href="/reports/revenue"
            value={
              data?.revenue
                ? formatMoney(String(data.revenue.value), currency, {
                    compact: true,
                  })
                : "—"
            }
            change={change(data?.revenue ?? null)}
            detail={
              data?.revenue && !change(data.revenue) ? "This month" : undefined
            }
          />
        )}
        {(can("orders.read") || loading) && (
          <MetricCard
            label="Orders this month"
            icon={ShoppingCart}
            loading={loading}
            href="/orders"
            value={formatNumber(data?.orders?.value ?? 0)}
            detail={data?.orders?.detail}
          />
        )}
        {(can("customers.read") || loading) && (
          <MetricCard
            label="Active customers"
            icon={Users}
            loading={loading}
            href="/customers"
            value={formatNumber(data?.customers?.value ?? 0)}
            detail={data?.customers?.detail}
          />
        )}
        {(can("billing.read") || loading) && (
          <MetricCard
            label="Pending payments"
            icon={Receipt}
            loading={loading}
            href="/billing/invoices?status=issued"
            tone={
              data?.pending_payments?.detail?.startsWith("0 ")
                ? "default"
                : "warning"
            }
            value={
              data?.pending_payments
                ? formatMoney(String(data.pending_payments.value), currency, {
                    compact: true,
                  })
                : "—"
            }
            detail={data?.pending_payments?.detail}
          />
        )}
        {(can("billing.read") || loading) && (
          <MetricCard
            label="Outstanding invoices"
            icon={FileText}
            loading={loading}
            href="/billing/invoices"
            value={formatNumber(data?.outstanding_invoices?.value ?? 0)}
            detail={data?.outstanding_invoices?.detail}
          />
        )}
        {(can("inventory.read") || loading) && (
          <MetricCard
            label="Inventory alerts"
            icon={AlertTriangle}
            loading={loading}
            href="/inventory/stock?low_only=true"
            tone={
              Number(data?.inventory_alerts?.value ?? 0) > 0
                ? "warning"
                : "default"
            }
            value={formatNumber(data?.inventory_alerts?.value ?? 0)}
            detail={data?.inventory_alerts?.detail}
          />
        )}
        {(can("quotes.read") || loading) && (
          <MetricCard
            label="Open quotes"
            icon={FileText}
            loading={loading}
            href="/quotes"
            value={formatNumber(data?.quotes?.value ?? 0)}
            detail={data?.quotes?.detail}
          />
        )}
        {(can("hr.read") || loading) && (
          <MetricCard
            label="Employees"
            icon={IdCard}
            loading={loading}
            href="/hr/employees"
            value={formatNumber(data?.employees?.value ?? 0)}
            detail={data?.employees?.detail}
          />
        )}
      </MetricGrid>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {can("reports.read") && can("billing.read") ? (
          <ChartCard
            title="Revenue trend"
            description="Invoiced vs collected, last 12 months"
            data={revenue.data?.months.map((m) => ({
              month: new Date(`${m.month}-01`).toLocaleDateString("en-US", {
                month: "short",
              }),
              invoiced: Number(m.invoiced),
              collected: Number(m.collected),
            }))}
            loading={revenue.isPending}
            xKey="month"
            xLabel="Month"
            series={[
              { key: "invoiced", label: "Invoiced" },
              { key: "collected", label: "Collected" },
            ]}
            format={(v) => formatMoney(v, currency, { compact: true })}
            kind="area"
            height={250}
            actions={
              <Link
                href="/reports/revenue"
                className="text-xs font-medium text-primary hover:underline"
              >
                Details
              </Link>
            }
          />
        ) : (
          <Card className="flex items-center justify-center p-8 text-center text-[13px] text-muted-foreground">
            Revenue trends are visible to members with report and billing
            access.
          </Card>
        )}

        <Card>
          <CardHeader
            title="Needs attention"
            description="Items waiting on your team"
          />
          <ul className="px-2 pb-2">
            {attention
              .filter((a) => a.show)
              .map((item) => (
                <li key={item.label}>
                  <Link
                    href={item.href}
                    className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-surface-muted"
                  >
                    <span
                      className={cn(
                        "flex size-8 items-center justify-center rounded-lg",
                        item.tone,
                      )}
                    >
                      <item.icon className="size-4" aria-hidden="true" />
                    </span>
                    <span className="flex-1 text-[13px] font-medium">
                      {item.label}
                    </span>
                    {item.count === undefined ? (
                      <Skeleton className="h-5 w-7" />
                    ) : (
                      <span
                        className={cn(
                          "tabular rounded-full px-2 py-0.5 text-xs font-semibold",
                          item.count > 0
                            ? "bg-foreground text-background"
                            : "bg-surface-muted text-muted-foreground",
                        )}
                      >
                        {item.count}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
          </ul>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {can("reports.read") && can("orders.read") && (
          <ChartCard
            title="Order activity"
            description="Orders per day, last 30 days"
            data={orders.data?.by_day.map((d) => ({
              day: new Date(d.day).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              }),
              orders: d.count,
            }))}
            loading={orders.isPending}
            xKey="day"
            xLabel="Day"
            series={[{ key: "orders", label: "Orders" }]}
            kind="bar"
            height={200}
            headline={
              orders.data && (
                <p className="text-[13px] text-muted-foreground">
                  Average order value{" "}
                  <span className="tabular font-semibold text-foreground">
                    {formatMoney(orders.data.average_order_value, currency)}
                  </span>
                </p>
              )
            }
          />
        )}

        {piEnabled && (
          <Card>
            <CardHeader
              title={
                <span className="flex items-center gap-1.5">
                  <Bot className="size-4 text-pi" /> PI today
                </span>
              }
              description="AI WhatsApp assistant"
              actions={
                <Link
                  href="/pi"
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Open PI
                </Link>
              }
            />
            <div className="grid grid-cols-2 gap-3 px-4 pb-4">
              {pi.isPending ? (
                Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className="h-16" />
                ))
              ) : pi.data ? (
                <>
                  <MiniStat
                    label="Active conversations"
                    value={formatNumber(pi.data.conversations_active)}
                  />
                  <MiniStat
                    label="Open handoffs"
                    value={formatNumber(pi.data.open_handoffs)}
                    tone={pi.data.open_handoffs ? "pi" : undefined}
                  />
                  <MiniStat
                    label="Handled by PI"
                    value={`${Math.round(pi.data.automation_rate * 100)}%`}
                  />
                  <MiniStat
                    label="Median reply"
                    value={`${(pi.data.avg_response_ms / 1000).toFixed(1)}s`}
                  />
                </>
              ) : (
                <p className="col-span-2 text-[13px] text-muted-foreground">
                  PI metrics are unavailable right now.
                </p>
              )}
            </div>
          </Card>
        )}

        <Card className={cn(!piEnabled && "lg:col-span-1")}>
          <CardHeader
            title="Recent activity"
            description="Latest changes in this environment"
          />
          <div className="px-4 pb-3">
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : !can("audit.read") ? (
              <p className="py-4 text-[13px] text-muted-foreground">
                Activity is visible to members with audit access.
              </p>
            ) : data?.recent_activity.length ? (
              <ul className="divide-y divide-border">
                {data.recent_activity.slice(0, 7).map((a) => (
                  <li
                    key={a.id}
                    className="flex items-center gap-3 py-2 text-[13px]"
                  >
                    <span
                      className={cn(
                        "size-1.5 shrink-0 rounded-full",
                        a.actor_label === "PI" ? "bg-pi" : "bg-primary",
                      )}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-medium">{a.actor_label}</span>{" "}
                      <span className="text-muted-foreground">
                        {ACTIVITY_LABELS[a.action] ??
                          humanize(a.action.replace(".", " "))}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {relativeTime(a.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-4 text-[13px] text-muted-foreground">
                No activity yet.
              </p>
            )}
            {can("audit.read") && (
              <Link
                href="/settings/audit"
                className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
              >
                Full audit log <ArrowRight className="size-3" />
              </Link>
            )}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Quick actions" />
          <div className="grid grid-cols-2 gap-2 px-4 pb-4 sm:grid-cols-3">
            {quickActions
              .filter((a) => can(a.permission))
              .map((a) => (
                <Button
                  key={a.href}
                  variant="secondary"
                  className="h-auto justify-start gap-2.5 px-3 py-2.5"
                  asChild
                >
                  <Link href={a.href}>
                    <a.icon className="text-primary" /> {a.label}
                  </Link>
                </Button>
              ))}
          </div>
        </Card>
        <Card>
          <CardHeader
            title="Installed products"
            icon={<Blocks />}
            actions={
              can("admin.products.manage") ? (
                <Link
                  href="/settings/products"
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Manage
                </Link>
              ) : undefined
            }
          />
          <ul className="px-4 pb-4">
            {loading ? (
              <Skeleton className="h-10" />
            ) : data?.installed_products.length ? (
              data.installed_products.map((p) => (
                <li
                  key={p.key}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5"
                >
                  <span className="flex items-center gap-2 text-[13px] font-semibold">
                    <Bot className="size-4 text-pi" /> {p.name}
                  </span>
                  <Badge tone={p.enabled ? "success" : "neutral"} dot>
                    {p.enabled ? "Enabled here" : "Disabled here"}
                  </Badge>
                </li>
              ))
            ) : (
              <li className="text-[13px] text-muted-foreground">
                No products installed yet.
              </li>
            )}
          </ul>
        </Card>
      </div>
    </PageShell>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "pi";
}) {
  return (
    <div className="rounded-lg bg-surface-muted/70 px-3 py-2.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          "tabular mt-0.5 text-lg font-semibold",
          tone === "pi" && "text-pi",
        )}
      >
        {value}
      </p>
    </div>
  );
}
