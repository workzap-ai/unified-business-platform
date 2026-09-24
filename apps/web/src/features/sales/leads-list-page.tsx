"use client";

import { useCallback, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Target } from "lucide-react";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  relativeTime,
} from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  FilterBar,
  FilterSelect,
  SavedViews,
  SearchInput,
  type SavedView,
} from "@/components/app/filters";
import {
  ColumnsMenu,
  DataTable,
  Pagination,
  useColumnVisibility,
  type Column,
} from "@/components/app/data-table";
import { EmptyState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { Lead } from "@/features/business/types";
import { salesService } from "./service";
import { LeadSourceBadge, STAGE_LABELS, STAGES } from "./lib";
import { LeadFormDialog } from "./components/lead-form-dialog";

const PAGE_SIZE = 25;

const VIEWS: SavedView[] = [
  { id: "all", name: "All", params: {}, builtIn: true },
  ...STAGES.map((stage) => ({
    id: stage,
    name: STAGE_LABELS[stage],
    params: { stage },
    builtIn: true,
  })),
];

const STAGE_OPTIONS = STAGES.map((stage) => ({
  value: stage,
  label: STAGE_LABELS[stage],
}));

export function LeadsListPage() {
  return (
    <RequirePermission permission="sales.read" area="leads">
      <LeadsList />
    </RequirePermission>
  );
}

function LeadsList() {
  const router = useRouter();
  const { can } = useSession();
  const canWrite = can("sales.write");
  const [state, setState, resetState] = useUrlState({
    search: "",
    stage: "",
    page: "1",
    new: "",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    search: state.search || undefined,
    stage: state.stage || undefined,
    page,
    pageSize: PAGE_SIZE,
  };
  const list = useScopedQuery(
    ["leads", "list", params],
    () => salesService.leads(params),
    { placeholderData: (p) => p },
  );

  const columns: Column<Lead>[] = useMemo(
    () => [
      {
        key: "title",
        header: "Lead",
        cell: (l) => (
          <div className="min-w-0">
            <Link
              href={`/sales/leads/${l.id}`}
              className="block max-w-[28rem] truncate font-medium hover:underline"
            >
              {l.title}
            </Link>
            <p className="truncate text-xs text-muted-foreground">
              {l.customer_name ?? "No customer linked"}
            </p>
          </div>
        ),
      },
      {
        key: "stage",
        header: "Stage",
        cell: (l) => <StatusBadge status={l.stage} />,
      },
      {
        key: "value",
        header: "Est. value",
        align: "right",
        hideBelow: "sm",
        cell: (l) => (
          <span className="tabular whitespace-nowrap">
            {l.estimated_value ? (
              formatMoney(l.estimated_value, l.currency)
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </span>
        ),
      },
      {
        key: "source",
        header: "Source",
        hideBelow: "md",
        optional: true,
        cell: (l) => <LeadSourceBadge source={l.source} compact />,
      },
      {
        key: "missing",
        header: "Missing info",
        hideBelow: "xl",
        optional: true,
        cell: (l) =>
          l.missing_information.length ? (
            <span className="text-xs font-medium text-warning">
              {l.missing_information.length} item
              {l.missing_information.length === 1 ? "" : "s"}
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        key: "updated",
        header: "Updated",
        hideBelow: "lg",
        optional: true,
        cell: (l) => (
          <time
            dateTime={l.updated_at}
            title={formatDateTime(l.updated_at)}
            className="whitespace-nowrap text-muted-foreground"
          >
            {relativeTime(l.updated_at)}
          </time>
        ),
      },
      {
        key: "created",
        header: "Created",
        hideBelow: "xl",
        optional: true,
        defaultHidden: true,
        cell: (l) => (
          <span className="tabular whitespace-nowrap text-muted-foreground">
            {formatDate(l.created_at)}
          </span>
        ),
      },
    ],
    [],
  );
  const { hidden, toggle } = useColumnVisibility("leads", columns);
  const onSearch = useCallback(
    (value: string) => setState({ search: value }),
    [setState],
  );
  const filtersActive = [state.search, state.stage].filter(Boolean).length;
  const creating = canWrite && state.new === "1";

  return (
    <PageShell>
      <PageHeader
        title="Leads"
        description="Potential sales from your team, referrals, your website and PI's WhatsApp conversations."
        actions={
          canWrite && (
            <Button
              onClick={() => setState({ new: "1" }, { resetPage: false })}
            >
              <Plus /> New lead
            </Button>
          )
        }
      />
      <ModuleNav moduleKey="sales" />

      <SavedViews
        tableId="leads"
        views={VIEWS}
        current={{ search: state.search, stage: state.stage }}
        onApply={(p) =>
          setState({ search: p.search ?? "", stage: p.stage ?? "" })
        }
      />
      <FilterBar
        activeCount={filtersActive}
        onClear={resetState}
        actions={
          <ColumnsMenu columns={columns} hidden={hidden} onToggle={toggle} />
        }
      >
        <SearchInput
          value={state.search}
          onChange={onSearch}
          placeholder="Search leads or customers…"
          className="w-full md:w-72"
        />
        <FilterSelect
          label="Stage"
          value={state.stage}
          options={STAGE_OPTIONS}
          onChange={(v) => setState({ stage: v })}
        />
      </FilterBar>

      <DataTable
        caption="Leads"
        columns={columns}
        rows={list.data?.items}
        getRowId={(l) => l.id}
        loading={list.isPending}
        error={list.error}
        onRetry={() => void list.refetch()}
        rowHref={(l) => `/sales/leads/${l.id}`}
        hiddenColumns={hidden}
        empty={
          filtersActive ? (
            <EmptyState
              icon={Target}
              title="No leads match these filters"
              description="Try another stage or search term."
              action={
                <Button size="sm" variant="secondary" onClick={resetState}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Target}
              title="No leads yet"
              description="Track potential sales here. When PI is connected, WhatsApp enquiries become leads automatically."
              action={
                canWrite ? (
                  <Button
                    size="sm"
                    onClick={() => setState({ new: "1" }, { resetPage: false })}
                  >
                    <Plus /> New lead
                  </Button>
                ) : undefined
              }
            />
          )
        }
      />
      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={list.data?.total ?? 0}
        onPage={(p) => setState({ page: String(p) })}
      />

      {canWrite && (
        <LeadFormDialog
          open={creating}
          onOpenChange={(open) =>
            setState({ new: open ? "1" : "" }, { resetPage: false })
          }
          onCreated={(lead) => router.push(`/sales/leads/${lead.id}`)}
        />
      )}
    </PageShell>
  );
}
