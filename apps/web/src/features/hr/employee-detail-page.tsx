"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  CalendarOff,
  Lock,
  Mail,
  Pencil,
  Phone,
  UserCheck,
  UserMinus,
} from "lucide-react";
import { formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Avatar, Card, CardHeader, Skeleton } from "@/components/ui/display";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PropertyList, RecordHeader } from "@/components/app/record";
import { ConfirmDialog } from "@/components/app/forms";
import { ErrorState, InlineError, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import { useSession } from "@/features/auth/session-provider";
import type { Employee, EmployeeInput } from "@/features/business/types";
import { daysFromToday, formatDay, todayISO } from "@/features/billing/utils";
import { hrService } from "./service";
import { PersonalDetailsCard } from "./personal-details-card";
import {
  CompensationFields,
  PersonFields,
  RoleFields,
  employeeDefaults,
  employeeFormSchema,
  toEmployeeInput,
  type EmployeeFormValues,
} from "./employee-fields";
import { ROSTER_PAGE_SIZE, employmentLabel } from "./utils";

type StatusChange = "on_leave" | "active" | "terminated";

export function EmployeeDetailPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="hr.read" area="employee records">
      <EmployeeDetail id={id} />
    </RequirePermission>
  );
}

function EmployeeDetail({ id }: { id: string }) {
  const { can } = useSession();
  const query = useScopedQuery(["employees", "detail", id], () =>
    hrService.employee(id),
  );
  const roster = useScopedQuery(
    ["employees", { pageSize: ROSTER_PAGE_SIZE }],
    () => hrService.employees({ pageSize: ROSTER_PAGE_SIZE }),
  );
  const employee = query.data;
  const [editing, setEditing] = useState(false);
  const [change, setChange] = useState<StatusChange | null>(null);

  useBreadcrumbs(employee ? [{ label: employee.full_name }] : [], {
    href: `/hr/employees/${id}`,
    kind: "employee",
  });

  const update = useScopedMutation(
    (input: Partial<EmployeeInput> & { termination_date?: string | null }) =>
      hrService.update(id, input),
    {
      invalidate: [["employees"], ["hr"]],
      success: (e) =>
        e.status === "terminated"
          ? `${e.full_name} marked as terminated`
          : e.status === "on_leave"
            ? `${e.full_name} is now on leave`
            : `${e.full_name} is active`,
      onSuccess: () => setChange(null),
    },
  );

  if (query.isPending) {
    return (
      <PageShell>
        <RecordHeader title="" loading />
        <div
          className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]"
          aria-busy="true"
          aria-label="Loading employee"
        >
          <Skeleton className="h-80 rounded-xl" />
          <Skeleton className="h-56 rounded-xl" />
        </div>
      </PageShell>
    );
  }
  if (query.isError || !employee) {
    return (
      <PageShell width="default">
        <Card>
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
          />
          <div className="-mt-8 pb-8 text-center">
            <Link
              href="/hr/employees"
              className="text-sm font-medium text-primary hover:underline"
            >
              Back to employees
            </Link>
          </div>
        </Card>
      </PageShell>
    );
  }

  const canWrite = can("hr.write");
  const people = roster.data?.items ?? [];
  const manager = employee.manager_id
    ? people.find((p) => p.id === employee.manager_id)
    : undefined;
  const reports = people.filter(
    (p) => p.manager_id === employee.id && p.status !== "terminated",
  );
  const startsIn = daysFromToday(employee.hire_date);

  const confirmCopy: Record<
    StatusChange,
    {
      title: string;
      label: string;
      consequences: string[];
      destructive?: boolean;
    }
  > = {
    on_leave: {
      title: `Mark ${employee.full_name} as on leave?`,
      label: "Mark on leave",
      consequences: [
        "They move from active to on-leave headcount.",
        "Their record, role and compensation stay unchanged.",
        "You can return them to active at any time.",
      ],
    },
    active: {
      title: `Return ${employee.full_name} to active?`,
      label: "Return to active",
      consequences: ["They count toward active headcount again."],
    },
    terminated: {
      title: `Terminate ${employee.full_name}?`,
      label: "Terminate",
      destructive: true,
      consequences: [
        `Their termination date is set to today (${formatDay(todayISO())}).`,
        "They leave active headcount and department counts.",
        reports.length
          ? `${reports.length} direct report${reports.length === 1 ? "" : "s"} will need a new manager.`
          : "The record stays in the directory for history.",
      ],
    },
  };

  return (
    <PageShell>
      <RecordHeader
        avatar={employee.full_name}
        title={employee.full_name}
        subtitle={[employee.job_title, employee.department_name]
          .filter(Boolean)
          .join(" · ")}
        status={<StatusBadge status={employee.status} />}
        meta={
          <>
            {employee.email && (
              <a
                href={`mailto:${employee.email}`}
                className="inline-flex items-center gap-1 hover:text-foreground"
              >
                <Mail className="size-3.5" aria-hidden="true" />{" "}
                {employee.email}
              </a>
            )}
            {employee.phone && (
              <a
                href={`tel:${employee.phone}`}
                className="inline-flex items-center gap-1 hover:text-foreground"
              >
                <Phone className="size-3.5" aria-hidden="true" />{" "}
                {employee.phone}
              </a>
            )}
            <span>{employmentLabel(employee.employment_type)}</span>
          </>
        }
        actions={
          canWrite ? (
            <>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
              {employee.status === "active" && (
                <Button
                  variant="secondary"
                  onClick={() => setChange("on_leave")}
                >
                  <CalendarOff /> Mark on leave
                </Button>
              )}
              {employee.status === "on_leave" && (
                <Button variant="secondary" onClick={() => setChange("active")}>
                  <UserCheck /> Return to active
                </Button>
              )}
              {employee.status !== "terminated" && (
                <Button
                  variant="danger-outline"
                  onClick={() => setChange("terminated")}
                >
                  <UserMinus /> Terminate
                </Button>
              )}
            </>
          ) : undefined
        }
      />

      {employee.status === "terminated" && (
        <Notice tone="neutral" title="Former employee" className="mb-4">
          Terminated on {formatDay(employee.termination_date)}. The record is
          kept for history.
        </Notice>
      )}
      {startsIn !== null &&
        startsIn > 0 &&
        employee.status !== "terminated" && (
          <Notice tone="info" title="Upcoming starter" className="mb-4">
            Starts on {formatDay(employee.hire_date)}, in {startsIn} day
            {startsIn === 1 ? "" : "s"}.
          </Notice>
        )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Employment" />
            <div className="px-4 pb-2">
              <PropertyList
                columns={2}
                items={[
                  { label: "Job title", value: employee.job_title },
                  { label: "Department", value: employee.department_name },
                  {
                    label: "Manager",
                    value: !employee.manager_id ? null : manager ? (
                      <Link
                        href={`/hr/employees/${manager.id}`}
                        className="text-primary hover:underline"
                      >
                        {manager.full_name}
                      </Link>
                    ) : roster.isPending ? (
                      <Skeleton className="ml-auto h-4 w-24" />
                    ) : (
                      <Link
                        href={`/hr/employees/${employee.manager_id}`}
                        className="text-primary hover:underline"
                      >
                        View manager
                      </Link>
                    ),
                  },
                  {
                    label: "Employment type",
                    value: employmentLabel(employee.employment_type),
                  },
                  { label: "Hire date", value: formatDay(employee.hire_date) },
                  {
                    label: "Termination date",
                    value: employee.termination_date
                      ? formatDay(employee.termination_date)
                      : null,
                  },
                ]}
              />
            </div>
          </Card>

          <Card>
            <CardHeader title="Contact" />
            <div className="px-4 pb-2">
              <PropertyList
                columns={2}
                items={[
                  {
                    label: "Email",
                    value: employee.email ? (
                      <a
                        href={`mailto:${employee.email}`}
                        className="text-primary hover:underline"
                      >
                        {employee.email}
                      </a>
                    ) : null,
                  },
                  {
                    label: "Phone",
                    value: employee.phone ? (
                      <a
                        href={`tel:${employee.phone}`}
                        className="text-primary hover:underline"
                      >
                        {employee.phone}
                      </a>
                    ) : null,
                  },
                ]}
              />
            </div>
          </Card>
          <PersonalDetailsCard employee={employee} />
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader title="Compensation" icon={<Lock />} />
            <div className="px-4 pb-4">
              {employee.sensitive_visible ? (
                employee.salary ? (
                  <>
                    <p className="tabular text-[22px] font-semibold tracking-tight">
                      {formatMoney(
                        employee.salary,
                        employee.salary_currency ?? "USD",
                      )}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Annual gross salary
                    </p>
                  </>
                ) : (
                  <p className="text-[13px] text-muted-foreground">
                    No salary recorded.{canWrite ? " Use Edit to add one." : ""}
                  </p>
                )
              ) : (
                <Notice tone="neutral" icon={Lock}>
                  Compensation is visible to HR with sensitive access.
                </Notice>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Direct reports"
              description={
                reports.length ? `${reports.length} people` : undefined
              }
            />
            <div className="px-2 pb-2">
              {roster.isPending ? (
                <div className="space-y-2 px-2 pb-2">
                  <Skeleton className="h-9" />
                  <Skeleton className="h-9" />
                </div>
              ) : reports.length === 0 ? (
                <p className="px-2 pt-1 pb-3 text-[13px] text-muted-foreground">
                  No one reports to them.
                </p>
              ) : (
                <ul>
                  {reports.map((r) => (
                    <li key={r.id}>
                      <Link
                        href={`/hr/employees/${r.id}`}
                        className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-surface-muted"
                      >
                        <Avatar name={r.full_name} size="sm" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">
                            {r.full_name}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {r.job_title}
                          </span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>
      </div>

      {canWrite && (
        <EditEmployeeDialog
          employee={employee}
          open={editing}
          onOpenChange={setEditing}
        />
      )}
      {change && (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setChange(null)}
          title={confirmCopy[change].title}
          consequences={confirmCopy[change].consequences}
          confirmLabel={confirmCopy[change].label}
          destructive={confirmCopy[change].destructive}
          loading={update.isPending}
          onConfirm={() =>
            update.mutate(
              change === "terminated"
                ? { status: "terminated", termination_date: todayISO() }
                : { status: change, termination_date: null },
            )
          }
        />
      )}
    </PageShell>
  );
}

function EditEmployeeDialog({
  employee,
  open,
  onOpenChange,
}: {
  employee: Employee;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        {open && (
          <EditEmployeeForm
            employee={employee}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function EditEmployeeForm({
  employee,
  onDone,
}: {
  employee: Employee;
  onDone: () => void;
}) {
  const { can } = useSession();
  const sensitive = employee.sensitive_visible && can("hr.sensitive");
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useForm<EmployeeFormValues>({
    resolver: zodResolver(employeeFormSchema),
    defaultValues: employeeDefaults(employee),
  });
  const save = useScopedMutation(
    (input: EmployeeInput) => hrService.update(employee.id, input),
    {
      invalidate: [["employees"], ["hr"]],
      success: "Employee updated",
      onSuccess: onDone,
    },
  );
  const saving = save.isPending;
  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    save.mutate(toEmployeeInput(values, sensitive), {
      onError: (e) =>
        setServerError(errorMessage(e, "The changes couldn't be saved.")),
    });
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex min-h-0 flex-col">
      <DialogHeader
        title={`Edit ${employee.full_name}`}
        description="Update contact details and role."
      />
      <DialogBody className="space-y-4">
        {serverError && <InlineError message={serverError} />}
        <PersonFields form={form} disabled={saving} idPrefix="edit" />
        <RoleFields
          form={form}
          disabled={saving}
          idPrefix="edit"
          employeeId={employee.id}
        />
        {sensitive ? (
          <div className="border-t border-border pt-4">
            <p className="mb-3 text-[13px] font-semibold">Compensation</p>
            <CompensationFields form={form} disabled={saving} idPrefix="edit" />
          </div>
        ) : (
          <Notice tone="neutral" icon={Lock}>
            Compensation is visible to HR with sensitive access and can&apos;t
            be changed here.
          </Notice>
        )}
      </DialogBody>
      <DialogFooter>
        <Button
          type="button"
          variant="secondary"
          onClick={onDone}
          disabled={saving}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          loading={saving}
          disabled={saving || !form.formState.isDirty}
        >
          Save changes
        </Button>
      </DialogFooter>
    </form>
  );
}
