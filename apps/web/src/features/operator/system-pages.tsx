"use client";

import * as React from "react";
import { FileClock, Search, ServerCog, Users } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { apiRequest } from "@/services/api-client";
import { OperatorShell } from "./operator-pages";
import type { OperatorMe } from "./service";

const pretty = (value: string | null | undefined) =>
  (value ?? "—").replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
const when = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

// ------------------------------------------------------------------ users

interface UserRow {
  id: string;
  email: string;
  name: string;
  status: "active" | "inactive";
  created_at: string;
  last_seen_at: string | null;
  workspaces: string[];
  operator_role: string | null;
  is_you: boolean;
}
interface UserPage {
  items: UserRow[];
  total: number;
  page: number;
  page_size: number;
}
const usersApi = {
  list: (q: { search: string; status: string; page: number }) =>
    apiRequest<UserPage>("GET", "/operator/users", null, {
      query: {
        search: q.search || undefined,
        status: q.status || undefined,
        page: q.page,
        page_size: 25,
      },
    }),
  setStatus: (id: string, body: { status: string; reason: string }) =>
    apiRequest<{ status: string; sessions_revoked: number }>(
      "POST",
      `/operator/users/${id}/status`,
      null,
      { body },
    ),
  signOut: (id: string) =>
    apiRequest<{ sessions_revoked: number }>(
      "POST",
      `/operator/users/${id}/sign-out`,
      null,
    ),
};

export function OperatorUsersPage() {
  return (
    <OperatorShell
      title="Users"
      description="Everyone with an account on the platform, the workspaces they belong to, and when they were last seen. No passwords or customer content."
    >
      {(me) => <UsersView me={me} />}
    </OperatorShell>
  );
}

function UsersView({ me }: { me: OperatorMe }) {
  const canRead = me.capabilities.includes("operator.users.read");
  const canManage = me.capabilities.includes("operator.users.manage");
  const [search, setSearch] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [acting, setActing] = React.useState<UserRow | null>(null);
  const list = useScopedQuery(
    ["operator", "users", query, status, page],
    () => usersApi.list({ search: query, status, page }),
    { enabled: canRead },
  );
  if (!canRead)
    return (
      <EmptyState
        icon={Users}
        title="Not available for your role"
        description="Ask a super admin for user access."
      />
    );
  const pages = list.data
    ? Math.max(1, Math.ceil(list.data.total / list.data.page_size))
    : 1;
  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(1);
          setQuery(search.trim());
        }}
      >
        <div className="relative min-w-0 flex-1 sm:max-w-sm">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            aria-label="Search by name or email"
            placeholder="Search name or email"
            className="pl-8"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <NativeSelect
          aria-label="Account status"
          className="w-auto"
          value={status}
          onChange={(e) => {
            setPage(1);
            setStatus(e.target.value);
          }}
        >
          <option value="">All accounts</option>
          <option value="active">Active</option>
          <option value="inactive">Disabled</option>
        </NativeSelect>
        <Button type="submit" variant="secondary">
          Search
        </Button>
        {list.data ? (
          <span className="ml-auto text-[13px] text-muted-foreground">
            {list.data.total.toLocaleString()} account(s)
          </span>
        ) : null}
      </form>
      {list.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !list.data.items.length ? (
        <EmptyState
          icon={Users}
          title="No accounts found"
          description="Try a different name or email."
        />
      ) : (
        <Card className="divide-y divide-border">
          {list.data.items.map((u) => (
            <div key={u.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary-soft-foreground">
                {(u.name || u.email).slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-medium">
                    {u.name || u.email}
                  </span>
                  {u.is_you ? <Badge tone="info">You</Badge> : null}
                  {u.operator_role ? (
                    <Badge tone="pi">
                      Operator · {pretty(u.operator_role)}
                    </Badge>
                  ) : null}
                  <Badge tone={u.status === "active" ? "success" : "danger"}>
                    {u.status === "active" ? "Active" : "Disabled"}
                  </Badge>
                </div>
                <p className="truncate text-[13px] text-muted-foreground">
                  {u.email} · joined {when(u.created_at)} · last seen{" "}
                  {when(u.last_seen_at)}
                </p>
                {u.workspaces.length ? (
                  <p className="truncate text-[12px] text-muted-foreground">
                    {u.workspaces.join(", ")}
                  </p>
                ) : null}
              </div>
              {canManage && !u.is_you ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setActing(u)}
                >
                  Manage
                </Button>
              ) : null}
            </div>
          ))}
        </Card>
      )}
      {list.data && pages > 1 ? (
        <div className="flex items-center justify-end gap-2 text-[13px]">
          <Button
            size="sm"
            variant="secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span>
            Page {page} of {pages}
          </span>
          <Button
            size="sm"
            variant="secondary"
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      ) : null}
      {acting ? (
        <UserDialog user={acting} onClose={() => setActing(null)} />
      ) : null}
    </div>
  );
}

function UserDialog({ user, onClose }: { user: UserRow; onClose: () => void }) {
  const [reason, setReason] = React.useState("");
  const invalidate = [["operator", "users"]];
  const enabled = user.status === "active";
  const status = useScopedMutation(
    () =>
      usersApi.setStatus(user.id, {
        status: enabled ? "inactive" : "active",
        reason: reason.trim(),
      }),
    {
      invalidate,
      success: enabled
        ? `${user.email} disabled and signed out`
        : `${user.email} enabled`,
      onSuccess: onClose,
    },
  );
  const signOut = useScopedMutation(() => usersApi.signOut(user.id), {
    invalidate,
    success: (r) => `Signed out of ${r.sessions_revoked} session(s)`,
    onSuccess: onClose,
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader
          title={user.name || user.email}
          description="Every change is recorded in the audit log with your reason."
        />
        <DialogBody className="space-y-3 text-[13px]">
          <p>
            {enabled
              ? "Disabling stops this person from signing in and ends their open sessions. Their workspaces and data are not touched."
              : "Enabling lets this person sign in again."}
          </p>
          <label className="block space-y-1">
            <span className="font-medium">Reason</span>
            <Textarea
              value={reason}
              maxLength={300}
              placeholder="e.g. Requested by the workspace owner"
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
        </DialogBody>
        <DialogFooter>
          <Button
            variant="secondary"
            loading={signOut.isPending}
            onClick={() => signOut.mutate(undefined)}
          >
            Sign out everywhere
          </Button>
          <Button
            variant={enabled ? "danger" : "default"}
            loading={status.isPending}
            disabled={reason.trim().length < 3}
            onClick={() => status.mutate(undefined)}
          >
            {enabled ? "Disable account" : "Enable account"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ audit

interface AuditRow {
  id: string;
  at: string;
  workspace: string | null;
  tenant_id: string | null;
  action: string;
  actor: string | null;
  actor_type: string | null;
  entity_type: string | null;
  outcome: string;
  details: Record<string, unknown> | null;
}

export function OperatorAuditPage() {
  return (
    <OperatorShell
      title="Audit log"
      description="Who did what, across every workspace. Details are the recorded metadata only, never secrets or customer messages."
    >
      {(me) => <AuditView me={me} />}
    </OperatorShell>
  );
}

const ACTION_FILTERS = [
  ["", "Everything"],
  ["pi_operator.", "Operator actions"],
  ["pi_operator.review_", "Business reviews"],
  ["pi_operator.platform_key_", "Platform keys"],
  ["pi_operator.user_", "User accounts"],
  ["pi_saas.pool_number", "WhatsApp numbers"],
  ["auth.", "Sign-ins"],
];

function AuditView({ me }: { me: OperatorMe }) {
  const allowed = me.capabilities.includes("operator.audit.read");
  const [action, setAction] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [open, setOpen] = React.useState<AuditRow | null>(null);
  const list = useScopedQuery(
    ["operator", "audit", action, page],
    () =>
      apiRequest<{ items: AuditRow[]; page: number; has_more: boolean }>(
        "GET",
        "/operator/audit",
        null,
        { query: { action: action || undefined, page, page_size: 50 } },
      ),
    { enabled: allowed },
  );
  if (!allowed)
    return (
      <EmptyState
        icon={FileClock}
        title="Not available for your role"
        description="Ask a super admin for audit access."
      />
    );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter">
        {ACTION_FILTERS.map(([value, text]) => (
          <Button
            key={value}
            role="tab"
            aria-selected={action === value}
            size="sm"
            variant={action === value ? "default" : "secondary"}
            onClick={() => {
              setPage(1);
              setAction(value);
            }}
          >
            {text}
          </Button>
        ))}
      </div>
      {list.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !list.data.items.length ? (
        <EmptyState icon={FileClock} title="Nothing recorded yet" />
      ) : (
        <Card className="divide-y divide-border">
          {list.data.items.map((e) => (
            <button
              key={e.id}
              type="button"
              className="flex w-full flex-wrap items-center gap-3 p-3 text-left hover:bg-surface-muted"
              onClick={() => setOpen(e)}
            >
              <span className="w-36 shrink-0 text-[12px] tabular-nums text-muted-foreground">
                {when(e.at)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-[12px]">
                  {e.action}
                </span>
                <span className="block truncate text-[12px] text-muted-foreground">
                  {e.actor || pretty(e.actor_type)} ·{" "}
                  {e.workspace || "Platform"}
                </span>
              </span>
              <Badge tone={e.outcome === "success" ? "success" : "warning"}>
                {pretty(e.outcome)}
              </Badge>
            </button>
          ))}
        </Card>
      )}
      {list.data ? (
        <div className="flex items-center justify-end gap-2 text-[13px]">
          <Button
            size="sm"
            variant="secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Newer
          </Button>
          <span>Page {page}</span>
          <Button
            size="sm"
            variant="secondary"
            disabled={!list.data.has_more}
            onClick={() => setPage((p) => p + 1)}
          >
            Older
          </Button>
        </div>
      ) : null}
      {open ? (
        <Dialog open onOpenChange={(o) => !o && setOpen(null)}>
          <DialogContent>
            <DialogHeader title={open.action} description={when(open.at)} />
            <DialogBody className="space-y-2 text-[13px]">
              <p>
                <span className="text-muted-foreground">By:</span>{" "}
                {open.actor || pretty(open.actor_type)}
              </p>
              <p>
                <span className="text-muted-foreground">Workspace:</span>{" "}
                {open.workspace || "Platform"}
              </p>
              <p>
                <span className="text-muted-foreground">Record:</span>{" "}
                {pretty(open.entity_type)}
              </p>
              <pre className="max-h-64 overflow-auto rounded-md bg-surface-muted p-3 text-[12px]">
                {JSON.stringify(open.details ?? {}, null, 2)}
              </pre>
            </DialogBody>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ system

interface SystemView {
  workspaces: Record<string, number>;
  users: Record<string, number>;
  pi_businesses: Record<string, number>;
  subscriptions: Record<string, number>;
  whatsapp_numbers: Record<string, number>;
  pool_numbers: Record<string, number>;
  operators: number;
  messages_24h: { received: number; sent: number; failed: number };
  failed_events: number;
  runtime: {
    environment: string;
    database_revision: string | null;
    job_queue: string;
    kapso_billing_mode: string;
  };
  generated_at: string;
}

const sum = (counts: Record<string, number>) =>
  Object.values(counts).reduce((a, b) => a + b, 0);

export function OperatorSystemPage() {
  return (
    <OperatorShell
      title="System"
      description="Platform counts and runtime state, refreshed every minute."
    >
      {(me) => <SystemStatus me={me} />}
    </OperatorShell>
  );
}

function SystemStatus({ me }: { me: OperatorMe }) {
  const allowed = me.capabilities.includes("operator.system.read");
  const sys = useScopedQuery(
    ["operator", "system"],
    () => apiRequest<SystemView>("GET", "/operator/system", null),
    { enabled: allowed, refetchInterval: 60_000 },
  );
  if (!allowed)
    return (
      <EmptyState
        icon={ServerCog}
        title="Not available for your role"
        description="Ask a super admin for system access."
      />
    );
  if (sys.isPending) return <Skeleton className="h-64 w-full" />;
  if (sys.isError)
    return <ErrorState error={sys.error} onRetry={() => sys.refetch()} />;
  const d = sys.data;
  const groups: [string, Record<string, number>][] = [
    ["Workspaces", d.workspaces],
    ["User accounts", d.users],
    ["Pi businesses (setup)", d.pi_businesses],
    ["Subscriptions", d.subscriptions],
    ["WhatsApp connections", d.whatsapp_numbers],
    ["Number pool", d.pool_numbers],
  ];
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {(
          [
            ["Messages received (24h)", d.messages_24h.received, "neutral"],
            ["Messages sent (24h)", d.messages_24h.sent, "neutral"],
            [
              "Failed sends (24h)",
              d.messages_24h.failed,
              d.messages_24h.failed ? "danger" : "neutral",
            ],
            [
              "Failed events",
              d.failed_events,
              d.failed_events ? "warning" : "neutral",
            ],
          ] as const
        ).map(([text, value, tone]) => (
          <Card key={text} className="p-4">
            <p className="text-[12px] text-muted-foreground">{text}</p>
            <p
              className={
                "mt-1 text-2xl font-semibold tabular-nums " +
                (tone === "danger"
                  ? "text-danger"
                  : tone === "warning"
                    ? "text-warning"
                    : "")
              }
            >
              {value.toLocaleString()}
            </p>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {groups.map(([title, counts]) => (
          <Card key={title} className="p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="text-[15px] font-semibold">{title}</h2>
              <span className="text-xl font-semibold tabular-nums">
                {sum(counts)}
              </span>
            </div>
            {Object.keys(counts).length ? (
              <ul className="space-y-1 text-[13px]">
                {Object.entries(counts)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => (
                    <li key={k} className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate text-muted-foreground">
                        {pretty(k)}
                      </span>
                      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-muted">
                        <span
                          className="block h-full rounded-full bg-primary"
                          style={{
                            width: `${Math.round((v / Math.max(1, sum(counts))) * 100)}%`,
                          }}
                        />
                      </span>
                      <span className="w-10 text-right tabular-nums">{v}</span>
                    </li>
                  ))}
              </ul>
            ) : (
              <p className="text-[13px] text-muted-foreground">None yet.</p>
            )}
          </Card>
        ))}
      </div>
      <Card className="p-4">
        <h2 className="mb-2 text-[15px] font-semibold">Runtime</h2>
        <dl className="grid gap-x-6 gap-y-2 text-[13px] sm:grid-cols-[200px_1fr]">
          <dt className="text-muted-foreground">Environment</dt>
          <dd>{pretty(d.runtime.environment)}</dd>
          <dt className="text-muted-foreground">Database version</dt>
          <dd className="font-mono text-[12px]">
            {d.runtime.database_revision ?? "Unknown"}
          </dd>
          <dt className="text-muted-foreground">Background jobs</dt>
          <dd>{d.runtime.job_queue}</dd>
          <dt className="text-muted-foreground">Meta message fees</dt>
          <dd>{pretty(d.runtime.kapso_billing_mode)}</dd>
          <dt className="text-muted-foreground">Active operators</dt>
          <dd>{d.operators}</dd>
          <dt className="text-muted-foreground">Updated</dt>
          <dd>{when(d.generated_at)}</dd>
        </dl>
      </Card>
    </div>
  );
}
