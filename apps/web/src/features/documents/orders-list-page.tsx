"use client";

import Link from "next/link";
import { Plus, SearchX, ShoppingCart } from "lucide-react";
import { formatDate, formatMoney, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  ColumnsMenu,
  DataTable,
  Pagination,
  useColumnVisibility,
  type Column,
} from "@/components/app/data-table";
import {
  FilterBar,
  FilterSelect,
  SavedViews,
  SearchInput,
  type SavedView,
} from "@/components/app/filters";
import { EmptyState } from "@/components/app/states";
import { StatusBadge, statusLabel } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { Order } from "@/features/business/types";
import { documentsService } from "./service";
import { SourceBadge } from "./badges";

const PAGE_SIZE = 25;
const STATUSES: Order["status"][] = [
  "draft",
  "confirmed",
  "processing",
  "shipped",
  "delivered",
  "cancelled",
];

const VIEWS: SavedView[] = [
  { id: "all", name: "All", params: {}, builtIn: true },
  ...STATUSES.map((s) => ({
    id: s,
    name: s === "draft" ? "Drafts" : statusLabel(s),
    params: { status: s },
    builtIn: true,
  })),
];

const COLUMNS: Column<Order>[] = [
  {
    key: "number",
    header: "Number",
    cell: (o) => (
      <Link
        href={`/orders/${o.id}`}
        className="font-mono text-[12.5px] font-medium hover:underline"
      >
        {o.number}
      </Link>
    ),
  },
  {
    key: "customer",
    header: "Customer",
    cell: (o) => (
      <span className="block max-w-56 truncate font-medium">
        {o.customer_name ?? "Unknown customer"}
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    cell: (o) => <StatusBadge status={o.status} />,
  },
  {
    key: "source",
    header: "Source",
    cell: (o) => <SourceBadge source={o.source} />,
    hideBelow: "lg",
    optional: true,
  },
  {
    key: "total",
    header: "Total",
    align: "right",
    cell: (o) => (
      <span className="tabular font-medium">
        {formatMoney(o.total, o.currency)}
      </span>
    ),
  },
  {
    key: "created",
    header: "Created",
    cell: (o) => (
      <time
        dateTime={o.created_at}
        title={formatDate(o.created_at)}
        className="text-muted-foreground"
      >
        {relativeTime(o.created_at)}
      </time>
    ),
    hideBelow: "sm",
    optional: true,
  },
  {
    key: "created_by",
    header: "Created by",
    cell: (o) => (
      <span className="text-muted-foreground">{o.created_by_label}</span>
    ),
    hideBelow: "xl",
    optional: true,
  },
];

export function OrdersListPage() {
  return (
    <RequirePermission permission="orders.read" area="orders">
      <OrdersList />
    </RequirePermission>
  );
}

function OrdersList() {
  const { can } = useSession();
  const [state, set, reset] = useUrlState({
    search: "",
    status: "",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const { hidden, toggle } = useColumnVisibility("orders", COLUMNS);
  const query = useScopedQuery(["orders", "list", state], () =>
    documentsService.orders({
      page,
      pageSize: PAGE_SIZE,
      search: state.search || undefined,
      status: state.status || undefined,
    }),
  );
  const filtered = Boolean(state.search || state.status);
  const canWrite = can("orders.write");

  return (
    <PageShell>
      <PageHeader
        title="Orders"
        description="Draft, confirm and fulfil customer orders. Confirming deducts stock and can issue the invoice."
        actions={
          canWrite && (
            <Button asChild>
              <Link href="/orders/new">
                <Plus /> Create order
              </Link>
            </Button>
          )
        }
      />
      <ModuleNav moduleKey="orders" />
      <SavedViews
        tableId="orders"
        views={VIEWS}
        current={{ search: state.search, status: state.status }}
        onApply={(params) =>
          set({ search: params.search ?? "", status: params.status ?? "" })
        }
      />
      <FilterBar
        activeCount={(state.search ? 1 : 0) + (state.status ? 1 : 0)}
        onClear={reset}
        actions={
          <ColumnsMenu columns={COLUMNS} hidden={hidden} onToggle={toggle} />
        }
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
        getRowId={(o) => o.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        rowHref={(o) => `/orders/${o.id}`}
        hiddenColumns={hidden}
        caption="Orders"
        empty={
          filtered ? (
            <EmptyState
              icon={SearchX}
              title="No orders match these filters"
              description="Try a different number or customer name, or clear the filters."
              action={
                <Button variant="secondary" size="sm" onClick={reset}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={ShoppingCart}
              title="No orders yet"
              description="Create an order from your catalog, or convert an accepted quote."
              action={
                canWrite && (
                  <Button size="sm" asChild>
                    <Link href="/orders/new">
                      <Plus /> Create order
                    </Link>
                  </Button>
                )
              }
              secondary={
                can("quotes.read") && (
                  <Button size="sm" variant="secondary" asChild>
                    <Link href="/quotes?status=accepted">Accepted quotes</Link>
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
