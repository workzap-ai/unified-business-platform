"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Bot,
  FileText,
  IdCard,
  Receipt,
  ShoppingCart,
  Users,
  Wallet,
  Warehouse,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatMoney, formatNumber } from "@/lib/format";
import { Skeleton } from "@/components/ui/display";
import { EmptyState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { billingService } from "@/features/billing/service";
import { piService } from "@/features/pi/service";
import { reportsService } from "./service";
import { ReportShell } from "./components";

type Headline = {
  value: string | undefined;
  caption: string;
  loading: boolean;
  error: boolean;
};

function ReportCard({
  title,
  description,
  href,
  icon: Icon,
  headline,
  tone = "default",
}: {
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  headline: Headline;
  tone?: "default" | "pi";
}) {
  return (
    <Link
      href={href}
      className="group flex h-full flex-col rounded-xl border border-border bg-surface p-4 shadow-sm transition-colors hover:border-border-strong focus-visible:outline-2 focus-visible:outline-ring"
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-lg",
            tone === "pi"
              ? "bg-pi-soft text-pi"
              : "bg-primary-soft text-primary",
          )}
        >
          <Icon className="size-4.5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[14px] font-semibold tracking-tight">{title}</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            {description}
          </p>
        </div>
        <ArrowRight
          className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </div>
      <div className="mt-4 border-t border-border pt-3">
        {headline.loading ? (
          <Skeleton className="h-7 w-28" />
        ) : headline.error ? (
          <p className="text-[13px] text-muted-foreground">
            Figure unavailable right now
          </p>
        ) : (
          <p className="tabular text-[20px] leading-tight font-semibold tracking-tight">
            {headline.value ?? "—"}
          </p>
        )}
        <p className="mt-0.5 text-xs text-muted-foreground">
          {headline.caption}
        </p>
      </div>
    </Link>
  );
}

function head<T>(
  q: { data: T | undefined; isPending: boolean; isError: boolean },
  pick: (d: T) => string,
  caption: string,
): Headline {
  return {
    value: q.data === undefined ? undefined : pick(q.data),
    caption,
    loading: q.isPending && !q.isError,
    error: q.isError,
  };
}

export function ReportsCatalog() {
  return (
    <ReportShell
      title="Reports"
      description="Revenue, customer growth, proposals, delivery, billing, people and PI."
      area="reports"
    >
      <CatalogContent />
    </ReportShell>
  );
}

function CatalogContent() {
  const { can } = useSession();
  const allow = {
    revenue: can("billing.read"),
    customers: can("customers.read"),
    orders: can("orders.read"),
    inventory: can("inventory.read"),
    quotes: can("quotes.read"),
    billing: can("billing.read"),
    employees: can("hr.read"),
    pi: can("pi.analytics.read"),
  };
  const revenue = useScopedQuery(
    ["reports", "revenue", 12],
    () => reportsService.revenue(12),
    { enabled: allow.revenue },
  );
  const customers = useScopedQuery(
    ["reports", "customers"],
    () => reportsService.customers(),
    { enabled: allow.customers },
  );
  const orders = useScopedQuery(
    ["reports", "orders", 30],
    () => reportsService.orders(30),
    { enabled: allow.orders },
  );
  const inventory = useScopedQuery(
    ["reports", "inventory"],
    () => reportsService.inventory(),
    { enabled: allow.inventory },
  );
  const quotes = useScopedQuery(
    ["reports", "quotes"],
    () => reportsService.quotes(),
    { enabled: allow.quotes },
  );
  const billing = useScopedQuery(
    ["billing", "summary"],
    () => billingService.summary(),
    { enabled: allow.billing },
  );
  const employees = useScopedQuery(
    ["reports", "employees"],
    () => reportsService.employees(),
    { enabled: allow.employees },
  );
  const pi = useScopedQuery(
    ["pi", "analytics", 30],
    () => piService.analytics(30),
    { enabled: allow.pi, retry: false },
  );

  const cards = [
    allow.revenue && (
      <ReportCard
        key="revenue"
        title="Revenue"
        description="Invoiced vs collected by month"
        href="/reports/revenue"
        icon={Wallet}
        headline={head(
          revenue,
          (d) => formatMoney(d.total_collected, d.currency, { compact: true }),
          "Collected, last 12 months",
        )}
      />
    ),
    allow.customers && (
      <ReportCard
        key="customers"
        title="Customers"
        description="Growth and top customers"
        href="/reports/customers"
        icon={Users}
        headline={head(
          customers,
          (d) => formatNumber(d.total),
          "Customers in total",
        )}
      />
    ),
    allow.orders && (
      <ReportCard
        key="orders"
        title="Orders"
        description="Volume, value and status"
        href="/reports/orders"
        icon={ShoppingCart}
        headline={head(
          orders,
          (d) => formatNumber(d.by_status.reduce((s, r) => s + r.count, 0)),
          "Orders, last 30 days",
        )}
      />
    ),
    allow.inventory && (
      <ReportCard
        key="inventory"
        title="Inventory"
        description="Stock value and low stock"
        href="/reports/inventory"
        icon={Warehouse}
        headline={head(
          inventory,
          (d) => formatMoney(d.stock_value, d.currency, { compact: true }),
          "Stock value on hand",
        )}
      />
    ),
    allow.quotes && (
      <ReportCard
        key="quotes"
        title="Quotes"
        description="Pipeline and conversion"
        href="/reports/quotes"
        icon={FileText}
        headline={head(
          quotes,
          (d) => formatMoney(d.open_value, d.currency, { compact: true }),
          "Open quote value",
        )}
      />
    ),
    allow.billing && (
      <ReportCard
        key="billing"
        title="Billing"
        description="Receivables and collections"
        href="/reports/billing"
        icon={Receipt}
        headline={head(
          billing,
          (d) => formatMoney(d.outstanding, d.currency, { compact: true }),
          "Outstanding receivables",
        )}
      />
    ),
    allow.employees && (
      <ReportCard
        key="employees"
        title="Employees"
        description="Headcount by department"
        href="/reports/employees"
        icon={IdCard}
        headline={head(
          employees,
          (d) => formatNumber(d.active),
          "Active employees",
        )}
      />
    ),
    allow.pi && (
      <ReportCard
        key="pi"
        title="PI Analytics"
        description="AI assistant performance"
        href="/reports/pi"
        icon={Bot}
        tone="pi"
        headline={head(
          pi,
          (d) => formatNumber(d.totals.conversations),
          "Conversations, last 30 days",
        )}
      />
    ),
  ].filter(Boolean);

  if (cards.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No reports available for your role"
        description="Reports follow the data you can access. Ask a workspace administrator for access to billing, sales or inventory."
      />
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{cards}</div>
  );
}
