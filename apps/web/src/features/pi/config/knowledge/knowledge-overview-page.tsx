"use client";

import Link from "next/link";
import {
  BookOpen,
  CheckCircle2,
  FileText,
  Layers,
  Loader2,
  Search,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { formatNumber, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import { humanizeError, piKeys } from "../shared";
import {
  KNOWLEDGE_HEADER,
  KnowledgeNav,
  pollWhileProcessing,
} from "./knowledge-shared";

export function KnowledgeOverviewPage() {
  return (
    <RequirePermission permission="pi.knowledge.manage" area="PI knowledge">
      <Overview />
    </RequirePermission>
  );
}

function Overview() {
  const sources = useScopedQuery(piKeys.sources, () => piService.sources());
  const documents = useScopedQuery(
    [...piKeys.documents, "", "", ""],
    () => piService.documents({}),
    { refetchInterval: (q) => pollWhileProcessing(q.state.data) },
  );
  const settings = useScopedQuery(piKeys.settings, () => piService.settings());

  const error = sources.error ?? documents.error;
  const loading = sources.isPending || documents.isPending;
  const docs = documents.data ?? [];
  const count = (s: string) => docs.filter((d) => d.status === s).length;
  const failed = docs.filter((d) => d.status === "failed");
  const processing = count("pending") + count("processing");
  const recent = [...docs]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 6);
  const semantic = settings.data?.knowledge_config.semantic_enabled;

  return (
    <PageShell>
      <PageHeader
        {...KNOWLEDGE_HEADER}
        actions={
          <Button asChild>
            <Link href="/pi/knowledge/documents?add=1">Add document</Link>
          </Button>
        }
      />
      <KnowledgeNav />

      {error ? (
        <Card>
          <ErrorState
            error={error}
            onRetry={() => {
              void sources.refetch();
              void documents.refetch();
            }}
          />
        </Card>
      ) : !loading && sources.data?.length === 0 && docs.length === 0 ? (
        <Card>
          <EmptyState
            tone="pi"
            icon={BookOpen}
            title="No knowledge yet"
            description="Add a source such as your FAQ or return policy, then add documents to it. PI only answers from approved sources."
            action={
              <Button size="sm" asChild>
                <Link href="/pi/knowledge/sources?new=1">New source</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          <MetricGrid className="xl:grid-cols-6 md:grid-cols-3">
            <MetricCard
              label="Active sources"
              icon={Layers}
              loading={loading}
              href="/pi/knowledge/sources"
              value={formatNumber(
                sources.data?.filter((s) => s.status === "active").length ?? 0,
              )}
              detail={`${formatNumber(sources.data?.length ?? 0)} total`}
            />
            <MetricCard
              label="Ready"
              icon={CheckCircle2}
              loading={loading}
              tone="success"
              href="/pi/knowledge/documents?status=ready"
              value={formatNumber(count("ready"))}
              detail="documents"
            />
            <MetricCard
              label="Processing"
              icon={Loader2}
              loading={loading}
              href="/pi/knowledge/ingestion"
              value={formatNumber(processing)}
              detail="pending or in progress"
            />
            <MetricCard
              label="Failed"
              icon={TriangleAlert}
              loading={loading}
              tone={failed.length ? "danger" : "default"}
              href="/pi/knowledge/ingestion"
              value={formatNumber(failed.length)}
              detail="need attention"
            />
            <MetricCard
              label="Passages"
              icon={FileText}
              loading={loading}
              value={formatNumber(docs.reduce((s, d) => s + d.chunk_count, 0))}
              detail="searchable chunks"
            />
            <MetricCard
              label="Retrieval"
              icon={Search}
              loading={settings.isPending}
              tone="pi"
              href="/pi/settings/knowledge-configuration"
              value={
                <span className="text-[15px]">
                  {settings.isError
                    ? "Unavailable"
                    : semantic
                      ? "Semantic + full-text"
                      : "Full-text search"}
                </span>
              }
            />
          </MetricGrid>

          {failed.length > 0 && (
            <Notice
              tone="danger"
              title={`${failed.length} document${failed.length === 1 ? "" : "s"} failed to process`}
              action={
                <Button size="xs" variant="secondary" asChild>
                  <Link href="/pi/knowledge/ingestion">Review</Link>
                </Button>
              }
            >
              {humanizeError(failed[0]!.error_code)}
            </Notice>
          )}

          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <Card>
              <CardHeader
                title="Recent documents"
                actions={
                  <Link
                    href="/pi/knowledge/documents"
                    className="text-xs font-medium text-primary hover:underline"
                  >
                    All documents
                  </Link>
                }
              />
              <CardBody>
                {loading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 4 }, (_, i) => (
                      <Skeleton key={i} className="h-9" />
                    ))}
                  </div>
                ) : recent.length === 0 ? (
                  <p className="py-4 text-[13px] text-muted-foreground">
                    No documents yet.
                  </p>
                ) : (
                  <ul className="divide-y divide-border">
                    {recent.map((d) => (
                      <li
                        key={d.id}
                        className="flex items-center gap-3 py-2 text-[13px]"
                      >
                        <FileText
                          className="size-4 shrink-0 text-muted-foreground"
                          aria-hidden="true"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">
                            {d.title}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {d.source_name} · {relativeTime(d.created_at)}
                          </span>
                        </span>
                        <StatusBadge status={d.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </CardBody>
            </Card>
            <Card>
              <CardHeader
                title="How PI uses knowledge"
                icon={<ShieldCheck />}
              />
              <CardBody className="space-y-2.5 text-[13px] text-foreground-secondary">
                <p>
                  Retrieval is always scoped to this workspace and environment —
                  other workspaces&apos; documents are never searched.
                </p>
                <p>
                  PI never answers from unapproved sources. Disabled sources and
                  documents that failed processing are excluded.
                </p>
                <p>
                  Prices and stock always come from the live catalog and
                  inventory, not from documents.
                </p>
              </CardBody>
            </Card>
          </div>
        </div>
      )}
    </PageShell>
  );
}
