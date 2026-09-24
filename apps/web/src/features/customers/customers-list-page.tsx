"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { Archive, Download, MessageCircle, Plus, Star, UserPlus, Users } from "lucide-react";
import { formatDate, formatDateTime, formatNumber, relativeTime } from "@/lib/format";
import { Avatar } from "@/components/ui/display";
import { Button } from "@/components/ui/button";
import { ModuleNav, PageHeader, PageShell, RequirePermission } from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { FilterBar, FilterSelect, SavedViews, SearchInput, type SavedView } from "@/components/app/filters";
import {
  BulkBar,
  ColumnsMenu,
  DataTable,
  Pagination,
  useColumnVisibility,
  type Column,
} from "@/components/app/data-table";
import { EmptyState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { ConfirmDialog } from "@/components/app/forms";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { Customer } from "@/features/business/types";
import { customersService } from "./service";
import { CUSTOMER_STATUS_OPTIONS, downloadCustomersCsv } from "./lib";
import { CustomerSourceBadge, TagList } from "./components/customer-badges";

const PAGE_SIZE = 25;

const VIEWS: SavedView[] = [
  { id: "all", name: "All", params: {}, builtIn: true },
  { id: "active", name: "Active", params: { status: "active" }, builtIn: true },
  { id: "whatsapp", name: "WhatsApp", params: { tag: "whatsapp" }, builtIn: true },
  { id: "vip", name: "VIP", params: { tag: "vip" }, builtIn: true },
  { id: "archived", name: "Archived", params: { status: "archived" }, builtIn: true },
];

function useCount(key: string, params: { status?: string; tag?: string }) {
  return useScopedQuery(["customers", "count", key], () => customersService.list({ ...params, pageSize: 1 }));
}

export function CustomersListPage() {
  return (
    <RequirePermission permission="customers.read" area="customers">
      <CustomersList />
    </RequirePermission>
  );
}

function CustomersList() {
  const { can } = useSession();
  const canWrite = can("customers.write");
  const [state, setState, resetState] = useUrlState({ search: "", status: "", tag: "", page: "1" });
  const page = Math.max(1, Number(state.page) || 1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmArchive, setConfirmArchive] = useState(false);

  const params = { search: state.search || undefined, status: state.status || undefined, tag: state.tag || undefined, page, pageSize: PAGE_SIZE };
  const list = useScopedQuery(["customers", "list", params], () => customersService.list(params), {
    placeholderData: (previous) => previous,
  });

  const active = useCount("active", { status: "active" });
  const whatsapp = useCount("whatsapp", { tag: "whatsapp" });
  const vip = useCount("vip", { tag: "vip" });
  const archived = useCount("archived", { status: "archived" });

  const rows = list.data?.items;
  const selectedRows = useMemo(() => (rows ?? []).filter((r) => selected.has(r.id)), [rows, selected]);
  const archivable = selectedRows.filter((r) => r.status === "active");

  const tagOptions = useMemo(() => {
    const tags = new Set<string>();
    rows?.forEach((r) => r.tags.forEach((t) => tags.add(t)));
    if (state.tag) tags.add(state.tag);
    return [...tags].sort().map((t) => ({ value: t, label: t }));
  }, [rows, state.tag]);

  const archive = useScopedMutation(
    async (ids: string[]) => {
      for (const id of ids) await customersService.setStatus(id, "archived");
      return ids.length;
    },
    {
      invalidate: [["customers"]],
      success: (count) => `Archived ${count === 1 ? "1 customer" : `${count} customers`}`,
      error: "Some customers couldn't be archived. Refresh and try again.",
      onSuccess: () => {
        setSelected(new Set());
        setConfirmArchive(false);
      },
    },
  );

  const columns: Column<Customer>[] = useMemo(
    () => [
      {
        key: "name",
        header: "Customer",
        cell: (c) => (
          <div className="flex min-w-0 items-center gap-2.5">
            <Avatar name={c.name} size="sm" />
            <div className="min-w-0">
              <Link href={`/customers/${c.id}`} className="block truncate font-medium text-foreground hover:underline">
                {c.name}
              </Link>
              <p className="truncate text-xs text-muted-foreground">{c.email ?? (c.status === "archived" ? "Archived" : "No email")}</p>
            </div>
            {c.status === "archived" && <StatusBadge status="archived" className="ml-1 hidden sm:inline-flex" />}
          </div>
        ),
      },
      {
        key: "phone",
        header: "Phone",
        hideBelow: "md",
        cell: (c) => <span className="tabular whitespace-nowrap">{c.phone ?? <span className="text-muted-foreground">—</span>}</span>,
      },
      {
        key: "company",
        header: "Company",
        hideBelow: "lg",
        optional: true,
        cell: (c) => <span className="block max-w-48 truncate">{c.company ?? <span className="text-muted-foreground">—</span>}</span>,
      },
      { key: "tags", header: "Tags", hideBelow: "lg", optional: true, cell: (c) => <TagList tags={c.tags} /> },
      { key: "source", header: "Source", hideBelow: "md", optional: true, cell: (c) => <CustomerSourceBadge source={c.source} /> },
      {
        key: "last_contacted",
        header: "Last contacted",
        hideBelow: "xl",
        optional: true,
        cell: (c) =>
          c.last_contacted_at ? (
            <time dateTime={c.last_contacted_at} title={formatDateTime(c.last_contacted_at)} className="whitespace-nowrap text-muted-foreground">
              {relativeTime(c.last_contacted_at)}
            </time>
          ) : (
            <span className="text-muted-foreground">Never</span>
          ),
      },
      {
        key: "created",
        header: "Created",
        hideBelow: "xl",
        optional: true,
        cell: (c) => <span className="tabular whitespace-nowrap text-muted-foreground">{formatDate(c.created_at)}</span>,
      },
    ],
    [],
  );
  const { hidden, toggle } = useColumnVisibility("customers", columns);

  const onSearch = useCallback((value: string) => setState({ search: value }), [setState]);
  const filtersActive = [state.search, state.status, state.tag].filter(Boolean).length;
  const current = { search: state.search, status: state.status, tag: state.tag };

  const empty = filtersActive ? (
    <EmptyState
      icon={Users}
      title="No customers match these filters"
      description="Try a different search, or clear filters to see everyone."
      action={
        <Button variant="secondary" size="sm" onClick={resetState}>
          Clear filters
        </Button>
      }
    />
  ) : (
    <EmptyState
      icon={Users}
      title="No customers yet"
      description="Add your first customer, or connect WhatsApp so PI adds new contacts automatically."
      action={
        canWrite ? (
          <Button size="sm" asChild>
            <Link href="/customers/new">
              <UserPlus /> Add customer
            </Link>
          </Button>
        ) : undefined
      }
    />
  );

  return (
    <PageShell>
      <PageHeader
        title="Customers"
        description="Everyone you sell to, with their orders, quotes, invoices and WhatsApp conversations in one place."
        actions={
          canWrite && (
            <Button asChild>
              <Link href="/customers/new">
                <Plus /> Add customer
              </Link>
            </Button>
          )
        }
      />
      <ModuleNav moduleKey="customers" />

      <MetricGrid className="mb-5 xl:grid-cols-4">
        <MetricCard label="Active customers" icon={Users} loading={active.isPending} value={active.data ? formatNumber(active.data.total) : "—"} href="/customers?status=active" />
        <MetricCard label="From WhatsApp" icon={MessageCircle} loading={whatsapp.isPending} value={whatsapp.data ? formatNumber(whatsapp.data.total) : "—"} detail="Tagged whatsapp" href="/customers?tag=whatsapp" />
        <MetricCard label="VIP" icon={Star} loading={vip.isPending} value={vip.data ? formatNumber(vip.data.total) : "—"} detail="Tagged vip" href="/customers?tag=vip" />
        <MetricCard label="Archived" icon={Archive} loading={archived.isPending} value={archived.data ? formatNumber(archived.data.total) : "—"} href="/customers?status=archived" />
      </MetricGrid>

      <SavedViews
        tableId="customers"
        views={VIEWS}
        current={current}
        onApply={(p) => {
          setSelected(new Set());
          setState({ search: p.search ?? "", status: p.status ?? "", tag: p.tag ?? "" });
        }}
      />

      <FilterBar
        activeCount={filtersActive}
        onClear={resetState}
        actions={<ColumnsMenu columns={columns} hidden={hidden} onToggle={toggle} />}
      >
        <SearchInput value={state.search} onChange={onSearch} placeholder="Search name, phone, email, company…" className="w-full md:w-72" />
        <FilterSelect label="Status" value={state.status} options={CUSTOMER_STATUS_OPTIONS} onChange={(v) => setState({ status: v })} />
        <FilterSelect label="Tag" value={state.tag} options={tagOptions} onChange={(v) => setState({ tag: v })} />
      </FilterBar>

      <DataTable
        caption="Customers"
        columns={columns}
        rows={rows}
        getRowId={(c) => c.id}
        loading={list.isPending}
        error={list.error}
        onRetry={() => void list.refetch()}
        empty={empty}
        rowHref={(c) => `/customers/${c.id}`}
        selectable
        selected={selected}
        onSelectedChange={setSelected}
        hiddenColumns={hidden}
        rowClassName={(c) => (c.status === "archived" ? "text-muted-foreground" : undefined)}
      />
      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={list.data?.total ?? 0}
        onPage={(p) => {
          setSelected(new Set());
          setState({ page: String(p) });
        }}
      />

      <BulkBar count={selectedRows.length} onClear={() => setSelected(new Set())}>
        <Button variant="ghost" size="sm" onClick={() => downloadCustomersCsv(selectedRows)}>
          <Download /> Export CSV
        </Button>
        {canWrite && (
          <Button variant="ghost" size="sm" onClick={() => setConfirmArchive(true)} disabled={!archivable.length}>
            <Archive /> Archive
          </Button>
        )}
      </BulkBar>

      <ConfirmDialog
        open={confirmArchive}
        onOpenChange={(open) => !archive.isPending && setConfirmArchive(open)}
        title={`Archive ${archivable.length === 1 ? "1 customer" : `${archivable.length} customers`}?`}
        description="Archived customers stay on record and can be restored at any time."
        consequences={[
          "They're hidden from the Active view and customer pickers.",
          "Existing orders, quotes, invoices and conversations are kept.",
          ...(selectedRows.length > archivable.length
            ? [`${selectedRows.length - archivable.length} selected customer(s) are already archived and will be skipped.`]
            : []),
        ]}
        confirmLabel="Archive"
        destructive
        loading={archive.isPending}
        onConfirm={() => archive.mutate(archivable.map((c) => c.id))}
      />
    </PageShell>
  );
}
