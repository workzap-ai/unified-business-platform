"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  FlaskConical,
  Pencil,
  Settings2,
  UserCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  formatDateTime,
  formatNumber,
  formatPercent,
  relativeTime,
} from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/display";
import { Switch } from "@/components/ui/controls";
import { Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { PageShell, RequirePermission } from "@/components/app/page";
import {
  ActivityTimeline,
  PropertyList,
  RecordHeader,
} from "@/components/app/record";
import { FormField } from "@/components/app/forms";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { piService, type AgentTestResult } from "../../service";
import type { Agent, AgentVersion, ToolDefinition } from "../../types";
import {
  AGENT_LABELS,
  CapabilityBadge,
  MODEL_ALIASES,
  MUTATION_WARNING,
  PROVIDER_LABELS,
  Stat,
  formatLatency,
  piKeys,
} from "../shared";

const TABS = [
  ["overview", "Overview"],
  ["instructions", "Instructions"],
  ["model", "Model & fallback"],
  ["tools", "Tools"],
  ["test", "Test run"],
  ["versions", "Versions"],
  ["history", "History"],
] as const;

export function AgentDetailPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="pi.agents.manage" area="PI agents">
      <AgentDetail id={id} />
    </RequirePermission>
  );
}

function AgentDetail({ id }: { id: string }) {
  const [state, setState] = useUrlState({ tab: "overview" });
  const agent = useScopedQuery(piKeys.agent(id), () => piService.agent(id));
  const versions = useScopedQuery(piKeys.versions(id), () =>
    piService.versions(id),
  );
  const [editOpen, setEditOpen] = useState(false);
  useBreadcrumbs(agent.data ? [{ label: agent.data.name }] : [], {
    href: `/pi/agents/${id}`,
    kind: "PI agent",
  });

  if (agent.isError) {
    return (
      <PageShell>
        <Card>
          <ErrorState
            error={agent.error}
            onRetry={() => void agent.refetch()}
          />
        </Card>
      </PageShell>
    );
  }
  const a = agent.data;
  const active = versions.data?.find((v) => v.status === "active");
  const tab = TABS.some(([k]) => k === state.tab) ? state.tab : "overview";

  return (
    <PageShell>
      {!a ? (
        <RecordHeader title="" loading />
      ) : (
        <RecordHeader
          icon={Bot}
          title={a.name}
          subtitle={a.role}
          identifier={`v${a.current_version}`}
          status={
            <StatusBadge
              status={a.enabled ? "active" : "disabled"}
              label={a.enabled ? "Enabled" : "Disabled"}
            />
          }
          meta={
            <>
              <span>
                Last run {a.last_run_at ? relativeTime(a.last_run_at) : "never"}
              </span>
              <span>{formatNumber(a.runs_7d)} runs in 7 days</span>
            </>
          }
          actions={
            <>
              <Button variant="secondary" asChild>
                <Link href={`/pi/agents/${a.id}/versions`}>Versions</Link>
              </Button>
              <Button asChild>
                <Link href={`/pi/agents/new?agent=${a.id}`}>
                  <Settings2 /> New configuration
                </Link>
              </Button>
            </>
          }
        />
      )}

      <Tabs value={tab} onValueChange={(value) => setState({ tab: value })}>
        <TabsList aria-label="Agent sections">
          {TABS.map(([key, label]) => (
            <TabsTrigger key={key} value={key}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        {!a ? (
          <Skeleton className="mt-4 h-72 rounded-xl" />
        ) : (
          <>
            <TabsContent value="overview">
              <OverviewTab agent={a} active={active} />
            </TabsContent>
            <TabsContent value="instructions">
              <Card>
                <CardHeader
                  title="Tenant instructions"
                  description={
                    active
                      ? `Active version v${active.version} · ${active.created_by_label} · ${formatDateTime(active.created_at)}`
                      : "No active version"
                  }
                  actions={
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setEditOpen(true)}
                      disabled={!versions.data}
                    >
                      <Pencil /> Edit
                    </Button>
                  }
                />
                <CardBody className="space-y-3">
                  <Notice tone="pi">
                    These instructions add business guidance on top of PI&apos;s
                    built-in safety rules, which can&apos;t be overridden.
                  </Notice>
                  {versions.isPending ? (
                    <Skeleton className="h-40" />
                  ) : versions.isError ? (
                    <ErrorState
                      compact
                      error={versions.error}
                      onRetry={() => void versions.refetch()}
                    />
                  ) : active?.instructions ? (
                    <pre className="scrollbar-thin max-h-[480px] overflow-auto rounded-lg border border-border bg-surface-muted/50 p-3 font-mono text-xs leading-5 whitespace-pre-wrap">
                      {active.instructions}
                    </pre>
                  ) : (
                    <EmptyState
                      compact
                      tone="pi"
                      icon={Pencil}
                      title="No tenant instructions yet"
                      description="PI uses its built-in behaviour for this role. Add guidance to tailor it to your business."
                      action={
                        <Button size="sm" onClick={() => setEditOpen(true)}>
                          Add instructions
                        </Button>
                      }
                    />
                  )}
                </CardBody>
              </Card>
              <EditInstructionsDialog
                open={editOpen}
                onOpenChange={setEditOpen}
                agent={a}
                active={active}
              />
            </TabsContent>
            <TabsContent value="model">
              <ModelTab agent={a} />
            </TabsContent>
            <TabsContent value="tools">
              <AgentToolsCard agent={a} />
            </TabsContent>
            <TabsContent value="test">
              <TestRun agent={a} />
            </TabsContent>
            <TabsContent value="versions">
              <VersionsSummary
                agent={a}
                versions={versions.data}
                error={versions.error}
                onRetry={() => void versions.refetch()}
              />
            </TabsContent>
            <TabsContent value="history">
              <Card>
                <CardHeader
                  title="Version history"
                  description="Every published configuration, newest first"
                />
                <CardBody>
                  {versions.isError ? (
                    <ErrorState
                      compact
                      error={versions.error}
                      onRetry={() => void versions.refetch()}
                    />
                  ) : (
                    <ActivityTimeline
                      loading={versions.isPending}
                      events={versions.data?.map((v) => ({
                        id: v.id,
                        kind: v.status === "active" ? "ai" : "updated",
                        title: (
                          <span className="flex flex-wrap items-center gap-1.5">
                            Version {v.version}
                            <StatusBadge status={v.status} />
                          </span>
                        ),
                        description: v.note || "No note",
                        actor: v.created_by_label,
                        at: v.created_at,
                      }))}
                      empty="No versions published yet."
                    />
                  )}
                </CardBody>
              </Card>
            </TabsContent>
          </>
        )}
      </Tabs>
    </PageShell>
  );
}

function OverviewTab({
  agent,
  active,
}: {
  agent: Agent;
  active?: AgentVersion;
}) {
  const alias = MODEL_ALIASES.find((m) => m.value === agent.model_alias);
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader title="What this agent does" />
        <CardBody className="space-y-4">
          <p className="text-[13.5px] leading-relaxed text-foreground-secondary">
            {agent.description}
          </p>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Runs (7d)" value={formatNumber(agent.runs_7d)} />
            <Stat
              label="Success rate"
              value={agent.runs_7d ? formatPercent(agent.success_rate, 1) : "—"}
            />
            <Stat
              label="Avg latency"
              value={formatLatency(agent.avg_latency_ms)}
            />
            <Stat label="Tools" value={formatNumber(agent.tools.length)} />
          </dl>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Current version" />
        <CardBody>
          <PropertyList
            items={[
              { label: "Version", value: `v${agent.current_version}` },
              { label: "Model", value: alias?.label ?? agent.model_alias },
              {
                label: "Temperature",
                value: Number(agent.temperature).toFixed(2),
              },
              { label: "Published by", value: active?.created_by_label },
              {
                label: "Published",
                value: active ? relativeTime(active.created_at) : undefined,
              },
              { label: "Note", value: active?.note || undefined },
            ]}
          />
        </CardBody>
      </Card>
    </div>
  );
}

const editSchema = z.object({
  instructions: z
    .string()
    .max(4000, "Keep instructions under 4,000 characters"),
  note: z
    .string()
    .trim()
    .min(3, "Describe what changed in a few words")
    .max(200, "Keep the note under 200 characters"),
});
type EditValues = z.infer<typeof editSchema>;

function EditInstructionsDialog({
  open,
  onOpenChange,
  agent,
  active,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agent: Agent;
  active?: AgentVersion;
}) {
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    values: { instructions: active?.instructions ?? "", note: "" },
  });
  const publish = useScopedMutation(
    (values: EditValues) =>
      piService.publishVersion(agent.id, {
        instructions: values.instructions,
        model_alias: agent.model_alias,
        temperature: agent.temperature,
        note: values.note,
      }),
    {
      invalidate: [[...piKeys.agents]],
      success: (v) => `Version ${v.version} published`,
      onSuccess: () => onOpenChange(false),
    },
  );
  const length = useWatch({
    control: form.control,
    name: "instructions",
  }).length;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <form
          onSubmit={form.handleSubmit((v) => publish.mutate(v))}
          noValidate
          className="flex min-h-0 flex-1 flex-col"
        >
          <DialogHeader
            title={`Edit ${agent.name} instructions`}
            description="Saving publishes a new active version. The current version is archived and can be restored."
          />
          <DialogBody className="space-y-4">
            <FormField
              label="Tenant instructions"
              htmlFor="edit-instructions"
              error={form.formState.errors.instructions}
              help={`${formatNumber(length)} / 4,000 characters. Built-in safety rules still apply.`}
            >
              <Textarea
                id="edit-instructions"
                rows={12}
                maxLength={4000}
                className="font-mono text-[13px]"
                {...form.register("instructions")}
              />
            </FormField>
            <FormField
              label="Change note"
              htmlFor="edit-note"
              required
              error={form.formState.errors.note}
            >
              <Textarea
                id="edit-note"
                rows={2}
                maxLength={200}
                {...form.register("note")}
              />
            </FormField>
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
              disabled={publish.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={publish.isPending}
              disabled={!form.formState.isDirty}
            >
              Publish new version
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ModelTab({ agent }: { agent: Agent }) {
  const settings = useScopedQuery(piKeys.settings, () => piService.settings());
  const alias = MODEL_ALIASES.find((m) => m.value === agent.model_alias);
  const order = settings.data?.provider_config.order ?? [];
  const roles = ["Primary", "Fallback", "Secondary fallback"];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="Model"
          actions={
            <Link
              href={`/pi/agents/new?agent=${agent.id}`}
              className="text-xs font-medium text-primary hover:underline"
            >
              Change
            </Link>
          }
        />
        <CardBody>
          <PropertyList
            items={[
              { label: "Model tier", value: alias?.label ?? agent.model_alias },
              {
                label: "Temperature",
                value: Number(agent.temperature).toFixed(2),
              },
            ]}
          />
          {alias && (
            <p className="mt-2 text-xs text-muted-foreground">
              {alias.description}
            </p>
          )}
        </CardBody>
      </Card>
      <Card>
        <CardHeader
          title="Fallback chain"
          description="Shared by every agent in this workspace"
          actions={
            <Link
              href="/pi/settings/provider-configuration"
              className="text-xs font-medium text-primary hover:underline"
            >
              Provider settings
            </Link>
          }
        />
        <CardBody>
          {settings.isPending ? (
            <Skeleton className="h-32" />
          ) : settings.isError ? (
            <ErrorState
              compact
              error={settings.error}
              onRetry={() => void settings.refetch()}
            />
          ) : (
            <ol className="space-y-2">
              {order.map((p, i) => (
                <li
                  key={p}
                  className="flex items-center gap-3 rounded-lg border border-border px-3 py-2 text-[13px]"
                >
                  <span className="tabular flex size-6 items-center justify-center rounded-full bg-surface-muted text-xs font-semibold">
                    {i + 1}
                  </span>
                  <span className="flex-1 font-medium">
                    {PROVIDER_LABELS[p]}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {roles[i] ?? "Fallback"}
                  </span>
                </li>
              ))}
              <li className="flex items-center gap-3 rounded-lg border border-dashed border-border px-3 py-2 text-[13px]">
                <UserCheck className="size-4 text-warning" aria-hidden="true" />
                <span className="flex-1 font-medium">Human handoff</span>
                <span className="text-xs text-muted-foreground">
                  Always last
                </span>
              </li>
            </ol>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

export function AgentToolsCard({ agent }: { agent: Agent }) {
  const tools = useScopedQuery(piKeys.tools, () => piService.tools());
  const toggle = useScopedMutation(
    (input: { tool: string; enabled: boolean }) =>
      piService.setAgentTool(agent.id, input.tool, input.enabled),
    {
      invalidate: [[...piKeys.agents]],
      success: (a) => `${a.name} tools updated`,
    },
  );
  const assigned = new Set(agent.tools);
  const list: ToolDefinition[] | undefined = tools.data
    ? [...tools.data].sort(
        (x, y) => Number(assigned.has(y.key)) - Number(assigned.has(x.key)),
      )
    : undefined;
  return (
    <Card>
      <CardHeader
        title="Tools this agent can use"
        description={`${formatNumber(agent.tools.length)} assigned. Permissions and business rules are still checked on every call.`}
        actions={
          <Link
            href={`/pi/agents/${agent.id}/tools`}
            className="text-xs font-medium text-primary hover:underline"
          >
            Tool catalog
          </Link>
        }
      />
      <CardBody>
        {tools.isError ? (
          <ErrorState
            compact
            error={tools.error}
            onRetry={() => void tools.refetch()}
          />
        ) : !list ? (
          <Skeleton className="h-64" />
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {list.map((tool) => {
              const id = `agent-tool-${tool.key}`;
              const mutation = tool.capability === "mutation";
              return (
                <li
                  key={tool.key}
                  className={cn(
                    "flex items-start gap-3 px-3 py-2.5",
                    mutation && "bg-warning-soft/40",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <label htmlFor={id} className="text-[13px] font-medium">
                        {tool.name}
                      </label>
                      <CapabilityBadge capability={tool.capability} />
                      {!tool.enabled && (
                        <Badge tone="neutral">Off workspace-wide</Badge>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {tool.description}
                    </p>
                    {mutation && (
                      <p className="mt-1 flex items-center gap-1 text-xs font-medium text-warning">
                        <AlertTriangle
                          className="size-3.5"
                          aria-hidden="true"
                        />
                        {MUTATION_WARNING}
                      </p>
                    )}
                  </div>
                  <Switch
                    id={id}
                    checked={assigned.has(tool.key)}
                    disabled={
                      toggle.isPending && toggle.variables?.tool === tool.key
                    }
                    onCheckedChange={(enabled) =>
                      toggle.mutate({ tool: tool.key, enabled })
                    }
                  />
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

function TestRun({ agent }: { agent: Agent }) {
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<AgentTestResult | null>(null);
  const run = useScopedMutation((text: string) => piService.testAgent(text), {
    error: "The test run couldn't complete. Try again.",
    onSuccess: (r) => setResult(r),
  });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="Test a message"
          description="See how PI would route a customer message."
          icon={<FlaskConical />}
        />
        <CardBody className="space-y-3">
          <Notice tone="info" title="Simulation — no customer message is sent">
            Nothing is written to conversations, orders or customers.
          </Notice>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (message.trim()) run.mutate(message.trim());
            }}
            className="space-y-3"
          >
            <FormField
              label="Customer message"
              htmlFor="test-message"
              help="Try e.g. “Is the blue kurta in stock in medium?”"
            >
              <Textarea
                id="test-message"
                rows={4}
                maxLength={1000}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </FormField>
            <Button
              type="submit"
              loading={run.isPending}
              disabled={!message.trim()}
            >
              Run simulation
            </Button>
          </form>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Result" />
        <CardBody>
          {run.isPending ? (
            <Skeleton className="h-40" />
          ) : !result ? (
            <EmptyState
              compact
              tone="pi"
              icon={FlaskConical}
              title="No test yet"
              description="Results show the detected intent, route and tools PI would use."
            />
          ) : (
            <div className="space-y-4" aria-live="polite">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">Simulation</Badge>
                {result.route.includes(agent.key) ? (
                  <Badge tone="pi">Reaches {agent.name}</Badge>
                ) : (
                  <Badge tone="outline">Doesn&apos;t reach {agent.name}</Badge>
                )}
              </div>
              <PropertyList
                items={[
                  { label: "Intent", value: result.intent.replace(/_/g, " ") },
                  {
                    label: "Confidence",
                    value: formatPercent(result.confidence),
                  },
                ]}
              />
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                  Route
                </p>
                <ol className="flex flex-wrap items-center gap-1.5">
                  {result.route.map((key, i) => (
                    <li
                      key={`${key}-${i}`}
                      className="flex items-center gap-1.5"
                    >
                      <Badge tone={key === agent.key ? "pi" : "neutral"}>
                        {AGENT_LABELS[key]}
                      </Badge>
                      {i < result.route.length - 1 && (
                        <ArrowRight
                          className="size-3 text-muted-foreground"
                          aria-hidden="true"
                        />
                      )}
                    </li>
                  ))}
                </ol>
              </div>
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                  Tools that would be used
                </p>
                {result.tools.length ? (
                  <ul className="flex flex-wrap gap-1.5">
                    {result.tools.map((t) => (
                      <li key={t}>
                        <Badge tone="outline" className="font-mono">
                          {t}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[13px] text-muted-foreground">None</p>
                )}
              </div>
              <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px] text-foreground-secondary">
                {result.note}
              </p>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function VersionsSummary({
  agent,
  versions,
  error,
  onRetry,
}: {
  agent: Agent;
  versions?: AgentVersion[];
  error: unknown;
  onRetry: () => void;
}) {
  return (
    <Card>
      <CardHeader
        title="Versions"
        description="Recent configurations. Compare, roll back or publish drafts on the versions page."
        actions={
          <Link
            href={`/pi/agents/${agent.id}/versions`}
            className="text-xs font-medium text-primary hover:underline"
          >
            All versions
          </Link>
        }
      />
      <CardBody>
        {error ? (
          <ErrorState compact error={error} onRetry={onRetry} />
        ) : !versions ? (
          <Skeleton className="h-32" />
        ) : versions.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">No versions yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {versions.slice(0, 5).map((v) => (
              <li
                key={v.id}
                className="flex items-center gap-3 py-2 text-[13px]"
              >
                <span className="w-10 font-mono text-xs">v{v.version}</span>
                <StatusBadge status={v.status} />
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {v.note || "No note"}
                </span>
                <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">
                  {relativeTime(v.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
