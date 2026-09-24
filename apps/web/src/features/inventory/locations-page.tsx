"use client";

import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { MapPin, Plus, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Badge } from "@/components/ui/display";
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
  ModuleNav,
  RequirePermission,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { FormField } from "@/components/app/forms";
import { EmptyState, InlineError, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError, errorMessage } from "@/services/api-client";
import { adminService } from "@/features/admin/service";
import type { Location } from "@/features/business/types";
import { inventoryService } from "./service";
import { SLUG_PATTERN as SLUG, slugify } from "@/features/catalog/lib";
import { useLocations } from "./hooks";

export function LocationsPage() {
  return (
    <RequirePermission permission="inventory.read" area="inventory">
      <LocationsPageInner />
    </RequirePermission>
  );
}

function useBranches(enabled: boolean) {
  return useScopedQuery(
    ["organization", "branches"],
    () => adminService.branches(),
    { enabled, retry: false, staleTime: 60_000 },
  );
}

function LocationsPageInner() {
  const { can } = useSession();
  const canCreate = can("inventory.adjust");
  const locations = useLocations();
  const branches = useBranches(true);
  const [open, setOpen] = useState(false);
  const branchName = (id: string | null) =>
    id ? (branches.data?.find((b) => b.id === id)?.name ?? "—") : null;

  const columns: Column<Location>[] = [
    {
      key: "name",
      header: "Location",
      cell: (l) => (
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-surface-muted text-muted-foreground">
            <MapPin className="size-3.5" aria-hidden="true" />
          </span>
          <span className="truncate font-medium">{l.name}</span>
          {l.is_default && (
            <Badge tone="primary">
              <Star aria-hidden="true" /> Default
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: "code",
      header: "Code",
      hideBelow: "sm",
      cell: (l) => <span className="font-mono text-xs">{l.code}</span>,
    },
    {
      key: "branch",
      header: "Branch",
      hideBelow: "md",
      cell: (l) =>
        branchName(l.branch_id) ?? (
          <span className="text-muted-foreground">No branch</span>
        ),
    },
    {
      key: "status",
      header: "Status",
      align: "right",
      cell: (l) => <StatusBadge status={l.status} />,
    },
  ];

  return (
    <PageShell>
      <PageHeader
        title="Locations"
        description="Warehouses, shops and storerooms where you keep stock. The default location receives stock when none is chosen."
        actions={
          canCreate ? (
            <Button onClick={() => setOpen(true)}>
              <Plus /> Add location
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="inventory" />
      <DataTable
        caption="Stock locations"
        columns={columns}
        rows={locations.sorted}
        getRowId={(l) => l.id}
        loading={locations.isPending}
        error={locations.error}
        onRetry={() => void locations.refetch()}
        loadingRows={4}
        empty={
          <EmptyState
            icon={MapPin}
            title="No locations yet"
            description="Add the place where you store products. Your first location becomes the default for stock movements."
            action={
              canCreate ? (
                <Button size="sm" onClick={() => setOpen(true)}>
                  <Plus /> Add location
                </Button>
              ) : undefined
            }
          />
        }
      />
      {locations.data && locations.data.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          Locations are part of the stock ledger history, so they can’t be
          deleted here.
        </p>
      )}
      <LocationDialog
        open={open}
        onOpenChange={setOpen}
        branches={branches.data}
        branchesFailed={branches.isError}
      />
    </PageShell>
  );
}

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter a name")
    .max(120, "Keep the name under 120 characters"),
  code: z
    .string()
    .trim()
    .min(1, "Enter a code")
    .max(40, "Keep the code under 40 characters")
    .regex(
      SLUG,
      "Use lowercase letters, numbers and single hyphens, e.g. main-warehouse",
    ),
  branch_id: z.string(),
});
type Values = z.infer<typeof schema>;

function LocationDialog({
  open,
  onOpenChange,
  branches,
  branchesFailed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  branches: { id: string; name: string }[] | undefined;
  branchesFailed: boolean;
}) {
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    setError,
    control,
    formState,
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", code: "", branch_id: "" },
  });
  useEffect(() => {
    if (open) {
      reset({ name: "", code: "", branch_id: "" });
    }
  }, [open, reset]);
  const name = useWatch({ control, name: "name" });
  // Keep generating from the name until the member edits the code by hand.
  const codeTouched = Boolean(formState.dirtyFields.code);
  useEffect(() => {
    if (!codeTouched) setValue("code", slugify(name, 40));
  }, [name, codeTouched, setValue]);

  const mutation = useScopedMutation(
    (input: { name: string; code: string; branch_id: string | null }) =>
      inventoryService.createLocation(input),
    {
      invalidate: [["inventory"]],
      success: (l) => `Location “${l.name}” added`,
      error: "Couldn't add this location.",
      onSuccess: () => onOpenChange(false),
    },
  );

  const submit = handleSubmit((values) =>
    mutation.mutate(
      {
        name: values.name.trim(),
        code: values.code.trim(),
        branch_id: values.branch_id || null,
      },
      {
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409)
            setError("code", {
              message: "Another location already uses this code",
            });
        },
      },
    ),
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !mutation.isPending && onOpenChange(next)}
    >
      <DialogContent size="sm">
        <DialogHeader
          title="Add location"
          description="A place where stock is held and counted."
        />
        <form
          onSubmit={submit}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogBody className="space-y-4">
            <FormField
              label="Name"
              htmlFor="location-name"
              required
              error={formState.errors.name}
            >
              <Input
                id="location-name"
                autoFocus
                placeholder="Main warehouse"
                aria-invalid={Boolean(formState.errors.name)}
                {...register("name")}
              />
            </FormField>
            <FormField
              label="Code"
              htmlFor="location-code"
              required
              error={formState.errors.code}
              help="Short identifier used in reports and imports."
            >
              <Input
                id="location-code"
                className="font-mono"
                placeholder="main-warehouse"
                aria-invalid={Boolean(formState.errors.code)}
                {...register("code")}
              />
            </FormField>
            {branchesFailed ? (
              <Notice tone="neutral">
                Branches couldn’t be loaded, so this location won’t be linked to
                a branch.
              </Notice>
            ) : branches && branches.length > 0 ? (
              <FormField label="Branch" htmlFor="location-branch" optional>
                <NativeSelect id="location-branch" {...register("branch_id")}>
                  <option value="">No branch</option>
                  {branches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
            ) : null}
            {mutation.isError &&
              !(
                mutation.error instanceof ApiError &&
                mutation.error.status === 409
              ) && <InlineError message={errorMessage(mutation.error)} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              Add location
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
