"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Building2, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { EmptyState, InlineError } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { ApiError, errorMessage } from "@/services/api-client";
import type { Branch } from "@/features/business/types";
import { adminService } from "./service";
import { codeField } from "./lib";

const createSchema = z.object({
  name: z
    .string()
    .trim()
    .min(2, "Use at least 2 characters")
    .max(120, "Keep the name under 120 characters"),
  code: codeField,
});
const renameSchema = createSchema.pick({ name: true });

export function BranchesPage() {
  return (
    <RequirePermission permission="admin.organization.manage" area="branches">
      <BranchesContent />
    </RequirePermission>
  );
}

function BranchesContent() {
  const branches = useScopedQuery(["admin", "branches"], () =>
    adminService.branches(),
  );
  const departments = useScopedQuery(["admin", "departments"], () =>
    adminService.departments(),
  );
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<Branch | null>(null);
  const [deleting, setDeleting] = useState<Branch | null>(null);
  const deptCount = (id: string) =>
    departments.data?.filter((d) => d.branch_id === id).length;
  const remove = useScopedMutation(
    (id: string) => adminService.deleteBranch(id),
    {
      invalidate: [["admin", "branches"]],
      success: "Branch deleted",
      onSuccess: () => setDeleting(null),
    },
  );

  const columns: Column<Branch>[] = [
    {
      key: "name",
      header: "Branch",
      cell: (b) => <span className="font-medium">{b.name}</span>,
    },
    {
      key: "code",
      header: "Code",
      cell: (b) => <span className="font-mono text-xs">{b.code}</span>,
    },
    {
      key: "departments",
      header: "Departments",
      align: "right",
      hideBelow: "sm",
      cell: (b) => (
        <span className="tabular">{formatNumber(deptCount(b.id))}</span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      width: "52px",
      cell: (b) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`Actions for ${b.name}`}
            >
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={() => setRenaming(b)}>
              <Pencil /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem destructive onSelect={() => setDeleting(b)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  return (
    <PageShell width="default">
      <PageHeader
        title="Branches"
        description="Physical or organizational sites. Departments and stock locations can belong to a branch."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus /> New branch
          </Button>
        }
      />
      <DataTable
        caption="Branches"
        columns={columns}
        rows={branches.data}
        getRowId={(b) => b.id}
        loading={branches.isPending}
        error={branches.error}
        onRetry={() => void branches.refetch()}
        loadingRows={4}
        empty={
          <EmptyState
            compact
            icon={Building2}
            title="No branches yet"
            description="Add a branch if your business runs from more than one site."
            action={
              <Button size="sm" onClick={() => setCreating(true)}>
                <Plus /> New branch
              </Button>
            }
          />
        }
      />
      {creating && <CreateBranchDialog open onOpenChange={setCreating} />}
      {renaming && (
        <RenameBranchDialog
          branch={renaming}
          onClose={() => setRenaming(null)}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "branch"}?`}
        description="This permanently removes the branch."
        consequences={[
          "Branches referenced by departments or stock locations can't be deleted — move those first.",
          "Past records keep their history.",
        ]}
        confirmLabel="Delete branch"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
      />
    </PageShell>
  );
}

function CreateBranchDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<z.infer<typeof createSchema>>({
    resolver: zodResolver(createSchema),
    defaultValues: { name: "", code: "" },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const create = useScopedMutation(
    (input: { name: string; code: string }) => adminService.createBranch(input),
    {
      invalidate: [["admin", "branches"]],
      success: (b) => `Branch ${b.name} created`,
    },
  );
  const e = form.formState.errors;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !create.isPending && onOpenChange(next)}
    >
      <DialogContent size="sm">
        <DialogHeader title="New branch" />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (v) => {
            setServerError(null);
            try {
              await create.mutateAsync({
                name: v.name.trim(),
                code: v.code.trim().toUpperCase(),
              });
              onOpenChange(false);
            } catch (error) {
              if (error instanceof ApiError && error.status === 409)
                form.setError("code", {
                  type: "server",
                  message: "This code is already used by another branch",
                });
              else
                setServerError(
                  errorMessage(error, "The branch could not be created."),
                );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <FormField
              label="Name"
              htmlFor="branch-name"
              required
              error={e.name}
            >
              <Input
                id="branch-name"
                autoComplete="off"
                disabled={create.isPending}
                aria-invalid={!!e.name || undefined}
                {...form.register("name")}
              />
            </FormField>
            <FormField
              label="Code"
              htmlFor="branch-code"
              required
              error={e.code}
              help="Short unique code, e.g. LHR or HQ."
            >
              <Input
                id="branch-code"
                autoComplete="off"
                className="font-mono uppercase"
                disabled={create.isPending}
                aria-invalid={!!e.code || undefined}
                {...form.register("code")}
              />
            </FormField>
            {serverError && <InlineError message={serverError} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create branch
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RenameBranchDialog({
  branch,
  onClose,
}: {
  branch: Branch;
  onClose: () => void;
}) {
  const form = useForm<z.infer<typeof renameSchema>>({
    resolver: zodResolver(renameSchema),
    defaultValues: { name: branch.name },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const rename = useScopedMutation(
    (name: string) => adminService.renameBranch(branch.id, name),
    {
      invalidate: [["admin", "branches"]],
      success: "Branch renamed",
    },
  );
  const e = form.formState.errors;
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !rename.isPending && onClose()}
    >
      <DialogContent size="sm">
        <DialogHeader
          title={`Rename ${branch.name}`}
          description={`Code ${branch.code} stays the same.`}
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (v) => {
            setServerError(null);
            try {
              await rename.mutateAsync(v.name.trim());
              onClose();
            } catch (error) {
              setServerError(
                errorMessage(error, "The branch could not be renamed."),
              );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <FormField
              label="Name"
              htmlFor="branch-rename"
              required
              error={e.name}
            >
              <Input
                id="branch-rename"
                autoComplete="off"
                disabled={rename.isPending}
                aria-invalid={!!e.name || undefined}
                {...form.register("name")}
              />
            </FormField>
            {serverError && <InlineError message={serverError} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={rename.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={rename.isPending}
              disabled={!form.formState.isDirty}
            >
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
