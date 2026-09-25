"use client";

import Link from "next/link";
import {
  LayoutGrid,
  Link2,
  SearchX,
  Table2,
  UserPlus,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Avatar,
  Card,
  SegmentedList,
  SegmentedTrigger,
  Skeleton,
  Tabs,
} from "@/components/ui/display";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { FilterBar, FilterSelect, SearchInput } from "@/components/app/filters";
import { EmptyState, ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { adminService } from "@/features/admin/service";
import type { Employee } from "@/features/business/types";
import { formatDay } from "@/features/billing/utils";
import { hrService } from "./service";
import { EMPLOYEE_STATUSES, employmentLabel } from "./utils";

const PAGE_SIZE = 24;

const COLUMNS: Column<Employee>[] = [
  {
    key: "name",
    header: "Name",
    cell: (e) => (
      <Link
        href={`/hr/employees/${e.id}`}
        className="flex min-w-0 items-center gap-2.5"
      >
        <Avatar name={e.full_name} size="sm" />
        <span className="min-w-0">
          <span className="block truncate font-medium hover:underline">
            {e.full_name}
          </span>
          {e.email && (
            <span className="block truncate text-xs text-muted-foreground">
              {e.email}
            </span>
          )}
        </span>
      </Link>
    ),
  },
  {
    key: "job_title",
    header: "Job title",
    cell: (e) => <span className="block max-w-48 truncate">{e.job_title}</span>,
    hideBelow: "sm",
  },
  {
    key: "department",
    header: "Department",
    cell: (e) =>
      e.department_name ?? <span className="text-muted-foreground">—</span>,
    hideBelow: "md",
  },
  {
    key: "type",
    header: "Type",
    cell: (e) => employmentLabel(e.employment_type),
    hideBelow: "lg",
  },
  {
    key: "status",
    header: "Status",
    cell: (e) => <StatusBadge status={e.status} />,
  },
  {
    key: "hire_date",
    header: "Hire date",
    cell: (e) => (
      <span className="tabular whitespace-nowrap">
        {formatDay(e.hire_date)}
      </span>
    ),
    hideBelow: "lg",
  },
];

export function EmployeesPage() {
  return (
    <RequirePermission permission="hr.read" area="the employee directory">
      <EmployeeDirectory />
    </RequirePermission>
  );
}

function EmployeeDirectory() {
  const { can } = useSession();
  const canWrite = can("hr.write");
  const [state, setState, reset] = useUrlState({
    search: "",
    status: "",
    department: "",
    view: "table",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const view = state.view === "cards" ? "cards" : "table";
  const params = {
    page,
    pageSize: PAGE_SIZE,
    search: state.search || undefined,
    status: state.status || undefined,
    departmentId: state.department || undefined,
  };
  const query = useScopedQuery(
    ["employees", params],
    () => hrService.employees(params),
    {
      placeholderData: (previous) => previous,
    },
  );
  const departments = useScopedQuery(
    ["departments"],
    () => adminService.departments(),
    { staleTime: 60_000 },
  );
  const activeCount = [state.search, state.status, state.department].filter(
    Boolean,
  ).length;

  const empty =
    activeCount > 0 ? (
      <EmptyState
        icon={SearchX}
        title="No one matches these filters"
        description="Try another name, status or department."
        action={
          <Button variant="secondary" size="sm" onClick={reset}>
            Clear filters
          </Button>
        }
      />
    ) : (
      <EmptyState
        icon={Users}
        title="Your directory is empty"
        description="Add your team to track roles, departments and employment status in one place."
        action={
          canWrite ? (
            <Button size="sm" asChild>
              <Link href="/hr/employees/new">
                <UserPlus /> Add employee
              </Link>
            </Button>
          ) : undefined
        }
      />
    );

  return (
    <PageShell>
      <PageHeader
        title="Employees"
        description="Everyone on the team, their role and where they sit."
        actions={
          canWrite ? (
            <>
              <Button variant="secondary" asChild>
                <Link href="/hr/onboarding?create=1">
                  <Link2 /> Send onboarding link
                </Link>
              </Button>
              <Button asChild>
                <Link href="/hr/employees/new">
                  <UserPlus /> Add employee
                </Link>
              </Button>
            </>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="hr" />

      <FilterBar
        activeCount={activeCount}
        onClear={() => setState({ search: "", status: "", department: "" })}
        actions={
          <Tabs
            value={view}
            onValueChange={(v) => setState({ view: v }, { resetPage: false })}
          >
            <SegmentedList aria-label="Layout">
              <SegmentedTrigger value="table" aria-label="Table view">
                <Table2 /> <span className="hidden sm:inline">Table</span>
              </SegmentedTrigger>
              <SegmentedTrigger value="cards" aria-label="Card view">
                <LayoutGrid /> <span className="hidden sm:inline">Cards</span>
              </SegmentedTrigger>
            </SegmentedList>
          </Tabs>
        }
      >
        <SearchInput
          value={state.search}
          onChange={(search) => setState({ search })}
          placeholder="Search name or job title…"
          className="w-full md:w-72"
        />
        <FilterSelect
          label="Status"
          value={state.status}
          options={EMPLOYEE_STATUSES}
          onChange={(status) => setState({ status })}
        />
        <FilterSelect
          label="Department"
          value={state.department}
          options={(departments.data ?? []).map((d) => ({
            value: d.id,
            label: d.name,
          }))}
          onChange={(department) => setState({ department })}
        />
      </FilterBar>

      {view === "table" ? (
        <DataTable
          columns={COLUMNS}
          rows={query.data?.items}
          getRowId={(e) => e.id}
          loading={query.isPending}
          error={query.error}
          onRetry={() => void query.refetch()}
          rowHref={(e) => `/hr/employees/${e.id}`}
          caption="Employees"
          empty={empty}
        />
      ) : query.isError ? (
        <Card>
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
            compact
          />
        </Card>
      ) : query.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-[132px] rounded-xl" />
          ))}
        </div>
      ) : query.data.items.length === 0 ? (
        <Card>{empty}</Card>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {query.data.items.map((e) => (
            <li key={e.id}>
              <Link
                href={`/hr/employees/${e.id}`}
                className="flex h-full flex-col rounded-xl border border-border bg-surface p-4 shadow-sm transition-colors hover:border-border-strong focus-visible:outline-2 focus-visible:outline-ring"
              >
                <div className="flex items-start gap-3">
                  <Avatar name={e.full_name} size="lg" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13.5px] font-semibold">
                      {e.full_name}
                    </p>
                    <p className="truncate text-[13px] text-muted-foreground">
                      {e.job_title}
                    </p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <StatusBadge status={e.status} />
                  <span className="text-xs text-muted-foreground">
                    {employmentLabel(e.employment_type)}
                  </span>
                </div>
                <p className="mt-auto truncate pt-3 text-xs text-muted-foreground">
                  {e.department_name ?? "No department"} · Since{" "}
                  {formatDay(e.hire_date, "MMM yyyy")}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {query.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={query.data.total}
          onPage={(next) =>
            setState({ page: String(next) }, { resetPage: false })
          }
        />
      )}
    </PageShell>
  );
}
