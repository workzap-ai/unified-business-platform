"use client";

import Link from "next/link";
import {
  CalendarOff,
  UserCheck,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react";
import { formatNumber, pluralize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Avatar, Card, CardHeader, Skeleton } from "@/components/ui/display";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { DistributionBar } from "@/components/app/charts";
import { ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import type { Employee } from "@/features/business/types";
import { daysFromToday, formatDay } from "@/features/billing/utils";
import { hrService } from "./service";
import { ROSTER_PAGE_SIZE } from "./utils";

export function HROverviewPage() {
  return (
    <RequirePermission permission="hr.read" area="HR">
      <HROverview />
    </RequirePermission>
  );
}

function HROverview() {
  const { can } = useSession();
  const headcount = useScopedQuery(["hr", "headcount"], () =>
    hrService.headcount(),
  );
  const roster = useScopedQuery(
    ["employees", { pageSize: ROSTER_PAGE_SIZE }],
    () => hrService.employees({ pageSize: ROSTER_PAGE_SIZE }),
  );
  const onLeave = useScopedQuery(
    ["employees", { status: "on_leave", pageSize: 10 }],
    () => hrService.employees({ status: "on_leave", pageSize: 10 }),
  );
  const data = headcount.data;
  const loading = headcount.isPending;
  const recentHires = roster.data
    ? [...roster.data.items]
        .filter((e) => e.status !== "terminated")
        .sort((a, b) => b.hire_date.localeCompare(a.hire_date))
        .slice(0, 6)
    : undefined;
  const departments = data
    ? [...data.by_department].sort((a, b) => b[1] - a[1])
    : [];
  const topDepartments =
    departments.length > 5
      ? [
          ...departments.slice(0, 4),
          [
            "Other departments",
            departments.slice(4).reduce((sum, d) => sum + d[1], 0),
          ] as [string, number],
        ]
      : departments;

  return (
    <PageShell>
      <PageHeader
        title="People"
        description="Headcount, departments and who's in or out right now."
        actions={
          can("hr.write") ? (
            <Button asChild>
              <Link href="/hr/employees/new">
                <UserPlus /> Add employee
              </Link>
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="hr" />

      {headcount.isError ? (
        <Card className="mb-4">
          <ErrorState
            error={headcount.error}
            onRetry={() => void headcount.refetch()}
            compact
          />
        </Card>
      ) : (
        <MetricGrid>
          <MetricCard
            label="Active"
            icon={UserCheck}
            loading={loading}
            tone="success"
            value={formatNumber(data?.active ?? 0)}
            href="/hr/employees?status=active"
            detail="Working now"
          />
          <MetricCard
            label="On leave"
            icon={CalendarOff}
            loading={loading}
            tone={data && data.on_leave > 0 ? "warning" : "default"}
            value={formatNumber(data?.on_leave ?? 0)}
            href="/hr/employees?status=on_leave"
            detail="Temporarily away"
          />
          <MetricCard
            label="Terminated"
            icon={UserMinus}
            loading={loading}
            value={formatNumber(data?.terminated ?? 0)}
            href="/hr/employees?status=terminated"
            detail="Former employees"
          />
          <MetricCard
            label="Total records"
            icon={Users}
            loading={loading}
            value={formatNumber(data?.total ?? 0)}
            href="/hr/employees"
            detail="Everyone in the directory"
          />
        </MetricGrid>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader
            title="By department"
            description="Current staff, excluding terminated"
            actions={
              <Link
                href="/hr/departments"
                className="text-xs font-medium text-primary hover:underline"
              >
                Departments
              </Link>
            }
          />
          <div className="px-4 pb-4">
            {loading ? (
              <div className="space-y-3">
                <Skeleton className="h-2.5 rounded-full" />
                <Skeleton className="h-16" />
              </div>
            ) : topDepartments.length === 0 ? (
              <p className="py-3 text-[13px] text-muted-foreground">
                No current employees yet.
              </p>
            ) : (
              <DistributionBar
                segments={topDepartments.map(([name, count]) => ({
                  key: name,
                  label: name,
                  value: count,
                }))}
                format={(v) => formatNumber(v)}
              />
            )}
          </div>
        </Card>

        <PeopleCard
          title="Recent hires"
          description="Newest start dates first"
          people={recentHires}
          loading={roster.isPending}
          error={roster.error}
          onRetry={() => void roster.refetch()}
          empty="No one has been added yet."
          meta={(e) => {
            const days = daysFromToday(e.hire_date);
            return days !== null && days > 0
              ? `Starts ${formatDay(e.hire_date)}`
              : `Joined ${formatDay(e.hire_date)}`;
          }}
        />

        <PeopleCard
          title="On leave"
          description={
            onLeave.data
              ? pluralize(onLeave.data.total, "person", "people")
              : undefined
          }
          people={onLeave.data?.items}
          loading={onLeave.isPending}
          error={onLeave.error}
          onRetry={() => void onLeave.refetch()}
          empty="Everyone is in. No one is on leave."
          viewAllHref={
            onLeave.data && onLeave.data.total > 10
              ? "/hr/employees?status=on_leave"
              : undefined
          }
          meta={(e) => e.department_name ?? "No department"}
        />
      </div>
    </PageShell>
  );
}

function PeopleCard({
  title,
  description,
  people,
  loading,
  error,
  onRetry,
  empty,
  meta,
  viewAllHref,
}: {
  title: string;
  description?: string;
  people: Employee[] | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  empty: string;
  meta: (e: Employee) => string;
  viewAllHref?: string;
}) {
  return (
    <Card>
      <CardHeader
        title={title}
        description={description}
        actions={
          viewAllHref ? (
            <Link
              href={viewAllHref}
              className="text-xs font-medium text-primary hover:underline"
            >
              View all
            </Link>
          ) : undefined
        }
      />
      <div className="px-2 pb-2">
        {loading ? (
          <div className="space-y-2 px-2 pb-2">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={onRetry} compact />
        ) : !people || people.length === 0 ? (
          <p className="px-2 pt-1 pb-3 text-[13px] text-muted-foreground">
            {empty}
          </p>
        ) : (
          <ul>
            {people.map((e) => (
              <li key={e.id}>
                <Link
                  href={`/hr/employees/${e.id}`}
                  className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-muted"
                >
                  <Avatar name={e.full_name} size="md" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium">
                      {e.full_name}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {e.job_title}
                    </span>
                  </span>
                  <span className="shrink-0 text-right text-xs text-muted-foreground">
                    {meta(e)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
