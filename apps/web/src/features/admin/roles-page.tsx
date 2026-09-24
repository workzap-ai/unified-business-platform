"use client";

import Link from "next/link";
import { Check, Plus, ShieldCheck } from "lucide-react";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { adminService, type Permission, type Role } from "./service";
import { groupPermissions } from "./lib";

export function RolesPage() {
  return (
    <RequirePermission
      permission="admin.members.read"
      area="roles and permissions"
    >
      <RolesContent />
    </RequirePermission>
  );
}

function RolesContent() {
  const { can } = useSession();
  const [state, setState] = useUrlState({ tab: "roles" });
  const roles = useScopedQuery(["admin", "roles"], () => adminService.roles());
  const permissions = useScopedQuery(["admin", "permissions"], () =>
    adminService.permissions(),
  );

  const columns: Column<Role>[] = [
    {
      key: "name",
      header: "Role",
      cell: (r) => (
        <span className="flex items-center gap-1.5 font-medium">
          {r.name}
          {r.is_system ? (
            <Badge tone="outline">System</Badge>
          ) : (
            <Badge tone="primary">Custom</Badge>
          )}
        </span>
      ),
    },
    {
      key: "key",
      header: "Key",
      hideBelow: "lg",
      cell: (r) => (
        <span className="font-mono text-xs text-muted-foreground">{r.key}</span>
      ),
    },
    {
      key: "description",
      header: "Description",
      hideBelow: "md",
      cell: (r) => (
        <span className="line-clamp-1 text-muted-foreground">
          {r.description || "—"}
        </span>
      ),
    },
    {
      key: "members",
      header: "Members",
      align: "right",
      cell: (r) => (
        <span className="tabular">{formatNumber(r.member_count)}</span>
      ),
    },
    {
      key: "permissions",
      header: "Permissions",
      align: "right",
      hideBelow: "sm",
      cell: (r) => (
        <span className="tabular">{formatNumber(r.permissions.length)}</span>
      ),
    },
  ];

  return (
    <PageShell>
      <PageHeader
        title="Roles & permissions"
        description="Roles bundle permissions. Members get the combined permissions of all their roles."
        actions={
          can("admin.roles.manage") && (
            <Button asChild>
              <Link href="/settings/roles/new">
                <Plus /> New role
              </Link>
            </Button>
          )
        }
      />
      <Tabs
        value={state.tab === "matrix" ? "matrix" : "roles"}
        onValueChange={(v) => setState({ tab: v })}
      >
        <TabsList>
          <TabsTrigger value="roles">Roles</TabsTrigger>
          <TabsTrigger value="matrix">Permission matrix</TabsTrigger>
        </TabsList>
        <TabsContent value="roles">
          <DataTable
            caption="Roles"
            columns={columns}
            rows={roles.data}
            getRowId={(r) => r.id}
            rowHref={(r) => `/settings/roles/${r.id}`}
            loading={roles.isPending}
            error={roles.error}
            onRetry={() => void roles.refetch()}
            loadingRows={6}
            empty={
              <EmptyState compact icon={ShieldCheck} title="No roles yet" />
            }
          />
        </TabsContent>
        <TabsContent value="matrix">
          {roles.isError || permissions.isError ? (
            <ErrorState
              error={roles.error ?? permissions.error}
              onRetry={() => {
                void roles.refetch();
                void permissions.refetch();
              }}
            />
          ) : !roles.data || !permissions.data ? (
            <Skeleton className="h-96 rounded-xl" />
          ) : (
            <PermissionMatrix
              roles={roles.data}
              permissions={permissions.data}
            />
          )}
        </TabsContent>
      </Tabs>
    </PageShell>
  );
}

function PermissionMatrix({
  roles,
  permissions,
}: {
  roles: Role[];
  permissions: Permission[];
}) {
  const groups = groupPermissions(permissions);
  const sets = new Map(roles.map((r) => [r.id, new Set(r.permissions)]));
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
      <div className="scrollbar-thin max-h-[70vh] overflow-auto">
        <table className="w-full border-collapse text-[13px]">
          <caption className="sr-only">
            Permissions granted to each role
          </caption>
          <thead className="sticky top-0 z-[2] bg-surface-muted">
            <tr className="border-b border-border">
              <th
                scope="col"
                className="sticky left-0 z-[3] min-w-52 bg-surface-muted px-3 py-2 text-left text-xs font-medium text-muted-foreground"
              >
                Permission
              </th>
              {roles.map((r) => (
                <th
                  key={r.id}
                  scope="col"
                  className="min-w-24 px-2 py-2 text-center text-xs font-medium whitespace-nowrap text-muted-foreground"
                >
                  <Link
                    href={`/settings/roles/${r.id}`}
                    className="hover:text-foreground hover:underline"
                  >
                    {r.name}
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map(([group, items]) => (
              <GroupRows
                key={group}
                group={group}
                items={items}
                roles={roles}
                sets={sets}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GroupRows({
  group,
  items,
  roles,
  sets,
}: {
  group: string;
  items: Permission[];
  roles: Role[];
  sets: Map<string, Set<string>>;
}) {
  return (
    <>
      <tr className="border-b border-border bg-surface-muted/50">
        <th
          scope="colgroup"
          colSpan={roles.length + 1}
          className="sticky left-0 px-3 py-1.5 text-left text-2xs font-semibold tracking-wide text-muted-foreground uppercase"
        >
          {group}
        </th>
      </tr>
      {items.map((p) => (
        <tr
          key={p.key}
          className="border-b border-border last:border-0 hover:bg-surface-muted/40"
        >
          <th
            scope="row"
            className="sticky left-0 z-[1] bg-surface px-3 py-2 text-left font-normal"
          >
            <span className="block font-medium">{p.label}</span>
            <span className="block font-mono text-2xs text-muted-foreground">
              {p.key}
            </span>
          </th>
          {roles.map((r) => {
            const has = sets.get(r.id)?.has(p.key) ?? false;
            return (
              <td key={r.id} className="px-2 py-2 text-center">
                {has ? (
                  <Check
                    className="mx-auto size-4 text-success"
                    aria-label="Granted"
                  />
                ) : (
                  <span className="text-border-strong" aria-label="Not granted">
                    ·
                  </span>
                )}
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}
