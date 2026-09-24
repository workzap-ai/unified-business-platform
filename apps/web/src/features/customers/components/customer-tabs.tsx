"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { FileText, MessageSquare, Receipt, ShoppingCart, StickyNote } from "lucide-react";
import { formatDate, formatDateTime, formatMoney, relativeTime } from "@/lib/format";
import { Avatar, Badge, Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { DataTable, Pagination, type Column } from "@/components/app/data-table";
import { EmptyState, ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { FormField } from "@/components/app/forms";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { documentsService } from "@/features/documents/service";
import { billingService } from "@/features/billing/service";
import { piService } from "@/features/pi/service";
import { ServiceNotConnectedError } from "@/services/api-client";
import type { CustomerDetail, Invoice, Order, Quote } from "@/features/business/types";
import type { Conversation } from "@/features/pi/types";
import { customersService } from "../service";

const PAGE_SIZE = 10;

export function OrdersTab({ customerId }: { customerId: string }) {
  const { can } = useSession();
  const [page, setPage] = useState(1);
  const params = { customerId, page, pageSize: PAGE_SIZE };
  const query = useScopedQuery(["orders", params], () => documentsService.orders(params), { placeholderData: (p) => p });
  const columns: Column<Order>[] = [
    { key: "number", header: "Order", cell: (o) => <Link href={`/orders/${o.id}`} className="font-mono font-medium hover:underline">{o.number}</Link> },
    { key: "status", header: "Status", cell: (o) => <StatusBadge status={o.status} /> },
    { key: "source", header: "Source", hideBelow: "md", cell: (o) => (o.source === "pi" ? <Badge tone="pi">PI</Badge> : <span className="text-muted-foreground">{o.source === "quote" ? "From quote" : "Manual"}</span>) },
    { key: "created", header: "Created", hideBelow: "sm", cell: (o) => <span className="tabular text-muted-foreground">{formatDate(o.created_at)}</span> },
    { key: "total", header: "Total", align: "right", cell: (o) => <span className="tabular font-medium">{formatMoney(o.total, o.currency)}</span> },
  ];
  return (
    <>
      <DataTable
        caption="Orders for this customer"
        columns={columns}
        rows={query.data?.items}
        getRowId={(o) => o.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        rowHref={(o) => `/orders/${o.id}`}
        loadingRows={4}
        empty={
          <EmptyState
            compact
            icon={ShoppingCart}
            title="No orders yet"
            description="Orders placed by your team or confirmed through PI show up here."
            action={can("orders.write") ? <Button size="sm" asChild><Link href={`/orders/new?customer=${customerId}`}>Create order</Link></Button> : undefined}
          />
        }
      />
      <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={setPage} />
    </>
  );
}

export function QuotesTab({ customerId }: { customerId: string }) {
  const { can } = useSession();
  const [page, setPage] = useState(1);
  const params = { customerId, page, pageSize: PAGE_SIZE };
  const query = useScopedQuery(["quotes", params], () => documentsService.quotes(params), { placeholderData: (p) => p });
  const columns: Column<Quote>[] = [
    { key: "number", header: "Quote", cell: (q) => <Link href={`/quotes/${q.id}`} className="font-mono font-medium hover:underline">{q.number}</Link> },
    { key: "status", header: "Status", cell: (q) => <StatusBadge status={q.status} /> },
    { key: "valid", header: "Valid until", hideBelow: "md", cell: (q) => <span className="tabular text-muted-foreground">{formatDate(q.valid_until)}</span> },
    { key: "created", header: "Created", hideBelow: "sm", cell: (q) => <span className="tabular text-muted-foreground">{formatDate(q.created_at)}</span> },
    { key: "total", header: "Total", align: "right", cell: (q) => <span className="tabular font-medium">{formatMoney(q.total, q.currency)}</span> },
  ];
  return (
    <>
      <DataTable
        caption="Quotes for this customer"
        columns={columns}
        rows={query.data?.items}
        getRowId={(q) => q.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        rowHref={(q) => `/quotes/${q.id}`}
        loadingRows={4}
        empty={
          <EmptyState
            compact
            icon={FileText}
            title="No quotes yet"
            description="Send a priced quote this customer can accept and turn into an order."
            action={can("quotes.write") ? <Button size="sm" asChild><Link href={`/quotes/new?customer=${customerId}`}>Create quote</Link></Button> : undefined}
          />
        }
      />
      <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={setPage} />
    </>
  );
}

export function InvoicesTab({ customerId }: { customerId: string }) {
  const [page, setPage] = useState(1);
  const params = { customerId, page, pageSize: PAGE_SIZE };
  const query = useScopedQuery(["invoices", params], () => billingService.invoices(params), { placeholderData: (p) => p });
  const columns: Column<Invoice>[] = [
    { key: "number", header: "Invoice", cell: (i) => <Link href={`/billing/invoices/${i.id}`} className="font-mono font-medium hover:underline">{i.number}</Link> },
    { key: "status", header: "Status", cell: (i) => <StatusBadge status={i.is_overdue ? "overdue" : i.status} /> },
    { key: "due", header: "Due", hideBelow: "md", cell: (i) => <span className="tabular text-muted-foreground">{formatDate(i.due_date)}</span> },
    { key: "total", header: "Total", align: "right", hideBelow: "sm", cell: (i) => <span className="tabular">{formatMoney(i.total, i.currency)}</span> },
    { key: "balance", header: "Balance due", align: "right", cell: (i) => <span className="tabular font-medium">{formatMoney(i.balance_due, i.currency)}</span> },
  ];
  return (
    <>
      <DataTable
        caption="Invoices for this customer"
        columns={columns}
        rows={query.data?.items}
        getRowId={(i) => i.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        rowHref={(i) => `/billing/invoices/${i.id}`}
        loadingRows={4}
        empty={<EmptyState compact icon={Receipt} title="No invoices yet" description="Invoices are created from confirmed orders or directly in Billing." />}
      />
      <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={setPage} />
    </>
  );
}

export function ConversationsTab({ customer }: { customer: CustomerDetail }) {
  const query = useScopedQuery(["pi", "conversations", { search: customer.name }], () => piService.conversations({ search: customer.name }), {
    retry: (count, error) => !(error instanceof ServiceNotConnectedError) && count < 2,
  });
  const rows: Conversation[] | undefined = query.data?.items.filter((c) => c.customer_id === customer.id);

  if (query.isError) {
    const notConnected = query.error instanceof ServiceNotConnectedError;
    return (
      <Card>
        <ErrorState
          error={query.error}
          title={notConnected ? "PI isn't connected here yet" : undefined}
          onRetry={notConnected ? undefined : () => void query.refetch()}
        />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="WhatsApp conversations"
        description="Chats with this customer handled by PI or your team"
        actions={
          <Link href={`/pi/inbox?search=${encodeURIComponent(customer.name)}`} className="text-xs font-medium text-primary hover:underline">
            Open PI inbox
          </Link>
        }
      />
      <div className="px-2 pb-2">
        {query.isPending || !rows ? (
          <div className="space-y-2 px-2 pb-2">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState compact icon={MessageSquare} tone="pi" title="No conversations yet" description="When this customer messages your WhatsApp number, PI's conversations appear here." />
        ) : (
          <ul className="divide-y divide-border">
            {rows.map((c) => (
              <li key={c.id}>
                <Link href={`/pi/inbox?conversation=${encodeURIComponent(c.id)}`} className="flex items-start gap-3 rounded-lg px-2 py-3 hover:bg-surface-muted">
                  <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-pi-soft text-pi">
                    <MessageSquare className="size-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <StatusBadge status={c.status} />
                      <StatusBadge status={c.mode} dot={false} label={c.mode === "ai" ? "PI replying" : "Team replying"} />
                      {c.handoff_status && <StatusBadge status={c.handoff_status} label={`Handoff: ${c.handoff_status.replace(/_/g, " ")}`} />}
                      {c.unread_count > 0 && <Badge tone="primary">{c.unread_count} unread</Badge>}
                    </span>
                    <span className="mt-1 block truncate text-[13px]">{c.last_message_preview || c.summary}</span>
                    {c.summary && c.last_message_preview && <span className="mt-0.5 block truncate text-xs text-muted-foreground">{c.summary}</span>}
                  </span>
                  <time dateTime={c.last_message_at} title={formatDateTime(c.last_message_at)} className="shrink-0 text-xs text-muted-foreground">
                    {relativeTime(c.last_message_at)}
                  </time>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

const noteSchema = z.object({
  body: z.string().trim().min(1, "Write a note first").max(5000, "Keep notes under 5,000 characters"),
});
type NoteValues = z.infer<typeof noteSchema>;

export function NotesTab({ customerId }: { customerId: string }) {
  const { can } = useSession();
  const notes = useScopedQuery(["customers", "notes", customerId], () => customersService.notes(customerId));
  const form = useForm<NoteValues>({ resolver: zodResolver(noteSchema), defaultValues: { body: "" } });
  const add = useScopedMutation((values: NoteValues) => customersService.addNote(customerId, values.body.trim()), {
    invalidate: [["customers", "notes", customerId], ["customers", "activities", customerId]],
    success: "Note added",
    onSuccess: () => form.reset({ body: "" }),
  });
  const error = form.formState.errors.body;

  return (
    <div className="grid max-w-3xl gap-4">
      {can("customers.write") && (
        <Card>
          <form onSubmit={form.handleSubmit((v) => add.mutate(v))} noValidate>
            <CardBody className="pt-4">
              <FormField label="Add a note" htmlFor="customer-note" error={error} help="Visible to your team only. PI doesn't share notes with customers.">
                <Textarea
                  id="customer-note"
                  rows={3}
                  placeholder="e.g. Prefers delivery after 5pm, asked about bulk pricing"
                  aria-invalid={!!error || undefined}
                  aria-describedby={error ? "customer-note-error" : "customer-note-help"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void form.handleSubmit((v) => add.mutate(v))();
                  }}
                  {...form.register("body")}
                />
              </FormField>
              <div className="mt-3 flex justify-end">
                <Button type="submit" size="sm" loading={add.isPending} disabled={add.isPending}>
                  <StickyNote /> Save note
                </Button>
              </div>
            </CardBody>
          </form>
        </Card>
      )}
      <Card>
        <CardHeader title="Notes" description={notes.data ? `${notes.data.total} ${notes.data.total === 1 ? "note" : "notes"}` : undefined} />
        <div className="px-4 pb-4">
          {notes.isError ? (
            <ErrorState error={notes.error} onRetry={() => void notes.refetch()} compact />
          ) : notes.isPending ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }, (_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : notes.data.items.length === 0 ? (
            <p className="py-6 text-center text-[13px] text-muted-foreground">No notes yet. Capture preferences and context your team should know.</p>
          ) : (
            <ul className="divide-y divide-border">
              {notes.data.items.map((note) => (
                <li key={note.id} className="flex gap-3 py-3">
                  <Avatar name={note.author_label} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{note.author_label}</span> ·{" "}
                      <time dateTime={note.created_at} title={formatDateTime(note.created_at)}>
                        {relativeTime(note.created_at)}
                      </time>
                    </p>
                    <p className="mt-1 text-[13px] leading-relaxed break-words whitespace-pre-wrap">{note.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  );
}
