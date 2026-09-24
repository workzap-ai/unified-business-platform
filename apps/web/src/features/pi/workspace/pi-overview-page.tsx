"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Bot,
  Gauge,
  Inbox,
  MessageCircle,
  MessagesSquare,
  PauseCircle,
  Timer,
  UserCheck,
  Wrench,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber, formatPercent, relativeTime } from "@/lib/format";
import { Avatar, Card, CardHeader, Skeleton } from "@/components/ui/display";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/controls";
import { PageHeader, PageShell } from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ChartCard } from "@/components/app/charts";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { piService } from "../service";
import type { PiOverview } from "../types";
import {
  AGENT_LABELS,
  HANDOFF_REASON_LABELS,
  PROVIDER_LABELS,
  PROVIDER_ROLE_LABELS,
  formatMs,
  inboxHref,
  piKeys,
} from "./lib";
import { ModeIndicator, PriorityBadge, TimeAgo, senderPrefix } from "./parts";

const cardLink = "text-xs font-medium text-primary hover:underline";

export function PiOverviewPage() {
  const overview = useScopedQuery<PiOverview>(piKeys.overview, () => piService.overview(), { refetchInterval: 60_000 });
  const data = overview.data;
  const loading = overview.isPending;
  const connected = data ? data.whatsapp !== null : true;

  return (
    <PageShell>
      <PageHeader
        title="AI operations"
        description={`How PI is handling customer conversations${data ? ` over the last ${data.period_days} days` : ""}.`}
        actions={
          <Button asChild>
            <Link href="/pi/inbox">
              <Inbox /> Open inbox
            </Link>
          </Button>
        }
      />

      {overview.isError ? (
        <Card>
          <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
        </Card>
      ) : (
        <>
          {data && !data.auto_reply_enabled && (
            <Notice
              tone="warning"
              icon={PauseCircle}
              title="Automatic replies are paused"
              className="mb-4"
              action={
                <Button variant="secondary" size="sm" asChild>
                  <Link href="/pi/settings">PI settings</Link>
                </Button>
              }
            >
              PI isn&apos;t answering customers right now. New messages wait in the inbox for your team.
            </Notice>
          )}

          {!connected ? (
            <FirstUse data={data!} />
          ) : (
            <>
              <MetricGrid>
                <MetricCard label="Active conversations" icon={MessagesSquare} loading={loading} href="/pi/inbox?status=open"
                  value={formatNumber(data?.conversations_active ?? 0)} detail={data ? `${formatNumber(data.conversations_total)} total` : undefined} />
                <MetricCard label="Unresolved" icon={AlertTriangle} loading={loading} href="/pi/inbox?status=open"
                  tone={data?.unresolved ? "warning" : "default"} value={formatNumber(data?.unresolved ?? 0)} detail="Waiting on a reply or handoff" />
                <MetricCard label="Open handoffs" icon={UserCheck} loading={loading} href="/pi/handoffs/open" tone="pi"
                  value={formatNumber(data?.open_handoffs ?? 0)} detail="Needs your team" />
                <MetricCard label="Automation rate" icon={Bot} loading={loading}
                  value={formatPercent(data?.automation_rate ?? null)} detail={data ? `${formatNumber(data.ai_responses)} AI replies` : undefined} />
                <MetricCard label="Avg reply time" icon={Timer} loading={loading}
                  value={formatMs(data?.avg_response_ms)} detail="Customer message to PI reply" />
                <MetricCard label="p95 reply time" icon={Gauge} loading={loading}
                  tone={data && data.p95_response_ms > 8000 ? "warning" : "default"} value={formatMs(data?.p95_response_ms)} detail="95% of replies are faster" />
                <MetricCard label="Fallback events" icon={Zap} loading={loading}
                  tone={data?.fallback_count ? "warning" : "default"} value={formatNumber(data?.fallback_count ?? 0)} detail="Answered by a fallback provider" />
                <MetricCard label="Tool calls" icon={Wrench} loading={loading}
                  tone={data?.tool_failures ? "warning" : "default"} value={formatNumber(data?.tool_calls ?? 0)}
                  detail={data ? (data.tool_failures ? `${formatNumber(data.tool_failures)} failed` : "No failures") : undefined} />
              </MetricGrid>

              <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                <ChartCard
                  title="Conversation volume"
                  description="Replies sent per day by PI and by your team"
                  data={data?.volume.map((v) => ({ day: v.day, ai: v.ai, human: v.human }))}
                  loading={loading}
                  xKey="day"
                  xLabel="Day"
                  series={[
                    { key: "ai", label: "PI replies" },
                    { key: "human", label: "Team replies" },
                  ]}
                  kind="bar"
                  stacked
                  height={240}
                  headline={
                    data && (
                      <p className="text-[13px] text-muted-foreground">
                        <span className="tabular font-semibold text-foreground">{formatNumber(data.messages_in)}</span> inbound ·{" "}
                        <span className="tabular font-semibold text-foreground">{formatNumber(data.messages_out)}</span> outbound this period
                      </p>
                    )
                  }
                  actions={<Link href="/pi/analytics" className={cardLink}>Analytics</Link>}
                />
                <ProviderHealthCard data={data} loading={loading} />
              </div>

              <div className="mt-4 grid gap-4 lg:grid-cols-3">
                <AgentActivityCard data={data} loading={loading} />
                <WhatsAppCard data={data} loading={loading} />
                <KnowledgeCard data={data} loading={loading} />
              </div>

              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <RecentConversations />
                <RecentHandoffs />
              </div>
            </>
          )}
        </>
      )}
    </PageShell>
  );
}

function FirstUse({ data }: { data: PiOverview }) {
  const { can } = useSession();
  return (
    <>
      <Card className="mb-4">
        <EmptyState
          tone="pi"
          icon={MessageCircle}
          title="Connect WhatsApp to start receiving conversations"
          description="PI answers customers on your WhatsApp Business number using your catalog, stock and approved knowledge. Connect a number to see conversations and activity here."
          action={
            can("pi.whatsapp.manage") ? (
              <Button variant="pi" asChild>
                <Link href="/pi/whatsapp">Connect WhatsApp</Link>
              </Button>
            ) : (
              <p className="text-[13px] text-muted-foreground">Ask a workspace administrator to connect WhatsApp.</p>
            )
          }
          secondary={
            can("pi.knowledge.manage") ? (
              <Button variant="secondary" asChild>
                <Link href="/pi/knowledge">Add knowledge first</Link>
              </Button>
            ) : undefined
          }
        />
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <KnowledgeCard data={data} loading={false} />
        <ProviderHealthCard data={data} loading={false} />
      </div>
    </>
  );
}

function ProviderHealthCard({ data, loading }: { data: PiOverview | undefined; loading: boolean }) {
  return (
    <Card className="flex flex-col">
      <CardHeader title="Provider health" description="AI providers in fallback order, last 24 hours" icon={<Activity />} />
      <div className="flex-1 px-4 pb-3">
        {loading || !data ? (
          <div className="space-y-2">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-14" />)}</div>
        ) : data.providers.length === 0 ? (
          <p className="py-4 text-[13px] text-muted-foreground">No AI providers are configured yet.</p>
        ) : (
          <ul className="space-y-2">
            {data.providers.map((p) => (
              <li key={`${p.role}-${p.name}`} className="rounded-lg border border-border px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">{PROVIDER_ROLE_LABELS[p.role]}</p>
                    <p className="truncate text-[13px] font-semibold">{PROVIDER_LABELS[p.name] ?? p.name}</p>
                  </div>
                  <StatusBadge status={p.status} label={p.status === "unconfigured" ? "Not configured" : undefined} />
                </div>
                {p.configured && (
                  <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <dt className="text-muted-foreground">Success</dt>
                      <dd className={cn("tabular font-semibold", p.success_rate < 0.95 && "text-warning")}>{formatPercent(p.success_rate, 1)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">p50 latency</dt>
                      <dd className="tabular font-semibold">{formatMs(p.p50_ms)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Requests</dt>
                      <dd className="tabular font-semibold">{formatNumber(p.requests_24h)}</dd>
                    </div>
                  </dl>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="border-t border-border px-4 py-2.5 text-xs text-muted-foreground">
        Provider order and models are configured in{" "}
        <Link href="/pi/settings" className="font-medium text-primary hover:underline">PI settings</Link>.
      </p>
    </Card>
  );
}

function AgentActivityCard({ data, loading }: { data: PiOverview | undefined; loading: boolean }) {
  const rows = [...(data?.agent_activity ?? [])].sort((a, b) => b.runs - a.runs);
  const max = Math.max(1, ...rows.map((r) => r.runs));
  return (
    <Card>
      <CardHeader title="Agent activity" description="Runs per agent this period" actions={<Link href="/pi/agents" className={cardLink}>Agents</Link>} />
      <div className="px-4 pb-4">
        {loading || !data ? (
          <div className="space-y-3">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-7" />)}</div>
        ) : rows.length === 0 ? (
          <p className="py-4 text-[13px] text-muted-foreground">No agent runs yet.</p>
        ) : (
          <ul className="space-y-2.5">
            {rows.map((r) => (
              <li key={r.agent}>
                <div className="flex items-center justify-between gap-2 text-[13px]">
                  <span className="truncate">{AGENT_LABELS[r.agent] ?? r.agent}</span>
                  <span className="tabular text-xs font-semibold">{formatNumber(r.runs)}</span>
                </div>
                <Progress value={(r.runs / max) * 100} tone="pi" className="mt-1 h-1" aria-label={`${AGENT_LABELS[r.agent]} runs`} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function WhatsAppCard({ data, loading }: { data: PiOverview | undefined; loading: boolean }) {
  const wa = data?.whatsapp;
  return (
    <Card>
      <CardHeader title="WhatsApp" description="Business number connection" icon={<MessageCircle />} actions={<Link href="/pi/whatsapp" className={cardLink}>Manage</Link>} />
      <div className="px-4 pb-4">
        {loading || !data ? (
          <Skeleton className="h-24" />
        ) : wa ? (
          <dl className="divide-y divide-border text-[13px]">
            <div className="flex items-center justify-between gap-3 py-2">
              <dt className="text-muted-foreground">Status</dt>
              <dd><StatusBadge status={wa.status} /></dd>
            </div>
            <div className="flex items-center justify-between gap-3 py-2">
              <dt className="text-muted-foreground">Number</dt>
              <dd className="tabular font-medium">{wa.display_phone_number}</dd>
            </div>
            <div className="flex items-center justify-between gap-3 py-2">
              <dt className="text-muted-foreground">Last inbound</dt>
              <dd className="font-medium">{wa.last_inbound_at ? relativeTime(wa.last_inbound_at) : "No messages yet"}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-[13px] text-muted-foreground">Not connected.</p>
        )}
      </div>
    </Card>
  );
}

function KnowledgeCard({ data, loading }: { data: PiOverview | undefined; loading: boolean }) {
  const k = data?.knowledge;
  const stats = k
    ? [
        { label: "Active sources", value: k.sources },
        { label: "Ready documents", value: k.documents_ready },
        { label: "Failed documents", value: k.documents_failed, danger: k.documents_failed > 0 },
        { label: "Passages", value: k.passages },
      ]
    : [];
  return (
    <Card>
      <CardHeader title="Knowledge health" description="What PI can cite when answering" icon={<BookOpen />} actions={<Link href="/pi/knowledge" className={cardLink}>Knowledge</Link>} />
      <div className="px-4 pb-4">
        {loading || !k ? (
          <Skeleton className="h-24" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              {stats.map((s) => (
                <div key={s.label} className="rounded-lg bg-surface-muted/70 px-3 py-2">
                  <p className="text-xs text-muted-foreground">{s.label}</p>
                  <p className={cn("tabular text-lg font-semibold", s.danger && "text-danger")}>{formatNumber(s.value)}</p>
                </div>
              ))}
            </div>
            {k.documents_failed > 0 && (
              <Link href="/pi/knowledge" className="mt-2.5 inline-flex items-center gap-1 text-xs font-medium text-danger hover:underline">
                Review failed documents <ArrowRight className="size-3" />
              </Link>
            )}
            {k.documents_ready === 0 && (
              <p className="mt-2.5 text-xs text-muted-foreground">No ready documents yet. PI will only answer from catalog and order data.</p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

function RecentConversations() {
  const query = useScopedQuery(piKeys.conversations({}), () => piService.conversations({}));
  const rows = query.data?.items.slice(0, 6);
  return (
    <Card>
      <CardHeader title="Recent conversations" actions={<Link href="/pi/inbox" className={cardLink}>Open inbox</Link>} />
      <div className="px-2 pb-2">
        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} compact />
        ) : !rows ? (
          <div className="space-y-2 px-2 pb-2">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-11" />)}</div>
        ) : rows.length === 0 ? (
          <EmptyState compact tone="pi" icon={MessagesSquare} title="No conversations yet" description="Customer conversations appear here as soon as someone messages your WhatsApp number." />
        ) : (
          <ul>
            {rows.map((c) => (
              <li key={c.id}>
                <Link href={inboxHref(c.id)} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-muted">
                  <Avatar name={c.customer_name} size="md" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={cn("truncate text-[13px]", c.unread_count ? "font-semibold" : "font-medium")}>{c.customer_name}</span>
                      <ModeIndicator mode={c.mode} />
                      <TimeAgo value={c.last_message_at} className="ml-auto text-xs text-muted-foreground" />
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {senderPrefix(c.last_sender)}
                      {c.last_message_preview}
                    </p>
                  </div>
                  {c.unread_count > 0 && (
                    <span className="tabular rounded-full bg-primary px-1.5 text-[10.5px] leading-4 font-semibold text-primary-foreground">
                      <span className="sr-only">Unread messages: </span>
                      {c.unread_count}
                    </span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function RecentHandoffs() {
  const query = useScopedQuery(piKeys.handoffs(), () => piService.handoffs());
  const rows = query.data?.slice(0, 5);
  return (
    <Card>
      <CardHeader title="Recent handoffs" description="Conversations PI passed to your team" actions={<Link href="/pi/handoffs" className={cardLink}>All handoffs</Link>} />
      <div className="px-2 pb-2">
        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} compact />
        ) : !rows ? (
          <div className="space-y-2 px-2 pb-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-11" />)}</div>
        ) : rows.length === 0 ? (
          <EmptyState compact tone="pi" icon={UserCheck} title="No handoffs" description="When PI needs a person, for a complaint, approval or low confidence, the conversation lands here." />
        ) : (
          <ul>
            {rows.map((h) => (
              <li key={h.id}>
                <Link href={inboxHref(h.conversation_id)} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-muted">
                  <Avatar name={h.customer_name} size="md" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[13px] font-medium">{h.customer_name}</span>
                      <PriorityBadge priority={h.priority} />
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {HANDOFF_REASON_LABELS[h.reason]} · {relativeTime(h.created_at)}
                    </p>
                  </div>
                  <StatusBadge status={h.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
