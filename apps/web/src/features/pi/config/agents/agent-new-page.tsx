"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Controller, useForm, type Path, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, ArrowLeft, ArrowRight, Rocket } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import { Textarea } from "@/components/ui/input";
import { Checkbox, RadioGroup, RadioGroupItem } from "@/components/ui/controls";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  FormField,
  Stepper,
  useUnsavedChangesWarning,
} from "@/components/app/forms";
import { ErrorState, Notice } from "@/components/app/states";
import { PropertyList } from "@/components/app/record";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import type { Agent, AgentVersion, ToolDefinition } from "../../types";
import {
  AGENT_ORDER,
  CapabilityBadge,
  MODEL_ALIASES,
  MUTATION_WARNING,
  piKeys,
} from "../shared";
import { SideBySideDiff } from "./line-diff";

const schema = z.object({
  agent_id: z.string().min(1, "Choose the agent to configure"),
  instructions: z
    .string()
    .max(4000, "Keep instructions under 4,000 characters"),
  model_alias: z.enum(["fast", "balanced", "reasoning"]),
  temperature: z.number().min(0).max(1),
  tools: z.array(z.string()),
  note: z
    .string()
    .trim()
    .min(3, "Describe what changed in a few words")
    .max(200, "Keep the note under 200 characters"),
});
type Values = z.infer<typeof schema>;

const STEPS: { key: string; label: string; fields: Path<Values>[] }[] = [
  { key: "basics", label: "Basics", fields: ["agent_id"] },
  { key: "instructions", label: "Instructions", fields: ["instructions"] },
  { key: "model", label: "Model", fields: ["model_alias", "temperature"] },
  { key: "tools", label: "Tools", fields: ["tools"] },
  { key: "review", label: "Rules & review", fields: ["note"] },
  { key: "publish", label: "Publish", fields: [] },
];

export function AgentNewPage() {
  return (
    <RequirePermission permission="pi.agents.manage" area="PI agents">
      <AgentWizard />
    </RequirePermission>
  );
}

function AgentWizard() {
  const router = useRouter();
  const params = useSearchParams();
  const [step, setStep] = useState(0);
  const prefilledFor = useRef<string | null>(null);
  const [published, setPublished] = useState(false);

  const agents = useScopedQuery(piKeys.agents, () => piService.agents());
  const tools = useScopedQuery(piKeys.tools, () => piService.tools());

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      agent_id: params.get("agent") ?? "",
      instructions: "",
      model_alias: "balanced",
      temperature: 0.3,
      tools: [],
      note: "",
    },
  });
  const agentId = useWatch({ control: form.control, name: "agent_id" });
  const agent = agents.data?.find((a) => a.id === agentId || a.key === agentId);
  const versions = useScopedQuery(
    piKeys.versions(agent?.id ?? "none"),
    () => piService.versions(agent!.id),
    { enabled: Boolean(agent) },
  );
  const active = versions.data?.find((v) => v.status === "active");
  const draft = versions.data?.find((v) => v.status === "draft");

  // Start from the agent's current configuration whenever a different agent is chosen.
  useEffect(() => {
    if (!agent || !versions.data || prefilledFor.current === agent.id) return;
    form.reset({
      agent_id: agent.id,
      instructions: active?.instructions ?? "",
      model_alias: agent.model_alias,
      temperature: Number(agent.temperature) || 0,
      tools: agent.tools,
      note: "",
    });
    prefilledFor.current = agent.id;
  }, [agent, versions.data, active, form]);

  const values = useWatch({ control: form.control }) as Values;
  useUnsavedChangesWarning(form.formState.isDirty && !published);

  const publish = useScopedMutation(
    async (values: Values) => {
      if (!agent) throw new Error("No agent selected");
      const version = await piService.publishVersion(agent.id, {
        instructions: values.instructions,
        model_alias: values.model_alias,
        temperature: values.temperature.toFixed(2),
        note: values.note,
      });
      const before = new Set(agent.tools);
      const after = new Set(values.tools);
      for (const key of values.tools)
        if (!before.has(key)) await piService.setAgentTool(agent.id, key, true);
      for (const key of agent.tools)
        if (!after.has(key)) await piService.setAgentTool(agent.id, key, false);
      return version;
    },
    {
      invalidate: [[...piKeys.agents], [...piKeys.tools]],
      success: (v) => `Version ${v.version} published and active`,
      error: "The configuration couldn't be published. Nothing was changed.",
    },
  );

  async function next() {
    const ok = await form.trigger(STEPS[step]!.fields);
    if (ok) setStep((s) => Math.min(STEPS.length - 1, s + 1));
  }

  const onSubmit = form.handleSubmit(async (values) => {
    if (step !== STEPS.length - 1) return;
    const version = await publish.mutateAsync(values).catch(() => null);
    if (!version || !agent) return;
    setPublished(true);
    router.push(`/pi/agents/${agent.id}`);
  });

  if (agents.isError || tools.isError) {
    return (
      <PageShell width="default">
        <Card>
          <ErrorState
            error={agents.error ?? tools.error}
            onRetry={() => {
              void agents.refetch();
              void tools.refetch();
            }}
          />
        </Card>
      </PageShell>
    );
  }

  const loadingAgent = Boolean(agent) && versions.isPending;

  return (
    <PageShell width="default">
      <Link
        href="/pi/agents"
        className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" /> Agents
      </Link>
      <PageHeader
        title="New configuration"
        description="Prepare a new version of an agent. Nothing changes for customers until you publish."
        actions={<Badge tone="neutral">Draft · not published</Badge>}
      />
      <Stepper
        steps={STEPS}
        current={step}
        onStep={(index) => setStep(index)}
      />

      <form onSubmit={onSubmit} noValidate>
        <Card className="p-5 sm:p-6">
          {step === 0 && (
            <BasicsStep
              agents={agents.data}
              value={agentId}
              error={form.formState.errors.agent_id?.message}
              onChange={(id) =>
                form.setValue("agent_id", id, { shouldValidate: true })
              }
              draft={draft}
              onLoadDraft={() => {
                if (!draft) return;
                form.setValue("instructions", draft.instructions, {
                  shouldDirty: true,
                });
                form.setValue("model_alias", draft.model_alias, {
                  shouldDirty: true,
                });
                form.setValue("temperature", Number(draft.temperature), {
                  shouldDirty: true,
                });
              }}
            />
          )}

          {step > 0 && loadingAgent && <Skeleton className="h-64" />}

          {step === 1 && !loadingAgent && (
            <div className="space-y-4">
              <StepTitle
                title="Instructions"
                description="Business guidance for this agent: products to emphasise, how to phrase things, what to avoid."
              />
              <Notice tone="pi" title="Built-in safety rules always apply">
                These instructions add guidance on top of PI&apos;s built-in
                safety rules, which can&apos;t be overridden: PI only uses
                verified prices and stock, confirms before changing business
                data and hands off when a person should decide.
              </Notice>
              <FormField
                label="Tenant instructions"
                htmlFor="instructions"
                error={form.formState.errors.instructions}
                help={`${formatNumber(values.instructions.length)} / 4,000 characters`}
              >
                <Textarea
                  id="instructions"
                  rows={12}
                  maxLength={4000}
                  className="font-mono text-[13px]"
                  aria-invalid={Boolean(form.formState.errors.instructions)}
                  {...form.register("instructions")}
                />
              </FormField>
            </div>
          )}

          {step === 2 && !loadingAgent && (
            <div className="space-y-5">
              <StepTitle
                title="Model"
                description="Choose a model tier. The platform operator maps tiers to concrete providers and models."
              />
              <Controller
                control={form.control}
                name="model_alias"
                render={({ field }) => (
                  <RadioGroup
                    value={field.value}
                    onValueChange={field.onChange}
                    aria-label="Model tier"
                    className="gap-2"
                  >
                    {MODEL_ALIASES.map((m) => (
                      <label
                        key={m.value}
                        htmlFor={`alias-${m.value}`}
                        className={cn(
                          "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                          field.value === m.value
                            ? "border-primary/50 bg-primary-soft/40"
                            : "border-border hover:bg-surface-muted",
                        )}
                      >
                        <RadioGroupItem
                          id={`alias-${m.value}`}
                          value={m.value}
                          className="mt-0.5"
                        />
                        <span>
                          <span className="block text-[13px] font-medium">
                            {m.label}
                          </span>
                          <span className="block text-xs text-muted-foreground">
                            {m.description}
                          </span>
                        </span>
                      </label>
                    ))}
                  </RadioGroup>
                )}
              />
              <Controller
                control={form.control}
                name="temperature"
                render={({ field }) => (
                  <FormField
                    label="Temperature"
                    htmlFor="temperature"
                    help="Lower is more consistent and literal; higher is more varied. 0.2–0.4 suits customer service."
                  >
                    <div className="flex items-center gap-3">
                      <input
                        id="temperature"
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={field.value}
                        onChange={(e) => field.onChange(Number(e.target.value))}
                        className="w-full accent-primary"
                      />
                      <span className="tabular w-10 text-right text-[13px] font-semibold">
                        {field.value.toFixed(2)}
                      </span>
                    </div>
                  </FormField>
                )}
              />
            </div>
          )}

          {step === 3 && !loadingAgent && (
            <Controller
              control={form.control}
              name="tools"
              render={({ field }) => (
                <ToolsStep
                  tools={tools.data}
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />
          )}

          {step === 4 && !loadingAgent && agent && (
            <div className="space-y-5">
              <StepTitle
                title="Rules & review"
                description="Check what changes compared with the active version, then add a short note for the history."
              />
              <FormField
                label="Change note"
                htmlFor="note"
                required
                error={form.formState.errors.note}
                help="Shown in the version history, e.g. “Emphasise same-day delivery in Lahore”."
              >
                <Textarea
                  id="note"
                  rows={2}
                  maxLength={200}
                  aria-invalid={Boolean(form.formState.errors.note)}
                  {...form.register("note")}
                />
              </FormField>
              <ReviewSummary
                agent={agent}
                active={active}
                values={values}
                tools={tools.data ?? []}
              />
            </div>
          )}

          {step === 5 && agent && (
            <div className="space-y-4">
              <StepTitle
                title="Publish"
                description="Publishing makes this configuration active immediately for new messages."
              />
              <PropertyList
                items={[
                  { label: "Agent", value: agent.name },
                  {
                    label: "Currently active",
                    value: active ? `v${active.version}` : "None",
                  },
                  {
                    label: "Will publish as",
                    value: (
                      <Badge tone="success" dot>
                        v
                        {(versions.data?.[0]?.version ??
                          agent.current_version) + 1}{" "}
                        · active
                      </Badge>
                    ),
                  },
                  {
                    label: "Model",
                    value: `${values.model_alias} · ${values.temperature.toFixed(2)}`,
                  },
                  {
                    label: "Tools",
                    value: formatNumber(values.tools.length),
                  },
                  { label: "Note", value: values.note || "—" },
                ]}
              />
              <Notice tone="neutral">
                The previous version is archived and stays available for
                rollback from the agent&apos;s version history.
              </Notice>
            </div>
          )}
        </Card>

        <div className="mt-4 flex items-center justify-between gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              step === 0
                ? router.push("/pi/agents")
                : setStep((s) => Math.max(0, s - 1))
            }
            disabled={publish.isPending}
          >
            {step === 0 ? "Cancel" : "Back"}
          </Button>
          {step < STEPS.length - 1 ? (
            <Button
              type="button"
              onClick={() => void next()}
              disabled={loadingAgent}
            >
              Continue <ArrowRight />
            </Button>
          ) : (
            <Button type="submit" loading={publish.isPending}>
              <Rocket /> Publish version
            </Button>
          )}
        </div>
      </form>
    </PageShell>
  );
}

function StepTitle({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div>
      <h2 className="text-[15px] font-semibold">{title}</h2>
      <p className="mt-0.5 text-[13px] text-muted-foreground">{description}</p>
    </div>
  );
}

function BasicsStep({
  agents,
  value,
  error,
  onChange,
  draft,
  onLoadDraft,
}: {
  agents: Agent[] | undefined;
  value: string;
  error?: string;
  onChange: (id: string) => void;
  draft?: AgentVersion;
  onLoadDraft: () => void;
}) {
  const sorted = agents
    ? [...agents].sort(
        (a, b) => AGENT_ORDER.indexOf(a.key) - AGENT_ORDER.indexOf(b.key),
      )
    : undefined;
  return (
    <div className="space-y-4">
      <StepTitle
        title="Which agent are you configuring?"
        description="Agents are fixed roles inside PI. You can't add or remove roles — you tune how each one behaves."
      />
      {!sorted ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : (
        <RadioGroup
          value={value}
          onValueChange={onChange}
          aria-label="Agent"
          className="gap-2 sm:grid-cols-2"
        >
          {sorted.map((a) => (
            <label
              key={a.id}
              htmlFor={`agent-${a.id}`}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                value === a.id
                  ? "border-primary/50 bg-primary-soft/40"
                  : "border-border hover:bg-surface-muted",
              )}
            >
              <RadioGroupItem
                id={`agent-${a.id}`}
                value={a.id}
                className="mt-0.5"
              />
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-[13px] font-medium">
                  {a.name}
                  <span className="font-mono text-2xs text-muted-foreground">
                    v{a.current_version}
                  </span>
                </span>
                <span className="block text-xs text-muted-foreground">
                  {a.role}
                </span>
              </span>
            </label>
          ))}
        </RadioGroup>
      )}
      {error && (
        <p role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      )}
      {draft && (
        <Notice
          tone="info"
          title={`An unpublished draft exists (v${draft.version})`}
          action={
            <Button
              type="button"
              size="xs"
              variant="secondary"
              onClick={onLoadDraft}
            >
              Start from draft
            </Button>
          }
        >
          {draft.note || "No note"} — by {draft.created_by_label}
        </Notice>
      )}
    </div>
  );
}

function ToolsStep({
  tools,
  value,
  onChange,
}: {
  tools: ToolDefinition[] | undefined;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const selected = new Set(value);
  return (
    <div className="space-y-4">
      <StepTitle
        title="Tools"
        description="What this agent may use. PI still checks permissions and business rules on every call."
      />
      {!tools ? (
        <Skeleton className="h-64" />
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {tools.map((tool) => {
            const id = `tool-${tool.key}`;
            const mutation = tool.capability === "mutation";
            return (
              <li
                key={tool.key}
                className={cn(
                  "flex items-start gap-3 px-3 py-3",
                  mutation && "bg-warning-soft/40",
                )}
              >
                <Checkbox
                  id={id}
                  checked={selected.has(tool.key)}
                  onCheckedChange={(checked) =>
                    onChange(
                      checked
                        ? [...value, tool.key]
                        : value.filter((k) => k !== tool.key),
                    )
                  }
                  className="mt-0.5"
                  aria-describedby={`${id}-description`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <label htmlFor={id} className="text-[13px] font-medium">
                      {tool.name}
                    </label>
                    <CapabilityBadge capability={tool.capability} />
                    {tool.requires_confirmation && (
                      <Badge tone="warning">Customer confirms</Badge>
                    )}
                    {!tool.enabled && (
                      <Badge tone="neutral">Off workspace-wide</Badge>
                    )}
                  </div>
                  <p
                    id={`${id}-description`}
                    className="mt-0.5 text-xs text-muted-foreground"
                  >
                    {tool.description}{" "}
                    <span className="font-mono">({tool.permission})</span>
                  </p>
                  {mutation && (
                    <p className="mt-1 flex items-center gap-1 text-xs font-medium text-warning">
                      <AlertTriangle className="size-3.5" aria-hidden="true" />
                      {MUTATION_WARNING}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ReviewSummary({
  agent,
  active,
  values,
  tools,
}: {
  agent: Agent;
  active?: AgentVersion;
  values: Values;
  tools: ToolDefinition[];
}) {
  const name = useMemo(
    () => new Map(tools.map((t) => [t.key, t.name])),
    [tools],
  );
  const added = values.tools.filter((t) => !agent.tools.includes(t));
  const removed = agent.tools.filter((t) => !values.tools.includes(t));
  const temperatureBefore = Number(agent.temperature).toFixed(2);
  const temperatureAfter = values.temperature.toFixed(2);
  const change = (before: string, after: string) =>
    before === after ? (
      <span className="text-muted-foreground">{after} (unchanged)</span>
    ) : (
      <span>
        <span className="text-muted-foreground line-through">{before}</span> →{" "}
        {after}
      </span>
    );
  return (
    <div className="space-y-4">
      <PropertyList
        items={[
          {
            label: "Model",
            value: change(agent.model_alias, values.model_alias),
          },
          {
            label: "Temperature",
            value: change(temperatureBefore, temperatureAfter),
          },
          {
            label: "Tools added",
            value: added.length
              ? added.map((k) => name.get(k) ?? k).join(", ")
              : "None",
          },
          {
            label: "Tools removed",
            value: removed.length
              ? removed.map((k) => name.get(k) ?? k).join(", ")
              : "None",
          },
        ]}
      />
      <SideBySideDiff
        before={active?.instructions ?? ""}
        after={values.instructions}
        beforeLabel={
          active ? `Active · v${active.version}` : "No active version"
        }
        afterLabel="Draft (this configuration)"
      />
    </div>
  );
}
