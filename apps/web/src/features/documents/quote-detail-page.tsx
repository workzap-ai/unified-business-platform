"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Ban,
  CalendarX,
  CheckCircle2,
  FileText,
  MoreHorizontal,
  Pencil,
  Send,
  ShoppingCart,
  Stamp,
  ThumbsDown,
  ThumbsUp,
  Undo2,
  type LucideIcon,
} from "lucide-react";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PropertyList, RecordHeader } from "@/components/app/record";
import { ConfirmDialog } from "@/components/app/forms";
import { ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { customersService } from "@/features/customers/service";
import type { QuoteDetail } from "@/features/business/types";
import { documentsService, type QuoteAction } from "./service";
import { SourceBadge, ValidUntil } from "./badges";
import { DocumentView } from "./document-view";
import { StatusFlow, type FlowStep } from "./status-flow";
import { useBusinessSettings, useQuote } from "./hooks";
import { approvalReasons } from "./lib";

type AnyAction = QuoteAction | "convert_to_order";

const ACTIONS: Record<
  AnyAction,
  {
    label: string;
    icon: LucideIcon;
    permission: string[];
    menu?: boolean;
    confirm?: {
      title: string;
      consequences: string[];
      destructive?: boolean;
      label: string;
    };
  }
> = {
  submit: { label: "Submit", icon: Send, permission: ["quotes.write"] },
  approve: {
    label: "Approve",
    icon: CheckCircle2,
    permission: ["quotes.approve"],
  },
  return_to_draft: {
    label: "Return to draft",
    icon: Undo2,
    permission: ["quotes.write", "quotes.approve"],
  },
  send: { label: "Mark as sent", icon: Send, permission: ["quotes.write"] },
  accept: {
    label: "Mark accepted",
    icon: ThumbsUp,
    permission: ["quotes.write"],
  },
  convert_to_order: {
    label: "Create order",
    icon: ShoppingCart,
    permission: ["orders.write"],
  },
  reject: {
    label: "Mark rejected",
    icon: ThumbsDown,
    permission: ["quotes.write"],
    menu: true,
    confirm: {
      title: "Mark this quote as rejected?",
      label: "Mark rejected",
      consequences: [
        "The quote is closed and can no longer be accepted or converted to an order.",
        "This can't be undone.",
      ],
    },
  },
  expire: {
    label: "Mark expired",
    icon: CalendarX,
    permission: ["quotes.write"],
    menu: true,
    confirm: {
      title: "Mark this quote as expired?",
      label: "Mark expired",
      consequences: [
        "The customer can no longer accept this quote.",
        "To offer it again, create a new quote.",
      ],
    },
  },
  cancel: {
    label: "Cancel quote",
    icon: Ban,
    permission: ["quotes.write"],
    menu: true,
    confirm: {
      title: "Cancel this quote?",
      label: "Cancel quote",
      destructive: true,
      consequences: [
        "The quote is withdrawn and can't be sent, accepted or converted.",
        "It stays in your records for reference. This can't be undone.",
      ],
    },
  },
};

export function QuoteDetailPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="quotes.read" area="quotes">
      <QuoteRecord id={id} />
    </RequirePermission>
  );
}

function QuoteRecord({ id }: { id: string }) {
  const router = useRouter();
  const { can, canAny } = useSession();
  const quote = useQuote(id);
  const settings = useBusinessSettings();
  const q = quote.data;
  useBreadcrumbs(
    q ? [{ label: q.number }] : [],
    q ? { href: `/quotes/${id}`, kind: "Quote" } : undefined,
  );

  const customer = useScopedQuery(
    ["customers", "detail", q?.customer_id],
    () => customersService.get(q!.customer_id),
    {
      enabled: Boolean(q) && can("customers.read"),
    },
  );
  const order = useScopedQuery(
    ["orders", "detail", q?.order_id],
    () => documentsService.order(q!.order_id!),
    {
      enabled: Boolean(q?.order_id) && can("orders.read"),
    },
  );

  const [confirming, setConfirming] = useState<QuoteAction | null>(null);
  const [running, setRunning] = useState<AnyAction | null>(null);

  const action = useScopedMutation(
    (a: QuoteAction) => documentsService.quoteAction(id, a),
    {
      invalidate: [["quotes"]],
      success: (r) =>
        `${r.number} is now ${r.status === "pending_approval" ? "waiting for approval" : r.status.replace(/_/g, " ")}`,
      onSuccess: () => setConfirming(null),
    },
  );
  const convert = useScopedMutation(() => documentsService.convertQuote(id), {
    invalidate: [["quotes"], ["orders"]],
    success: (o) => `Draft order ${o.number} created`,
    onSuccess: (o) => router.push(`/orders/${o.id}`),
  });

  function run(a: AnyAction) {
    if (a === "convert_to_order") {
      setRunning(a);
      convert.mutate(undefined, { onSettled: () => setRunning(null) });
      return;
    }
    if (ACTIONS[a].confirm) {
      setConfirming(a);
      return;
    }
    setRunning(a);
    action.mutate(a, { onSettled: () => setRunning(null) });
  }

  if (quote.isError) {
    return (
      <PageShell>
        <Card>
          <ErrorState
            error={quote.error}
            onRetry={() => void quote.refetch()}
          />
        </Card>
      </PageShell>
    );
  }
  if (!q) {
    return (
      <PageShell>
        <RecordHeader title="" loading />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Skeleton className="h-[480px] rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      </PageShell>
    );
  }

  const available = (q.next_actions as AnyAction[]).filter(
    (a) => ACTIONS[a] && canAny(...ACTIONS[a].permission),
  );
  const primary = available.filter((a) => !ACTIONS[a].menu);
  const menu = available.filter((a) => ACTIONS[a].menu);
  const canEdit = q.status === "draft" && can("quotes.write");
  const reasons = approvalReasons(q, settings.data, q.currency);
  const confirmSpec = confirming ? ACTIONS[confirming].confirm : undefined;
  const busy = running !== null || action.isPending;

  return (
    <PageShell>
      <RecordHeader
        icon={FileText}
        title={<span className="font-mono">{q.number}</span>}
        status={<StatusBadge status={q.status} />}
        subtitle={
          <>
            For{" "}
            {can("customers.read") ? (
              <Link
                href={`/customers/${q.customer_id}`}
                className="font-medium text-foreground hover:underline"
              >
                {q.customer_name ?? "customer"}
              </Link>
            ) : (
              <span className="font-medium text-foreground">
                {q.customer_name ?? "customer"}
              </span>
            )}{" "}
            · {formatMoney(q.total, q.currency)}
          </>
        }
        meta={
          <>
            <span>
              Valid until <ValidUntil quote={q} />
            </span>
            <span className="flex items-center gap-1.5">
              Source <SourceBadge source={q.source} />
            </span>
            <span>Created {formatDate(q.created_at)}</span>
          </>
        }
        actions={
          <>
            {canEdit && (
              <Button variant="secondary" size="sm" asChild>
                <Link href={`/quotes/${q.id}/edit`}>
                  <Pencil /> Edit
                </Link>
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
                  loading={running === a}
                  disabled={busy}
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
                    aria-label="More quote actions"
                    disabled={busy}
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
                        destructive={spec.confirm?.destructive}
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

      {q.status === "draft" && (
        <Notice tone="neutral" className="mb-4" title="This quote is a draft">
          Nothing has been sent to the customer.{" "}
          {q.requires_approval
            ? "Submit it for approval when ready."
            : "Submit it when ready."}
        </Notice>
      )}
      {q.status === "pending_approval" && (
        <Notice
          tone="warning"
          icon={Stamp}
          className="mb-4"
          title="Waiting for approval"
        >
          {can("quotes.approve")
            ? "Review the lines and totals, then approve or return it to draft."
            : "A reviewer needs to approve it before it can be sent."}
        </Notice>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <DocumentView
          kind="Quote"
          number={q.number}
          status={<StatusBadge status={q.status} />}
          dates={[
            { label: "Date", value: formatDate(q.created_at) },
            { label: "Valid until", value: <ValidUntil quote={q} /> },
            ...(q.sent_at
              ? [{ label: "Sent", value: formatDate(q.sent_at) }]
              : []),
          ]}
          billTo={{
            name: q.customer_name ?? "Customer",
            href: can("customers.read")
              ? `/customers/${q.customer_id}`
              : undefined,
            lines: customer.data
              ? [
                  customer.data.company,
                  customer.data.email,
                  customer.data.phone,
                ]
              : [],
          }}
          lines={q.lines.map((l) => ({ ...l, custom: l.variant_id === null }))}
          totals={q}
          taxRate={q.tax_rate}
          currency={q.currency}
          notes={q.notes}
        />

        <aside className="space-y-4">
          <Card>
            <CardHeader title="Progress" />
            <CardBody>
              <StatusFlow steps={quoteSteps(q)} terminal={quoteTerminal(q)} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Approval" icon={<Stamp />} />
            <CardBody>
              {q.requires_approval || q.source === "pi" ? (
                <>
                  <p className="text-[13px] text-foreground-secondary">
                    {q.approved_at
                      ? "Approved before sending."
                      : "Needs a reviewer's approval before it can be sent."}
                  </p>
                  {reasons.length > 0 && (
                    <ul className="mt-2 space-y-1 text-[13px] text-muted-foreground">
                      {reasons.map((r) => (
                        <li key={r} className="flex gap-1.5">
                          <span aria-hidden="true">•</span> {r}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  Within discount and value limits — no approval needed.
                </p>
              )}
              <PropertyList
                className="mt-2"
                items={[
                  {
                    label: "Approved",
                    value: q.approved_at ? formatDateTime(q.approved_at) : null,
                  },
                ]}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Linked order" icon={<ShoppingCart />} />
            <CardBody>
              {q.order_id ? (
                <Link
                  href={`/orders/${q.order_id}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5 hover:bg-surface-muted"
                >
                  <span className="font-mono text-[13px] font-medium">
                    {order.data?.number ??
                      (order.isPending && can("orders.read")
                        ? "Loading…"
                        : "View order")}
                  </span>
                  {order.data && <StatusBadge status={order.data.status} />}
                </Link>
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  {q.status === "accepted"
                    ? "Accepted — create an order to fulfil it."
                    : "An order can be created once the customer accepts."}
                </p>
              )}
            </CardBody>
          </Card>
        </aside>
      </div>

      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={confirmSpec?.title ?? ""}
        consequences={confirmSpec?.consequences}
        confirmLabel={confirmSpec?.label}
        destructive={confirmSpec?.destructive}
        loading={action.isPending}
        onConfirm={() => confirming && action.mutate(confirming)}
      />
    </PageShell>
  );
}

function quoteSteps(q: QuoteDetail): FlowStep[] {
  const order = ["draft", "pending_approval", "approved", "sent", "accepted"];
  const reached = order.indexOf(q.status);
  const state = (doneFrom: number, currentAt: number[]): FlowStep["state"] =>
    reached >= doneFrom
      ? "done"
      : currentAt.includes(reached)
        ? "current"
        : "upcoming";
  return [
    {
      key: "draft",
      label: "Draft",
      state: state(1, [0]),
      at: null,
      hint: "Prepared",
    },
    {
      key: "approval",
      label: q.requires_approval ? "Approval" : "Approval (not needed)",
      state: state(2, [1]),
      at: q.approved_at,
    },
    {
      key: "sent",
      label: "Sent to customer",
      state: state(3, [2]),
      at: q.sent_at,
    },
    {
      key: "accepted",
      label: "Accepted",
      state: reached >= 4 ? "done" : reached === 3 ? "current" : "upcoming",
    },
  ];
}

function quoteTerminal(q: QuoteDetail) {
  if (q.status === "rejected") return { label: "Rejected by the customer" };
  if (q.status === "expired")
    return {
      label: "Expired",
      description: `Validity ended ${formatDate(q.valid_until)}`,
    };
  if (q.status === "cancelled")
    return { label: "Cancelled", description: "Withdrawn before acceptance" };
  return null;
}
