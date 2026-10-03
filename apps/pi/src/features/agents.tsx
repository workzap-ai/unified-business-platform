"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bot,
  ChevronRight,
  History,
  RotateCcw,
  Send,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { SubNav } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogClose,
  DialogContent,
  EmptyState,
  ErrorState,
  Field,
  LoadingBlock,
  Notice,
  PageHeader,
  Select,
  Switch,
  Textarea,
} from "@/components/ui";
import { errorText, get, post, put } from "@/lib/api";
import { cn } from "@/lib/cn";
import { dateTime, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

/* ------------------------------------------------------------------ types */

type ModelAlias = "fast" | "balanced" | "reasoning";

/** GET /pi/agents and /pi/agents/{id} (config_routes.agent_view). */
export type Agent = {
  id: string;
  key: string;
  name: string;
  role: string;
  description: string;
  enabled: boolean;
  current_version: number;
  model_alias: ModelAlias;
  temperature: string;
  /** Tool keys this agent may use (allowed for the business and not switched off here). */
  tools: string[];
  runs_7d: number;
  success_rate: number;
  avg_latency_ms: number;
  last_run_at: string | null;
};

/** config_routes.version_view */
export type AgentVersion = {
  id: string;
  agent_id: string;
  version: number;
  status: "active" | "archived";
  instructions: string;
  model_alias: ModelAlias;
  temperature: string;
  note: string;
  created_by_label: string;
  created_at: string;
};

/** GET /pi/tools */
export type ToolDefinition = {
  key: string;
  name: string;
  description: string;
  capability: "read" | "draft" | "mutation" | "communication";
  permission: string;
  requires_confirmation: boolean;
  /** Allowed for the whole business (My Pi -> Tools). */
  enabled: boolean;
  calls_7d: number;
  failures_7d: number;
  last_called_at: string | null;
};

/** POST /pi/agent-test: a routing preview, not a real reply. */
type AgentTestResult = {
  simulated: boolean;
  intent: string;
  confidence: number;
  route: string[];
  tools: string[];
  note: string;
};

/* -------------------------------------------------------------- constants */

const SECTIONS = [
  { href: "/my-pi/knowledge", label: "Business knowledge" },
  { href: "/my-pi/behaviour", label: "Behaviour" },
  { href: "/my-pi/agents", label: "Agents" },
  { href: "/my-pi/tools", label: "Tools" },
  { href: "/my-pi/follow-ups", label: "Follow-ups" },
  { href: "/my-pi/test", label: "Test pi" },
];

const PERMISSION = "pi.agents.manage";
const MAX_INSTRUCTIONS = 4000;

const FRIENDLY: Record<string, { name: string; role: string }> = {
  router: {
    name: "Front desk",
    role: "Reads every message first and passes it to the right helper.",
  },
  customer_memory: {
    name: "Customer memory",
    role: "Remembers what customers tell pi, like names and preferences.",
  },
  support: {
    name: "Customer help",
    role: "Answers questions using your business knowledge.",
  },
  requirement: {
    name: "Enquiries",
    role: "Collects what a customer needs so your team can quote.",
  },
  sales_order: {
    name: "Orders",
    role: "Helps customers place and check orders.",
  },
  handoff: {
    name: "Team handover",
    role: "Passes the conversation to your team when a person should step in.",
  },
};

const MODEL_LABEL: Record<ModelAlias, string> = {
  fast: "Fast",
  balanced: "Balanced",
  reasoning: "Thorough",
};

const MODEL_HINT: Record<ModelAlias, string> = {
  fast: "Quick, short answers. Best for most helpers.",
  balanced: "A little slower, a little more careful.",
  reasoning: "Slowest. Thinks harder before answering.",
};

const CAPABILITY: Record<
  ToolDefinition["capability"],
  { label: string; tone: "info" | "neutral" | "warning" | "accent" }
> = {
  read: { label: "Looks things up", tone: "info" },
  draft: { label: "Prepares drafts", tone: "neutral" },
  mutation: { label: "Changes records", tone: "warning" },
  communication: { label: "Sends messages", tone: "accent" },
};

const OUTLINE = `Role:
You are ...

Goals:
- ...

Style:
- Friendly, short replies in the customer's language.

Hand to the team when:
- The customer asks for a person.
- ...`;

function friendly(agent: Pick<Agent, "key" | "name" | "description">) {
  return FRIENDLY[agent.key] ?? { name: agent.name, role: agent.description };
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function seconds(ms: number) {
  if (!ms) return "-";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/* ------------------------------------------------------------------ shell */

function Shell({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  const can = useCan();
  return (
    <div className="min-w-0">
      <PageHeader title={title} description={description} action={action} />
      <SubNav items={SECTIONS} />
      <div className="mt-6 min-w-0">
        {can(PERMISSION) ? (
          children
        ) : (
          <Notice tone="warning" title="You can't manage agents">
            Ask your business owner to give you access to pi&apos;s agents.
          </Notice>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------- list */

export function AgentsPage() {
  return (
    <Shell
      title="Agents"
      description="pi is a small team of helpers. Each one handles a part of the conversation."
    >
      <AgentList />
    </Shell>
  );
}

function AgentList() {
  const key = useBusinessKey();
  const query = useQuery({
    queryKey: key(["agents"]),
    queryFn: () => get<Agent[]>("/pi/agents"),
  });
  if (query.isPending) return <LoadingBlock rows={4} label="Loading agents" />;
  if (query.isError)
    return (
      <ErrorState
        message={errorText(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  if (!query.data.length)
    return (
      <Card>
        <EmptyState
          icon={<Bot className="size-6" aria-hidden />}
          title="No agents yet"
        >
          pi sets up its helpers the first time you open this page. Try again in
          a moment.
        </EmptyState>
      </Card>
    );
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {query.data.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}

function AgentCard({ agent }: { agent: Agent }) {
  const { name, role } = friendly(agent);
  const toggle = useAction(
    (enabled: boolean) =>
      put<Agent>(`/pi/agents/${agent.id}/enabled`, { enabled }),
    {
      success: (a) => (a.enabled ? `${name} is on` : `${name} is off`),
      invalidate: [["agents"]],
    },
  );
  const enabled = toggle.isPending ? Boolean(toggle.variables) : agent.enabled;
  const switchId = `agent-enabled-${agent.id}`;
  return (
    <Card className="min-w-0">
      <CardSection className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold">{name}</h2>
              <Badge tone="accent">{MODEL_LABEL[agent.model_alias]}</Badge>
              {!enabled ? <Badge>Off</Badge> : null}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{role}</p>
          </div>
          <label
            htmlFor={switchId}
            className="flex min-h-11 min-w-11 shrink-0 cursor-pointer items-center justify-end"
          >
            <Switch
              id={switchId}
              checked={enabled}
              disabled={toggle.isPending}
              onCheckedChange={(value) => toggle.mutate(value)}
              label={`${name} on or off`}
            />
          </label>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Stat label="Runs (7 days)" value={String(agent.runs_7d)} />
          <Stat
            label="Success"
            value={agent.runs_7d ? percent(agent.success_rate) : "-"}
          />
          <Stat label="Avg. time" value={seconds(agent.avg_latency_ms)} />
          <Stat
            label="Last run"
            value={agent.last_run_at ? timeAgo(agent.last_run_at) : "Not yet"}
          />
        </dl>
        <Button asChild variant="secondary" className="w-full sm:w-auto">
          <Link href={`/my-pi/agents/${agent.id}`}>
            Open {name}
            <ChevronRight className="size-4" aria-hidden />
          </Link>
        </Button>
      </CardSection>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-surface-muted px-3 py-2">
      <dt className="truncate text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate font-medium">{value}</dd>
    </div>
  );
}

/* ----------------------------------------------------------------- detail */

type Tab = "instructions" | "tools" | "versions" | "test";
const TABS: { id: Tab; label: string }[] = [
  { id: "instructions", label: "Instructions" },
  { id: "tools", label: "Tools" },
  { id: "versions", label: "Versions" },
  { id: "test", label: "Test" },
];

function useAgent(id: string) {
  const key = useBusinessKey();
  return useQuery({
    queryKey: key(["agents", id]),
    queryFn: () => get<Agent>(`/pi/agents/${id}`),
  });
}

function useVersions(id: string) {
  const key = useBusinessKey();
  return useQuery({
    queryKey: key(["agents", id, "versions"]),
    queryFn: () => get<AgentVersion[]>(`/pi/agents/${id}/versions`),
  });
}

export function AgentDetailPage({ id }: { id: string }) {
  const agent = useAgent(id);
  const can = useCan();
  const title = agent.data ? friendly(agent.data).name : "Agent";
  const description = agent.data
    ? friendly(agent.data).role
    : "One of pi's helpers.";
  return (
    <Shell
      title={title}
      description={description}
      action={
        <Button asChild variant="ghost">
          <Link href="/my-pi/agents">
            <ArrowLeft className="size-4" aria-hidden />
            All agents
          </Link>
        </Button>
      }
    >
      {!can(PERMISSION) ? null : agent.isPending ? (
        <LoadingBlock rows={4} label="Loading agent" />
      ) : agent.isError ? (
        <ErrorState
          message={errorText(agent.error)}
          onRetry={() => agent.refetch()}
        />
      ) : (
        <AgentDetail agent={agent.data} />
      )}
    </Shell>
  );
}

function AgentDetail({ agent }: { agent: Agent }) {
  const [tab, setTab] = React.useState<Tab>("instructions");
  const tabRefs = React.useRef<Record<Tab, HTMLButtonElement | null>>({
    instructions: null,
    tools: null,
    versions: null,
    test: null,
  });
  function onKey(event: React.KeyboardEvent) {
    const index = TABS.findIndex((t) => t.id === tab);
    const step =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = TABS[(index + step + TABS.length) % TABS.length].id;
    setTab(next);
    tabRefs.current[next]?.focus();
  }
  return (
    <div className="min-w-0 space-y-5">
      {!agent.enabled ? (
        <Notice tone="warning" title="This helper is off">
          pi won&apos;t use it until you switch it back on from the Agents list.
        </Notice>
      ) : null}
      <div
        role="tablist"
        aria-label="Agent settings"
        onKeyDown={onKey}
        className="grid grid-cols-2 gap-1 rounded-xl border border-border bg-surface p-1 sm:inline-grid sm:grid-cols-4"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              tabRefs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            className={cn(
              "min-h-11 rounded-lg px-4 text-sm font-medium text-foreground-secondary hover:text-foreground focus-visible:outline-2",
              tab === t.id && "bg-accent-soft text-accent-soft-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        className="min-w-0"
      >
        {tab === "instructions" ? <InstructionsTab agent={agent} /> : null}
        {tab === "tools" ? <ToolsTab agent={agent} /> : null}
        {tab === "versions" ? <VersionsTab agent={agent} /> : null}
        {tab === "test" ? <TestTab agent={agent} /> : null}
      </div>
    </div>
  );
}

/* ----------------------------------------------------- instructions tab */

function InstructionsTab({ agent }: { agent: Agent }) {
  const versions = useVersions(agent.id);
  if (versions.isPending) return <LoadingBlock rows={3} />;
  if (versions.isError)
    return (
      <ErrorState
        message={errorText(versions.error)}
        onRetry={() => versions.refetch()}
      />
    );
  const active = versions.data.find((v) => v.status === "active");
  return (
    <InstructionsEditor
      key={active?.id ?? "none"}
      agent={agent}
      active={active}
    />
  );
}

function InstructionsEditor({
  agent,
  active,
}: {
  agent: Agent;
  active: AgentVersion | undefined;
}) {
  const [instructions, setInstructions] = React.useState(
    active?.instructions ?? "",
  );
  const [model, setModel] = React.useState<ModelAlias>(
    active?.model_alias ?? agent.model_alias,
  );
  const [temperature, setTemperature] = React.useState(
    Number(active?.temperature ?? agent.temperature) || 0,
  );
  const [note, setNote] = React.useState("");
  const original = {
    instructions: active?.instructions ?? "",
    model: active?.model_alias ?? agent.model_alias,
    temperature: Number(active?.temperature ?? agent.temperature) || 0,
  };
  const changed =
    instructions !== original.instructions ||
    model !== original.model ||
    temperature !== original.temperature;
  const tooLong = instructions.length > MAX_INSTRUCTIONS;
  const save = useAction(
    () =>
      post<AgentVersion>(`/pi/agents/${agent.id}/versions`, {
        instructions,
        model_alias: model,
        temperature: Number(temperature.toFixed(2)),
        note: note.trim(),
      }),
    {
      success: (v) => `Saved as version ${v.version}. pi uses it now.`,
      invalidate: [["agents"]],
      onSuccess: () => setNote(""),
    },
  );
  const id = `agent-${agent.id}`;
  return (
    <form
      className="grid min-w-0 grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]"
      onSubmit={(event) => {
        event.preventDefault();
        if (changed && !tooLong) save.mutate(undefined);
      }}
    >
      <Card className="min-w-0">
        <CardSection className="space-y-3">
          <Field
            label="Instructions"
            htmlFor={`${id}-instructions`}
            hint="Tell this helper what to do in plain words. Saving makes a new version that pi uses straight away."
            error={
              tooLong
                ? `Please keep it under ${MAX_INSTRUCTIONS} characters.`
                : null
            }
          >
            <Textarea
              id={`${id}-instructions`}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder={OUTLINE}
              rows={14}
              className="min-h-72 font-mono text-base leading-relaxed sm:text-sm"
              aria-describedby={`${id}-count`}
            />
          </Field>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p
              id={`${id}-count`}
              className={cn(
                "text-xs text-muted-foreground",
                tooLong && "font-medium text-danger",
              )}
              aria-live="polite"
            >
              {instructions.length} / {MAX_INSTRUCTIONS}
            </p>
            {!instructions.trim() ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setInstructions(OUTLINE)}
              >
                Start from an outline
              </Button>
            ) : null}
          </div>
        </CardSection>
      </Card>
      <Card className="min-w-0 self-start">
        <CardSection className="space-y-4">
          <Field
            label="Thinking style"
            htmlFor={`${id}-model`}
            hint={MODEL_HINT[model]}
          >
            <Select
              id={`${id}-model`}
              value={model}
              onChange={(e) => setModel(e.target.value as ModelAlias)}
              className="text-base sm:text-[15px]"
            >
              {(Object.keys(MODEL_LABEL) as ModelAlias[]).map((m) => (
                <option key={m} value={m}>
                  {MODEL_LABEL[m]}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label={`Creativity: ${temperature.toFixed(2)}`}
            htmlFor={`${id}-temperature`}
            hint="Lower keeps answers steady and predictable. Higher adds variety."
          >
            <input
              id={`${id}-temperature`}
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))}
              className="h-11 w-full accent-accent"
            />
          </Field>
          <Field
            label="What changed?"
            htmlFor={`${id}-note`}
            optional
            hint="A short note so you can find this version later."
          >
            <Textarea
              id={`${id}-note`}
              value={note}
              maxLength={200}
              onChange={(e) => setNote(e.target.value)}
              className="min-h-20 text-base sm:text-[15px]"
            />
          </Field>
          <Button
            type="submit"
            className="w-full"
            loading={save.isPending}
            disabled={!changed || tooLong}
          >
            Save new version
          </Button>
          <p className="text-xs text-muted-foreground">
            {active
              ? `Now using version ${active.version}, saved ${timeAgo(active.created_at)}.`
              : "No saved version yet."}
          </p>
        </CardSection>
      </Card>
    </form>
  );
}

/* --------------------------------------------------------------- tools */

function ToolsTab({ agent }: { agent: Agent }) {
  const key = useBusinessKey();
  const tools = useQuery({
    queryKey: key(["pi-tools"]),
    queryFn: () => get<ToolDefinition[]>("/pi/tools"),
  });
  if (tools.isPending) return <LoadingBlock rows={4} label="Loading tools" />;
  if (tools.isError)
    return (
      <ErrorState
        message={errorText(tools.error)}
        onRetry={() => tools.refetch()}
      />
    );
  if (!tools.data.length)
    return (
      <Card>
        <EmptyState title="No tools available">
          pi doesn&apos;t have any tools to use yet.
        </EmptyState>
      </Card>
    );
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Choose what this helper may do. Tools switched off for the whole
        business in{" "}
        <Link href="/my-pi/tools" className="text-accent underline">
          My pi Tools
        </Link>{" "}
        stay off here too.
      </p>
      <Card className="min-w-0">
        <ul className="divide-y divide-border">
          {tools.data.map((tool) => (
            <ToolRow key={tool.key} agent={agent} tool={tool} />
          ))}
        </ul>
      </Card>
    </div>
  );
}

function ToolRow({ agent, tool }: { agent: Agent; tool: ToolDefinition }) {
  const toggle = useAction(
    (enabled: boolean) =>
      put<Agent>(`/pi/agents/${agent.id}/tools/${tool.key}`, { enabled }),
    {
      success: () => `${tool.name} updated`,
      invalidate: [["agents"]],
    },
  );
  const on = toggle.isPending
    ? Boolean(toggle.variables)
    : agent.tools.includes(tool.key);
  const capability = CAPABILITY[tool.capability];
  const switchId = `tool-${agent.id}-${tool.key}`;
  return (
    <li className="flex min-w-0 items-start justify-between gap-3 p-4 sm:p-5">
      <div className="min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={switchId} className="font-medium">
            {tool.name}
          </label>
          {capability ? (
            <Badge tone={capability.tone}>{capability.label}</Badge>
          ) : null}
          {!tool.enabled ? <Badge>Off for business</Badge> : null}
        </div>
        <p className="text-sm text-muted-foreground">{tool.description}</p>
        {tool.requires_confirmation ? (
          <p className="text-xs text-warning">
            Needs confirmation: pi asks the customer or your team before this
            happens.
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          {tool.calls_7d
            ? `${tool.calls_7d} uses in 7 days${tool.failures_7d ? `, ${tool.failures_7d} failed` : ""}`
            : "Not used in the last 7 days"}
        </p>
      </div>
      <label
        htmlFor={switchId}
        className="flex min-h-11 min-w-11 shrink-0 cursor-pointer items-center justify-end"
      >
        <Switch
          id={switchId}
          checked={on && tool.enabled}
          disabled={!tool.enabled || toggle.isPending}
          onCheckedChange={(value) => toggle.mutate(value)}
          label={`Let this helper use ${tool.name}`}
        />
      </label>
    </li>
  );
}

/* ------------------------------------------------------------ versions */

type DiffLine = { kind: "same" | "added" | "removed"; text: string };

/** Line diff via longest common subsequence (instructions are short). */
function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const n = a.length;
  const m = b.length;
  const table: number[][] = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0),
  );
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i][j] =
        a[i] === b[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i] });
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      out.push({ kind: "removed", text: a[i++] });
    } else {
      out.push({ kind: "added", text: b[j++] });
    }
  }
  while (i < n) out.push({ kind: "removed", text: a[i++] });
  while (j < m) out.push({ kind: "added", text: b[j++] });
  return out;
}

function LineDiff({ before, after }: { before: string; after: string }) {
  const lines = diffLines(before, after);
  if (!lines.some((l) => l.kind !== "same"))
    return (
      <p className="text-sm text-muted-foreground">
        Same instructions as the version pi uses now.
      </p>
    );
  return (
    <div className="min-w-0 space-y-2">
      <p className="text-xs text-muted-foreground">
        Compared with the version pi uses now:{" "}
        <span className="text-success">+ in this version</span>,{" "}
        <span className="text-danger">- only in the current one</span>.
      </p>
      <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-surface-sunken p-3 font-mono text-xs leading-relaxed">
        {lines.map((line, index) => (
          <div
            key={index}
            className={cn(
              "px-1",
              line.kind === "added" && "bg-success-soft text-success",
              line.kind === "removed" && "bg-danger-soft text-danger",
            )}
          >
            {line.kind === "added"
              ? "+ "
              : line.kind === "removed"
                ? "- "
                : "  "}
            {line.text || " "}
          </div>
        ))}
      </pre>
    </div>
  );
}

function VersionsTab({ agent }: { agent: Agent }) {
  const versions = useVersions(agent.id);
  const [open, setOpen] = React.useState<string | null>(null);
  if (versions.isPending) return <LoadingBlock rows={3} />;
  if (versions.isError)
    return (
      <ErrorState
        message={errorText(versions.error)}
        onRetry={() => versions.refetch()}
      />
    );
  if (!versions.data.length)
    return (
      <Card>
        <EmptyState
          icon={<History className="size-6" aria-hidden />}
          title="No versions yet"
        >
          Save instructions to create the first version.
        </EmptyState>
      </Card>
    );
  const active = versions.data.find((v) => v.status === "active");
  return (
    <Card className="min-w-0">
      <ul className="divide-y divide-border">
        {versions.data.map((version) => (
          <li key={version.id} className="min-w-0 p-4 sm:p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Version {version.version}</span>
                  {version.status === "active" ? (
                    <Badge tone="success">In use</Badge>
                  ) : null}
                  <Badge>{MODEL_LABEL[version.model_alias]}</Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {version.note || "No note"}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {dateTime(version.created_at)}
                  {version.created_by_label
                    ? ` by ${version.created_by_label}`
                    : ""}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  className="min-h-11"
                  aria-expanded={open === version.id}
                  onClick={() =>
                    setOpen(open === version.id ? null : version.id)
                  }
                >
                  {open === version.id ? "Hide" : "View"}
                </Button>
                {version.status !== "active" ? (
                  <RollbackButton agent={agent} version={version} />
                ) : null}
              </div>
            </div>
            {open === version.id ? (
              <div className="mt-4">
                {version.status === "active" || !active ? (
                  <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-surface-sunken p-3 font-mono text-xs leading-relaxed">
                    {version.instructions || "No instructions."}
                  </pre>
                ) : (
                  <LineDiff
                    before={active.instructions}
                    after={version.instructions}
                  />
                )}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function RollbackButton({
  agent,
  version,
}: {
  agent: Agent;
  version: AgentVersion;
}) {
  const [open, setOpen] = React.useState(false);
  const rollback = useAction(
    () =>
      post<AgentVersion>(
        `/pi/agents/${agent.id}/versions/${version.id}/rollback`,
      ),
    {
      success: (v) =>
        `Back to version ${version.version} (saved as version ${v.version})`,
      invalidate: [["agents"]],
      onSuccess: () => setOpen(false),
    },
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        variant="secondary"
        size="sm"
        className="min-h-11"
        onClick={() => setOpen(true)}
      >
        <RotateCcw className="size-4" aria-hidden />
        Use this version
      </Button>
      <DialogContent
        title={`Go back to version ${version.version}?`}
        description="pi will start using these instructions straight away. Nothing is deleted: this is saved as a new version, so you can switch again later."
      >
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <DialogClose asChild>
            <Button variant="secondary">Cancel</Button>
          </DialogClose>
          <Button
            loading={rollback.isPending}
            onClick={() => rollback.mutate(undefined)}
          >
            Use version {version.version}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------- test */

function TestTab({ agent }: { agent: Agent }) {
  const [message, setMessage] = React.useState("");
  const [result, setResult] = React.useState<
    (AgentTestResult & { latency: number; message: string }) | null
  >(null);
  const test = useAction(
    async (body: string) => {
      const started = performance.now();
      const data = await post<AgentTestResult>("/pi/agent-test", { body });
      return {
        ...data,
        latency: performance.now() - started,
        message: body,
      };
    },
    { onSuccess: setResult },
  );
  const id = `agent-test-${agent.id}`;
  const trimmed = message.trim();
  return (
    <div className="grid min-w-0 grid-cols-1 gap-5 lg:grid-cols-2">
      <Card className="min-w-0">
        <CardSection>
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (trimmed) test.mutate(trimmed);
            }}
          >
            <Field
              label="Try a customer message"
              htmlFor={id}
              hint="See which helper pi would pick. Nothing is sent and no records are created."
            >
              <Textarea
                id={id}
                value={message}
                maxLength={MAX_INSTRUCTIONS}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Hi, do you deliver to Lahore? How much is it?"
                className="text-base sm:text-[15px]"
              />
            </Field>
            <Button
              type="submit"
              className="w-full sm:w-auto"
              loading={test.isPending}
              disabled={!trimmed}
            >
              <Send className="size-4" aria-hidden />
              Run test
            </Button>
          </form>
        </CardSection>
      </Card>
      <Card className="min-w-0">
        <CardSection aria-live="polite">
          {!result ? (
            <p className="text-sm text-muted-foreground">
              The result shows here: what pi thinks the customer wants, which
              helpers handle it, and how long it took.
            </p>
          ) : (
            <div className="space-y-4">
              <div className="rounded-xl bg-surface-muted p-3 text-sm">
                <p className="text-xs text-muted-foreground">Customer said</p>
                <p className="mt-1 break-words">{result.message}</p>
              </div>
              <div className="rounded-xl border border-border p-3 text-sm">
                <p className="text-xs text-muted-foreground">
                  What would happen
                </p>
                <p className="mt-1 break-words">{result.note}</p>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Stat
                  label="Customer wants"
                  value={result.intent.replace(/_/g, " ")}
                />
                <Stat label="Confidence" value={percent(result.confidence)} />
                <Stat label="Time" value={seconds(result.latency)} />
                <Stat
                  label="Tools used"
                  value={
                    result.tools.length
                      ? result.tools.map((t) => t.replace(/_/g, " ")).join(", ")
                      : "None"
                  }
                />
              </dl>
              <div>
                <p className="text-xs text-muted-foreground">Handled by</p>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  {result.route.map((step, index) => (
                    <React.Fragment key={`${step}-${index}`}>
                      {index ? (
                        <ChevronRight
                          className="size-4 text-muted-foreground"
                          aria-hidden
                        />
                      ) : null}
                      <Badge tone={step === agent.key ? "accent" : "neutral"}>
                        {FRIENDLY[step]?.name ?? step.replace(/_/g, " ")}
                      </Badge>
                    </React.Fragment>
                  ))}
                </div>
                {!result.route.includes(agent.key) ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    This message went to a different helper, not{" "}
                    {friendly(agent).name}.
                  </p>
                ) : null}
              </div>
            </div>
          )}
        </CardSection>
      </Card>
    </div>
  );
}
