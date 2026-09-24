"use client";

import { Plane, UserCheck, UserMinus, Users } from "lucide-react";
import { formatNumber, formatPercent } from "@/lib/format";
import { ChartCard } from "@/components/app/charts";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { reportsService } from "./service";
import { ExportMenu, ReportShell, ratio } from "./components";

export function EmployeesReport() {
  return (
    <ReportShell
      title="Employees"
      description="Headcount by status and department."
      permission="hr.read"
      area="employee reports"
    >
      <EmployeesContent />
    </ReportShell>
  );
}

function EmployeesContent() {
  const query = useScopedQuery(["reports", "employees"], () =>
    reportsService.employees(),
  );
  const data = query.data;
  const loading = query.isPending;

  if (query.isError)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );

  const departments = data
    ? [...data.by_department].sort((a, b) => b[1] - a[1])
    : undefined;

  return (
    <>
      <div className="mb-4 flex justify-end">
        <ExportMenu
          disabled={!data}
          exports={[
            {
              label: "Headcount by department",
              filename: "headcount-by-department",
              headers: ["Department", "Employees"],
              rows: () =>
                (departments ?? []).map(([name, count]) => [name, count]),
            },
          ]}
        />
      </div>

      <MetricGrid>
        <MetricCard
          label="Total employees"
          icon={Users}
          loading={loading}
          value={formatNumber(data?.total)}
          href="/hr/employees"
        />
        <MetricCard
          label="Active"
          icon={UserCheck}
          loading={loading}
          tone="success"
          value={formatNumber(data?.active)}
          detail={
            data
              ? `${formatPercent(ratio(data.active, data.total))} of total`
              : undefined
          }
        />
        <MetricCard
          label="On leave"
          icon={Plane}
          loading={loading}
          tone={(data?.on_leave ?? 0) > 0 ? "warning" : "default"}
          value={formatNumber(data?.on_leave)}
        />
        <MetricCard
          label="Terminated"
          icon={UserMinus}
          loading={loading}
          value={formatNumber(data?.terminated)}
          detail="Kept for records"
        />
      </MetricGrid>

      <ChartCard
        className="mt-4"
        title="Headcount by department"
        description="Employees per department"
        data={departments?.map(([name, count]) => ({
          department: name,
          employees: count,
        }))}
        loading={loading}
        xKey="department"
        xLabel="Department"
        series={[{ key: "employees", label: "Employees" }]}
        format={(v) => formatNumber(v)}
        kind="bar"
        height={260}
        emptyMessage="No employees recorded yet."
      />
    </>
  );
}
