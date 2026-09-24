"use client";

import Link from "next/link";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  formatDate,
  formatMoney,
  formatNumber,
  humanize,
  relativeTime,
  toCents,
} from "@/lib/format";
import { Avatar, Badge, Skeleton } from "@/components/ui/display";
import { ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../service";
import type { AgentRun, ConversationContext } from "../types";
import {
  PROVIDER_LABELS,
  agentLabel,
  formatMs,
  piKeys,
  toolLabel,
} from "./lib";
import { SectionLabel, usePiNames } from "./parts";

const LANGUAGES: Record<string, string> = {
  en: "English",
  ur: "Urdu",
  roman_ur: "Roman Urdu",
};
const MEMORY_TONES = {
  preference: "primary",
  requirement: "info",
  context: "neutral",
} as const;

export function useConversationContext(id: string) {
  return useScopedQuery<ConversationContext>(
    piKeys.context(id),
    () => piService.context(id),
    {
      enabled: Boolean(id),
      refetchInterval: 30_000,
    },
  );
}

export function ContextPanel({ conversationId }: { conversationId: string }) {
  const query = useConversationContext(conversationId);
  const names = usePiNames();

  if (query.isError)
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        compact
      />
    );
  if (query.isPending || !query.data) {
    return (
      <div className="space-y-4 p-4" aria-busy="true">
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-2/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    );
  }

  const ctx = query.data;
  const c = ctx.conversation;
  const owing = ctx.balance !== null && toCents(ctx.balance) > BigInt(0);

  return (
    <div className="divide-y divide-border">
      <section className="p-4" aria-label="Customer">
        <div className="flex items-center gap-3">
          <Avatar name={c.customer_name} size="lg" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13.5px] font-semibold">
              {c.customer_name}
            </p>
            <p className="tabular truncate text-xs text-muted-foreground">
              {c.customer_phone ?? "No phone on file"}
            </p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {c.language && (
            <Badge tone="outline">{LANGUAGES[c.language] ?? c.language}</Badge>
          )}
          {c.assigned_label && (
            <Badge tone="info">Assigned to {c.assigned_label}</Badge>
          )}
        </div>
        <dl className="mt-3 flex items-center justify-between rounded-lg bg-surface-muted/70 px-3 py-2 text-[13px]">
          <dt className="text-muted-foreground">Outstanding balance</dt>
          <dd className={cn("tabular font-semibold", owing && "text-danger")}>
            {ctx.balance === null
              ? "—"
              : formatMoney(ctx.balance, ctx.currency)}
          </dd>
        </dl>
        <Link
          href={`/customers/${c.customer_id}`}
          className="mt-2.5 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          Open customer profile{" "}
          <ArrowUpRight className="size-3" aria-hidden="true" />
        </Link>
      </section>

      <section className="p-4" aria-labelledby="ctx-summary">
        <SectionLabel>
          <span id="ctx-summary">Conversation summary</span>
        </SectionLabel>
        <p className="mt-1.5 text-[13px] leading-relaxed text-foreground-secondary">
          {c.summary || "No summary yet."}
        </p>
        {c.last_intent && (
          <p className="mt-2 text-xs text-muted-foreground">
            Last intent{" "}
            <Badge tone="pi" className="ml-1">
              {humanize(c.last_intent)}
            </Badge>
          </p>
        )}
      </section>

      <section className="p-4">
        <SectionLabel>What PI remembers</SectionLabel>
        {ctx.memory.length === 0 ? (
          <p className="mt-1.5 text-[13px] text-muted-foreground">
            Nothing remembered about this customer yet.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {ctx.memory.map((m) => (
              <li key={m.id} className="text-[13px]">
                <Badge
                  tone={MEMORY_TONES[m.kind]}
                  className="mr-1.5 align-middle"
                >
                  {humanize(m.kind)}
                </Badge>
                {m.content}
                <span className="ml-1 text-xs text-muted-foreground">
                  · {relativeTime(m.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {ctx.knowledge_used.length > 0 && (
        <section className="p-4">
          <SectionLabel>Knowledge used</SectionLabel>
          <ul className="mt-2 space-y-2">
            {ctx.knowledge_used.map((k, i) => (
              <li
                key={`${k.title}-${i}`}
                className="rounded-lg border border-border p-2.5"
              >
                <p className="text-[13px] font-medium">{k.title}</p>
                <p className="text-xs text-muted-foreground">{k.source}</p>
                <p className="mt-1 line-clamp-3 text-xs text-foreground-secondary">
                  {k.snippet}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="p-4">
        <SectionLabel>Recent orders</SectionLabel>
        {ctx.recent_orders.length === 0 ? (
          <p className="mt-1.5 text-[13px] text-muted-foreground">
            No orders yet.
          </p>
        ) : (
          <ul className="mt-1.5 divide-y divide-border">
            {ctx.recent_orders.map((o) => (
              <li key={o.id}>
                <Link
                  href={`/orders/${o.id}`}
                  className="flex items-center gap-2 py-2 text-[13px] hover:underline"
                >
                  <span className="font-mono text-xs font-medium">
                    {o.number}
                  </span>
                  <StatusBadge status={o.status} />
                  <span className="tabular ml-auto font-medium">
                    {formatMoney(o.total, ctx.currency)}
                  </span>
                </Link>
                <p className="-mt-1.5 pb-1 text-2xs text-muted-foreground">
                  {formatDate(o.created_at)}
                </p>
              </li>
            ))}
          </ul>
        )}
        {ctx.open_quotes.length > 0 && (
          <>
            <SectionLabel className="mt-3">Open quotes</SectionLabel>
            <ul className="mt-1.5 divide-y divide-border">
              {ctx.open_quotes.map((q) => (
                <li key={q.id}>
                  <Link
                    href={`/quotes/${q.id}`}
                    className="flex items-center gap-2 py-2 text-[13px] hover:underline"
                  >
                    <span className="font-mono text-xs font-medium">
                      {q.number}
                    </span>
                    <StatusBadge status={q.status} />
                    <span className="tabular ml-auto font-medium">
                      {formatMoney(q.total, ctx.currency)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="p-4">
        <SectionLabel>Agent runs</SectionLabel>
        {ctx.runs.length === 0 ? (
          <p className="mt-1.5 text-[13px] text-muted-foreground">
            PI hasn&apos;t processed messages in this conversation yet.
          </p>
        ) : (
          <ul className="mt-2 space-y-2">
            {ctx.runs.map((run) => (
              <RunCard
                key={run.id}
                run={run}
                agentNames={names.agentNames}
                toolNames={names.toolNames}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function RunCard({
  run,
  agentNames,
  toolNames,
}: {
  run: AgentRun;
  agentNames: Map<string, string>;
  toolNames: Map<string, string>;
}) {
  const confidence =
    run.confidence === null ? null : Math.round(run.confidence * 100);
  return (
    <li className="rounded-lg border border-border p-2.5 text-xs">
      <div className="flex items-center gap-2">
        <span className="truncate text-[13px] font-medium">
          {run.intent ? humanize(run.intent) : "No intent"}
        </span>
        {confidence !== null && (
          <span
            className={cn(
              "tabular shrink-0 font-semibold",
              confidence < 60 ? "text-warning" : "text-muted-foreground",
            )}
          >
            {confidence}%
          </span>
        )}
        <StatusBadge status={run.status} className="ml-auto" />
      </div>
      {run.agent_path.length > 0 && (
        <ol
          className="mt-2 flex flex-wrap items-center gap-1"
          aria-label="Agent route"
        >
          {run.agent_path.map((a, i) => (
            <li key={`${a}-${i}`} className="flex items-center gap-1">
              {i > 0 && (
                <ChevronRight
                  className="size-3 text-muted-foreground"
                  aria-hidden="true"
                />
              )}
              <Badge tone="pi">{agentLabel(a, agentNames)}</Badge>
            </li>
          ))}
        </ol>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
        {run.provider && (
          <span>
            {PROVIDER_LABELS[run.provider] ?? run.provider}
            {run.model_alias && ` · ${humanize(run.model_alias)}`}
          </span>
        )}
        {run.fallback_used && <Badge tone="warning">Fallback used</Badge>}
        <span className="tabular">{formatMs(run.latency_ms)}</span>
        <span className="tabular" title="Input / output tokens">
          {formatNumber(run.input_tokens, true)} /{" "}
          {formatNumber(run.output_tokens, true)} tokens
        </span>
      </div>
      {run.tools.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1">
          {run.tools.map((t, i) => (
            <li key={`${t.tool}-${i}`} title={t.summary}>
              <Badge
                tone={
                  t.status === "success"
                    ? "outline"
                    : t.status === "confirmation_required"
                      ? "warning"
                      : "danger"
                }
              >
                {toolLabel(t.tool, toolNames)}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
