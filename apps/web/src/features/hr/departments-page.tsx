"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Building2, Plus } from "lucide-react";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { FormField } from "@/components/app/forms";
import { EmptyState, InlineError, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import { useSession } from "@/features/auth/session-provider";
import { adminService } from "@/features/admin/service";
import type { Branch, Department } from "@/features/business/types";
import { hrService } from "./service";
import { ROSTER_PAGE_SIZE } from "./utils";

type Row = Department & {
  headcount: number | null;
  onLeave: number | null;
  branchName: string | null;
};

export function DepartmentsPage() {
  return (
    <RequirePermission permission="hr.read" area="departments">
      <Departments />
    </RequirePermission>
  );
}

function Departments() {
  const { can } = useSession();
  const canManage = can("admin.organization.manage");
  const [creating, setCreating] = useState(false);
  const departments = useScopedQuery(["departments"], () =>
    adminService.departments(),
  );
  const branches = useScopedQuery(["branches"], () => adminService.branches(), {
    staleTime: 60_000,
  });
  const roster = useScopedQuery(
    ["employees", { pageSize: ROSTER_PAGE_SIZE }],
    () => hrService.employees({ pageSize: ROSTER_PAGE_SIZE }),
  );
  const people = roster.data?.items;
  const truncated = (roster.data?.total ?? 0) > ROSTER_PAGE_SIZE;
  const current = people?.filter((p) => p.status !== "terminated");
  const unassigned = current?.filter((p) => !p.department_id).length ?? 0;

  const rows: Row[] | undefined = departments.data
    ?.map((d) => ({
      ...d,
      headcount: current
        ? current.filter((p) => p.department_id === d.id).length
        : null,
      onLeave: current
        ? current.filter(
            (p) => p.department_id === d.id && p.status === "on_leave",
          ).length
        : null,
      branchName: d.branch_id
        ? (branches.data?.find((b) => b.id === d.branch_id)?.name ?? null)
        : null,
    }))
    .sort((a, b) => a.name.localeCompare(b.name));

  const columns: Column<Row>[] = [
    {
      key: "name",
      header: "Department",
      cell: (d) => (
        <Link
          href={`/hr/employees?department=${d.id}`}
          className="font-medium hover:underline"
        >
          {d.name}
        </Link>
      ),
    },
    {
      key: "code",
      header: "Code",
      cell: (d) => (
        <span className="font-mono text-xs text-muted-foreground">
          {d.code}
        </span>
      ),
      hideBelow: "sm",
    },
    {
      key: "branch",
      header: "Branch",
      cell: (d) =>
        d.branch_id ? (
          (d.branchName ?? <span className="text-muted-foreground">—</span>)
        ) : (
          <span className="text-muted-foreground">All branches</span>
        ),
      hideBelow: "md",
    },
    {
      key: "on_leave",
      header: "On leave",
      align: "right",
      cell: (d) => (
        <span className="tabular text-muted-foreground">
          {d.onLeave === null ? "…" : formatNumber(d.onLeave)}
        </span>
      ),
      hideBelow: "md",
    },
    {
      key: "headcount",
      header: "Headcount",
      align: "right",
      cell: (d) => (
        <span className="tabular font-medium">
          {d.headcount === null ? "…" : formatNumber(d.headcount)}
        </span>
      ),
    },
  ];

  return (
    <PageShell>
      <PageHeader
        title="Departments"
        description="How the team is organized. Headcount excludes terminated employees."
        actions={
          canManage ? (
            <Button onClick={() => setCreating(true)}>
              <Plus /> New department
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="hr" />

      {truncated && (
        <Notice tone="info" className="mb-3">
          Headcounts are based on the first {ROSTER_PAGE_SIZE} employee records.
        </Notice>
      )}
      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(d) => d.id}
        loading={departments.isPending}
        error={departments.error}
        onRetry={() => void departments.refetch()}
        rowHref={(d) => `/hr/employees?department=${d.id}`}
        caption="Departments"
        loadingRows={5}
        empty={
          <EmptyState
            icon={Building2}
            title="No departments yet"
            description={
              canManage
                ? "Create departments to group employees and see headcount by team."
                : "An administrator with organization access can create departments."
            }
            action={
              canManage ? (
                <Button size="sm" onClick={() => setCreating(true)}>
                  <Plus /> New department
                </Button>
              ) : undefined
            }
          />
        }
      />
      {rows && rows.length > 0 && unassigned > 0 && (
        <p className="mt-3 text-[13px] text-muted-foreground">
          {formatNumber(unassigned)} current employee
          {unassigned === 1 ? " has" : "s have"} no department.
        </p>
      )}

      {canManage && (
        <Dialog open={creating} onOpenChange={setCreating}>
          <DialogContent size="sm">
            {creating && (
              <NewDepartmentForm
                branches={branches.data ?? []}
                onDone={() => setCreating(false)}
              />
            )}
          </DialogContent>
        </Dialog>
      )}
    </PageShell>
  );
}

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter a department name")
    .max(120, "Keep it under 120 characters"),
  code: z
    .string()
    .trim()
    .min(2, "Use at least 2 characters")
    .max(40, "Keep it under 40 characters")
    .regex(
      /^[a-z0-9]+(-[a-z0-9]+)*$/,
      "Lowercase letters, numbers and single dashes only",
    ),
  branch_id: z.string(),
});
type Values = z.infer<typeof schema>;

function slugify(value: string) {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}

function NewDepartmentForm({
  branches,
  onDone,
}: {
  branches: Branch[];
  onDone: () => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const [codeTouched, setCodeTouched] = useState(false);
  const { register, handleSubmit, setValue, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", code: "", branch_id: "" },
  });
  const { errors } = formState;
  const create = useScopedMutation(adminService.createDepartment, {
    invalidate: [["departments"]],
    success: (d) => `${d.name} created`,
    onSuccess: onDone,
  });
  const saving = create.isPending;
  const nameField = register("name");
  const codeField = register("code");

  const onSubmit = handleSubmit((values) => {
    setServerError(null);
    create.mutate(
      {
        name: values.name.trim(),
        code: values.code.trim(),
        branch_id: values.branch_id || null,
      },
      {
        onError: (e) =>
          setServerError(
            errorMessage(e, "The department couldn't be created."),
          ),
      },
    );
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex min-h-0 flex-col">
      <DialogHeader
        title="New department"
        description="Employees can be assigned to it right away."
      />
      <DialogBody className="space-y-4">
        {serverError && <InlineError message={serverError} />}
        <FormField
          label="Name"
          htmlFor="dept-name"
          required
          error={errors.name?.message}
        >
          <Input
            id="dept-name"
            placeholder="e.g. Customer Support"
            autoFocus
            aria-invalid={Boolean(errors.name) || undefined}
            disabled={saving}
            {...nameField}
            onChange={(e) => {
              void nameField.onChange(e);
              if (!codeTouched)
                setValue("code", slugify(e.target.value), {
                  shouldValidate: formState.isSubmitted,
                });
            }}
          />
        </FormField>
        <FormField
          label="Code"
          htmlFor="dept-code"
          required
          error={errors.code?.message}
          help="A short unique identifier, like customer-support."
        >
          <Input
            id="dept-code"
            className="font-mono text-[13px]"
            aria-invalid={Boolean(errors.code) || undefined}
            disabled={saving}
            {...codeField}
            onChange={(e) => {
              setCodeTouched(true);
              void codeField.onChange(e);
            }}
          />
        </FormField>
        <FormField
          label="Branch"
          htmlFor="dept-branch"
          optional
          help="Leave empty if the team works across branches."
        >
          <NativeSelect
            id="dept-branch"
            disabled={saving}
            {...register("branch_id")}
          >
            <option value="">All branches</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </NativeSelect>
        </FormField>
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
        <Button type="submit" loading={saving}>
          Create department
        </Button>
      </DialogFooter>
    </form>
  );
}
