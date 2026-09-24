import { apiRequest } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness, mulMoney, sumMoney } from "@/demo/business";
import { dateOnly } from "@/demo/random";
import { demoSession } from "@/demo/workspace";
import { demoLevelRows } from "@/features/inventory/service";
import { productsService } from "@/features/products/service";
import { toCents, centsToString } from "@/lib/format";
import {
  customersReportSchema,
  headcountSchema,
  inventoryReportSchema,
  ordersReportSchema,
  overviewSchema,
  quotesReportSchema,
  revenueReportSchema,
  type CustomersReport,
  type Headcount,
  type InventoryReport,
  type OrdersReport,
  type Overview,
  type QuotesReport,
  type RevenueReport,
} from "@/features/business/types";
import { hrService } from "@/features/hr/service";

export interface ReportsService {
  overview(): Promise<Overview>;
  revenue(months?: number): Promise<RevenueReport>;
  orders(days?: number): Promise<OrdersReport>;
  customers(): Promise<CustomersReport>;
  quotes(): Promise<QuotesReport>;
  inventory(): Promise<InventoryReport>;
  employees(): Promise<Headcount>;
}

const live: ReportsService = {
  overview: () => apiRequest("GET", "/overview", overviewSchema),
  revenue: (months = 12) =>
    apiRequest("GET", "/reports/revenue", revenueReportSchema, {
      query: { months },
    }),
  orders: (days = 30) =>
    apiRequest("GET", "/reports/orders", ordersReportSchema, {
      query: { days },
    }),
  customers: () =>
    apiRequest("GET", "/reports/customers", customersReportSchema),
  quotes: () => apiRequest("GET", "/reports/quotes", quotesReportSchema),
  inventory: () =>
    apiRequest("GET", "/reports/inventory", inventoryReportSchema),
  employees: () => apiRequest("GET", "/reports/employees", headcountSchema),
};

function monthsBack(count: number): string[] {
  const now = new Date();
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - (count - 1 - i), 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
}

const can = (p: string) => demoSession()?.permissions.includes(p) ?? false;

const demo: ReportsService = {
  async overview() {
    await demoDelay(250);
    const b = demoBusiness();
    const currency = b.settings.default_currency;
    const monthStart = dateOnly(0).slice(0, 8) + "01";
    const prev = new Date(
      new Date().getFullYear(),
      new Date().getMonth() - 1,
      1,
    )
      .toISOString()
      .slice(0, 10);
    const payments = b.invoices.flatMap((i) => i.payments);
    const open = b.invoices.filter((i) =>
      ["issued", "partially_paid"].includes(i.status),
    );
    const overdue = open.filter((i) => i.due_date && i.due_date < dateOnly(0));
    const openQuotes = b.quotes.filter((q) =>
      ["draft", "pending_approval", "approved", "sent"].includes(q.status),
    );
    const products = (await productsService.list()).filter(
      (p) => p.tenant_status === "installed",
    );
    return {
      currency,
      revenue: can("billing.read")
        ? {
            value: sumMoney(
              payments
                .filter((p) => p.received_on >= monthStart)
                .map((p) => p.amount),
            ),
            previous: sumMoney(
              payments
                .filter(
                  (p) => p.received_on >= prev && p.received_on < monthStart,
                )
                .map((p) => p.amount),
            ),
            currency,
            detail: "Payments received this month",
          }
        : null,
      orders: can("orders.read")
        ? {
            value: b.orders.filter(
              (o) =>
                !["draft", "cancelled"].includes(o.status) &&
                o.created_at.slice(0, 10) >= monthStart,
            ).length,
            detail: `${b.orders.filter((o) => ["confirmed", "processing", "shipped"].includes(o.status)).length} open`,
          }
        : null,
      customers: can("customers.read")
        ? {
            value: b.customers.filter((c) => c.status === "active").length,
            detail: `${b.customers.filter((c) => c.created_at.slice(0, 10) >= monthStart).length} new this month`,
          }
        : null,
      pending_payments: can("billing.read")
        ? {
            value: sumMoney(
              open.map((i) => sumMoney([i.total, `-${i.amount_paid}`])),
            ),
            currency,
            detail: `${overdue.length} overdue`,
          }
        : null,
      outstanding_invoices: can("billing.read")
        ? { value: open.length, detail: "Issued and unpaid" }
        : null,
      inventory_alerts: can("inventory.read")
        ? {
            value: new Set(
              demoLevelRows()
                .filter((l) => l.is_low)
                .map((l) => l.variant_id),
            ).size,
            detail: "Items at or below threshold",
          }
        : null,
      quotes: can("quotes.read")
        ? {
            value: openQuotes.length,
            currency,
            detail: `${currency} ${Number(sumMoney(openQuotes.map((q) => q.total))).toLocaleString("en-US", { maximumFractionDigits: 0 })} open`,
          }
        : null,
      employees: can("hr.read")
        ? {
            value: b.employees.filter((e) => e.status === "active").length,
            detail: "Active employees",
          }
        : null,
      installed_products: products.map((p) => ({
        key: p.key,
        name: p.name,
        enabled: p.environment_enabled,
      })),
      recent_activity: can("audit.read")
        ? [
            ...b.orders.slice(0, 6).map((o) => ({
              id: `ra-${o.id}`,
              action:
                o.source === "pi" ? "order.confirm" : "order.draft_created",
              actor_label: o.created_by_label,
              entity_type: "order",
              entity_id: o.id,
              created_at: o.created_at,
            })),
            ...b.invoices
              .flatMap((i) => i.payments)
              .slice(0, 3)
              .map((p) => ({
                id: `ra-${p.id}`,
                action: "payment.recorded",
                actor_label: p.recorded_by_label,
                entity_type: "payment",
                entity_id: p.id,
                created_at: p.created_at,
              })),
            ...b.customers.slice(0, 3).map((c) => ({
              id: `ra-${c.id}`,
              action: "customer.created",
              actor_label: c.source === "whatsapp" ? "PI" : "Sana Malik",
              entity_type: "customer",
              entity_id: c.id,
              created_at: c.created_at,
            })),
          ]
            .sort((a, b2) => b2.created_at.localeCompare(a.created_at))
            .slice(0, 12)
        : [],
    };
  },
  async revenue(months = 12) {
    await demoDelay();
    const b = demoBusiness();
    const keys = monthsBack(months);
    const points = keys.map((month) => ({
      month,
      invoiced: sumMoney(
        b.invoices
          .filter(
            (i) =>
              i.issue_date?.startsWith(month) &&
              ["issued", "partially_paid", "paid"].includes(i.status),
          )
          .map((i) => i.total),
      ),
      collected: sumMoney(
        b.invoices
          .flatMap((i) => i.payments)
          .filter((p) => p.received_on.startsWith(month))
          .map((p) => p.amount),
      ),
    }));
    return {
      currency: b.settings.default_currency,
      months: points,
      total_invoiced: sumMoney(points.map((p) => p.invoiced)),
      total_collected: sumMoney(points.map((p) => p.collected)),
    };
  },
  async orders(days = 30) {
    await demoDelay();
    const b = demoBusiness();
    const since = new Date(Date.now() - days * 86400000).toISOString();
    const rows = b.orders.filter((o) => o.created_at >= since);
    const statuses = [...new Set(rows.map((o) => o.status))];
    const byDay = new Map<string, { count: number; values: string[] }>();
    for (const o of rows.filter((o) => o.status !== "cancelled")) {
      const day = o.created_at.slice(0, 10);
      const entry = byDay.get(day) ?? { count: 0, values: [] };
      entry.count += 1;
      entry.values.push(o.total);
      byDay.set(day, entry);
    }
    const counted = rows.filter(
      (o) => !["draft", "cancelled"].includes(o.status),
    );
    const total = counted.reduce((s, o) => s + toCents(o.total), BigInt(0));
    return {
      currency: b.settings.default_currency,
      by_status: statuses.map((status) => ({
        status,
        count: rows.filter((o) => o.status === status).length,
        value: sumMoney(
          rows.filter((o) => o.status === status).map((o) => o.total),
        ),
      })),
      by_day: [...byDay.entries()].sort().map(([day, v]) => ({
        day,
        count: v.count,
        value: sumMoney(v.values),
      })),
      average_order_value: counted.length
        ? centsToString(total / BigInt(counted.length))
        : "0.00",
    };
  },
  async customers() {
    await demoDelay();
    const b = demoBusiness();
    const totals = new Map<string, { invoiced: string[]; orders: number }>();
    for (const i of b.invoices.filter((i) =>
      ["issued", "partially_paid", "paid"].includes(i.status),
    )) {
      const entry = totals.get(i.customer_id) ?? { invoiced: [], orders: 0 };
      entry.invoiced.push(i.total);
      entry.orders += i.order_id ? 1 : 0;
      totals.set(i.customer_id, entry);
    }
    const top = [...totals.entries()]
      .map(([id, v]) => ({
        customer_id: id,
        name: b.customers.find((c) => c.id === id)?.name ?? "Unknown",
        invoiced: sumMoney(v.invoiced),
        orders: v.orders,
      }))
      .sort((a, c) => Number(c.invoiced) - Number(a.invoiced))
      .slice(0, 10);
    return {
      currency: b.settings.default_currency,
      total: b.customers.length,
      new_by_month: monthsBack(12).map(
        (m) =>
          [m, b.customers.filter((c) => c.created_at.startsWith(m)).length] as [
            string,
            number,
          ],
      ),
      top,
    };
  },
  async quotes() {
    await demoDelay();
    const b = demoBusiness();
    const statuses = [...new Set(b.quotes.map((q) => q.status))];
    const decided = b.quotes.filter((q) =>
      ["accepted", "rejected", "expired"].includes(q.status),
    ).length;
    const accepted = b.quotes.filter((q) => q.status === "accepted").length;
    return {
      currency: b.settings.default_currency,
      by_status: statuses.map((status) => ({
        status,
        count: b.quotes.filter((q) => q.status === status).length,
        value: sumMoney(
          b.quotes.filter((q) => q.status === status).map((q) => q.total),
        ),
      })),
      conversion_rate: decided ? (accepted / decided).toFixed(4) : null,
      open_value: sumMoney(
        b.quotes
          .filter((q) =>
            ["draft", "pending_approval", "approved", "sent"].includes(
              q.status,
            ),
          )
          .map((q) => q.total),
      ),
    };
  },
  async inventory() {
    await demoDelay();
    const b = demoBusiness();
    const rows = demoLevelRows();
    const prices = new Map(
      b.products.flatMap((p) =>
        p.variants.map((v) => [v.id, v.price] as const),
      ),
    );
    return {
      low_stock_count: new Set(
        rows.filter((l) => l.is_low).map((l) => l.variant_id),
      ).size,
      stock_value: sumMoney(
        rows.map((l) => mulMoney(prices.get(l.variant_id) ?? "0", l.on_hand)),
      ),
      currency: b.settings.default_currency,
    };
  },
  employees: () => hrService.headcount(),
};

export const reportsService = select<ReportsService>({ demo, live });
