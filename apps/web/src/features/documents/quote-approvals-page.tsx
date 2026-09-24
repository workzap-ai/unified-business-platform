"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, CheckCircle2, Stamp, Undo2 } from "lucide-react";
import { formatMoney, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/display";
import { ModuleNav, PageHeader, PageShell, RequirePermission } from "@/components/app/page";
import { Pagination } from "@/components/app/data-table";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import type { BusinessSettings, Quote } from "@/features/business/types";
import { documentsService, type QuoteAction } from "./service";
import { SourceBadge, ValidUntil } from "./badges";
import { useBusinessSettings } from "./hooks";
import { approvalReasons } from "./lib";

const PAGE_SIZE = 24;

export function QuoteApprovalsPage() {
  return (
    <RequirePermission permission="quotes.approve" area="quote approvals">
      <ApprovalQueue />
    </RequirePermission>
  );
}

function ApprovalQueue() {
  const [state, set] = useUrlState({ page: "1" });
  const page = Math.max(1, Number(state.page) || 1);
  const settings = useBusinessSettings();
  const query = useScopedQuery(["quotes", "list", "approvals", page], () =>
    documentsService.quotes({ status: "pending_approval", page, pageSize: PAGE_SIZE }),
  );

  return (
    <PageShell>
      <PageHeader
        title="Approvals"
        description="Quotes that exceed discount or value limits, or were drafted by PI, wait here for a reviewer."
      />
      <ModuleNav moduleKey="quotes" />
      {query.isError ? (
        <Card>
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        </Card>
      ) : query.isPending ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-52 rounded-xl" />
          ))}
        </div>
      ) : query.data.items.length === 0 ? (
        <Card>
          <EmptyState
            icon={CheckCircle2}
            title="No quotes waiting"
            description="Everything submitted has been reviewed. New quotes that need approval will appear here."
            action={
              <Button variant="secondary" size="sm" asChild>
                <Link href="/quotes">View all quotes</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <>
          <p className="mb-3 text-[13px] text-muted-foreground" aria-live="polite">
            {query.data.total} {query.data.total === 1 ? "quote needs" : "quotes need"} a decision
          </p>
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {query.data.items.map((quote) => (
              <li key={quote.id}>
                <ApprovalCard quote={quote} settings={settings.data} settingsLoading={settings.isPending} />
              </li>
            ))}
          </ul>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={query.data.total}
            onPage={(next) => set({ page: String(next) }, { resetPage: false })}
          />
        </>
      )}
    </PageShell>
  );
}

function ApprovalCard({
  quote,
  settings,
  settingsLoading,
}: {
  quote: Quote;
  settings: BusinessSettings | undefined;
  settingsLoading: boolean;
}) {
  const [pending, setPending] = useState<QuoteAction | null>(null);
  const action = useScopedMutation((a: QuoteAction) => documentsService.quoteAction(quote.id, a), {
    invalidate: [["quotes"]],
    success: (q) => (q.status === "approved" ? `${q.number} approved` : `${q.number} returned to draft`),
  });
  const reasons = approvalReasons(quote, settings, quote.currency);
  const run = (a: QuoteAction) => {
    setPending(a);
    action.mutate(a, { onSettled: () => setPending(null) });
  };

  return (
    <Card className="flex h-full flex-col p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href={`/quotes/${quote.id}`} className="font-mono text-[13px] font-semibold hover:underline">
            {quote.number}
          </Link>
          <p className="mt-0.5 truncate text-[13px] text-muted-foreground">{quote.customer_name ?? "Unknown customer"}</p>
        </div>
        <SourceBadge source={quote.source} />
      </div>
      <p className="tabular mt-3 text-xl font-semibold tracking-tight">{formatMoney(quote.total, quote.currency)}</p>
      <p className="text-xs text-muted-foreground">
        Submitted {relativeTime(quote.created_at)} · valid until <ValidUntil quote={quote} />
      </p>

      <div className="mt-3 flex-1 rounded-lg bg-warning-soft/60 px-3 py-2.5">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-warning">
          <Stamp className="size-3.5" aria-hidden="true" /> Why it needs approval
        </p>
        {settingsLoading ? (
          <Skeleton className="mt-2 h-3.5 w-3/4" />
        ) : reasons.length ? (
          <ul className="mt-1.5 space-y-1 text-[13px] text-foreground-secondary">
            {reasons.map((r) => (
              <li key={r} className="flex gap-1.5">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden="true" />
                {r}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-[13px] text-foreground-secondary">
            Flagged when it was submitted. Limits may have changed since — review the details.
          </p>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => run("approve")} loading={pending === "approve"} disabled={pending !== null}>
          <CheckCircle2 /> Approve
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => run("return_to_draft")}
          loading={pending === "return_to_draft"}
          disabled={pending !== null}
        >
          <Undo2 /> Return to draft
        </Button>
        <Button size="sm" variant="ghost" className="ml-auto" asChild>
          <Link href={`/quotes/${quote.id}`} aria-label={`Open ${quote.number}`}>
            Details <ArrowRight />
          </Link>
        </Button>
      </div>
    </Card>
  );
}
