"use client";

import { useState } from "react";
import { RecordAttachments } from "@/features/integrations/business-panels";
import Link from "next/link";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Ban,
  CheckCircle2,
  FileText,
  ListPlus,
  MoreHorizontal,
  PackageCheck,
  PackageOpen,
  Receipt,
  ShoppingCart,
  Truck,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { formatDate, formatMoney, formatNumber, toCents } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Avatar,
  Card,
  CardBody,
  CardHeader,
  Skeleton,
} from "@/components/ui/display";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PropertyList, RecordHeader } from "@/components/app/record";
import { DataTable, type Column } from "@/components/app/data-table";
import { ConfirmDialog } from "@/components/app/forms";
import { ErrorState, InlineError, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { customersService } from "@/features/customers/service";
import { errorMessage } from "@/services/api-client";
import type { OrderDetail } from "@/features/business/types";
import { documentsService, type OrderAction } from "./service";
import { SourceBadge } from "./badges";
import { useBusinessSettings, useOrder } from "./hooks";
import { LinesEditor } from "./lines-editor";
import { TotalsPanel } from "./totals-panel";
import { StatusFlow, type FlowStep } from "./status-flow";
import { fromDocumentLines, linesSchema, toOrderLineInputs } from "./schema";

type OrderLine = OrderDetail["lines"][number];

const ACTIONS: Record<
  OrderAction,
  { label: string; icon: LucideIcon; permission: string; menu?: boolean }
> = {
  confirm: {
    label: "Confirm order",
    icon: CheckCircle2,
    permission: "orders.write",
  },
  start_processing: {
    label: "Start processing",
    icon: PackageOpen,
    permission: "orders.write",
  },
  complete: {
    label: "Complete service",
    icon: CheckCircle2,
    permission: "orders.write",
  },
  ship: { label: "Mark shipped", icon: Truck, permission: "orders.write" },
  deliver: {
    label: "Mark delivered",
    icon: PackageCheck,
    permission: "orders.write",
  },
  cancel: {
    label: "Cancel order",
    icon: Ban,
    permission: "orders.cancel",
    menu: true,
  },
};

const FLOW: OrderDetail["status"][] = [
  "draft",
  "confirmed",
  "processing",
  "shipped",
  "delivered",
];

export function OrderDetailPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="orders.read" area="orders">
      <OrderRecord id={id} />
    </RequirePermission>
  );
}

function OrderRecord({ id }: { id: string }) {
  const { can } = useSession();
  const order = useOrder(id);
  const settings = useBusinessSettings();
  const o = order.data;
  useBreadcrumbs(
    o ? [{ label: o.number }] : [],
    o ? { href: `/orders/${id}`, kind: "Order" } : undefined,
  );
  const customer = useScopedQuery(
    ["customers", "detail", o?.customer_id],
    () => customersService.get(o!.customer_id),
    {
      enabled: Boolean(o) && can("customers.read"),
    },
  );
  const quote = useScopedQuery(
    ["quotes", "detail", o?.quote_id],
    () => documentsService.quote(o!.quote_id!),
    {
      enabled: Boolean(o?.quote_id) && can("quotes.read"),
    },
  );

  const [confirming, setConfirming] = useState<"confirm" | "cancel" | null>(
    null,
  );
  const [editing, setEditing] = useState(false);
  const action = useScopedMutation(
    (a: OrderAction) => documentsService.orderAction(id, a),
    {
      invalidate: [["orders"], ["invoices"], ["inventory"], ["quotes"]],
      success: (r) => `${r.number} is now ${r.status}`,
      error: "The order couldn't be updated. Please try again.",
      onSuccess: () => setConfirming(null),
    },
  );

  if (order.isError) {
    return (
      <PageShell>
        <Card>
          <ErrorState
            error={order.error}
            onRetry={() => void order.refetch()}
          />
        </Card>
      </PageShell>
    );
  }
  if (!o) {
    return (
      <PageShell>
        <RecordHeader title="" loading />
        <Skeleton className="mb-4 h-16 rounded-xl" />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Skeleton className="h-96 rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      </PageShell>
    );
  }

  const available = (o.next_actions as OrderAction[]).filter(
    (a) => ACTIONS[a] && can(ACTIONS[a].permission),
  );
  const primary = available.filter((a) => !ACTIONS[a].menu);
  const menu = available.filter((a) => ACTIONS[a].menu);
  const canEditLines = o.status === "draft" && can("orders.write");
  const autoInvoice = settings.data?.auto_invoice_on_order_confirm;

  function run(a: OrderAction) {
    if (a === "confirm" || a === "cancel") setConfirming(a);
    else action.mutate(a);
  }

  const lineColumns: Column<OrderLine>[] = [
    {
      key: "sku",
      header: "SKU",
      cell: (l) => (
        <span className="font-mono text-xs text-muted-foreground">
          {l.sku ?? "—"}
        </span>
      ),
      hideBelow: "sm",
    },
    {
      key: "description",
      header: "Description",
      cell: (l) => <span className="font-medium">{l.description}</span>,
    },
    {
      key: "qty",
      header: "Qty",
      align: "right",
      cell: (l) => <span className="tabular">{formatNumber(l.quantity)}</span>,
    },
    {
      key: "unit",
      header: "Unit price",
      align: "right",
      cell: (l) => (
        <span className="tabular">{formatMoney(l.unit_price, o.currency)}</span>
      ),
      hideBelow: "md",
    },
    {
      key: "discount",
      header: "Discount",
      align: "right",
      cell: (l) => (
        <span className="tabular text-muted-foreground">
          {toCents(l.discount) > BigInt(0)
            ? `−${formatMoney(l.discount, o.currency)}`
            : "—"}
        </span>
      ),
      hideBelow: "md",
    },
    {
      key: "total",
      header: "Line total",
      align: "right",
      cell: (l) => (
        <span className="tabular font-medium">
          {formatMoney(l.line_total, o.currency)}
        </span>
      ),
    },
  ];

  return (
    <PageShell>
      <RecordHeader
        icon={ShoppingCart}
        title={<span className="font-mono">{o.number}</span>}
        status={<StatusBadge status={o.status} />}
        subtitle={
          <>
            For{" "}
            {can("customers.read") ? (
              <Link
                href={`/customers/${o.customer_id}`}
                className="font-medium text-foreground hover:underline"
              >
                {o.customer_name ?? "customer"}
              </Link>
            ) : (
              <span className="font-medium text-foreground">
                {o.customer_name ?? "customer"}
              </span>
            )}{" "}
            · {formatMoney(o.total, o.currency)}
          </>
        }
        meta={
          <>
            <span className="flex items-center gap-1.5">
              Source <SourceBadge source={o.source} />
            </span>
            <span>Created by {o.created_by_label}</span>
            <span>{formatDate(o.created_at)}</span>
          </>
        }
        actions={
          <>
            {canEditLines && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setEditing(true)}
              >
                <ListPlus /> Edit items
              </Button>
            )}
            {primary.map((a, i) => {
              const spec = ACTIONS[a];
              return (
                <Button
                  key={a}
                  size="sm"
                  variant={i === 0 ? "default" : "secondary"}
                  onClick={() => run(a)}
                  loading={action.isPending && action.variables === a}
                  disabled={action.isPending}
                >
                  <spec.icon /> {spec.label}
                </Button>
              );
            })}
            {menu.length > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="secondary"
                    size="icon-sm"
                    aria-label="More order actions"
                    disabled={action.isPending}
                  >
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  {menu.map((a) => {
                    const spec = ACTIONS[a];
                    return (
                      <DropdownMenuItem
                        key={a}
                        onSelect={() => run(a)}
                        destructive={a === "cancel"}
                      >
                        <spec.icon /> {spec.label}
                      </DropdownMenuItem>
                    );
                  })}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </>
        }
      />

      <Card className="mb-4 px-4 py-4">
        <StatusFlow
          steps={orderSteps(o)}
          terminal={
            o.status === "cancelled"
              ? { label: "Cancelled", at: o.cancelled_at }
              : null
          }
          orientation="horizontal"
        />
      </Card>

      {o.status === "draft" && (
        <Notice tone="neutral" className="mb-4" title="Draft order">
          Nothing has been deducted or invoiced yet. Review the items, then
          confirm the order.
        </Notice>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-4">
          <DataTable
            columns={lineColumns}
            rows={o.lines}
            getRowId={(l) => l.id}
            caption="Order lines"
          />
          <Card>
            <CardBody className="grid gap-5 pt-4 sm:grid-cols-[1fr_minmax(240px,300px)]">
              <div className="text-[13px]">
                {o.notes ? (
                  <>
                    <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                      Notes
                    </p>
                    <p className="mt-1 whitespace-pre-line text-foreground-secondary">
                      {o.notes}
                    </p>
                  </>
                ) : (
                  <p className="text-muted-foreground">
                    No notes on this order.
                  </p>
                )}
              </div>
              <TotalsPanel
                totals={o}
                taxRate={o.tax_rate}
                currency={o.currency}
              />
            </CardBody>
          </Card>
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader title="Customer" icon={<UserRound />} />
            <CardBody>
              <div className="flex items-start gap-3">
                <Avatar name={o.customer_name ?? "?"} />
                <div className="min-w-0 text-[13px]">
                  {can("customers.read") ? (
                    <Link
                      href={`/customers/${o.customer_id}`}
                      className="font-semibold hover:underline"
                    >
                      {o.customer_name ?? "Customer"}
                    </Link>
                  ) : (
                    <p className="font-semibold">
                      {o.customer_name ?? "Customer"}
                    </p>
                  )}
                  {customer.isPending && can("customers.read") ? (
                    <Skeleton className="mt-1.5 h-3.5 w-32" />
                  ) : customer.data ? (
                    [
                      customer.data.company,
                      customer.data.email,
                      customer.data.phone,
                    ]
                      .filter(Boolean)
                      .map((line) => (
                        <p
                          key={line}
                          className="truncate text-muted-foreground"
                        >
                          {line}
                        </p>
                      ))
                  ) : null}
                </div>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Invoice" icon={<Receipt />} />
            <CardBody>
              {o.invoice_id ? (
                <Link
                  href={`/billing/invoices/${o.invoice_id}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5 hover:bg-surface-muted"
                >
                  <span className="font-mono text-[13px] font-medium">
                    {o.invoice_number ?? "View invoice"}
                  </span>
                  <span className="text-xs text-primary">Open</span>
                </Link>
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  No invoice yet.
                  {o.status === "draft" && autoInvoice
                    ? " One is issued automatically when the order is confirmed."
                    : ""}
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Details" icon={<FileText />} />
            <CardBody>
              <PropertyList
                items={[
                  {
                    label: "Quote",
                    value: o.quote_id ? (
                      <Link
                        href={`/quotes/${o.quote_id}`}
                        className="font-mono text-primary hover:underline"
                      >
                        {quote.data?.number ?? "View quote"}
                      </Link>
                    ) : null,
                  },
                  {
                    label: "Confirmed",
                    value: o.confirmed_at ? formatDate(o.confirmed_at) : null,
                  },
                  {
                    label: "Cancelled",
                    value: o.cancelled_at ? formatDate(o.cancelled_at) : null,
                  },
                  { label: "Created by", value: o.created_by_label },
                ]}
              />
            </CardBody>
          </Card>
        </aside>
      </div>
      <RecordAttachments type="order" id={id} permission="orders.write" />

      <ConfirmDialog
        open={confirming === "confirm"}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={`Confirm ${o.number}?`}
        description="Confirming commits this order."
        consequences={[
          "Stock is deducted for stock-tracked items. Confirmation fails if any item is short.",
          autoInvoice === false
            ? "Auto-invoicing is off — you'll need to invoice this order separately."
            : "An invoice is issued automatically if auto-invoicing is on.",
          "Prices are re-verified against the catalog; if any changed, you'll be asked to review the items.",
        ]}
        confirmLabel="Confirm order"
        loading={action.isPending}
        onConfirm={() => action.mutate("confirm")}
      />
      <ConfirmDialog
        open={confirming === "cancel"}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={`Cancel ${o.number}?`}
        consequences={[
          ...(o.status !== "draft"
            ? ["Deducted stock is returned to inventory."]
            : []),
          ...(o.invoice_id
            ? [
                "The unpaid invoice is voided. Orders with paid invoices can't be cancelled.",
              ]
            : []),
          "The order is closed permanently. This cannot be undone.",
        ]}
        confirmLabel="Cancel order"
        destructive
        loading={action.isPending}
        onConfirm={() => action.mutate("cancel")}
      />
      {canEditLines && (
        <EditLinesDialog order={o} open={editing} onOpenChange={setEditing} />
      )}
    </PageShell>
  );
}

function orderSteps(o: OrderDetail): FlowStep[] {
  const flow =
    o.fulfillment_type === "service"
      ? FLOW.filter((s) => s !== "shipped")
      : FLOW;
  const reached = flow.indexOf(o.status);
  const labels: Record<string, string> = {
    draft: "Draft",
    confirmed: "Confirmed",
    processing: "Processing",
    shipped: "Shipped",
    delivered: o.fulfillment_type === "service" ? "Completed" : "Delivered",
  };
  return flow.map((status, index) => ({
    key: status,
    label: labels[status]!,
    state:
      o.status === "cancelled"
        ? "upcoming"
        : index < reached || o.status === "delivered"
          ? "done"
          : index === reached
            ? "current"
            : "upcoming",
    at:
      status === "confirmed"
        ? o.confirmed_at
        : status === "draft"
          ? o.created_at
          : null,
  }));
}

const editSchema = z.object({ lines: linesSchema("order") });
type EditValues = z.infer<typeof editSchema>;

function EditLinesDialog({
  order,
  open,
  onOpenChange,
}: {
  order: OrderDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [saving, setSaving] = useState(false);
  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent size="xl">
        <DialogHeader
          title={`Edit items on ${order.number}`}
          description="Catalog prices are applied automatically. Stock is only checked when the order is confirmed."
        />
        {open && (
          <EditLinesForm
            order={order}
            onDone={() => onOpenChange(false)}
            onSavingChange={setSaving}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function EditLinesForm({
  order,
  onDone,
  onSavingChange,
}: {
  order: OrderDetail;
  onDone: () => void;
  onSavingChange: (saving: boolean) => void;
}) {
  const settings = useBusinessSettings();
  const [initial] = useState<EditValues>(() => ({
    lines: fromDocumentLines(order.lines),
  }));
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: initial,
  });
  const save = useScopedMutation(
    (v: EditValues) =>
      documentsService.updateOrderLines(order.id, toOrderLineInputs(v.lines)),
    {
      invalidate: [["orders"]],
      success: (r) => `${r.number} items updated`,
      onSuccess: () => onDone(),
    },
  );
  const lines = useWatch({ control: form.control, name: "lines" }) ?? [];

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit((v) => {
        onSavingChange(true);
        save.mutate(v, { onSettled: () => onSavingChange(false) });
      })}
      className="flex min-h-0 flex-1 flex-col"
    >
      <DialogBody className="space-y-4">
        <Controller
          control={form.control}
          name="lines"
          render={({ field }) => (
            <LinesEditor
              mode="order"
              lines={field.value ?? []}
              onChange={(next) => {
                field.onChange(next);
                if (form.formState.isSubmitted) void form.trigger("lines");
              }}
              currency={order.currency}
              errors={form.formState.errors.lines}
              disabled={save.isPending}
            />
          )}
        />
        <div className="flex justify-end">
          <TotalsPanel
            className="w-full sm:w-72"
            lines={lines}
            taxRate={settings.data?.tax_rate ?? order.tax_rate}
            currency={order.currency}
            preview
          />
        </div>
        {save.isError && (
          <InlineError
            message={errorMessage(save.error, "The items couldn't be saved.")}
          />
        )}
      </DialogBody>
      <DialogFooter>
        <Button
          type="button"
          variant="secondary"
          onClick={onDone}
          disabled={save.isPending}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          loading={save.isPending}
          disabled={save.isPending || !form.formState.isDirty}
        >
          Save items
        </Button>
      </DialogFooter>
    </form>
  );
}
