"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  MessageCircle,
  Pencil,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { MarketingConsent } from "@/features/campaigns";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  EmptyState,
  ErrorState,
  Input,
  LoadingBlock,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";
import {
  METHOD_LABEL,
  PaymentStatus,
  type PaymentRequest,
  type PaymentSettings,
} from "@/features/getting-paid";
import { del, errorText, get, patch, post } from "@/lib/api";
import { date, timeAgo } from "@/lib/format";
import product from "@/components/product.module.css";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

interface CustomerRow {
  id: string;
  name: string;
  phone: string | null;
  last_message_at: string;
  conversations: number;
}

interface Profile {
  customer: {
    id: string;
    name: string;
    phone: string | null;
    email: string | null;
    tags: string[];
    created_at: string;
  };
  conversations: {
    id: string;
    status: string;
    mode: string;
    last_message_at: string;
    summary: string;
    language: string | null;
    requirements: Record<string, string>;
  }[];
  memory: {
    id: string;
    content: string;
    kind: string;
    created_at: string;
    last_used_at: string | null;
  }[];
  consents: {
    purpose: string;
    status: string;
    source: string;
    updated_at: string;
  }[];
  open_issues: { kind: string; id: string; summary: string; status: string }[];
  bookings: {
    id: string;
    starts_at: string;
    status: string;
    timezone: string;
  }[];
  tasks: { id: string; title: string; status: string }[];
}

export function CustomersPage() {
  const key = useBusinessKey();
  const can = useCan();
  const [search, setSearch] = React.useState("");
  const [page, setPage] = React.useState(1);
  const list = useQuery({
    queryKey: key(["customers", search, page]),
    queryFn: () =>
      get<{
        items: CustomerRow[];
        total: number;
        page: number;
        page_size: number;
      }>("/pi/customers", {
        search: search || undefined,
        page,
        page_size: 25,
      }),
    placeholderData: (previous) => previous,
  });
  return (
    <div>
      <PageHeader
        title="Customers"
        description="Everyone who has talked to pi, and what pi remembers about them."
        action={
          <>
            {list.data ? (
              <Badge tone="accent">{list.data.total} customers</Badge>
            ) : null}
            {can("pi.campaigns.read") ? (
              <Link
                href="/customers/campaigns"
                className="text-sm font-medium text-accent underline"
              >
                Campaigns
              </Link>
            ) : null}
          </>
        }
      />
      <div className="relative mb-4 max-w-md">
        <Search
          className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          aria-label="Search customers"
          placeholder="Search name or phone"
          className="ps-9"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
      </div>
      {list.isPending ? (
        <LoadingBlock rows={4} />
      ) : list.isError ? (
        <ErrorState
          message={errorText(list.error)}
          onRetry={() => list.refetch()}
        />
      ) : list.data.items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Users className="size-6" aria-hidden />}
            title={search ? "No matches" : "No customers yet"}
          >
            {search
              ? "Try another name or number."
              : "Customers appear here after they message your WhatsApp number."}
          </EmptyState>
        </Card>
      ) : (
        <Card className={product.customerList}>
          <ul className="divide-y divide-border">
            {list.data.items.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/customers/${c.id}`}
                  className="flex min-h-16 items-center gap-3 px-4 py-3 hover:bg-surface-muted sm:px-5"
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-surface-sunken font-semibold">
                    {c.name.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium" data-user-text>
                      {c.name}
                    </span>
                    <span className="block truncate text-sm text-muted-foreground">
                      {c.phone ?? "No phone"}
                    </span>
                  </span>
                  <span className="hidden text-end text-sm text-muted-foreground sm:block">
                    {c.conversations} conversation
                    {c.conversations === 1 ? "" : "s"}
                    <span className="block text-xs">
                      Last message {timeAgo(c.last_message_at)}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm">
            <span className="text-muted-foreground">
              {list.data.total} customer{list.data.total === 1 ? "" : "s"}
            </span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={page * list.data.page_size >= list.data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function MemoryItem({
  item,
  customerId,
}: {
  item: Profile["memory"][number];
  customerId: string;
}) {
  const can = useCan();
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState(item.content);
  const save = useAction(
    () => patch(`/pi/memory/${item.id}`, { content: text }),
    {
      invalidate: [["profile", customerId]],
      success: "Correction saved",
      onSuccess: () => setEditing(false),
    },
  );
  const forget = useAction(() => del(`/pi/memory/${item.id}`), {
    invalidate: [["profile", customerId]],
    success: "pi has forgotten this",
  });
  return (
    <li className="rounded-lg border border-border p-3">
      {editing ? (
        <div className="space-y-2">
          <Textarea
            aria-label="Correct this memory"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={500}
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={save.isPending}
              onClick={() => save.mutate(undefined)}
              disabled={!text.trim()}
            >
              Save
            </Button>
          </div>
        </div>
      ) : (
        <>
          <p className="whitespace-pre-line text-sm" data-user-text>
            {item.content}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>From a conversation on {date(item.created_at)}</span>
            {item.last_used_at ? (
              <span>· last used {timeAgo(item.last_used_at)}</span>
            ) : null}
            {can("pi.inbox.reply") ? (
              <span className="ms-auto flex gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setEditing(true)}
                  aria-label="Correct this memory"
                >
                  <Pencil className="size-4" aria-hidden /> Correct
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={forget.isPending}
                  onClick={() => forget.mutate(undefined)}
                  aria-label="Forget this memory"
                >
                  <Trash2 className="size-4" aria-hidden /> Forget
                </Button>
              </span>
            ) : null}
          </div>
        </>
      )}
    </li>
  );
}

export function CustomerProfilePage({ id }: { id: string }) {
  const key = useBusinessKey();
  const can = useCan();
  const [exportData, setExportData] = React.useState<string | null>(null);
  const profile = useQuery({
    queryKey: key(["profile", id]),
    queryFn: () => get<Profile>(`/pi/customers/${id}/profile`),
  });
  const exporter = useAction(() => get<unknown>(`/pi/customers/${id}/export`), {
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      setExportData(URL.createObjectURL(blob));
    },
  });
  if (profile.isPending)
    return <LoadingBlock rows={4} label="Loading customer" />;
  if (profile.isError)
    return (
      <ErrorState
        message={errorText(profile.error)}
        onRetry={() => profile.refetch()}
      />
    );
  const p = profile.data;
  const requirements = p.conversations.flatMap((c) =>
    Object.entries(c.requirements ?? {}).filter(([, v]) => v),
  );
  return (
    <div className="space-y-6">
      <Link
        href="/customers"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden /> Customers
      </Link>
      <PageHeader
        title={p.customer.name}
        description={
          [p.customer.phone, p.customer.email].filter(Boolean).join(" · ") ||
          "No contact details"
        }
        action={
          can("pi.customers.export") ? (
            <Button
              variant="secondary"
              loading={exporter.isPending}
              onClick={() => exporter.mutate(undefined)}
            >
              <Download className="size-4" aria-hidden /> Export data
            </Button>
          ) : null
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardSection>
              <h2 className="text-base font-semibold">What pi remembers</h2>
              <p className="mb-4 text-sm text-muted-foreground">
                Facts from this customer&apos;s own conversations. They are
                never used for anyone else.
              </p>
              {!can("pi.memory.read") ? (
                <p className="text-sm text-muted-foreground">
                  You don&apos;t have access to customer memory.
                </p>
              ) : p.memory.length ? (
                <ul className="space-y-2">
                  {p.memory.map((m) => (
                    <MemoryItem key={m.id} item={m} customerId={id} />
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Nothing yet.</p>
              )}
            </CardSection>
          </Card>
          <Card>
            <CardSection>
              <h2 className="mb-3 text-base font-semibold">Conversations</h2>
              <ul className="space-y-3">
                {p.conversations.map((c) => (
                  <li
                    key={c.id}
                    className="rounded-lg border border-border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={c.status === "open" ? "accent" : "neutral"}>
                        {c.status === "open" ? "Open" : "Closed"}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        {timeAgo(c.last_message_at)}
                      </span>
                      <Link
                        href={`/inbox?conversation=${c.id}`}
                        className="ms-auto inline-flex items-center gap-1 text-sm text-accent underline"
                      >
                        <MessageCircle className="size-4" aria-hidden /> Open
                      </Link>
                    </div>
                    {c.summary ? (
                      <p
                        className="mt-2 whitespace-pre-line text-sm"
                        data-user-text
                      >
                        {c.summary}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </CardSection>
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardSection>
              <h2 className="mb-2 text-base font-semibold">
                Confirmed requirements
              </h2>
              {requirements.length ? (
                <dl className="space-y-2 text-sm">
                  {requirements.map(([k, v], i) => (
                    <div key={k + i}>
                      <dt className="text-muted-foreground">
                        {k.replaceAll("_", " ")}
                      </dt>
                      <dd data-user-text>{v}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">None recorded.</p>
              )}
            </CardSection>
          </Card>
          <Card>
            <CardSection>
              <h2 className="mb-2 text-base font-semibold">Open issues</h2>
              {p.open_issues.length ? (
                <ul className="space-y-2 text-sm">
                  {p.open_issues.map((issue) => (
                    <li key={issue.kind + issue.id} className="flex gap-2">
                      <Badge tone="warning">{issue.kind}</Badge>
                      <span data-user-text>
                        {issue.summary || "No summary"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Nothing open.</p>
              )}
            </CardSection>
          </Card>
          {can("billing.read") ? (
            <CustomerPayments
              customerId={id}
              conversationId={
                p.conversations.find((c) => c.status === "open")?.id ?? null
              }
            />
          ) : null}
          <Card>
            <CardSection>
              <h2 className="mb-2 text-base font-semibold">
                Messaging permission
              </h2>
              {p.consents.length ? (
                <ul className="space-y-2 text-sm">
                  {p.consents.map((c) => (
                    <li key={c.purpose}>
                      <Badge
                        tone={c.status === "granted" ? "success" : "neutral"}
                      >
                        {c.purpose === "reminders"
                          ? "Follow-up reminders"
                          : "Marketing"}
                        : {c.status === "granted" ? "allowed" : "not allowed"}
                      </Badge>
                      {c.source ? (
                        <p
                          className="mt-1 text-xs text-muted-foreground"
                          data-user-text
                        >
                          &ldquo;{c.source}&rdquo;
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">
                  The customer hasn&apos;t agreed to follow-ups.
                </p>
              )}
              {can("customers.write") ? (
                <div className="mt-3">
                  <MarketingConsent
                    customerId={id}
                    granted={p.consents.some(
                      (c) =>
                        c.purpose === "marketing" && c.status === "granted",
                    )}
                  />
                </div>
              ) : null}
            </CardSection>
          </Card>
        </div>
      </div>
      <Dialog
        open={Boolean(exportData)}
        onOpenChange={(open) => (!open ? setExportData(null) : null)}
      >
        <DialogContent
          title="Export ready"
          description="This file contains the customer's messages and what pi remembers. Share it only with the customer."
        >
          <Button asChild className="w-full">
            <a href={exportData ?? "#"} download={`customer-${id}.json`}>
              <Download className="size-4" aria-hidden /> Download file
            </a>
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CustomerPayments({
  customerId,
  conversationId,
}: {
  customerId: string;
  conversationId: string | null;
}) {
  const key = useBusinessKey();
  const can = useCan();
  const [method, setMethod] = React.useState("");
  const [invoiceId, setInvoiceId] = React.useState("");
  const [created, setCreated] = React.useState<PaymentRequest | null>(null);
  const invoices = useQuery({
    queryKey: key(["open-invoices", customerId]),
    queryFn: () =>
      get<{ id: string; number: string; due: string; currency: string }[]>(
        `/pi/customers/${customerId}/open-invoices`,
      ),
  });
  const settings = useQuery({
    queryKey: key(["payment-settings"]),
    queryFn: () => get<PaymentSettings>("/pi/customer-payments/settings"),
  });
  const requests = useQuery({
    queryKey: key(["payment-requests", "customer", customerId]),
    queryFn: () =>
      get<PaymentRequest[]>("/pi/payment-requests", {
        customer_id: customerId,
      }),
  });
  const create = useAction(
    () =>
      post<PaymentRequest>("/pi/payment-requests", {
        invoice_id: invoiceId || invoices.data?.[0]?.id,
        method: method || settings.data?.enabled_methods[0],
        conversation_id: conversationId,
      }),
    {
      invalidate: [["payment-requests"]],
      onSuccess: (r) => setCreated(r),
      success: "Payment details ready",
    },
  );
  const send = useAction(
    (id: string) => post(`/pi/payment-requests/${id}/send`),
    {
      invalidate: [["history"], ["conversations"]],
      success: "Sent to the customer on WhatsApp",
    },
  );
  const [description, setDescription] = React.useState("");
  const [amount, setAmount] = React.useState("");
  // The draft survives a failed "issue" so retrying never creates a second invoice.
  const draft = React.useRef<{ id: string; key: string } | null>(null);
  const makeInvoice = useAction(
    async () => {
      const key = `${description}|${amount}`;
      if (draft.current?.key !== key) {
        const created = await post<{ id: string }>("/sales/billing/invoices", {
          customer_id: customerId,
          lines: [{ description, quantity: "1", unit_price: amount }],
        });
        draft.current = { id: created.id, key };
      }
      const invoice = { id: draft.current.id };
      await post(`/sales/billing/invoices/${invoice.id}/actions`, {
        action: "issue",
      });
      return invoice;
    },
    {
      invalidate: [["open-invoices", customerId]],
      success: "Invoice created",
      onSuccess: (invoice) => {
        draft.current = null;
        setInvoiceId(invoice.id);
        setDescription("");
        setAmount("");
      },
    },
  );
  const methods = settings.data?.enabled_methods ?? [];
  return (
    <Card>
      <CardSection className="space-y-3">
        <h2 className="text-base font-semibold">Payments</h2>
        {requests.data?.length ? (
          <ul className="space-y-1 text-sm">
            {requests.data.slice(0, 5).map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <span className="flex-1 tabular-nums">
                  {r.amount} {r.currency} · {METHOD_LABEL[r.method] ?? r.method}
                </span>
                <PaymentStatus status={r.status} />
              </li>
            ))}
          </ul>
        ) : null}
        {can("billing.write") ? (
          <details className="rounded-lg border border-border p-3 text-sm">
            <summary className="cursor-pointer font-medium">
              Create an invoice
            </summary>
            <div className="mt-3 space-y-2">
              <Input
                aria-label="What it's for"
                placeholder="What it's for"
                value={description}
                maxLength={200}
                onChange={(e) => setDescription(e.target.value)}
              />
              <Input
                aria-label="Amount"
                placeholder="Amount"
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
              <Button
                size="sm"
                variant="secondary"
                loading={makeInvoice.isPending}
                disabled={
                  !description.trim() || !/^\d+(\.\d{1,2})?$/.test(amount)
                }
                onClick={() => makeInvoice.mutate(undefined)}
              >
                Create and issue
              </Button>
            </div>
          </details>
        ) : null}
        {!invoices.data?.length ? (
          <p className="text-sm text-muted-foreground">
            No open invoices for this customer.
          </p>
        ) : !methods.length ? (
          <p className="text-sm text-muted-foreground">
            Turn on a payment method in{" "}
            <Link className="text-accent underline" href="/settings/payments">
              Settings → Getting paid
            </Link>
            .
          </p>
        ) : can("billing.write") ? (
          <div className="space-y-2">
            <Select
              aria-label="Invoice"
              value={invoiceId}
              onChange={(e) => setInvoiceId(e.target.value)}
            >
              {invoices.data.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.number} · {i.due} {i.currency} due
                </option>
              ))}
            </Select>
            <Select
              aria-label="Payment method"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            >
              {methods.map((m) => (
                <option key={m} value={m}>
                  {METHOD_LABEL[m] ?? m}
                </option>
              ))}
            </Select>
            <Button
              size="sm"
              loading={create.isPending}
              onClick={() => create.mutate(undefined)}
            >
              Prepare payment details
            </Button>
          </div>
        ) : null}
        {created ? (
          <div className="space-y-2 rounded-lg border border-border bg-surface-muted p-3">
            <p className="whitespace-pre-line text-sm" data-user-text>
              {created.message}
            </p>
            {created.conversation_id ? (
              <Button
                size="sm"
                loading={send.isPending}
                onClick={() => send.mutate(created.id)}
              >
                Send in WhatsApp chat
              </Button>
            ) : (
              <p className="text-xs text-muted-foreground">
                No open conversation. Copy these details to the customer.
              </p>
            )}
          </div>
        ) : null}
      </CardSection>
    </Card>
  );
}
