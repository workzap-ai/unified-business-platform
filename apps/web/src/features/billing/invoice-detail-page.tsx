"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Ban,
  CalendarDays,
  ExternalLink,
  Receipt,
  Send,
  ShoppingCart,
  User,
  Wallet,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  formatDateTime,
  formatMoney,
  formatNumber,
  toCents,
} from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, Skeleton } from "@/components/ui/display";
import { PageShell, RequirePermission } from "@/components/app/page";
import {
  ActivityTimeline,
  PropertyList,
  RecordHeader,
  type TimelineEvent,
} from "@/components/app/record";
import { ConfirmDialog } from "@/components/app/forms";
import { ErrorState, Notice } from "@/components/app/states";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import type { InvoiceDetail } from "@/features/business/types";
import { billingService } from "./service";
import { InvoiceStatus } from "./invoice-bits";
import { RecordPaymentSheet } from "./record-payment-sheet";
import { dueHint, formatDay, methodLabel } from "./utils";

export function InvoiceDetailPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="billing.read" area="invoices">
      <InvoiceDetailView id={id} />
    </RequirePermission>
  );
}

function InvoiceDetailView({ id }: { id: string }) {
  const { can } = useSession();
  const query = useScopedQuery(["invoices", "detail", id], () =>
    billingService.invoice(id),
  );
  const invoice = query.data;
  const [dialog, setDialog] = useState<"issue" | "void" | "payment" | null>(
    null,
  );

  useBreadcrumbs(invoice ? [{ label: invoice.number }] : [], {
    href: `/billing/invoices/${id}`,
    kind: "invoice",
  });

  const invalidate = [["invoices"], ["billing"], ["finance"]];
  const issue = useScopedMutation(
    () => billingService.invoiceAction(id, "issue"),
    {
      invalidate,
      success: (i) => `${i.number} issued`,
      onSuccess: () => setDialog(null),
    },
  );
  const voidInvoice = useScopedMutation(
    () => billingService.invoiceAction(id, "void"),
    {
      invalidate,
      success: (i) => `${i.number} voided`,
      onSuccess: () => setDialog(null),
    },
  );

  if (query.isPending) return <DetailSkeleton />;
  if (query.isError || !invoice) {
    return (
      <PageShell width="default">
        <Card>
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
          />
          <div className="-mt-8 pb-8 text-center">
            <Link
              href="/billing/invoices"
              className="text-sm font-medium text-primary hover:underline"
            >
              Back to invoices
            </Link>
          </div>
        </Card>
      </PageShell>
    );
  }

  const canWrite = can("billing.write");
  const actions = canWrite ? invoice.next_actions : [];
  const hint = dueHint(invoice);
  const paidSomething = toCents(invoice.amount_paid) > BigInt(0);

  return (
    <PageShell>
      <RecordHeader
        icon={Receipt}
        title={invoice.number}
        status={<InvoiceStatus invoice={invoice} />}
        subtitle={
          invoice.customer_name ? (
            <>
              Billed to{" "}
              <Link
                href={`/customers/${invoice.customer_id}`}
                className="font-medium text-foreground hover:underline"
              >
                {invoice.customer_name}
              </Link>
            </>
          ) : undefined
        }
        meta={
          <>
            <span className="tabular font-medium text-foreground">
              {formatMoney(invoice.total, invoice.currency)}
            </span>
            {invoice.issue_date && (
              <span className="inline-flex items-center gap-1">
                <CalendarDays className="size-3.5" aria-hidden="true" /> Issued{" "}
                {formatDay(invoice.issue_date)}
              </span>
            )}
            {invoice.due_date && (
              <span
                className={cn(
                  hint?.tone === "danger" && "font-medium text-danger",
                )}
              >
                Due {formatDay(invoice.due_date)}
                {hint ? ` · ${hint.text}` : ""}
              </span>
            )}
          </>
        }
        actions={
          actions.length > 0 ? (
            <>
              {actions.includes("void") && (
                <Button
                  variant="danger-outline"
                  onClick={() => setDialog("void")}
                >
                  <Ban /> Void
                </Button>
              )}
              {actions.includes("issue") && (
                <Button onClick={() => setDialog("issue")}>
                  <Send /> Issue invoice
                </Button>
              )}
              {actions.includes("record_payment") && (
                <Button onClick={() => setDialog("payment")}>
                  <Wallet /> Record payment
                </Button>
              )}
            </>
          ) : undefined
        }
      />

      {invoice.status === "draft" && (
        <Notice tone="info" title="Draft — not yet sent" className="mb-4">
          {canWrite
            ? "Customers don't owe anything on a draft. Issue it when the lines and totals are right; after that it can only be paid or voided."
            : "This invoice hasn't been issued yet, so no balance is owed."}
        </Notice>
      )}
      {invoice.status === "void" && (
        <Notice
          tone="neutral"
          icon={Ban}
          title="This invoice is void"
          className="mb-4"
        >
          It no longer counts toward receivables and can&apos;t be paid or
          reopened.
        </Notice>
      )}
      {invoice.is_overdue && (
        <Notice tone="danger" title="Payment is overdue" className="mb-4">
          {formatMoney(invoice.balance_due, invoice.currency)} was due on{" "}
          {formatDay(invoice.due_date)}.
        </Notice>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <InvoiceDocument invoice={invoice} />

        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Summary" />
            <div className="px-4 pb-2">
              <PropertyList
                items={[
                  {
                    label: "Status",
                    value: (
                      <InvoiceStatus
                        invoice={invoice}
                        className="justify-end"
                      />
                    ),
                  },
                  {
                    label: "Balance due",
                    value: (
                      <span
                        className={cn(
                          "tabular",
                          invoice.is_overdue && "text-danger",
                        )}
                      >
                        {invoice.status === "void"
                          ? "—"
                          : formatMoney(invoice.balance_due, invoice.currency)}
                      </span>
                    ),
                  },
                  {
                    label: "Amount paid",
                    value: (
                      <span className="tabular">
                        {formatMoney(invoice.amount_paid, invoice.currency)}
                      </span>
                    ),
                  },
                  {
                    label: "Customer",
                    value: (
                      <Link
                        href={`/customers/${invoice.customer_id}`}
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        <User className="size-3.5" aria-hidden="true" />
                        {invoice.customer_name ?? "View customer"}
                      </Link>
                    ),
                  },
                  {
                    label: "Order",
                    value: invoice.order_id ? (
                      <Link
                        href={`/orders/${invoice.order_id}`}
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        <ShoppingCart className="size-3.5" aria-hidden="true" />{" "}
                        View order
                      </Link>
                    ) : (
                      <span className="font-normal text-muted-foreground">
                        Not linked
                      </span>
                    ),
                  },
                  {
                    label: "Created",
                    value: formatDateTime(invoice.created_at),
                  },
                ]}
              />
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Payments"
              description={
                invoice.payments.length
                  ? `${formatNumber(invoice.payments.length)} recorded`
                  : undefined
              }
              actions={
                actions.includes("record_payment") ? (
                  <Button
                    variant="ghost"
                    size="xs"
                    onClick={() => setDialog("payment")}
                  >
                    <Wallet /> Record
                  </Button>
                ) : undefined
              }
            />
            <div className="px-2 pb-2">
              {invoice.payments.length === 0 ? (
                <p className="px-2 pt-1 pb-3 text-[13px] text-muted-foreground">
                  {invoice.status === "draft"
                    ? "Payments can be recorded once the invoice is issued."
                    : invoice.status === "void"
                      ? "No payments were recorded before this invoice was voided."
                      : "No payments yet."}
                </p>
              ) : (
                <ul>
                  {invoice.payments.map((p) => (
                    <li
                      key={p.id}
                      className="flex items-start gap-3 rounded-lg px-2 py-2"
                    >
                      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-success-soft text-success">
                        <Wallet className="size-3.5" aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1 text-[13px]">
                        <span className="block font-medium">
                          {p.number} · {methodLabel(p.method)}
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {formatDay(p.received_on)}
                          {p.reference ? ` · Ref ${p.reference}` : ""} ·{" "}
                          {p.recorded_by_label}
                        </span>
                      </span>
                      <span className="tabular shrink-0 text-[13px] font-semibold">
                        {formatMoney(p.amount, p.currency)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Timeline" />
            <div className="px-4 pb-4">
              <ActivityTimeline events={timeline(invoice)} />
            </div>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={dialog === "issue"}
        onOpenChange={(open) => !open && setDialog(null)}
        title={`Issue ${invoice.number}?`}
        description={`${invoice.customer_name ?? "The customer"} will owe ${formatMoney(invoice.total, invoice.currency)}.`}
        consequences={[
          "The issue date is set to today and the invoice starts counting toward receivables.",
          invoice.due_date
            ? `Payment is due on ${formatDay(invoice.due_date)}.`
            : "The due date is set from your standard payment terms.",
          "Lines and totals can no longer be edited. Mistakes are corrected by voiding.",
        ]}
        confirmLabel="Issue invoice"
        loading={issue.isPending}
        onConfirm={() => issue.mutate(undefined)}
      />
      <ConfirmDialog
        open={dialog === "void"}
        onOpenChange={(open) => !open && setDialog(null)}
        title={`Void ${invoice.number}?`}
        description="Voiding cannot be undone."
        consequences={[
          "The invoice is permanently cancelled and can't be issued, paid or reopened.",
          invoice.status === "draft"
            ? "The draft stays in your records for reference."
            : `${formatMoney(invoice.balance_due, invoice.currency)} is removed from receivables.`,
          "To bill the customer again, create a new invoice.",
        ]}
        confirmLabel="Void invoice"
        destructive
        loading={voidInvoice.isPending}
        onConfirm={() => voidInvoice.mutate(undefined)}
      />
      {actions.includes("record_payment") && (
        <RecordPaymentSheet
          invoice={invoice}
          open={dialog === "payment"}
          onOpenChange={(open) => setDialog(open ? "payment" : null)}
        />
      )}
      {paidSomething && invoice.status === "paid" && (
        <span className="sr-only">Invoice paid in full.</span>
      )}
    </PageShell>
  );
}

function InvoiceDocument({ invoice }: { invoice: InvoiceDetail }) {
  const money = (v: string) => formatMoney(v, invoice.currency);
  const hasDiscounts = toCents(invoice.discount_total) > BigInt(0);
  return (
    <Card className="min-w-0 overflow-hidden">
      <div className="grid gap-5 border-b border-border p-4 sm:grid-cols-2 sm:p-6">
        <div>
          <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
            Bill to
          </p>
          <Link
            href={`/customers/${invoice.customer_id}`}
            className="mt-1 inline-flex items-center gap-1 text-[15px] font-semibold hover:underline"
          >
            {invoice.customer_name ?? "Customer"}
            <ExternalLink
              className="size-3.5 text-muted-foreground"
              aria-hidden="true"
            />
          </Link>
        </div>
        <dl className="grid grid-cols-3 gap-3 text-[13px] sm:text-right">
          <div>
            <dt className="text-xs text-muted-foreground">Invoice</dt>
            <dd className="mt-0.5 font-medium">{invoice.number}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Issued</dt>
            <dd className="tabular mt-0.5 font-medium">
              {invoice.issue_date ? formatDay(invoice.issue_date) : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Due</dt>
            <dd className="tabular mt-0.5 font-medium">
              {invoice.due_date ? formatDay(invoice.due_date) : "On issue"}
            </dd>
          </div>
        </dl>
      </div>

      <div className="scrollbar-thin overflow-x-auto">
        <table className="w-full text-[13px]">
          <caption className="sr-only">Invoice lines</caption>
          <thead>
            <tr className="border-b border-border bg-surface-muted/70 text-xs text-muted-foreground">
              <th
                scope="col"
                className="px-4 py-2 text-left font-medium sm:px-6"
              >
                Description
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Qty
              </th>
              <th
                scope="col"
                className="hidden px-3 py-2 text-right font-medium sm:table-cell"
              >
                Unit price
              </th>
              {hasDiscounts && (
                <th
                  scope="col"
                  className="hidden px-3 py-2 text-right font-medium md:table-cell"
                >
                  Discount
                </th>
              )}
              <th
                scope="col"
                className="px-4 py-2 text-right font-medium sm:px-6"
              >
                Amount
              </th>
            </tr>
          </thead>
          <tbody>
            {invoice.lines.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-6 text-center text-muted-foreground"
                >
                  This invoice has no lines.
                </td>
              </tr>
            ) : (
              [...invoice.lines]
                .sort((a, b) => a.position - b.position)
                .map((line) => (
                  <tr
                    key={line.id}
                    className="border-b border-border align-top last:border-0"
                  >
                    <td className="px-4 py-2.5 sm:px-6">
                      <span className="block">{line.description}</span>
                      <span className="tabular block text-xs text-muted-foreground sm:hidden">
                        {money(line.unit_price)} each
                      </span>
                    </td>
                    <td className="tabular px-3 py-2.5 text-right">
                      {formatNumber(line.quantity)}
                    </td>
                    <td className="tabular hidden px-3 py-2.5 text-right sm:table-cell">
                      {money(line.unit_price)}
                    </td>
                    {hasDiscounts && (
                      <td className="tabular hidden px-3 py-2.5 text-right text-muted-foreground md:table-cell">
                        {toCents(line.discount) > BigInt(0)
                          ? `−${money(line.discount)}`
                          : "—"}
                      </td>
                    )}
                    <td className="tabular px-4 py-2.5 text-right font-medium sm:px-6">
                      {money(line.line_total)}
                    </td>
                  </tr>
                ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col gap-5 border-t border-border p-4 sm:flex-row sm:justify-between sm:p-6">
        <div className="max-w-sm text-[13px]">
          {invoice.notes ? (
            <>
              <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                Notes
              </p>
              <p className="mt-1 whitespace-pre-line text-foreground-secondary">
                {invoice.notes}
              </p>
            </>
          ) : null}
        </div>
        <dl className="w-full space-y-1.5 text-[13px] sm:max-w-64">
          <Row label="Subtotal" value={money(invoice.subtotal)} />
          {hasDiscounts && (
            <Row
              label="Discounts"
              value={`−${money(invoice.discount_total)}`}
            />
          )}
          <Row label="Tax" value={money(invoice.tax_total)} />
          <Row label="Total" value={money(invoice.total)} strong />
          <Row label="Amount paid" value={money(invoice.amount_paid)} />
          <div className="flex justify-between gap-4 rounded-md bg-surface-muted px-2 py-1.5 text-sm font-semibold">
            <dt>Balance due</dt>
            <dd className={cn("tabular", invoice.is_overdue && "text-danger")}>
              {invoice.status === "void" ? "—" : money(invoice.balance_due)}
            </dd>
          </div>
        </dl>
      </div>
    </Card>
  );
}

function Row({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex justify-between gap-4 px-2",
        strong && "border-t border-border pt-2 font-semibold",
      )}
    >
      <dt className={strong ? undefined : "text-muted-foreground"}>{label}</dt>
      <dd className="tabular">{value}</dd>
    </div>
  );
}

function timeline(invoice: InvoiceDetail): TimelineEvent[] {
  const events: TimelineEvent[] = [
    {
      id: "created",
      kind: "created",
      title: "Draft created",
      at: invoice.created_at,
    },
  ];
  if (invoice.issue_date) {
    events.push({
      id: "issued",
      kind: "invoice",
      title: "Issued to customer",
      description: invoice.due_date
        ? `Due ${formatDay(invoice.due_date)}`
        : undefined,
      at: invoice.issue_date,
    });
  }
  for (const p of invoice.payments) {
    events.push({
      id: p.id,
      kind: "payment",
      title: `${formatMoney(p.amount, p.currency)} received`,
      description: `${methodLabel(p.method)} · ${p.number}`,
      actor: p.recorded_by_label,
      at: p.created_at,
    });
  }
  events.sort((a, b) => b.at.localeCompare(a.at));
  if (invoice.status === "paid") {
    const last = events.find((e) => e.kind === "payment");
    if (last)
      events.unshift({
        id: "paid",
        kind: "status",
        title: "Paid in full",
        at: last.at,
      });
  }
  return events;
}

function DetailSkeleton() {
  return (
    <PageShell>
      <RecordHeader title="" loading />
      <div
        className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]"
        aria-busy="true"
        aria-label="Loading invoice"
      >
        <Skeleton className="h-[460px] rounded-xl" />
        <div className="space-y-4">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      </div>
    </PageShell>
  );
}
