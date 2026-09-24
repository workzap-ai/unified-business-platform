"use client";

import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  MoreHorizontal,
  ShieldCheck,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/controls";
import { Avatar, Badge } from "@/components/ui/display";
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
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { FilterBar, SearchInput } from "@/components/app/filters";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { EmptyState, InlineError } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { ApiError, errorMessage } from "@/services/api-client";
import { adminService, type Member, type Role } from "./service";

const PAGE_SIZE = 50;

/** Owner-protection rules come back as fixed server messages; add the next step. */
function memberError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.code === "LAST_OWNER") {
    return `${errorMessage(error, fallback)}. Give another member the Owner role first.`;
  }
  if (error instanceof ApiError && error.code === "SELF_REVOKE") {
    return `${errorMessage(error, fallback)}. Ask another administrator to remove your membership.`;
  }
  return errorMessage(error, fallback);
}

export function MembersPage() {
  return (
    <RequirePermission permission="admin.members.read" area="members">
      <MembersContent />
    </RequirePermission>
  );
}

function MembersContent() {
  const { can, session } = useSession();
  const canManage = can("admin.members.manage");
  const [state, setState] = useUrlState({ search: "", page: "1", invite: "" });
  const page = Math.max(1, Number(state.page) || 1);
  const members = useScopedQuery(
    ["admin", "members", { page, search: state.search }],
    () => adminService.members({ page, search: state.search || undefined }),
  );
  const roles = useScopedQuery(["admin", "roles"], () => adminService.roles());
  const [editing, setEditing] = useState<Member | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const roleName = (key: string) =>
    roles.data?.find((r) => r.key === key)?.name ?? key;

  const remove = useScopedMutation(
    (id: string) => adminService.revokeMember(id),
    {
      invalidate: [
        ["admin", "members"],
        ["admin", "roles"],
      ],
      success: "Member removed",
      onSuccess: () => setRemoving(null),
    },
  );

  const columns: Column<Member>[] = [
    {
      key: "member",
      header: "Member",
      cell: (m) => (
        <div className="flex min-w-0 items-center gap-2.5">
          <Avatar name={m.display_name} size="sm" />
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 truncate font-medium">
              {m.display_name}
              {m.user_id === session?.user.id && (
                <Badge tone="outline">You</Badge>
              )}
            </p>
            <p className="truncate text-xs text-muted-foreground">{m.email}</p>
          </div>
        </div>
      ),
    },
    {
      key: "roles",
      header: "Roles",
      hideBelow: "sm",
      cell: (m) => (
        <div className="flex flex-wrap gap-1">
          {m.roles.length ? (
            m.roles.map((r) => (
              <Badge key={r} tone={r === "owner" ? "primary" : "neutral"}>
                {roleName(r)}
              </Badge>
            ))
          ) : (
            <span className="text-muted-foreground">No roles</span>
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (m) => (
        <StatusBadge
          status={m.status === "revoked" ? "inactive" : "active"}
          label={m.status === "revoked" ? "Removed" : "Active"}
        />
      ),
    },
    {
      key: "joined",
      header: "Joined",
      hideBelow: "md",
      cell: (m) => (
        <span className="text-muted-foreground">{formatDate(m.joined_at)}</span>
      ),
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: <span className="sr-only">Actions</span>,
            align: "right" as const,
            width: "52px",
            cell: (m: Member) =>
              m.status === "active" ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label={`Actions for ${m.display_name}`}
                    >
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem onSelect={() => setEditing(m)}>
                      <ShieldCheck /> Change roles
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      destructive
                      onSelect={() => setRemoving(m)}
                    >
                      <UserMinus /> Remove from workspace
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null,
          },
        ]
      : []),
  ];

  return (
    <PageShell>
      <PageHeader
        title="Members"
        description="People with access to this workspace and the roles that decide what they can do."
        actions={
          canManage && (
            <Button
              onClick={() => setState({ invite: "1" }, { resetPage: false })}
            >
              <UserPlus /> Add member
            </Button>
          )
        }
      />
      <FilterBar>
        <SearchInput
          value={state.search}
          onChange={(v) => setState({ search: v })}
          placeholder="Search name or email…"
          className="w-full md:w-72"
        />
      </FilterBar>
      <DataTable
        caption="Workspace members"
        columns={columns}
        rows={members.data?.items}
        getRowId={(m) => m.membership_id}
        loading={members.isPending}
        error={members.error}
        onRetry={() => void members.refetch()}
        rowClassName={(m) =>
          m.status === "revoked" ? "opacity-60" : undefined
        }
        empty={
          <EmptyState
            compact
            icon={Users}
            title={
              state.search ? "No members match your search" : "No members yet"
            }
            description={
              state.search
                ? "Try a different name or email."
                : "Add teammates so they can work in this workspace."
            }
          />
        }
      />
      {members.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={members.data.total}
          onPage={(p) => setState({ page: String(p) })}
        />
      )}

      {canManage && state.invite === "1" && (
        <AddMemberDialog
          open
          onOpenChange={(open) =>
            setState({ invite: open ? "1" : "" }, { resetPage: false })
          }
          roles={roles.data}
        />
      )}
      {editing && (
        <ChangeRolesDialog
          member={editing}
          roles={roles.data}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.display_name ?? "member"}?`}
        description="They lose access to this workspace. Their account and past activity stay intact."
        consequences={[
          "Their sessions for this workspace end immediately.",
          "Records they created keep their name in history and the audit log.",
          "You can add them again later with the same email.",
        ]}
        confirmLabel="Remove member"
        destructive
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing.membership_id)}
      />
    </PageShell>
  );
}

/* Role picker ---------------------------------------------------------------------------- */

function RolePicker({
  roles,
  value,
  onChange,
  idPrefix,
  disabled,
}: {
  roles: Role[] | undefined;
  value: string[];
  onChange: (next: string[]) => void;
  idPrefix: string;
  disabled?: boolean;
}) {
  if (!roles)
    return <p className="text-[13px] text-muted-foreground">Loading roles…</p>;
  return (
    <ul className="max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border">
      {roles.map((role) => {
        const id = `${idPrefix}-${role.id}`;
        const checked = value.includes(role.id);
        return (
          <li key={role.id} className="flex items-start gap-3 px-3 py-2.5">
            <Checkbox
              id={id}
              checked={checked}
              disabled={disabled}
              onCheckedChange={(next) =>
                onChange(
                  next === true
                    ? [...value, role.id]
                    : value.filter((v) => v !== role.id),
                )
              }
              className="mt-0.5"
            />
            <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
              <span className="flex items-center gap-1.5 text-[13px] font-medium">
                {role.name}
                {role.is_system && <Badge tone="outline">System</Badge>}
              </span>
              {role.description && (
                <span className="block text-xs text-muted-foreground">
                  {role.description}
                </span>
              )}
            </label>
          </li>
        );
      })}
    </ul>
  );
}

/* Add member ------------------------------------------------------------------------------ */

const addSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Enter an email address")
    .refine(
      (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v),
      "Enter a valid email address",
    ),
  display_name: z
    .string()
    .trim()
    .min(1, "Enter their name")
    .max(120, "Keep the name under 120 characters"),
  role_ids: z.array(z.string()).min(1, "Choose at least one role"),
  initial_password: z
    .string()
    .refine(
      (v) => !v || v.length >= 12,
      "Use at least 12 characters, or leave empty",
    ),
});
type AddValues = z.infer<typeof addSchema>;
const emptyAdd: AddValues = {
  email: "",
  display_name: "",
  role_ids: [],
  initial_password: "",
};

function AddMemberDialog({
  open,
  onOpenChange,
  roles,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  roles: Role[] | undefined;
}) {
  const form = useForm<AddValues>({
    resolver: zodResolver(addSchema),
    defaultValues: emptyAdd,
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const add = useScopedMutation(
    (input: AddValues) =>
      adminService.addMember({
        email: input.email.trim(),
        display_name: input.display_name.trim(),
        role_ids: input.role_ids,
        initial_password: input.initial_password || null,
      }),
    {
      invalidate: [
        ["admin", "members"],
        ["admin", "roles"],
      ],
      success: (m) => `${m.display_name} added`,
    },
  );
  const e = form.formState.errors;
  const saving = add.isPending;

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent size="md">
        <DialogHeader
          title="Add member"
          description="Give someone access to this workspace. They sign in with their email."
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (values) => {
            setServerError(null);
            try {
              await add.mutateAsync(values);
              onOpenChange(false);
            } catch (error) {
              if (error instanceof ApiError && error.fields.email)
                form.setError("email", {
                  type: "server",
                  message: error.fields.email,
                });
              setServerError(
                memberError(error, "The member could not be added."),
              );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                label="Email"
                htmlFor="add-email"
                required
                error={e.email}
              >
                <Input
                  id="add-email"
                  type="email"
                  autoComplete="off"
                  disabled={saving}
                  aria-invalid={!!e.email || undefined}
                  aria-describedby={e.email ? "add-email-error" : undefined}
                  {...form.register("email")}
                />
              </FormField>
              <FormField
                label="Display name"
                htmlFor="add-name"
                required
                error={e.display_name}
              >
                <Input
                  id="add-name"
                  autoComplete="off"
                  disabled={saving}
                  aria-invalid={!!e.display_name || undefined}
                  aria-describedby={
                    e.display_name ? "add-name-error" : undefined
                  }
                  {...form.register("display_name")}
                />
              </FormField>
            </div>
            <FormField label="Roles" required error={e.role_ids?.message}>
              <Controller
                control={form.control}
                name="role_ids"
                render={({ field }) => (
                  <RolePicker
                    roles={roles}
                    value={field.value}
                    onChange={field.onChange}
                    idPrefix="add-role"
                    disabled={saving}
                  />
                )}
              />
            </FormField>
            <FormField
              label="Initial password"
              htmlFor="add-password"
              optional
              error={e.initial_password}
              help="Only used if this email has no account yet. At least 12 characters; share it privately."
            >
              <Input
                id="add-password"
                type="password"
                autoComplete="new-password"
                disabled={saving}
                aria-invalid={!!e.initial_password || undefined}
                aria-describedby={
                  e.initial_password
                    ? "add-password-error"
                    : "add-password-help"
                }
                {...form.register("initial_password")}
              />
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
              Add member
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* Change roles ------------------------------------------------------------------------------ */

function ChangeRolesDialog({
  member,
  roles,
  onClose,
}: {
  member: Member;
  roles: Role[] | undefined;
  onClose: () => void;
}) {
  const [value, setValue] = useState<string[]>(member.role_ids);
  const [error, setError] = useState<string | null>(null);
  const update = useScopedMutation(
    (ids: string[]) =>
      adminService.updateMemberRoles(member.membership_id, ids),
    {
      invalidate: [
        ["admin", "members"],
        ["admin", "roles"],
      ],
      success: "Roles updated",
    },
  );
  const dirty =
    value.length !== member.role_ids.length ||
    value.some((v) => !member.role_ids.includes(v));

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !update.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title={`Change roles for ${member.display_name}`}
          description="Changes apply the next time they load a page."
        />
        <DialogBody className="space-y-3">
          <RolePicker
            roles={roles}
            value={value}
            onChange={(next) => {
              setValue(next);
              setError(null);
            }}
            idPrefix="edit-role"
            disabled={update.isPending}
          />
          {value.length === 0 && (
            <p className="text-xs font-medium text-danger" role="alert">
              Choose at least one role.
            </p>
          )}
          {error && <InlineError message={error} />}
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={update.isPending}
          >
            Cancel
          </Button>
          <Button
            loading={update.isPending}
            disabled={!dirty || value.length === 0}
            onClick={async () => {
              setError(null);
              try {
                await update.mutateAsync(value);
                onClose();
              } catch (err) {
                setError(memberError(err, "Roles could not be updated."));
              }
            }}
          >
            Save roles
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
