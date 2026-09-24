"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  GitCompare,
  History,
  Rocket,
  RotateCcw,
} from "lucide-react";
import { formatDateTime, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import { NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { ConfirmDialog } from "@/components/app/forms";
import { PropertyList } from "@/components/app/record";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import type { AgentVersion } from "../../types";
import { piKeys } from "../shared";
import { SideBySideDiff } from "./line-diff";

export function AgentVersionsPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="pi.agents.manage" area="PI agents">
      <Versions id={id} />
    </RequirePermission>
  );
}

function Versions({ id }: { id: string }) {
  const agent = useScopedQuery(piKeys.agent(id), () => piService.agent(id));
  const versions = useScopedQuery(piKeys.versions(id), () =>
    piService.versions(id),
  );
  useBreadcrumbs(
    agent.data
      ? [
          { label: agent.data.name, href: `/pi/agents/${agent.data.id}` },
          { label: "Versions" },
        ]
      : [],
  );
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [rollbackTarget, setRollbackTarget] = useState<AgentVersion | null>(
    null,
  );
  const [publishOpen, setPublishOpen] = useState(false);

  const agentId = agent.data?.id ?? id;
  const rollback = useScopedMutation(
    (v: AgentVersion) => piService.rollback(agentId, v.id),
    {
      invalidate: [[...piKeys.agents]],
      success: (v) => `Restored as version ${v.version}`,
      onSuccess: () => setRollbackTarget(null),
    },
  );
  const draft = versions.data?.find((v) => v.status === "draft");
  const publishDraft = useScopedMutation(
    (v: AgentVersion) =>
      piService.publishVersion(agentId, {
        instructions: v.instructions,
        model_alias: v.model_alias,
        temperature: v.temperature,
        note: v.note || `Published draft v${v.version}`,
      }),
    {
      invalidate: [[...piKeys.agents]],
      success: (v) => `Draft published as version ${v.version}`,
      onSuccess: () => setPublishOpen(false),
    },
  );

  const error = agent.error ?? versions.error;
  if (error) {
    return (
      <PageShell>
        <Card>
          <ErrorState
            error={error}
            onRetry={() => {
              void agent.refetch();
              void versions.refetch();
            }}
          />
        </Card>
      </PageShell>
    );
  }

  const list = versions.data;
  const active = list?.find((v) => v.status === "active");
  const leftVersion =
    list?.find((v) => v.id === left) ?? list?.[1] ?? list?.[0];
  const rightVersion = list?.find((v) => v.id === right) ?? list?.[0];

  const columns: Column<AgentVersion>[] = [
    {
      key: "version",
      header: "Version",
      cell: (v) => <span className="font-mono text-xs">v{v.version}</span>,
      width: "80px",
    },
    {
      key: "status",
      header: "Status",
      cell: (v) => <StatusBadge status={v.status} />,
    },
    {
      key: "note",
      header: "Note",
      cell: (v) => (
        <span className="line-clamp-2 text-foreground-secondary">
          {v.note || "—"}
        </span>
      ),
    },
    {
      key: "model",
      header: "Model",
      cell: (v) => (
        <span className="text-xs">
          {v.model_alias} · {Number(v.temperature).toFixed(2)}
        </span>
      ),
      hideBelow: "lg",
    },
    {
      key: "author",
      header: "Author",
      cell: (v) => v.created_by_label,
      hideBelow: "md",
    },
    {
      key: "date",
      header: "Date",
      cell: (v) => (
        <time dateTime={v.created_at} title={formatDateTime(v.created_at)}>
          {relativeTime(v.created_at)}
        </time>
      ),
      hideBelow: "sm",
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (v) =>
        v.status === "archived" ? (
          <Button
            size="xs"
            variant="secondary"
            onClick={() => setRollbackTarget(v)}
          >
            <RotateCcw /> Roll back
          </Button>
        ) : v.status === "draft" ? (
          <Button size="xs" onClick={() => setPublishOpen(true)}>
            <Rocket /> Publish
          </Button>
        ) : null,
    },
  ];

  return (
    <PageShell>
      <Link
        href={`/pi/agents/${agentId}`}
        className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        {agent.data?.name ?? "Agent"}
      </Link>
      <PageHeader
        title="Versions"
        description="Every configuration is kept. Rolling back publishes a copy of an older version as the new active one."
        actions={
          draft ? (
            <Button onClick={() => setPublishOpen(true)}>
              <Rocket /> Publish draft v{draft.version}
            </Button>
          ) : undefined
        }
      />

      {draft && (
        <Notice
          tone="info"
          className="mb-4"
          title={`Draft v${draft.version} is not live`}
        >
          Customers are served by the active version
          {active ? ` (v${active.version})` : ""} until you publish the draft.
        </Notice>
      )}

      <DataTable
        columns={columns}
        rows={list}
        getRowId={(v) => v.id}
        loading={versions.isPending}
        loadingRows={4}
        caption="Agent versions"
        empty={
          <EmptyState
            tone="pi"
            icon={History}
            title="No versions yet"
            description="Publish a configuration to start the history."
            action={
              <Button size="sm" asChild>
                <Link href={`/pi/agents/new?agent=${agentId}`}>
                  New configuration
                </Link>
              </Button>
            }
          />
        }
      />

      <Card className="mt-5">
        <CardHeader
          title="Compare versions"
          icon={<GitCompare />}
          description="Added lines are highlighted green, removed lines red."
        />
        <CardBody className="space-y-4">
          {!list ? (
            <Skeleton className="h-48" />
          ) : list.length < 2 ? (
            <p className="text-[13px] text-muted-foreground">
              At least two versions are needed to compare.
            </p>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <VersionSelect
                  id="compare-left"
                  label="Base version"
                  versions={list}
                  value={leftVersion?.id ?? ""}
                  onChange={setLeft}
                />
                <VersionSelect
                  id="compare-right"
                  label="Compared with"
                  versions={list}
                  value={rightVersion?.id ?? ""}
                  onChange={setRight}
                />
              </div>
              {leftVersion && rightVersion && (
                <>
                  <PropertyList
                    columns={2}
                    items={[
                      {
                        label: "Model",
                        value:
                          leftVersion.model_alias === rightVersion.model_alias
                            ? `${rightVersion.model_alias} (unchanged)`
                            : `${leftVersion.model_alias} → ${rightVersion.model_alias}`,
                      },
                      {
                        label: "Temperature",
                        value:
                          leftVersion.temperature === rightVersion.temperature
                            ? `${Number(rightVersion.temperature).toFixed(2)} (unchanged)`
                            : `${Number(leftVersion.temperature).toFixed(2)} → ${Number(rightVersion.temperature).toFixed(2)}`,
                      },
                    ]}
                  />
                  <SideBySideDiff
                    before={leftVersion.instructions}
                    after={rightVersion.instructions}
                    beforeLabel={`v${leftVersion.version} · ${leftVersion.status}`}
                    afterLabel={`v${rightVersion.version} · ${rightVersion.status}`}
                  />
                </>
              )}
            </>
          )}
        </CardBody>
      </Card>

      <ConfirmDialog
        open={Boolean(rollbackTarget)}
        onOpenChange={(open) => !open && setRollbackTarget(null)}
        title={`Roll back to v${rollbackTarget?.version ?? ""}?`}
        description="A new active version is created as a copy of the selected one."
        consequences={[
          "New messages immediately use the restored instructions, model and temperature.",
          `The current active version${active ? ` (v${active.version})` : ""} is archived and can be restored later.`,
          "Tool assignments are not changed.",
        ]}
        confirmLabel="Roll back"
        loading={rollback.isPending}
        onConfirm={() => rollbackTarget && rollback.mutate(rollbackTarget)}
      />
      <ConfirmDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        title={`Publish draft v${draft?.version ?? ""}?`}
        description="The draft becomes the active configuration for new messages."
        consequences={[
          `The current active version${active ? ` (v${active.version})` : ""} is archived.`,
          "You can roll back from this page at any time.",
        ]}
        confirmLabel="Publish"
        loading={publishDraft.isPending}
        onConfirm={() => draft && publishDraft.mutate(draft)}
      />
    </PageShell>
  );
}

function VersionSelect({
  id,
  label,
  versions,
  value,
  onChange,
}: {
  id: string;
  label: string;
  versions: AgentVersion[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <NativeSelect
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {versions.map((v) => (
          <option key={v.id} value={v.id}>
            v{v.version} · {v.status} · {v.note || "no note"}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
