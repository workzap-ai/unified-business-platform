"use client";

import Link from "next/link";
import { ArrowRight, FileText, RotateCcw, Workflow } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import type { KnowledgeDocument } from "../../types";
import { humanizeError, piKeys } from "../shared";
import {
  KNOWLEDGE_HEADER,
  KnowledgeNav,
  pollWhileProcessing,
} from "./knowledge-shared";

const STAGES: {
  key: KnowledgeDocument["status"];
  label: string;
  description: string;
  accent: string;
}[] = [
  {
    key: "pending",
    label: "Pending",
    description: "Waiting to be processed",
    accent: "bg-border-strong",
  },
  {
    key: "processing",
    label: "Processing",
    description: "Reading and splitting into passages",
    accent: "bg-warning",
  },
  {
    key: "ready",
    label: "Ready",
    description: "Searchable by PI",
    accent: "bg-success",
  },
  {
    key: "failed",
    label: "Failed",
    description: "Needs attention",
    accent: "bg-danger",
  },
];

export function KnowledgeIngestionPage() {
  return (
    <RequirePermission permission="pi.knowledge.manage" area="PI knowledge">
      <Ingestion />
    </RequirePermission>
  );
}

function Ingestion() {
  const documents = useScopedQuery(
    [...piKeys.documents, "", "", ""],
    () => piService.documents({}),
    { refetchInterval: (q) => pollWhileProcessing(q.state.data) },
  );
  const retry = useScopedMutation((id: string) => piService.retryDocument(id), {
    invalidate: [[...piKeys.documents], [...piKeys.sources]],
    success: (d) => `${d.title} queued for processing`,
  });

  const docs = documents.data;
  return (
    <PageShell>
      <PageHeader {...KNOWLEDGE_HEADER} />
      <KnowledgeNav />
      {documents.isError ? (
        <Card>
          <ErrorState
            error={documents.error}
            onRetry={() => void documents.refetch()}
          />
        </Card>
      ) : !docs ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {STAGES.map((s) => (
            <Skeleton key={s.key} className="h-72 rounded-xl" />
          ))}
        </div>
      ) : docs.length === 0 ? (
        <Card>
          <EmptyState
            tone="pi"
            icon={Workflow}
            title="Nothing in the pipeline"
            description="Documents you add move through processing here before PI can search them."
            action={
              <Button size="sm" asChild>
                <Link href="/pi/knowledge/documents?add=1">Add document</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <ol
          className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"
          aria-label="Ingestion pipeline"
        >
          {STAGES.map((stage, index) => {
            const items = docs
              .filter((d) => d.status === stage.key)
              .sort((a, b) => b.created_at.localeCompare(a.created_at));
            return (
              <li key={stage.key} className="min-w-0">
                <Card className="flex h-full flex-col">
                  <header className="flex items-center gap-2 border-b border-border px-4 py-3">
                    <span
                      className={cn("size-2 rounded-full", stage.accent)}
                      aria-hidden="true"
                    />
                    <h2 className="text-[13.5px] font-semibold">
                      {stage.label}
                    </h2>
                    <span className="tabular ml-auto rounded-full bg-surface-muted px-2 py-0.5 text-xs font-semibold">
                      {formatNumber(items.length)}
                    </span>
                    {index < 2 && (
                      <ArrowRight
                        className="hidden size-3.5 text-border-strong xl:block"
                        aria-hidden="true"
                      />
                    )}
                  </header>
                  <p className="px-4 pt-2 text-xs text-muted-foreground">
                    {stage.description}
                  </p>
                  {items.length === 0 ? (
                    <p className="px-4 py-6 text-center text-[13px] text-muted-foreground">
                      None
                    </p>
                  ) : (
                    <ul className="scrollbar-thin max-h-[420px] space-y-2 overflow-y-auto p-3">
                      {items.map((d) => (
                        <li
                          key={d.id}
                          className="rounded-lg border border-border bg-surface px-3 py-2"
                        >
                          <p className="flex items-center gap-1.5 text-[13px] font-medium">
                            <FileText
                              className="size-3.5 shrink-0 text-muted-foreground"
                              aria-hidden="true"
                            />
                            <span className="truncate">{d.title}</span>
                          </p>
                          <p className="mt-0.5 truncate text-xs text-muted-foreground">
                            {d.source_name} ·{" "}
                            {relativeTime(d.processed_at ?? d.created_at)}
                            {d.status === "ready" &&
                              ` · ${formatNumber(d.chunk_count)} passages`}
                          </p>
                          {d.status === "failed" && (
                            <>
                              <p className="mt-1.5 text-xs text-danger">
                                {humanizeError(d.error_code)}
                              </p>
                              <Button
                                size="xs"
                                variant="secondary"
                                className="mt-2"
                                loading={
                                  retry.isPending && retry.variables === d.id
                                }
                                onClick={() => retry.mutate(d.id)}
                                aria-label={`Retry ${d.title}`}
                              >
                                <RotateCcw /> Retry
                              </Button>
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              </li>
            );
          })}
        </ol>
      )}
    </PageShell>
  );
}
