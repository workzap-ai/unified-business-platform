"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Lock, SearchX, ShieldCheck, Trash2 } from "lucide-react";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/controls";
import { Badge } from "@/components/ui/display";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PageSkeleton } from "@/components/app/page-skeleton";
import { RecordHeader } from "@/components/app/record";
import {
  ConfirmDialog,
  FormActions,
  FormField,
  FormSection,
  useUnsavedChangesWarning,
} from "@/components/app/forms";
import {
  EmptyState,
  ErrorState,
  InlineError,
  Notice,
} from "@/components/app/states";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError, errorMessage } from "@/services/api-client";
import { adminService, type Permission, type Role } from "./service";
import { SLUG, groupPermissions, slugify } from "./lib";

const schema = z.object({
  key: z.string().trim(),
  name: z
    .string()
    .trim()
    .min(2, "Use at least 2 characters")
    .max(80, "Keep the name under 80 characters"),
  description: z
    .string()
    .trim()
    .max(300, "Keep the description under 300 characters"),
  permissions: z.array(z.string()).min(1, "Grant at least one permission"),
});
type Values = z.infer<typeof schema>;

export function RoleEditor({ roleId }: { roleId?: string }) {
  return (
    <RequirePermission
      permission={roleId ? "admin.members.read" : "admin.roles.manage"}
      area={roleId ? "roles" : "role creation"}
    >
      <RoleEditorContent roleId={roleId} />
    </RequirePermission>
  );
}

function RoleEditorContent({ roleId }: { roleId?: string }) {
  const roles = useScopedQuery(["admin", "roles"], () => adminService.roles());
  const permissions = useScopedQuery(["admin", "permissions"], () =>
    adminService.permissions(),
  );
  const isNew = !roleId;
  const role = roleId ? roles.data?.find((r) => r.id === roleId) : undefined;

  if (roles.isPending || permissions.isPending)
    return <PageSkeleton variant="detail" />;
  if (roles.isError || permissions.isError) {
    return (
      <PageShell width="default">
        <ErrorState
          error={roles.error ?? permissions.error}
          onRetry={() => {
            void roles.refetch();
            void permissions.refetch();
          }}
        />
      </PageShell>
    );
  }
  if (!isNew && !role) {
    return (
      <PageShell width="default">
        <EmptyState
          icon={SearchX}
          title="Role not found"
          description="It may have been deleted, or it belongs to another workspace."
          action={
            <Button variant="secondary" asChild>
              <Link href="/settings/roles">Back to roles</Link>
            </Button>
          }
        />
      </PageShell>
    );
  }
  return <RoleForm role={role} permissions={permissions.data} />;
}

function RoleForm({
  role,
  permissions,
}: {
  role?: Role;
  permissions: Permission[];
}) {
  const router = useRouter();
  const { can } = useSession();
  const isNew = !role;
  const readOnly = !can("admin.roles.manage") || Boolean(role?.is_system);
  useBreadcrumbs(
    [{ label: role?.name ?? "New role" }],
    role ? { href: `/settings/roles/${role.id}`, kind: "Role" } : undefined,
  );

  const form = useForm<Values>({
    resolver: zodResolver(
      schema.superRefine((v, ctx) => {
        if (isNew && !SLUG.test(v.key))
          ctx.addIssue({
            code: "custom",
            path: ["key"],
            message:
              "Use 2–48 lowercase letters, digits or dashes, starting with a letter",
          });
      }),
    ),
    defaultValues: role
      ? {
          key: role.key,
          name: role.name,
          description: role.description,
          permissions: role.permissions,
        }
      : { key: "", name: "", description: "", permissions: [] },
  });
  const { formState, reset } = form;
  const [keyTouched, setKeyTouched] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useUnsavedChangesWarning(formState.isDirty && !readOnly);

  const name = useWatch({ control: form.control, name: "name" });
  useEffect(() => {
    if (isNew && !keyTouched) form.setValue("key", slugify(name));
  }, [name, isNew, keyTouched, form]);

  const create = useScopedMutation(
    (v: Values) =>
      adminService.createRole({
        key: v.key.trim(),
        name: v.name.trim(),
        description: v.description.trim(),
        permissions: v.permissions,
      }),
    {
      invalidate: [["admin", "roles"]],
      success: (r) => `Role “${r.name}” created`,
    },
  );
  const update = useScopedMutation(
    (v: Values) =>
      adminService.updateRole(role!.id, {
        name: v.name.trim(),
        description: v.description.trim(),
        permissions: v.permissions,
      }),
    {
      invalidate: [["admin", "roles"]],
      success: "Role saved",
    },
  );
  const remove = useScopedMutation(() => adminService.deleteRole(role!.id), {
    invalidate: [["admin", "roles"]],
    success: "Role deleted",
    onSuccess: () => router.push("/settings/roles"),
  });
  const saving = create.isPending || update.isPending;
  const e = formState.errors;

  return (
    <PageShell width="default">
      <RecordHeader
        icon={ShieldCheck}
        title={role?.name ?? "New role"}
        subtitle={
          role
            ? role.description || "No description"
            : "Bundle permissions into a role you can assign to members."
        }
        status={
          role ? (
            role.is_system ? (
              <Badge tone="outline">System</Badge>
            ) : (
              <Badge tone="primary">Custom</Badge>
            )
          ) : undefined
        }
        identifier={role?.key}
        meta={
          role && (
            <span>
              {formatNumber(role.member_count)} member
              {role.member_count === 1 ? "" : "s"} ·{" "}
              {formatNumber(role.permissions.length)} permissions
            </span>
          )
        }
        actions={
          role && !role.is_system && can("admin.roles.manage") ? (
            <Button
              variant="danger-outline"
              size="sm"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 /> Delete role
            </Button>
          ) : undefined
        }
      />

      {role?.is_system && (
        <Notice
          tone="neutral"
          icon={Lock}
          className="mb-5"
          title="System roles are read-only"
        >
          System roles are maintained by the platform so upgrades stay safe. To
          customise access, create a new role and assign it instead.
        </Notice>
      )}
      {!role?.is_system && readOnly && (
        <Notice tone="neutral" icon={Lock} className="mb-5">
          You can view this role. Editing roles needs the “Manage roles”
          permission.
        </Notice>
      )}

      <form
        noValidate
        onSubmit={form.handleSubmit(async (values) => {
          setServerError(null);
          try {
            if (isNew) {
              const created = await create.mutateAsync(values);
              reset(values);
              router.replace(`/settings/roles/${created.id}`);
            } else {
              const saved = await update.mutateAsync(values);
              reset({
                key: saved.key,
                name: saved.name,
                description: saved.description,
                permissions: saved.permissions,
              });
              setSavedAt((n) => (n ?? 0) + 1);
            }
          } catch (error) {
            if (error instanceof ApiError && error.status === 409 && isNew)
              form.setError("key", {
                type: "server",
                message: errorMessage(error),
              });
            setServerError(errorMessage(error, "The role could not be saved."));
          }
        })}
      >
        <FormSection
          title="Details"
          description="How the role appears when assigning members."
        >
          <FormField label="Name" htmlFor="role-name" required error={e.name}>
            <Input
              id="role-name"
              autoComplete="off"
              disabled={readOnly || saving}
              aria-invalid={!!e.name || undefined}
              aria-describedby={e.name ? "role-name-error" : undefined}
              {...form.register("name")}
            />
          </FormField>
          {isNew && (
            <FormField
              label="Key"
              htmlFor="role-key"
              required
              error={e.key}
              help="Stable identifier used by integrations and the audit log. Can't be changed later."
            >
              <Input
                id="role-key"
                autoComplete="off"
                className="font-mono"
                disabled={saving}
                aria-invalid={!!e.key || undefined}
                aria-describedby={e.key ? "role-key-error" : "role-key-help"}
                {...form.register("key", {
                  onChange: () => setKeyTouched(true),
                })}
              />
            </FormField>
          )}
          <FormField
            label="Description"
            htmlFor="role-description"
            optional
            error={e.description}
          >
            <Textarea
              id="role-description"
              rows={2}
              disabled={readOnly || saving}
              aria-invalid={!!e.description || undefined}
              {...form.register("description")}
            />
          </FormField>
        </FormSection>

        <FormSection
          title="Permissions"
          description="Select what members with this role can see and do. The API enforces every permission."
        >
          <Controller
            control={form.control}
            name="permissions"
            render={({ field }) => (
              <PermissionGroups
                permissions={permissions}
                value={field.value}
                onChange={field.onChange}
                disabled={readOnly || saving}
              />
            )}
          />
          {e.permissions && (
            <p role="alert" className="text-xs font-medium text-danger">
              {e.permissions.message}
            </p>
          )}
          {serverError && <InlineError message={serverError} />}
        </FormSection>

        {!readOnly && (
          <FormActions
            dirty={formState.isDirty}
            saving={saving}
            savedAt={savedAt}
            submitLabel={isNew ? "Create role" : "Save role"}
            onCancel={() => (isNew ? router.push("/settings/roles") : reset())}
          />
        )}
      </form>

      {role && (
        <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title={`Delete “${role.name}”?`}
          description="This permanently removes the role."
          consequences={
            role.member_count > 0
              ? [
                  `${formatNumber(role.member_count)} member(s) still have this role. Remove it from them first — the server blocks deleting assigned roles.`,
                ]
              : [
                  "Members can no longer be given this role.",
                  "Past audit entries keep the role key.",
                ]
          }
          confirmLabel="Delete role"
          destructive
          loading={remove.isPending}
          onConfirm={() => remove.mutate(undefined)}
        />
      )}
    </PageShell>
  );
}

function PermissionGroups({
  permissions,
  value,
  onChange,
  disabled,
}: {
  permissions: Permission[];
  value: string[];
  onChange: (next: string[]) => void;
  disabled: boolean;
}) {
  const selected = new Set(value);
  return (
    <div className="space-y-3">
      {groupPermissions(permissions).map(([group, items]) => {
        const count = items.filter((p) => selected.has(p.key)).length;
        const all = count === items.length;
        const groupId = `perm-group-${group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
        return (
          <fieldset
            key={group}
            className="overflow-hidden rounded-lg border border-border"
          >
            <legend className="sr-only">{group} permissions</legend>
            <div className="flex items-center gap-3 border-b border-border bg-surface-muted/60 px-3 py-2">
              <Checkbox
                id={groupId}
                checked={all ? true : count > 0 ? "indeterminate" : false}
                disabled={disabled}
                onCheckedChange={() => {
                  const keys = items.map((p) => p.key);
                  onChange(
                    all
                      ? value.filter((k) => !keys.includes(k))
                      : [...new Set([...value, ...keys])],
                  );
                }}
                aria-label={`Select all ${group} permissions`}
              />
              <label
                htmlFor={groupId}
                className="flex-1 cursor-pointer text-[13px] font-semibold"
              >
                {group}
              </label>
              <span className="tabular text-xs text-muted-foreground">
                {count}/{items.length}
              </span>
            </div>
            <ul className="grid gap-x-4 sm:grid-cols-2">
              {items.map((p) => {
                const id = `perm-${p.key}`;
                return (
                  <li key={p.key} className="flex items-start gap-3 px-3 py-2">
                    <Checkbox
                      id={id}
                      className="mt-0.5"
                      checked={selected.has(p.key)}
                      disabled={disabled}
                      onCheckedChange={(next) =>
                        onChange(
                          next === true
                            ? [...value, p.key]
                            : value.filter((k) => k !== p.key),
                        )
                      }
                    />
                    <label htmlFor={id} className="min-w-0 cursor-pointer">
                      <span className="block text-[13px] font-medium">
                        {p.label}
                      </span>
                      <span className="block font-mono text-2xs text-muted-foreground">
                        {p.key}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </fieldset>
        );
      })}
    </div>
  );
}
