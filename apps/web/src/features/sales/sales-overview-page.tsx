"use client";

import Link from "next/link";
import {
  AlertCircle,
  Bot,
  ChevronRight,
  Kanban,
  Plus,
  Target,
  Trophy,
} from "lucide-react";
import {
  formatMoney,
  formatNumber,
  formatPercent,
  humanize,
  relativeTime,
} from "@/lib/format";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  Skeleton,
} from "@/components/ui/display";
import { Button } from "@/components/ui/button";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { DistributionBar } from "@/components/app/charts";
import { EmptyState, ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import type { Lead } from "@/features/business/types";
import { salesService } from "./service";
import {
  formatRequirement,
  LeadSourceBadge,
  OPEN_STAGES,
  requirementEntries,
  STAGE_LABELS,
  STAGES,
} from "./lib";

export function SalesOverviewPage() {
  return (
    <RequirePermission permission="sales.read" area="sales">
      <SalesOverview />
    </RequirePermission>
  );
}

function SalesOverview() {
  const { can } = useSession();
  const pipeline = useScopedQuery(["pipeline"], () => salesService.pipeline());
  const leads = useScopedQuery(
    ["leads", "list", { page: 1, pageSize: 100 }],
    () => salesService.leads({ page: 1, pageSize: 100 }),
  );

  const currency = leads.data?.items[0]?.currency ?? "USD";
  const byStage = new Map(pipeline.data?.map((s) => [s.stage, s]) ?? []);
  const won = byStage.get("won")?.count ?? 0;
  const lost = byStage.get("lost")?.count ?? 0;
  const winRate = won + lost > 0 ? won / (won + lost) : null;
  const openSegments = OPEN_STAGES.map((stage) => ({
    key: stage,
    label: STAGE_LABELS[stage],
    value: Number(byStage.get(stage)?.value ?? 0),
  }));
  const openValue = openSegments.reduce((sum, s) => sum + s.value, 0);
  const openCount = OPEN_STAGES.reduce(
    (sum, s) => sum + (byStage.get(s)?.count ?? 0),
    0,
  );

  const items = leads.data?.items ?? [];
  const recent = [...items]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 6);
  const captured = items
    .filter((l) => l.source === "pi" && l.stage !== "won" && l.stage !== "lost")
    .slice(0, 5);
  const noLeads = leads.data && leads.data.total === 0;

  return (
    <PageShell>
      <PageHeader
        title="Sales"
        description="Your pipeline at a glance: what's open, what's closing and what PI captured from WhatsApp."
        actions={
          <>
            <Button variant="secondary" asChild>
              <Link href="/sales/pipeline">
                <Kanban /> Open pipeline
              </Link>
            </Button>
            {can("sales.write") && (
              <Button asChild>
                <Link href="/sales/leads?new=1">
                  <Plus /> New lead
                </Link>
              </Button>
            )}
          </>
        }
      />
      <ModuleNav moduleKey="sales" />

      {pipeline.isError ? (
        <Card className="mb-4">
          <ErrorState
            error={pipeline.error}
            onRetry={() => void pipeline.refetch()}
            compact
          />
        </Card>
      ) : (
        <MetricGrid className="md:grid-cols-3 xl:grid-cols-6">
          {STAGES.map((stage) => {
            const s = byStage.get(stage);
            return (
              <MetricCard
                key={stage}
                label={STAGE_LABELS[stage]}
                loading={pipeline.isPending}
                value={formatNumber(s?.count ?? 0)}
                detail={
                  s
                    ? formatMoney(s.value, currency, { compact: true })
                    : undefined
                }
                href={`/sales/leads?stage=${stage}`}
                tone={stage === "won" ? "success" : "default"}
              />
            );
          })}
          <MetricCard
            label="Win rate"
            icon={Trophy}
            loading={pipeline.isPending}
            value={formatPercent(winRate)}
            detail={
              winRate === null
                ? "No closed leads yet"
                : `${won} won · ${lost} lost`
            }
          />
        </MetricGrid>
      )}

      {noLeads ? (
        <Card className="mt-4">
          <EmptyState
            icon={Target}
            title="No leads yet"
            description="Add a lead to start tracking your pipeline. With PI connected, WhatsApp enquiries become leads automatically."
            action={
              can("sales.write") ? (
                <Button size="sm" asChild>
                  <Link href="/sales/leads?new=1">
                    <Plus /> New lead
                  </Link>
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <>
          <Card className="mt-4">
            <CardHeader
              title="Open pipeline value"
              description={
                pipeline.data
                  ? `${formatMoney(String(openValue), currency)} across ${openCount === 1 ? "1 open lead" : `${formatNumber(openCount)} open leads`}`
                  : "By stage"
              }
            />
            <CardBody>
              {pipeline.isPending ? (
                <Skeleton className="h-14" />
              ) : openValue > 0 ? (
                <DistributionBar
                  segments={openSegments}
                  format={(v) => formatMoney(v, currency, { compact: true })}
                />
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  No estimated value on open leads yet. Add values to see where
                  your pipeline sits.
                </p>
              )}
            </CardBody>
          </Card>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader
                title={
                  <span className="flex items-center gap-1.5">
                    <Bot className="size-4 text-pi" aria-hidden="true" />{" "}
                    Captured by PI
                  </span>
                }
                description="Open leads PI qualified from WhatsApp conversations"
              />
              <div className="px-2 pb-2">
                {leads.isError ? (
                  <ErrorState
                    error={leads.error}
                    onRetry={() => void leads.refetch()}
                    compact
                  />
                ) : leads.isPending ? (
                  <ListSkeleton />
                ) : captured.length === 0 ? (
                  <EmptyState
                    compact
                    tone="pi"
                    icon={Bot}
                    title="Nothing captured yet"
                    description="When customers describe what they need on WhatsApp, PI records the requirements here as a lead."
                  />
                ) : (
                  <ul className="divide-y divide-border">
                    {captured.map((lead) => (
                      <li key={lead.id}>
                        <CapturedLead lead={lead} />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader
                title="Recent leads"
                description="Latest activity across the pipeline"
                actions={
                  <Link
                    href="/sales/leads"
                    className="text-xs font-medium text-primary hover:underline"
                  >
                    View all
                  </Link>
                }
              />
              <div className="px-2 pb-2">
                {leads.isError ? (
                  <ErrorState
                    error={leads.error}
                    onRetry={() => void leads.refetch()}
                    compact
                  />
                ) : leads.isPending ? (
                  <ListSkeleton />
                ) : (
                  <ul>
                    {recent.map((lead) => (
                      <li key={lead.id}>
                        <Link
                          href={`/sales/leads/${lead.id}`}
                          className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-surface-muted"
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] font-medium">
                              {lead.title}
                            </span>
                            <span className="block truncate text-xs text-muted-foreground">
                              {lead.customer_name ?? "No customer"} · updated{" "}
                              {relativeTime(lead.updated_at)}
                            </span>
                          </span>
                          {lead.source === "pi" && (
                            <LeadSourceBadge source="pi" compact />
                          )}
                          <StatusBadge status={lead.stage} />
                          <span className="tabular hidden w-20 shrink-0 text-right text-[13px] sm:block">
                            {lead.estimated_value
                              ? formatMoney(
                                  lead.estimated_value,
                                  lead.currency,
                                  { compact: true },
                                )
                              : "—"}
                          </span>
                          <ChevronRight
                            className="size-4 shrink-0 text-muted-foreground"
                            aria-hidden="true"
                          />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>
          </div>
        </>
      )}
    </PageShell>
  );
}

function CapturedLead({ lead }: { lead: Lead }) {
  const fields = requirementEntries(lead.requirements).slice(0, 4);
  return (
    <Link
      href={`/sales/leads/${lead.id}`}
      className="block rounded-lg px-2 py-3 hover:bg-surface-muted"
    >
      <span className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
          {lead.title}
        </span>
        <StatusBadge status={lead.stage} />
      </span>
      <span className="mt-0.5 block truncate text-xs text-muted-foreground">
        {lead.customer_name ?? "Unknown customer"} ·{" "}
        {relativeTime(lead.created_at)}
      </span>
      {fields.length > 0 && (
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {fields.map(([key, value]) => (
            <div key={key} className="flex min-w-0 gap-1.5">
              <dt className="shrink-0 text-muted-foreground">
                {humanize(key)}:
              </dt>
              <dd className="truncate font-medium">
                {formatRequirement(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {lead.missing_information.length > 0 && (
        <span className="mt-2 flex flex-wrap items-center gap-1">
          <span className="sr-only">Missing information:</span>
          {lead.missing_information.map((m) => (
            <Badge key={m} tone="warning">
              <AlertCircle aria-hidden="true" /> {humanize(m)}
            </Badge>
          ))}
        </span>
      )}
    </Link>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2 px-2 pb-2">
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} className="h-12" />
      ))}
    </div>
  );
}
