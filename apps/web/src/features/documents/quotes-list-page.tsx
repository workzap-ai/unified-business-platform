"use client";

import Link from "next/link";
import { FileText, Plus, SearchX } from "lucide-react";
import { formatDate, formatMoney, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ModuleNav, PageHeader, PageShell, RequirePermission } from "@/components/app/page";
import { ColumnsMenu, DataTable, Pagination, useColumnVisibility, type Column } from "@/components/app/data-table";
import { FilterBar, FilterSelect, SavedViews, SearchInput, type SavedView } from "@/components/app/filters";
import { EmptyState } from "@/components/app/states";
import { StatusBadge, statusLabel } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { Quote } from "@/features/business/types";
import { documentsService } from "./service";
import { SourceBadge, ValidUntil } from "./badges";

const PAGE_SIZE = 25;
const STATUSES: Quote["status"][] = ["draft", "pending_approval", "approved", "sent", "accepted", "rejected", "expired", "cancelled"];

const VIEWS: SavedView[] = [
  { id: "all", name: "All", params: {}, builtIn: true },
  { id: "drafts", name: "Drafts", params: { status: "draft" }, builtIn: true },
  { id: "approval", name: "Needs approval", params: { status: "pending_approval" }, builtIn: true },
  { id: "sent", name: "Sent", params: { status: "sent" }, builtIn: true },
  { id: "accepted", name: "Accepted", params: { status: "accepted" }, builtIn: true },
];

const COLUMNS: Column<Quote>[] = [
  {
    key: "number",
    header: "Number",
    cell: (q) => (
      <Link href={`/quotes/${q.id}`} className="font-mono text-[12.5px] font-medium hover:underline">
        {q.number}
      </Link>
    ),
  },
  {
    key: "customer",
    header: "Customer",
    cell: (q) => <span className="block max-w-56 truncate font-medium">{q.customer_name ?? "Unknown customer"}</span>,
  },
  { key: "status", header: "Status", cell: (q) => <StatusBadge status={q.status} /> },
  { key: "source", header: "Source", cell: (q) => <SourceBadge source={q.source} />, hideBelow: "lg", optional: true },
  {
    key: "total",
    header: "Total",
    align: "right",
    cell: (q) => <span className="tabular font-medium">{formatMoney(q.total, q.currency)}</span>,
  },
  { key: "valid_until", header: "Valid until", cell: (q) => <ValidUntil quote={q} />, hideBelow: "md", optional: true },
  {
    key: "created",
    header: "Created",
    cell: (q) => (
      <time dateTime={q.created_at} title={formatDate(q.created_at)} className="text-muted-foreground">
        {relativeTime(q.created_at)}
      </time>
    ),
    hideBelow: "sm",
    optional: true,
  },
];

export function QuotesListPage() {
  return (
    <RequirePermission permission="quotes.read" area="quotes">
      <QuotesList />
    </RequirePermission>
  );
}

function QuotesList() {
  const { can } = useSession();
  const [state, set, reset] = useUrlState({ search: "", status: "", page: "1" });
  const page = Math.max(1, Number(state.page) || 1);
  const { hidden, toggle } = useColumnVisibility("quotes", COLUMNS);
  const query = useScopedQuery(["quotes", "list", state], () =>
    documentsService.quotes({ page, pageSize: PAGE_SIZE, search: state.search || undefined, status: state.status || undefined }),
  );
  const filtered = Boolean(state.search || state.status);
  const canWrite = can("quotes.write");

  return (
    <PageShell>
      <PageHeader
        title="Quotes"
        description="Prepare, approve and send priced proposals, then turn accepted quotes into orders."
        actions={
          canWrite && (
            <Button asChild>
              <Link href="/quotes/new">
                <Plus /> Create quote
              </Link>
            </Button>
          )
        }
      />
      <ModuleNav moduleKey="quotes" />
      <SavedViews
        tableId="quotes"
        views={VIEWS}
        current={{ search: state.search, status: state.status }}
        onApply={(params) => set({ search: params.search ?? "", status: params.status ?? "" })}
      />
      <FilterBar
        activeCount={(state.search ? 1 : 0) + (state.status ? 1 : 0)}
        onClear={reset}
        actions={<ColumnsMenu columns={COLUMNS} hidden={hidden} onToggle={toggle} />}
      >
        <SearchInput
          value={state.search}
          onChange={(search) => set({ search })}
          placeholder="Search number or customer…"
          className="w-full sm:w-72"
        />
        <FilterSelect
          label="Status"
          value={state.status}
          options={STATUSES.map((s) => ({ value: s, label: statusLabel(s) }))}
          onChange={(status) => set({ status })}
        />
      </FilterBar>
      <DataTable
        columns={COLUMNS}
        rows={query.data?.items}
        getRowId={(q) => q.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        rowHref={(q) => `/quotes/${q.id}`}
        hiddenColumns={hidden}
        caption="Quotes"
        empty={
          filtered ? (
            <EmptyState
              icon={SearchX}
              title="No quotes match these filters"
              description="Try a different number or customer name, or clear the filters."
              action={
                <Button variant="secondary" size="sm" onClick={reset}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={FileText}
              title="No quotes yet"
              description="Build a quote from your catalog, send it to a customer, and convert it to an order once accepted."
              action={
                canWrite && (
                  <Button size="sm" asChild>
                    <Link href="/quotes/new">
                      <Plus /> Create quote
                    </Link>
                  </Button>
                )
              }
            />
          )
        }
      />
      {query.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={query.data.total}
          onPage={(next) => set({ page: String(next) }, { resetPage: false })}
        />
      )}
    </PageShell>
  );
}
