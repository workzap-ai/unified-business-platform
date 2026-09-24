"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Network, Plus } from "lucide-react";
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
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { FormField } from "@/components/app/forms";
import { EmptyState, InlineError } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { ApiError, errorMessage } from "@/services/api-client";
import type { Branch, Department } from "@/features/business/types";
import { adminService } from "./service";
import { codeField } from "./lib";

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(2, "Use at least 2 characters")
    .max(120, "Keep the name under 120 characters"),
  code: codeField,
  branch_id: z.string(),
});

export function DepartmentsPage() {
  return (
    <RequirePermission
      permission="admin.organization.manage"
      area="departments"
    >
      <DepartmentsContent />
    </RequirePermission>
  );
}

function DepartmentsContent() {
  const departments = useScopedQuery(["admin", "departments"], () =>
    adminService.departments(),
  );
  const branches = useScopedQuery(["admin", "branches"], () =>
    adminService.branches(),
  );
  const [creating, setCreating] = useState(false);
  const branchName = (id: string | null) =>
    id ? (branches.data?.find((b) => b.id === id)?.name ?? "—") : null;

  const columns: Column<Department>[] = [
    {
      key: "name",
      header: "Department",
      cell: (d) => <span className="font-medium">{d.name}</span>,
    },
    {
      key: "code",
      header: "Code",
      cell: (d) => <span className="font-mono text-xs">{d.code}</span>,
    },
    {
      key: "branch",
      header: "Branch",
      hideBelow: "sm",
      cell: (d) =>
        branchName(d.branch_id) ?? (
          <span className="text-muted-foreground">Whole organization</span>
        ),
    },
  ];

  return (
    <PageShell width="default">
      <PageHeader
        title="Departments"
        description="Teams employees belong to. Used by HR and headcount reports."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus /> New department
          </Button>
        }
      />
      <DataTable
        caption="Departments"
        columns={columns}
        rows={departments.data}
        getRowId={(d) => d.id}
        loading={departments.isPending}
        error={departments.error}
        onRetry={() => void departments.refetch()}
        loadingRows={5}
        empty={
          <EmptyState
            compact
            icon={Network}
            title="No departments yet"
            description="Create departments such as Sales or Warehouse to organize employees."
            action={
              <Button size="sm" onClick={() => setCreating(true)}>
                <Plus /> New department
              </Button>
            }
          />
        }
      />
      {creating && (
        <CreateDepartmentDialog
          open
          onOpenChange={setCreating}
          branches={branches.data}
        />
      )}
    </PageShell>
  );
}

function CreateDepartmentDialog({
  open,
  onOpenChange,
  branches,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  branches: Branch[] | undefined;
}) {
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", code: "", branch_id: "" },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const create = useScopedMutation(
    (input: { name: string; code: string; branch_id: string | null }) =>
      adminService.createDepartment(input),
    {
      invalidate: [["admin", "departments"]],
      success: (d) => `Department ${d.name} created`,
    },
  );
  const e = form.formState.errors;
  const saving = create.isPending;
  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent size="sm">
        <DialogHeader title="New department" />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (v) => {
            setServerError(null);
            try {
              await create.mutateAsync({
                name: v.name.trim(),
                code: v.code.trim().toUpperCase(),
                branch_id: v.branch_id || null,
              });
              onOpenChange(false);
            } catch (error) {
              if (error instanceof ApiError && error.status === 409)
                form.setError("code", {
                  type: "server",
                  message: "This code is already used by another department",
                });
              else
                setServerError(
                  errorMessage(error, "The department could not be created."),
                );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <FormField label="Name" htmlFor="dept-name" required error={e.name}>
              <Input
                id="dept-name"
                autoComplete="off"
                disabled={saving}
                aria-invalid={!!e.name || undefined}
                {...form.register("name")}
              />
            </FormField>
            <FormField
              label="Code"
              htmlFor="dept-code"
              required
              error={e.code}
              help="Short unique code, e.g. SALES."
            >
              <Input
                id="dept-code"
                autoComplete="off"
                className="font-mono uppercase"
                disabled={saving}
                aria-invalid={!!e.code || undefined}
                {...form.register("code")}
              />
            </FormField>
            <FormField label="Branch" htmlFor="dept-branch" optional>
              <NativeSelect
                id="dept-branch"
                disabled={saving}
                {...form.register("branch_id")}
              >
                <option value="">Whole organization</option>
                {branches?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name} ({b.code})
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            {serverError && <InlineError message={serverError} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Create department
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
