"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Archive,
  ArchiveRestore,
  Bot,
  CalendarClock,
  ChevronRight,
  FileText,
  Mail,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Phone,
  Receipt,
  ShoppingCart,
  Wallet,
} from "lucide-react";
import {
  formatDate,
  formatMoney,
  formatNumber,
  relativeTime,
} from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardBody,
  CardHeader,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/display";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { PageShell, RequirePermission } from "@/components/app/page";
import {
  ActivityTimeline,
  PropertyList,
  RecordHeader,
  RelatedList,
} from "@/components/app/record";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ConfirmDialog } from "@/components/app/forms";
import { ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { documentsService } from "@/features/documents/service";
import { billingService } from "@/features/billing/service";
import type { CustomerDetail } from "@/features/business/types";
import { customersService } from "./service";
import { activityToEvent } from "./lib";
import { CustomerSourceBadge, TagList } from "./components/customer-badges";
import { CustomerEditDialog } from "./components/customer-edit-dialog";
import {
  ConversationsTab,
  InvoicesTab,
  NotesTab,
  OrdersTab,
  QuotesTab,
} from "./components/customer-tabs";

const TABS = [
  "overview",
  "activity",
  "orders",
  "quotes",
  "invoices",
  "conversations",
  "notes",
] as const;
type Tab = (typeof TABS)[number];

export function CustomerDetailPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="customers.read" area="customers">
      <CustomerDetailView id={id} />
    </RequirePermission>
  );
}

function CustomerDetailView({ id }: { id: string }) {
  const query = useScopedQuery(["customers", "detail", id], () =>
    customersService.get(id),
  );
  const customer = query.data;
  useBreadcrumbs(
    customer ? [{ label: customer.name }] : [],
    customer ? { href: `/customers/${id}`, kind: "Customer" } : undefined,
  );

  if (query.isError) {
    return (
      <PageShell>
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        <div className="text-center">
          <Link
            href="/customers"
            className="text-sm font-medium text-primary hover:underline"
          >
            Back to customers
          </Link>
        </div>
      </PageShell>
    );
  }

  if (!customer) {
    return (
      <PageShell>
        <RecordHeader title="" loading />
        <div className="mb-4 h-9 border-b border-border" />
        <MetricGrid className="xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <MetricCard key={i} label="Loading" value="" loading />
          ))}
        </MetricGrid>
      </PageShell>
    );
  }

  return <CustomerRecord customer={customer} />;
}

function CustomerRecord({ customer }: { customer: CustomerDetail }) {
  const { can } = useSession();
  const canWrite = can("customers.write");
  const [state, setState] = useUrlState({ tab: "overview" });
  const gated: Partial<Record<Tab, boolean>> = {
    orders: can("orders.read"),
    quotes: can("quotes.read"),
    invoices: can("billing.read"),
    conversations: can("pi.read"),
  };
  const allowed = TABS.filter((t) => gated[t] ?? true) as readonly string[];
  const tab: Tab = allowed.includes(state.tab)
    ? (state.tab as Tab)
    : "overview";
  const [editing, setEditing] = useState(false);
  const [confirmStatus, setConfirmStatus] = useState(false);
  const archived = customer.status === "archived";

  const setStatus = useScopedMutation(
    () =>
      customersService.setStatus(customer.id, archived ? "active" : "archived"),
    {
      invalidate: [["customers"]],
      success: archived
        ? `${customer.name} restored`
        : `${customer.name} archived`,
      onSuccess: () => setConfirmStatus(false),
    },
  );

  const meta = (
    <>
      {customer.phone && (
        <a
          href={`tel:${customer.phone}`}
          className="inline-flex items-center gap-1.5 hover:text-foreground"
        >
          <Phone className="size-3.5" aria-hidden="true" />{" "}
          <span className="tabular">{customer.phone}</span>
        </a>
      )}
      {customer.email && (
        <a
          href={`mailto:${customer.email}`}
          className="inline-flex min-w-0 items-center gap-1.5 hover:text-foreground"
        >
          <Mail className="size-3.5" aria-hidden="true" />{" "}
          <span className="truncate">{customer.email}</span>
        </a>
      )}
      <span className="inline-flex items-center gap-1.5">
        <CalendarClock className="size-3.5" aria-hidden="true" />
        {customer.last_contacted_at
          ? `Last contacted ${relativeTime(customer.last_contacted_at)}`
          : "Not contacted yet"}
      </span>
    </>
  );

  const actions = (
    <>
      {can("quotes.write") && !archived && (
        <Button size="sm" asChild>
          <Link href={`/quotes/new?customer=${customer.id}`}>
            <FileText /> Create quote
          </Link>
        </Button>
      )}
      {can("orders.write") && !archived && (
        <Button size="sm" variant="secondary" asChild>
          <Link href={`/orders/new?customer=${customer.id}`}>
            <ShoppingCart /> Create order
          </Link>
        </Button>
      )}
      {canWrite && (
        <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
          <Pencil /> Edit
        </Button>
      )}
      {canWrite && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              size="icon-sm"
              variant="secondary"
              aria-label="More customer actions"
            >
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem
              onSelect={() => setConfirmStatus(true)}
              destructive={!archived}
            >
              {archived ? <ArchiveRestore /> : <Archive />}{" "}
              {archived ? "Restore customer" : "Archive customer"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </>
  );

  return (
    <PageShell>
      <RecordHeader
        avatar={customer.name}
        title={customer.name}
        status={
          <>
            <StatusBadge status={customer.status} />
            <CustomerSourceBadge source={customer.source} />
          </>
        }
        subtitle={customer.company ?? undefined}
        meta={meta}
        actions={actions}
      />

      <Tabs
        value={tab}
        onValueChange={(v) => setState({ tab: v }, { resetPage: false })}
      >
        <TabsList aria-label="Customer sections">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
          {can("orders.read") && (
            <TabsTrigger value="orders">Orders</TabsTrigger>
          )}
          {can("quotes.read") && (
            <TabsTrigger value="quotes">Quotes</TabsTrigger>
          )}
          {can("billing.read") && (
            <TabsTrigger value="invoices">Invoices</TabsTrigger>
          )}
          {can("pi.read") && (
            <TabsTrigger value="conversations">Conversations</TabsTrigger>
          )}
          <TabsTrigger value="notes">Notes</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab
            customer={customer}
            onTab={(t) => setState({ tab: t }, { resetPage: false })}
          />
        </TabsContent>
        <TabsContent value="activity">
          <ActivityTab customerId={customer.id} />
        </TabsContent>
        {can("orders.read") && (
          <TabsContent value="orders">
            <OrdersTab customerId={customer.id} />
          </TabsContent>
        )}
        {can("quotes.read") && (
          <TabsContent value="quotes">
            <QuotesTab customerId={customer.id} />
          </TabsContent>
        )}
        {can("billing.read") && (
          <TabsContent value="invoices">
            <InvoicesTab customerId={customer.id} />
          </TabsContent>
        )}
        {can("pi.read") && (
          <TabsContent value="conversations">
            <ConversationsTab customer={customer} />
          </TabsContent>
        )}
        <TabsContent value="notes">
          <NotesTab customerId={customer.id} />
        </TabsContent>
      </Tabs>

      {canWrite && (
        <CustomerEditDialog
          customer={customer}
          open={editing}
          onOpenChange={setEditing}
        />
      )}
      <ConfirmDialog
        open={confirmStatus}
        onOpenChange={(open) => !setStatus.isPending && setConfirmStatus(open)}
        title={
          archived ? `Restore ${customer.name}?` : `Archive ${customer.name}?`
        }
        description={
          archived
            ? "The customer becomes active again and appears in pickers and the Active view."
            : "You can restore this customer at any time."
        }
        consequences={
          archived
            ? undefined
            : [
                "They're hidden from the Active view and customer pickers for new quotes and orders.",
                "Existing orders, quotes, invoices, notes and conversations are kept.",
              ]
        }
        confirmLabel={archived ? "Restore" : "Archive"}
        destructive={!archived}
        loading={setStatus.isPending}
        onConfirm={() => setStatus.mutate(undefined)}
      />
    </PageShell>
  );
}

function OverviewTab({
  customer,
  onTab,
}: {
  customer: CustomerDetail;
  onTab: (tab: Tab) => void;
}) {
  const { can } = useSession();
  const { summary } = customer;
  const currency = summary.currency ?? "USD";
  const orders = useScopedQuery(
    ["orders", { customerId: customer.id, pageSize: 5 }],
    () => documentsService.orders({ customerId: customer.id, pageSize: 5 }),
    { enabled: can("orders.read") },
  );
  const quotes = useScopedQuery(
    ["quotes", { customerId: customer.id, pageSize: 5 }],
    () => documentsService.quotes({ customerId: customer.id, pageSize: 5 }),
    { enabled: can("quotes.read") },
  );
  const invoices = useScopedQuery(
    ["invoices", { customerId: customer.id, pageSize: 5 }],
    () => billingService.invoices({ customerId: customer.id, pageSize: 5 }),
    { enabled: can("billing.read") },
  );

  return (
    <div className="space-y-4">
      <MetricGrid className="xl:grid-cols-4">
        <MetricCard
          label="Orders"
          icon={ShoppingCart}
          value={formatNumber(summary.order_count)}
          detail="Excluding cancelled"
        />
        <MetricCard
          label="Open quotes"
          icon={FileText}
          value={formatNumber(summary.open_quote_count)}
        />
        {summary.outstanding_balance !== null && (
          <MetricCard
            label="Outstanding balance"
            icon={Wallet}
            tone={
              Number(summary.outstanding_balance) > 0 ? "warning" : "default"
            }
            value={formatMoney(summary.outstanding_balance, currency)}
            detail="Issued, unpaid invoices"
          />
        )}
        <MetricCard
          label="Open conversations"
          icon={MessageSquare}
          tone={summary.open_conversations > 0 ? "pi" : "default"}
          value={formatNumber(summary.open_conversations)}
          detail="On WhatsApp"
        />
      </MetricGrid>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Contact" />
            <CardBody className="pb-2">
              <PropertyList
                items={[
                  { label: "Name", value: customer.name },
                  {
                    label: "Email",
                    value: customer.email ? (
                      <a
                        href={`mailto:${customer.email}`}
                        className="text-primary hover:underline"
                      >
                        {customer.email}
                      </a>
                    ) : null,
                  },
                  {
                    label: "Phone",
                    value: customer.phone ? (
                      <span className="tabular">{customer.phone}</span>
                    ) : null,
                  },
                  { label: "Company", value: customer.company },
                  {
                    label: "Tags",
                    value: customer.tags.length ? (
                      <span className="inline-flex justify-end">
                        <TagList tags={customer.tags} max={8} />
                      </span>
                    ) : null,
                  },
                  {
                    label: "Source",
                    value: <CustomerSourceBadge source={customer.source} />,
                  },
                  {
                    label: "Customer since",
                    value: formatDate(customer.created_at),
                  },
                ]}
              />
            </CardBody>
          </Card>
          {can("pi.read") && (
            <Card>
              <CardHeader
                title={
                  <span className="flex items-center gap-1.5">
                    <Bot className="size-4 text-pi" aria-hidden="true" /> PI
                    conversations
                  </span>
                }
                description="WhatsApp chats handled by PI and your team"
              />
              <CardBody>
                <p className="text-[13px] text-muted-foreground">
                  {summary.open_conversations > 0
                    ? `${summary.open_conversations === 1 ? "1 conversation is" : `${summary.open_conversations} conversations are`} open with this customer.`
                    : "No open conversations right now."}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="secondary" asChild>
                    <Link
                      href={`/pi/inbox?search=${encodeURIComponent(customer.name)}`}
                    >
                      <MessageSquare /> Open in PI inbox
                    </Link>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onTab("conversations")}
                  >
                    View here
                  </Button>
                </div>
              </CardBody>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {can("orders.read") && (
            <RelatedList
              title="Recent orders"
              items={orders.data?.items}
              loading={orders.isPending}
              getKey={(o) => o.id}
              empty={
                orders.isError ? "Orders couldn't be loaded." : "No orders yet."
              }
              action={
                orders.data && orders.data.total > 5 ? (
                  <TabLink onClick={() => onTab("orders")} />
                ) : undefined
              }
              render={(o) => (
                <RelatedRow
                  href={`/orders/${o.id}`}
                  icon={ShoppingCart}
                  title={o.number}
                  meta={formatDate(o.created_at)}
                  status={o.status}
                  amount={formatMoney(o.total, o.currency)}
                />
              )}
            />
          )}
          {can("quotes.read") && (
            <RelatedList
              title="Recent quotes"
              items={quotes.data?.items}
              loading={quotes.isPending}
              getKey={(q) => q.id}
              empty={
                quotes.isError ? "Quotes couldn't be loaded." : "No quotes yet."
              }
              action={
                quotes.data && quotes.data.total > 5 ? (
                  <TabLink onClick={() => onTab("quotes")} />
                ) : undefined
              }
              render={(q) => (
                <RelatedRow
                  href={`/quotes/${q.id}`}
                  icon={FileText}
                  title={q.number}
                  meta={`Valid until ${formatDate(q.valid_until)}`}
                  status={q.status}
                  amount={formatMoney(q.total, q.currency)}
                />
              )}
            />
          )}
          {can("billing.read") && (
            <RelatedList
              title="Recent invoices"
              items={invoices.data?.items}
              loading={invoices.isPending}
              getKey={(i) => i.id}
              empty={
                invoices.isError
                  ? "Invoices couldn't be loaded."
                  : "No invoices yet."
              }
              action={
                invoices.data && invoices.data.total > 5 ? (
                  <TabLink onClick={() => onTab("invoices")} />
                ) : undefined
              }
              render={(i) => (
                <RelatedRow
                  href={`/billing/invoices/${i.id}`}
                  icon={Receipt}
                  title={i.number}
                  meta={
                    i.due_date
                      ? `Due ${formatDate(i.due_date)}`
                      : formatDate(i.created_at)
                  }
                  status={i.is_overdue ? "overdue" : i.status}
                  amount={formatMoney(i.total, i.currency)}
                />
              )}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function TabLink({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-xs font-medium text-primary hover:underline"
    >
      View all
    </button>
  );
}

function RelatedRow({
  href,
  icon: Icon,
  title,
  meta,
  status,
  amount,
}: {
  href: string;
  icon: typeof FileText;
  title: string;
  meta: string;
  status: string;
  amount: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-muted"
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-muted-foreground">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-mono text-[13px] font-medium">
          {title}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {meta}
        </span>
      </span>
      <StatusBadge status={status} className="hidden sm:inline-flex" />
      <span className="tabular shrink-0 text-[13px] font-medium">{amount}</span>
      <ChevronRight
        className="size-4 shrink-0 text-muted-foreground"
        aria-hidden="true"
      />
    </Link>
  );
}

function ActivityTab({ customerId }: { customerId: string }) {
  const activities = useScopedQuery(
    ["customers", "activities", customerId],
    () => customersService.activities(customerId),
  );
  return (
    <Card className="max-w-3xl">
      <CardHeader
        title="Activity"
        description="Changes, notes, documents and conversations for this customer"
      />
      <CardBody>
        {activities.isError ? (
          <ErrorState
            error={activities.error}
            onRetry={() => void activities.refetch()}
            compact
          />
        ) : (
          <ActivityTimeline
            events={activities.data?.items.map(activityToEvent)}
            loading={activities.isPending}
            empty="No activity recorded for this customer yet."
          />
        )}
      </CardBody>
    </Card>
  );
}
