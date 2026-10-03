"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  Building2,
  CreditCard,
  LifeBuoy,
  Pause,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UserPlus,
  Users,
} from "lucide-react";
import { PageHeader, PageShell } from "@/components/app/page";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
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
import { cn } from "@/lib/utils";
import { ApiError, apiRequest } from "@/services/api-client";
import { NeedsYouCard, PlansManager } from "./control-pages";
import {
  PlatformChecklistCard,
  WhatsAppUsageCard,
  WorkspaceWhatsAppDialog,
} from "./numbers-page";
import {
  operatorService as api,
  type AgentaAnswer,
  type BusinessDetail,
  type OperatorMe,
  type Plan,
} from "./service";

const STATE_TONE: Record<
  string,
  "neutral" | "primary" | "success" | "warning" | "danger" | "info"
> = {
  draft: "neutral",
  awaiting_connection: "info",
  awaiting_approval: "info",
  ready: "primary",
  active: "success",
  paused: "warning",
  action_required: "danger",
  trialing: "info",
  past_due: "warning",
  suspended: "danger",
  canceled: "neutral",
  connected: "success",
  setup_pending: "info",
  disconnected: "danger",
  inactive: "danger",
};
const label = (value: string | null | undefined) =>
  (value ?? "—").replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());

// Usage counters arrive as decimal strings ("1.000000"); show counts as whole numbers.
const quantity = (value: string | number) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
};

function StateBadge({ value }: { value: string | null | undefined }) {
  return (
    <Badge tone={STATE_TONE[value ?? ""] ?? "neutral"}>{label(value)}</Badge>
  );
}

const date = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "—";

const NAV = [
  { href: "/operator", label: "Overview", cap: "operator.accounts.read" },
  {
    href: "/operator/businesses",
    label: "Pi businesses",
    cap: "operator.accounts.read",
  },
  {
    href: "/operator/reviews",
    label: "Reviews",
    cap: "operator.onboarding.assist",
  },
  {
    href: "/operator/workspaces",
    label: "Workspaces",
    cap: "operator.workspaces.read",
  },
  {
    href: "/operator/numbers",
    label: "Numbers",
    cap: "operator.accounts.read",
  },
  {
    href: "/operator/help",
    label: "Pi help guides",
    cap: "operator.onboarding.assist",
  },
  {
    href: "/settings/pi-billing",
    label: "Subscription payments",
    cap: "operator.billing.read",
  },
  { href: "/operator/plans", label: "Plans", cap: "operator.accounts.read" },
  {
    href: "/operator/events",
    label: "Failed work",
    cap: "operator.health.read",
  },
  {
    href: "/operator/team",
    label: "Operator team",
    cap: "operator.team.manage",
  },
  {
    href: "/operator/users",
    label: "Users",
    cap: "operator.users.read",
  },
  {
    href: "/operator/audit",
    label: "Audit log",
    cap: "operator.audit.read",
  },
  {
    href: "/operator/system",
    label: "System",
    cap: "operator.system.read",
  },
  {
    href: "/operator/keys",
    label: "Platform keys",
    cap: "operator.settings.manage",
  },
];

function useOperator() {
  return useScopedQuery(["operator", "me"], api.me, { retry: false });
}

/** Only the Pi operator team sees the console; the API enforces every capability. */
export function OperatorShell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: (me: OperatorMe) => React.ReactNode;
}) {
  const me = useOperator();
  const pathname = usePathname();
  if (me.isPending) {
    return (
      <PageShell>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-6 h-40 w-full" />
      </PageShell>
    );
  }
  if (me.isError) {
    const denied = me.error instanceof ApiError && me.error.status === 403;
    return (
      <PageShell width="narrow">
        {denied ? (
          <EmptyState
            icon={ShieldCheck}
            title="Operator console"
            description="Only members of the Pi operator team can open this. An operator owner can add you."
          />
        ) : (
          <ErrorState error={me.error} onRetry={() => me.refetch()} />
        )}
      </PageShell>
    );
  }
  const caps = new Set(me.data.capabilities);
  return (
    <PageShell>
      <PageHeader
        eyebrow={`Pi operator · ${me.data.role_name}`}
        title={title}
        description={description}
        actions={actions}
      />
      <nav
        aria-label="Operator sections"
        className="-mx-1 mb-6 overflow-x-auto px-1"
      >
        <div className="flex w-max gap-1 rounded-lg border border-border bg-surface p-1">
          {NAV.filter((n) => caps.has(n.cap)).map((n) => {
            const active =
              n.href === "/operator"
                ? pathname === n.href
                : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-8 items-center whitespace-nowrap rounded-md px-3 text-[13px] font-medium text-foreground-secondary hover:text-foreground",
                  active && "bg-primary-soft text-primary-soft-foreground",
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </div>
      </nav>
      {children(me.data)}
    </PageShell>
  );
}

function Stat({
  label: name,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: "danger" | "warning";
}) {
  return (
    <Card className="p-4">
      <p className="text-[13px] text-muted-foreground">{name}</p>
      <p
        className={cn(
          "mt-1 text-2xl font-semibold tabular-nums",
          tone === "danger" && Number(value) > 0 && "text-danger",
          tone === "warning" && Number(value) > 0 && "text-warning",
        )}
      >
        {value}
      </p>
    </Card>
  );
}

function Loading() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

export function OperatorOverviewPage() {
  return (
    <OperatorShell
      title="Operator console"
      description="Pi businesses, workspaces and platform health."
    >
      {(me) => <Overview me={me} />}
    </OperatorShell>
  );
}

const AGENTA_EXAMPLES = [
  "Which businesses need attention?",
  "Kis ki payment ruki hui hai?",
  "Who is stuck in setup?",
];

/** Pi (Agenta): answers from the same operator services and permissions as this console. */
function AskAgenta() {
  const [question, setQuestion] = React.useState("");
  const [result, setResult] = React.useState<AgentaAnswer | null>(null);
  const ask = useScopedMutation((q: string) => api.agenta(q), {
    onSuccess: (answer) => setResult(answer),
  });
  const submit = (q: string) => {
    const text = q.trim();
    if (text.length < 2) return;
    setQuestion(text);
    ask.mutate(text);
  };
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center gap-2">
        <Sparkles className="size-4 text-primary" aria-hidden />
        <h2 className="text-[15px] font-semibold">Ask Pi</h2>
        <Badge tone="pi">Agenta</Badge>
      </div>
      <p className="mb-3 text-[13px] text-muted-foreground">
        Answers only from what your operator role can see here. Customer
        conversations are never included.
      </p>
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <Input
          aria-label="Ask Pi about your businesses"
          placeholder="Which businesses need attention?"
          value={question}
          maxLength={500}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button type="submit" loading={ask.isPending}>
          Ask
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap gap-2">
        {AGENTA_EXAMPLES.map((q) => (
          <button
            key={q}
            type="button"
            className="rounded-full border border-border px-3 py-1 text-[12px] text-muted-foreground hover:bg-surface-muted"
            onClick={() => submit(q)}
          >
            {q}
          </button>
        ))}
      </div>
      {result ? (
        <div
          className="mt-4 rounded-lg bg-surface-muted p-3 text-[13px]"
          aria-live="polite"
        >
          <p className="whitespace-pre-line">{result.answer}</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {result.links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="font-medium text-primary underline"
              >
                {l.label}
              </Link>
            ))}
            <span className="text-[12px] text-muted-foreground">
              {result.generated_by === "model"
                ? "Worded by AI from console data"
                : "Straight from console data"}
            </span>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function Overview({ me }: { me: OperatorMe }) {
  const caps = new Set(me.capabilities);
  const summary = useScopedQuery(["operator", "summary"], api.summary);
  const weekly = useScopedQuery(["operator", "weekly"], api.weekly);
  const health = useScopedQuery(["operator", "health"], api.health, {
    enabled: caps.has("operator.health.read"),
  });
  if (summary.isPending) return <Loading />;
  if (summary.isError)
    return (
      <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
    );
  const s = summary.data;
  return (
    <div className="space-y-6">
      <NeedsYouCard />
      <AskAgenta />
      <div className="grid gap-4 lg:grid-cols-2">
        <WhatsAppUsageCard />
        <PlatformChecklistCard />
      </div>
      {weekly.data && Object.keys(weekly.data.week).length ? (
        <div>
          <h2 className="mb-2 text-[15px] font-semibold">Last 7 days</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {(
              [
                ["new_businesses", "New businesses"],
                ["went_live", "Went live"],
                ["messages_received", "Customer messages"],
                ["pi_replies", "Replies sent by Pi"],
              ] as const
            )
              .filter(([k]) => weekly.data.week[k] !== undefined)
              .map(([k, label]) => (
                <Stat key={k} label={label} value={weekly.data.week[k] ?? 0} />
              ))}
          </div>
        </div>
      ) : null}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Pi businesses you can see" value={s.businesses} />
        <Stat label="Live" value={s.by_state.active ?? 0} />
        <Stat
          label="Setting up"
          value={
            (s.by_state.draft ?? 0) +
            (s.by_state.awaiting_connection ?? 0) +
            (s.by_state.awaiting_approval ?? 0) +
            (s.by_state.ready ?? 0)
          }
        />
        <Stat
          label="Need attention"
          value={s.by_state.action_required ?? 0}
          tone="danger"
        />
      </div>
      {health.data ? (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat
              label="Failed messages (24h)"
              value={health.data.failed_messages_24h}
              tone="danger"
            />
            <Stat
              label="Failed provider events"
              value={health.data.failed_provider_events}
              tone="danger"
            />
            <Stat
              label="Past-due subscriptions"
              value={health.data.subscriptions_past_due}
              tone="warning"
            />
            <Stat
              label="Help and number requests"
              value={health.data.help_requests + health.data.number_requests}
              tone="warning"
            />
          </div>
          <Card className="p-4">
            <h2 className="mb-3 text-[15px] font-semibold">
              Platform configuration
            </h2>
            <ul className="grid gap-2 text-[13px] sm:grid-cols-2">
              {(
                [
                  [
                    "WhatsApp provider (Kapso) key",
                    health.data.configuration.whatsapp_provider,
                  ],
                  [
                    "Kapso webhook secret",
                    health.data.configuration.provider_webhook_secret,
                  ],
                  [
                    "Subscription billing (Stripe) key",
                    health.data.configuration.billing,
                  ],
                  [
                    "Billing webhook secret",
                    health.data.configuration.billing_webhook_secret,
                  ],
                  [
                    "Background worker (ARQ)",
                    health.data.configuration.job_queue === "arq",
                  ],
                  [
                    "AI provider configured",
                    health.data.configuration.ai_providers.length > 0,
                  ],
                ] as [string, boolean][]
              ).map(([name, ok]) => (
                <li
                  key={name}
                  className="flex items-center justify-between gap-3 rounded-md bg-surface-muted px-3 py-2"
                >
                  <span>{name}</span>
                  <Badge tone={ok ? "success" : "warning"}>
                    {ok ? "Configured" : "Not configured"}
                  </Badge>
                </li>
              ))}
            </ul>
          </Card>
        </>
      ) : null}
      <Card className="p-4">
        <h2 className="mb-3 text-[15px] font-semibold">Needs attention</h2>
        {s.needs_attention.length ? (
          <ul className="divide-y divide-border">
            {s.needs_attention.map((a) => (
              <li key={a.tenant_id}>
                <Link
                  href={`/operator/businesses/${a.tenant_id}`}
                  className="flex items-center gap-3 py-2 text-[14px] hover:text-primary"
                >
                  <AlertTriangle className="size-4 text-warning" aria-hidden />
                  <span className="flex-1">{a.name}</span>
                  <StateBadge value={a.state} />
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-muted-foreground">
            Nothing needs attention.
          </p>
        )}
      </Card>
    </div>
  );
}

export function OperatorBusinessesPage() {
  const [search, setSearch] = React.useState("");
  const [state, setState] = React.useState("");
  const [page, setPage] = React.useState(1);
  const list = useScopedQuery(
    ["operator", "businesses", search, state, page],
    () =>
      api.businesses({
        search: search || undefined,
        state: state || undefined,
        page,
        page_size: 25,
      }),
    { placeholderData: (previous) => previous },
  );
  return (
    <OperatorShell
      title="Pi businesses"
      description="Onboarding, connection and plan state. Customer conversations are not shown here."
    >
      {() => (
        <div className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              aria-label="Search businesses"
              placeholder="Search by name"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="sm:max-w-xs"
            />
            <NativeSelect
              aria-label="Filter by state"
              value={state}
              onChange={(e) => {
                setState(e.target.value);
                setPage(1);
              }}
              className="sm:w-52"
            >
              <option value="">All states</option>
              {Object.keys(STATE_TONE)
                .slice(0, 7)
                .map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
            </NativeSelect>
          </div>
          {list.isPending ? (
            <Loading />
          ) : list.isError ? (
            <ErrorState error={list.error} onRetry={() => list.refetch()} />
          ) : list.data.items.length === 0 ? (
            <EmptyState
              icon={Building2}
              title="No businesses"
              description="Businesses appear here after they sign up for Pi."
            />
          ) : (
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead className="text-left text-muted-foreground">
                    <tr className="border-b border-border">
                      <th className="px-4 py-2 font-medium">Business</th>
                      <th className="px-4 py-2 font-medium">Setup</th>
                      <th className="hidden px-4 py-2 font-medium md:table-cell">
                        WhatsApp
                      </th>
                      <th className="hidden px-4 py-2 font-medium md:table-cell">
                        Plan
                      </th>
                      <th className="hidden px-4 py-2 font-medium lg:table-cell">
                        Joined
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.data.items.map((b) => (
                      <tr
                        key={b.tenant_id}
                        className="border-b border-border last:border-0 hover:bg-surface-muted"
                      >
                        <td className="px-4 py-2.5">
                          <Link
                            href={`/operator/businesses/${b.tenant_id}`}
                            className="font-medium hover:text-primary"
                          >
                            {b.name}
                          </Link>
                          {b.help_requested ? (
                            <Badge tone="info" className="ml-2">
                              <LifeBuoy aria-hidden /> Help requested
                            </Badge>
                          ) : null}
                          {b.status !== "active" ? (
                            <Badge tone="danger" className="ml-2">
                              {label(b.status)}
                            </Badge>
                          ) : null}
                        </td>
                        <td className="px-4 py-2.5">
                          <StateBadge value={b.setup_state} />
                        </td>
                        <td className="hidden px-4 py-2.5 md:table-cell">
                          <StateBadge value={b.connection_status} />
                        </td>
                        <td className="hidden px-4 py-2.5 md:table-cell">
                          {label(b.plan)} ·{" "}
                          <StateBadge value={b.subscription_status} />
                        </td>
                        <td className="hidden px-4 py-2.5 text-muted-foreground lg:table-cell">
                          {date(b.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between border-t border-border px-4 py-2 text-[13px]">
                <span className="text-muted-foreground">
                  {list.data.total} businesses
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={page * list.data.page_size >= list.data.total}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </Card>
          )}
        </div>
      )}
    </OperatorShell>
  );
}

function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  confirm,
  tone = "default",
  onConfirm,
  loading,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description: string;
  confirm: string;
  tone?: "default" | "danger";
  onConfirm: (reason: string) => void;
  loading?: boolean;
}) {
  const [reason, setReason] = React.useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader title={title} description={description} />
        <DialogBody>
          <label className="text-[13px] font-medium" htmlFor="reason">
            Reason (recorded in the audit log)
          </label>
          <Textarea
            id="reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={300}
            className="mt-1"
          />
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant={tone === "danger" ? "danger" : "default"}
            disabled={reason.trim().length < 3}
            loading={loading}
            onClick={() => onConfirm(reason.trim())}
          >
            {confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function OperatorBusinessPage({ id }: { id: string }) {
  return (
    <OperatorShell
      title="Pi business"
      description="Operational view. Customer content needs the business's approval."
    >
      {(me) => <BusinessDetailView id={id} me={me} />}
    </OperatorShell>
  );
}

function BusinessDetailView({ id, me }: { id: string; me: OperatorMe }) {
  const caps = new Set(me.capabilities);
  const detail = useScopedQuery(["operator", "business", id], () =>
    api.business(id),
  );
  const [dialog, setDialog] = React.useState<
    null | "pause" | "suspend" | "reinstate" | "support" | "plan"
  >(null);
  const invalidate = [["operator"]];
  const pause = useScopedMutation((reason: string) => api.pause(id, reason), {
    invalidate,
    success: "Pi paused for this business",
    onSuccess: () => setDialog(null),
  });
  const resume = useScopedMutation(() => api.resume(id), {
    invalidate,
    success: "Pi resumed",
  });
  const status = useScopedMutation(
    ({ value, reason }: { value: "active" | "suspended"; reason: string }) =>
      api.accountStatus(id, value, reason),
    {
      invalidate,
      success: "Account status updated",
      onSuccess: () => setDialog(null),
    },
  );
  const support = useScopedMutation(
    (body: { scope: string; reason: string; days: number }) =>
      api.requestSupport(id, body),
    {
      invalidate,
      success: "Request sent. The business must approve it.",
      onSuccess: () => setDialog(null),
    },
  );
  const subscription = useScopedMutation(
    (body: {
      plan?: string;
      status?: string;
      extend_trial_days?: number;
      reason: string;
    }) => api.subscription(id, body),
    {
      invalidate,
      success: "Subscription updated",
      onSuccess: () => setDialog(null),
    },
  );
  const plans = useScopedQuery(["operator", "plans"], api.plans, {
    enabled: caps.has("operator.billing.manage"),
  });
  if (detail.isPending) return <Loading />;
  if (detail.isError)
    return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  const d: BusinessDetail = detail.data;
  return (
    <div className="space-y-5">
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">{d.name}</h2>
          <StateBadge value={d.setup_state} />
          {d.status !== "active" ? <StateBadge value={d.status} /> : null}
          <span className="ml-auto flex flex-wrap gap-2">
            {caps.has("operator.accounts.manage") &&
            d.setup_state === "active" ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setDialog("pause")}
              >
                <Pause aria-hidden /> Pause Pi
              </Button>
            ) : null}
            {caps.has("operator.accounts.manage") &&
            ["paused", "action_required", "ready"].includes(d.setup_state) ? (
              <Button
                size="sm"
                variant="secondary"
                loading={resume.isPending}
                onClick={() => resume.mutate(undefined)}
              >
                <Play aria-hidden /> Resume
              </Button>
            ) : null}
            {caps.has("operator.support.request") ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setDialog("support")}
              >
                <LifeBuoy aria-hidden /> Request access
              </Button>
            ) : null}
            {caps.has("operator.accounts.manage") ? (
              d.status === "active" ? (
                <Button
                  size="sm"
                  variant="danger-outline"
                  onClick={() => setDialog("suspend")}
                >
                  Suspend
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setDialog("reinstate")}
                >
                  Reinstate
                </Button>
              )
            ) : null}
          </span>
        </div>
        <dl className="mt-3 grid gap-x-6 gap-y-1 text-[13px] sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">Offers</dt>
            <dd>{label(d.offer_type)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Language / time zone</dt>
            <dd>
              {d.language} · {d.timezone}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Launched</dt>
            <dd>{date(d.launched_at)}</dd>
          </div>
        </dl>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-4">
          <h3 className="mb-2 font-semibold">Go-live checklist</h3>
          <ul className="space-y-1 text-[13px]">
            {d.readiness.map((r) => (
              <li key={r.key} className="flex items-center justify-between">
                <span>{r.label}</span>
                <Badge tone={r.done ? "success" : "neutral"}>
                  {r.done ? "Done" : "Not yet"}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="p-4">
          <h3 className="mb-2 font-semibold">WhatsApp</h3>
          {d.connections.length ? (
            <ul className="space-y-2 text-[13px]">
              {d.connections.map((c) => (
                <li
                  key={c.environment}
                  className="rounded-md bg-surface-muted p-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="outline">{label(c.environment)}</Badge>
                    <StateBadge value={c.status} />
                    <span>{c.display_phone_number ?? "No number yet"}</span>
                    {c.problem ? (
                      <Badge tone="danger">{label(c.problem)}</Badge>
                    ) : null}
                  </div>
                  {c.number_request?.status ? (
                    <p className="mt-1 text-muted-foreground">
                      New number request ({c.number_request.country}):{" "}
                      {label(c.number_request.status)}
                      {c.number_request.quote
                        ? ` · quoted ${c.number_request.quote.monthly_price} ${c.number_request.quote.currency}/month`
                        : ""}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-muted-foreground">Not started.</p>
          )}
          {caps.has("operator.numbers.manage") ? (
            <NumberRequestActions detail={d} />
          ) : null}
        </Card>
        {d.subscription !== undefined ? (
          <Card className="p-4">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="font-semibold">Subscription</h3>
              <StateBadge value={d.subscription?.status} />
              {caps.has("operator.billing.manage") ? (
                <Button
                  size="xs"
                  variant="secondary"
                  className="ml-auto"
                  onClick={() => setDialog("plan")}
                >
                  <CreditCard aria-hidden /> Change
                </Button>
              ) : null}
            </div>
            {d.subscription ? (
              <dl className="grid grid-cols-2 gap-y-1 text-[13px]">
                <dt className="text-muted-foreground">Plan</dt>
                <dd>{label(d.subscription.plan)}</dd>
                <dt className="text-muted-foreground">Billed by</dt>
                <dd>{label(d.subscription.billing_provider)}</dd>
                <dt className="text-muted-foreground">Trial ends</dt>
                <dd>{date(d.subscription.trial_ends_at)}</dd>
                <dt className="text-muted-foreground">Period ends</dt>
                <dd>{date(d.subscription.current_period_end)}</dd>
              </dl>
            ) : (
              <p className="text-[13px] text-muted-foreground">
                No subscription.
              </p>
            )}
            {d.invoices?.length ? (
              <ul className="mt-3 divide-y divide-border text-[13px]">
                {d.invoices.map((i) => (
                  <li key={i.number} className="flex justify-between py-1">
                    <span>{i.number || "Invoice"}</span>
                    <span>
                      {i.amount_due} {i.currency} · {label(i.status)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
            <Link
              href="/settings/pi-billing"
              className="mt-3 inline-block text-[13px] text-primary underline"
            >
              Bank and cash payments
            </Link>
          </Card>
        ) : null}
        <Card className="p-4">
          <h3 className="mb-2 font-semibold">
            Collecting from their customers
          </h3>
          <p className="mb-2 text-[13px] text-muted-foreground">
            Payment methods this business has switched on. Balances and account
            details stay private to the business.
          </p>
          <div className="flex flex-wrap gap-2">
            {d.customer_payment_methods.length ? (
              d.customer_payment_methods.map((m) => (
                <Badge key={m} tone="primary">
                  {label(m)}
                </Badge>
              ))
            ) : (
              <span className="text-[13px] text-muted-foreground">
                None yet
              </span>
            )}
          </div>
          {d.usage ? (
            <>
              <h3 className="mb-1 mt-4 font-semibold">Usage this month</h3>
              <dl className="grid grid-cols-2 gap-y-1 text-[13px]">
                {Object.entries(d.usage.production).map(([k, v]) => (
                  <React.Fragment key={k}>
                    <dt className="text-muted-foreground">{label(k)}</dt>
                    <dd className="tabular-nums">{quantity(v)}</dd>
                  </React.Fragment>
                ))}
              </dl>
            </>
          ) : null}
        </Card>
        <Card className="p-4 lg:col-span-2">
          <h3 className="mb-2 font-semibold">Support access</h3>
          <p className="mb-2 text-[13px] text-muted-foreground">
            Granted and revoked by the business. Every read of customer content
            is audited.
          </p>
          {d.support_grants.length ? (
            <ul className="divide-y divide-border text-[13px]">
              {d.support_grants.map((g) => (
                <li
                  key={g.id}
                  className="flex flex-wrap items-center gap-2 py-1.5"
                >
                  <span className="flex-1">
                    {label(g.scope)} · requested by {g.requested_by}
                  </span>
                  <StateBadge value={g.status} />
                  <span className="text-muted-foreground">
                    until {date(g.expires_at)}
                  </span>
                  {g.status === "active" && g.scope !== "configuration" ? (
                    <Link
                      href={`/operator/businesses/${d.tenant_id}/conversations`}
                      className="text-primary underline"
                    >
                      Open
                    </Link>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              No access granted.
            </p>
          )}
        </Card>
      </div>

      <ReasonDialog
        open={dialog === "pause"}
        onOpenChange={(v) => setDialog(v ? "pause" : null)}
        title="Pause Pi for this business?"
        description="Pi stops replying to their customers. Their team keeps handling messages."
        confirm="Pause Pi"
        loading={pause.isPending}
        onConfirm={(reason) => pause.mutate(reason)}
      />
      <ReasonDialog
        open={dialog === "suspend"}
        onOpenChange={(v) => setDialog(v ? "suspend" : null)}
        title="Suspend this business?"
        description="All sending stops. Data is kept and the business can be reinstated."
        confirm="Suspend"
        tone="danger"
        loading={status.isPending}
        onConfirm={(reason) => status.mutate({ value: "suspended", reason })}
      />
      <ReasonDialog
        open={dialog === "reinstate"}
        onOpenChange={(v) => setDialog(v ? "reinstate" : null)}
        title="Reinstate this business?"
        description="Sending is allowed again. Pi stays paused until it is resumed."
        confirm="Reinstate"
        loading={status.isPending}
        onConfirm={(reason) => status.mutate({ value: "active", reason })}
      />
      <SupportDialog
        open={dialog === "support"}
        onOpenChange={(v) => setDialog(v ? "support" : null)}
        loading={support.isPending}
        onSubmit={(body) => support.mutate(body)}
      />
      <PlanDialog
        open={dialog === "plan"}
        onOpenChange={(v) => setDialog(v ? "plan" : null)}
        plans={plans.data ?? []}
        current={d.subscription?.plan}
        loading={subscription.isPending}
        onSubmit={(body) => subscription.mutate(body)}
      />
    </div>
  );
}

function NumberRequestActions({ detail }: { detail: BusinessDetail }) {
  const production = detail.connections.find(
    (c) => c.environment === "production",
  );
  const status = production?.number_request?.status;
  const [open, setOpen] = React.useState(false);
  const [quote, setQuote] = React.useState({
    monthly_price: "",
    setup_fee: "0",
    currency: "USD",
    phone_number_preview: "",
    note: "",
  });
  const save = useScopedMutation(
    () => api.numberQuote(detail.tenant_id, quote),
    {
      invalidate: [["operator"]],
      success: "Quote sent. The business must accept it.",
      onSuccess: () => setOpen(false),
    },
  );
  const link = useScopedMutation(() => api.numberLink(detail.tenant_id), {
    invalidate: [["operator"]],
    success: "Setup link ready for the business",
  });
  if (!status) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {status === "requested" || status === "quoted" ? (
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          Enter real price and availability
        </Button>
      ) : null}
      {status === "confirmed" ? (
        <Button
          size="sm"
          loading={link.isPending}
          onClick={() => link.mutate(undefined)}
        >
          Prepare provisioning link
        </Button>
      ) : null}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader
            title="Number quote"
            description="Use the provider's real price. The business confirms before anything is bought."
          />
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <Input
              aria-label="Monthly price"
              placeholder="Monthly price"
              inputMode="decimal"
              value={quote.monthly_price}
              onChange={(e) =>
                setQuote((q) => ({ ...q, monthly_price: e.target.value }))
              }
            />
            <Input
              aria-label="Setup fee or deposit"
              placeholder="Setup fee / deposit"
              inputMode="decimal"
              value={quote.setup_fee}
              onChange={(e) =>
                setQuote((q) => ({ ...q, setup_fee: e.target.value }))
              }
            />
            <Input
              aria-label="Currency"
              value={quote.currency}
              maxLength={3}
              onChange={(e) =>
                setQuote((q) => ({
                  ...q,
                  currency: e.target.value.toUpperCase(),
                }))
              }
            />
            <Input
              aria-label="Number preview"
              placeholder="+971 …"
              value={quote.phone_number_preview}
              onChange={(e) =>
                setQuote((q) => ({
                  ...q,
                  phone_number_preview: e.target.value,
                }))
              }
            />
            <Textarea
              aria-label="Note for the business"
              placeholder="Verification needed, timing…"
              className="sm:col-span-2"
              value={quote.note}
              onChange={(e) =>
                setQuote((q) => ({ ...q, note: e.target.value }))
              }
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!/^\d+(\.\d{1,2})?$/.test(quote.monthly_price)}
              loading={save.isPending}
              onClick={() => save.mutate(undefined)}
            >
              Send quote
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SupportDialog({
  open,
  onOpenChange,
  onSubmit,
  loading,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSubmit: (b: { scope: string; reason: string; days: number }) => void;
  loading?: boolean;
}) {
  const [scope, setScope] = React.useState("configuration");
  const [reason, setReason] = React.useState("");
  const [days, setDays] = React.useState("7");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title="Request support access"
          description="The business sees this request and decides. Nothing is granted until they approve."
        />
        <DialogBody className="space-y-3">
          <NativeSelect
            aria-label="Access needed"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
          >
            <option value="configuration">
              Prepare settings and knowledge
            </option>
            <option value="conversations">Read customer conversations</option>
            <option value="full_support">
              Read and reply to conversations
            </option>
          </NativeSelect>
          <NativeSelect
            aria-label="For how long"
            value={days}
            onChange={(e) => setDays(e.target.value)}
          >
            {[1, 3, 7, 14, 30].map((d) => (
              <option key={d} value={d}>
                {d} day{d === 1 ? "" : "s"}
              </option>
            ))}
          </NativeSelect>
          <Textarea
            aria-label="Why you need access"
            placeholder="Why you need access (the business sees this)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={300}
          />
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={reason.trim().length < 5}
            loading={loading}
            onClick={() =>
              onSubmit({ scope, reason: reason.trim(), days: Number(days) })
            }
          >
            Send request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PlanDialog({
  open,
  onOpenChange,
  plans,
  current,
  onSubmit,
  loading,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  plans: Plan[];
  current?: string;
  onSubmit: (b: {
    plan?: string;
    status?: string;
    extend_trial_days?: number;
    reason: string;
  }) => void;
  loading?: boolean;
}) {
  const [plan, setPlan] = React.useState(current ?? "");
  const [status, setStatus] = React.useState("");
  const [extend, setExtend] = React.useState("");
  const [reason, setReason] = React.useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title="Change subscription"
          description="For invoiced or goodwill changes. Online payments update automatically."
        />
        <DialogBody className="space-y-3">
          <NativeSelect
            aria-label="Plan"
            value={plan}
            onChange={(e) => setPlan(e.target.value)}
          >
            {plans.map((p) => (
              <option key={p.key} value={p.key}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            aria-label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Keep status</option>
            {["trialing", "active", "past_due", "suspended", "canceled"].map(
              (s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ),
            )}
          </NativeSelect>
          <NativeSelect
            aria-label="Extend trial"
            value={extend}
            onChange={(e) => setExtend(e.target.value)}
          >
            <option value="">Don&apos;t extend trial</option>
            {[7, 14, 30].map((d) => (
              <option key={d} value={d}>
                Extend trial by {d} days
              </option>
            ))}
          </NativeSelect>
          <Textarea
            aria-label="Reason"
            placeholder="Reason (recorded in the audit log)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={200}
          />
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={reason.trim().length < 3}
            loading={loading}
            onClick={() =>
              onSubmit({
                plan: plan || undefined,
                status: status || undefined,
                extend_trial_days: extend ? Number(extend) : undefined,
                reason: reason.trim(),
              })
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function OperatorWorkspacesPage() {
  return (
    <OperatorShell
      title="Workspaces"
      description="Every Owner OS workspace, including Pi businesses. Operational details only."
    >
      {(me) => <Workspaces me={me} />}
    </OperatorShell>
  );
}

function Workspaces({ me }: { me: OperatorMe }) {
  const canManage = me.capabilities.includes("operator.workspaces.manage");
  const [kind, setKind] = React.useState("all");
  const [search, setSearch] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [whatsapp, setWhatsapp] = React.useState<{
    id: string;
    name: string;
  } | null>(null);
  const [target, setTarget] = React.useState<{
    id: string;
    name: string;
    status: string;
  } | null>(null);
  const list = useScopedQuery(
    ["operator", "workspaces", kind, search, page],
    () =>
      api.workspaces({
        kind,
        search: search || undefined,
        page,
        page_size: 25,
      }),
    { placeholderData: (p) => p },
  );
  const change = useScopedMutation(
    ({
      id,
      status,
      reason,
    }: {
      id: string;
      status: "active" | "inactive";
      reason: string;
    }) => api.workspaceStatus(id, status, reason),
    {
      invalidate: [["operator"]],
      success: "Workspace updated",
      onSuccess: () => setTarget(null),
    },
  );
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          aria-label="Search workspaces"
          placeholder="Search by name"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="sm:max-w-xs"
        />
        <NativeSelect
          aria-label="Workspace type"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setPage(1);
          }}
          className="sm:w-52"
        >
          <option value="all">All workspaces</option>
          <option value="owner_os">Owner OS workspaces</option>
          <option value="pi">Pi businesses</option>
        </NativeSelect>
      </div>
      {list.isPending ? (
        <Loading />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.data.items.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No workspaces"
          description="Try another search."
        />
      ) : (
        <Card>
          <ul className="divide-y divide-border">
            {list.data.items.map((w) => (
              <li
                key={w.id}
                className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center"
              >
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {w.kind === "pi" ? (
                      <Link
                        href={`/operator/businesses/${w.id}`}
                        className="hover:text-primary"
                      >
                        {w.name}
                      </Link>
                    ) : (
                      w.name
                    )}
                  </p>
                  <p className="text-[12px] text-muted-foreground">
                    {w.members} member{w.members === 1 ? "" : "s"} · since{" "}
                    {date(w.created_at)} ·{" "}
                    {w.products.length
                      ? w.products.join(", ").toUpperCase()
                      : "no products"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={w.kind === "pi" ? "pi" : "outline"}>
                    {w.kind === "pi" ? "Pi business" : "Owner OS"}
                  </Badge>
                  <StateBadge value={w.status} />
                  <Button
                    size="xs"
                    variant="secondary"
                    onClick={() => setWhatsapp({ id: w.id, name: w.name })}
                  >
                    WhatsApp
                  </Button>
                  {w.is_member ? (
                    <span className="text-[12px] text-muted-foreground">
                      Your workspace
                    </span>
                  ) : canManage ? (
                    <Button
                      size="xs"
                      variant={
                        w.status === "active" ? "danger-outline" : "secondary"
                      }
                      onClick={() =>
                        setTarget({ id: w.id, name: w.name, status: w.status })
                      }
                    >
                      {w.status === "active" ? "Suspend" : "Reactivate"}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between border-t border-border px-4 py-2 text-[13px]">
            <span className="text-muted-foreground">
              {list.data.total} workspaces
            </span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={page * list.data.page_size >= list.data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </Card>
      )}
      <ReasonDialog
        open={Boolean(target)}
        onOpenChange={(v) => (!v ? setTarget(null) : null)}
        title={
          target?.status === "active"
            ? `Suspend ${target?.name}?`
            : `Reactivate ${target?.name}?`
        }
        description={
          target?.status === "active"
            ? "Members lose access and Pi stops sending. Data is kept."
            : "Members regain access. Pi stays paused until resumed."
        }
        confirm={target?.status === "active" ? "Suspend" : "Reactivate"}
        tone={target?.status === "active" ? "danger" : "default"}
        loading={change.isPending}
        onConfirm={(reason) =>
          target &&
          change.mutate({
            id: target.id,
            status: target.status === "active" ? "inactive" : "active",
            reason,
          })
        }
      />
      <WorkspaceWhatsAppDialog
        tenant={whatsapp}
        onOpenChange={(open) => !open && setWhatsapp(null)}
      />
    </div>
  );
}

export function OperatorPlansPage() {
  return (
    <OperatorShell
      title="Plans"
      description="Free and paid plans, what each includes and its monthly limits. Card checkout needs a price and a Stripe price id."
    >
      {(me) => <PlansManager me={me} />}
    </OperatorShell>
  );
}

export function OperatorEventsPage() {
  return (
    <OperatorShell
      title="Failed work"
      description="Provider events that failed after retries. Replay is safe: processing is idempotent."
    >
      {(me) => <Events me={me} />}
    </OperatorShell>
  );
}

function Events({ me }: { me: OperatorMe }) {
  const events = useScopedQuery(["operator", "events"], api.failedEvents);
  const replay = useScopedMutation((id: string) => api.replay(id), {
    invalidate: [["operator", "events"]],
    success: "Queued for another try",
  });
  if (events.isPending) return <Loading />;
  if (events.isError)
    return <ErrorState error={events.error} onRetry={() => events.refetch()} />;
  if (!events.data.length)
    return (
      <EmptyState
        icon={Activity}
        title="No failed work"
        description="Everything processed successfully."
      />
    );
  return (
    <Card>
      <ul className="divide-y divide-border text-[13px]">
        {events.data.map((e) => (
          <li
            key={e.id}
            className="flex flex-wrap items-center gap-2 px-4 py-2.5"
          >
            <span className="flex-1 font-mono">{e.event_type}</span>
            <Badge tone="danger">{e.error_code ?? "failed"}</Badge>
            <span className="text-muted-foreground">
              {e.attempts} tries · {date(e.created_at)}
            </span>
            {me.capabilities.includes("operator.jobs.replay") ? (
              <Button
                size="xs"
                variant="secondary"
                loading={replay.isPending && replay.variables === e.id}
                onClick={() => replay.mutate(e.id)}
              >
                <RefreshCw aria-hidden /> Replay
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function OperatorTeamPage() {
  return (
    <OperatorShell
      title="Operator team"
      description="Who runs Pi for customers. Roles never include customer conversations by default."
    >
      {() => <Team />}
    </OperatorShell>
  );
}

function Team() {
  const team = useScopedQuery(["operator", "team"], api.team);
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("support");
  const add = useScopedMutation(() => api.addOperator({ email, role }), {
    invalidate: [["operator", "team"]],
    success: "Operator added",
    onSuccess: () => setEmail(""),
  });
  const revoke = useScopedMutation((id: string) => api.revokeOperator(id), {
    invalidate: [["operator", "team"]],
    success: "Access removed",
  });
  if (team.isPending) return <Loading />;
  if (team.isError)
    return <ErrorState error={team.error} onRetry={() => team.refetch()} />;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h3 className="mb-2 font-semibold">Add an operator</h3>
        <Notice tone="info">The person needs an Owner OS account first.</Notice>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <Input
            aria-label="Email"
            placeholder="name@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <NativeSelect
            aria-label="Role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="sm:w-60"
          >
            {Object.entries(team.data.roles).map(([key, r]) => (
              <option key={key} value={key}>
                {r.name}
              </option>
            ))}
          </NativeSelect>
          <Button
            disabled={!email.includes("@")}
            loading={add.isPending}
            onClick={() => add.mutate(undefined)}
          >
            <UserPlus aria-hidden /> Add
          </Button>
        </div>
        <p className="mt-2 text-[12px] text-muted-foreground">
          {team.data.roles[role]?.description}
        </p>
      </Card>
      <Card>
        <ul className="divide-y divide-border">
          {team.data.members.map((m) => (
            <li
              key={m.id}
              className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center"
            >
              <div className="min-w-0 flex-1">
                <p className="font-medium">{m.name}</p>
                <p className="text-[12px] text-muted-foreground">{m.email}</p>
              </div>
              <Badge tone="outline">
                {team.data.roles[m.role]?.name ?? m.role}
              </Badge>
              <StateBadge value={m.status} />
              {m.status === "active" ? (
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={() => revoke.mutate(m.id)}
                >
                  Remove
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function OperatorConversationsPage({ id }: { id: string }) {
  return (
    <OperatorShell
      title="Customer conversations"
      description="Available only while the business has granted access. Every read is recorded."
    >
      {() => <SupportConversations id={id} />}
    </OperatorShell>
  );
}

function SupportConversations({ id }: { id: string }) {
  const [open, setOpen] = React.useState<string | null>(null);
  const list = useScopedQuery(["operator", "support", id], () =>
    apiRequestList<
      {
        id: string;
        status: string;
        mode: string;
        last_message_at: string;
        preview: string;
      }[]
    >(`/operator/pi/accounts/${id}/conversations`),
  );
  const messages = useScopedQuery(
    ["operator", "support", id, open],
    () =>
      apiRequestList<
        { id: string; sender: string; body: string; at: string }[]
      >(`/operator/pi/accounts/${id}/conversations/${open}/messages`),
    { enabled: Boolean(open) },
  );
  if (list.isPending) return <Loading />;
  if (list.isError) {
    const denied = list.error instanceof ApiError && list.error.status === 403;
    return denied ? (
      <EmptyState
        icon={ShieldCheck}
        title="No access"
        description="The business hasn't granted conversation access, or it has expired or been revoked."
      />
    ) : (
      <ErrorState error={list.error} onRetry={() => list.refetch()} />
    );
  }
  return (
    <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
      <Card>
        <ul className="divide-y divide-border text-[13px]">
          {list.data.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setOpen(c.id)}
                className={cn(
                  "w-full px-3 py-2 text-left hover:bg-surface-muted",
                  open === c.id && "bg-primary-soft",
                )}
              >
                <span className="line-clamp-1">
                  {c.preview || "No messages"}
                </span>
                <span className="text-[12px] text-muted-foreground">
                  {label(c.mode)} · {date(c.last_message_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="p-4">
        {!open ? (
          <p className="text-[13px] text-muted-foreground">
            Choose a conversation.
          </p>
        ) : messages.isPending ? (
          <Loading />
        ) : messages.isError ? (
          <ErrorState error={messages.error} />
        ) : (
          <ul className="space-y-2">
            {messages.data.map((m) => (
              <li
                key={m.id}
                className={cn(
                  "max-w-[80%] rounded-lg px-3 py-2 text-[13px]",
                  m.sender === "customer"
                    ? "bg-surface-muted"
                    : "ml-auto bg-primary-soft",
                )}
              >
                <p className="text-[11px] text-muted-foreground">
                  {label(m.sender)}
                </p>
                <p
                  className="whitespace-pre-line"
                  style={{ unicodeBidi: "plaintext" }}
                >
                  {m.body}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function apiRequestList<T>(path: string): Promise<T> {
  return apiRequest<T>("GET", path, null);
}
