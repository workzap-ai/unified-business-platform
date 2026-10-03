"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import * as React from "react";

import { SubNav } from "@/components/shell";
import {
  Badge,
  Button,
  Card,
  CardSection,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Notice,
  PageHeader,
  Select,
  Switch,
} from "@/components/ui";
import { errorText, get, patch } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

const SECTIONS = [
  { href: "/my-pi/knowledge", label: "Business knowledge" },
  { href: "/my-pi/behaviour", label: "Behaviour" },
  { href: "/my-pi/agents", label: "Agents" },
  { href: "/my-pi/tools", label: "Tools" },
  { href: "/my-pi/follow-ups", label: "Follow-ups" },
  { href: "/my-pi/advanced", label: "Advanced" },
  { href: "/my-pi/test", label: "Test Pi" },
];

interface AiConfig {
  router_alias: string;
  reply_alias: string;
  temperature: string;
  clarify_before_handoff: number;
}
interface HandoffRules {
  keywords: string[];
  low_confidence_threshold: string;
  max_failed_turns: number;
  handoff_on_complaint: boolean;
  notify_roles: string[];
}
interface KnowledgeConfig {
  top_k: number;
  min_score: string;
  semantic_enabled: boolean;
  cite_sources_to_operators: boolean;
}
interface ProviderConfig {
  order: string[];
  retry_transient: boolean;
  max_retries: number;
  timeout_seconds: number;
}
interface AdvancedSettings {
  auto_reply_enabled: boolean;
  ai_config: AiConfig;
  handoff_rules: HandoffRules;
  knowledge_config: KnowledgeConfig;
  tool_permissions: Record<string, boolean>;
  provider_config: ProviderConfig;
}
interface ToolView {
  key: string;
  name: string;
  description: string;
  requires_confirmation: boolean;
  enabled: boolean;
}

const input = "text-base sm:text-[15px]";

function useSave(section: string) {
  const client = useQueryClient();
  const key = useBusinessKey();
  return useAction(
    (value: unknown) =>
      patch<AdvancedSettings>(`/pi/settings/${section}`, { value }),
    {
      success: "Saved",
      invalidate: [["tools"]],
      onSuccess: (settings) => client.setQueryData(key(["settings"]), settings),
    },
  );
}

/** A decimal between 0 and 1 as the API stores it ("0.75"), or null when invalid. */
function decimal(value: string): string | null {
  const n = Number(value);
  if (value.trim() === "" || Number.isNaN(n) || n < 0 || n > 1) return null;
  return n.toFixed(2);
}

function whole(value: string, min: number, max: number): number | null {
  const n = Number(value);
  if (value.trim() === "" || !Number.isInteger(n) || n < min || n > max)
    return null;
  return n;
}

function SectionCard({
  title,
  description,
  children,
  onSave,
  saving,
  dirty,
  readOnly,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  onSave?: () => void;
  saving?: boolean;
  dirty?: boolean;
  readOnly?: boolean;
}) {
  return (
    <Card className="min-w-0">
      <CardSection className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold">{title}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          </div>
          {readOnly ? <Badge tone="neutral">Managed by Pi</Badge> : null}
        </div>
        {children}
        {onSave ? (
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border pt-4">
            {dirty ? (
              <span className="text-sm text-muted-foreground">
                Unsaved changes
              </span>
            ) : null}
            <Button onClick={onSave} loading={saving} disabled={!dirty}>
              Save
            </Button>
          </div>
        ) : null}
      </CardSection>
    </Card>
  );
}

function ToggleRow({
  id,
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex min-h-11 items-start justify-between gap-4">
      <label htmlFor={id} className="min-w-0 cursor-pointer">
        <span className="block text-sm font-medium text-foreground">
          {label}
        </span>
        <span className="block text-[13px] text-muted-foreground">{hint}</span>
      </label>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        label={label}
      />
    </div>
  );
}

function AutoReplyCard({ enabled }: { enabled: boolean }) {
  const save = useSave("auto_reply_enabled");
  return (
    <SectionCard
      title="Automatic replies"
      description="Turn Pi's replies to customers on or off. When off, every message waits for your team."
    >
      <ToggleRow
        id="auto-reply"
        label="Pi replies to customers"
        hint={
          enabled
            ? "Pi answers new WhatsApp messages on its own."
            : "Pi is quiet. Your team replies to every message."
        }
        checked={enabled}
        disabled={save.isPending}
        onChange={(value) => save.mutate(value)}
      />
    </SectionCard>
  );
}

function AiCard({ value }: { value: AiConfig }) {
  const [form, setForm] = React.useState({
    router_alias: value.router_alias,
    reply_alias: value.reply_alias,
    temperature: String(value.temperature),
    clarify: String(value.clarify_before_handoff),
  });
  const save = useSave("ai_config");
  const temperature = decimal(form.temperature);
  const clarify = whole(form.clarify, 0, 3);
  const dirty =
    form.router_alias !== value.router_alias ||
    form.reply_alias !== value.reply_alias ||
    temperature !== Number(value.temperature).toFixed(2) ||
    clarify !== value.clarify_before_handoff;
  return (
    <SectionCard
      title="AI configuration"
      description="How Pi thinks before it answers."
      dirty={dirty}
      saving={save.isPending}
      onSave={() => {
        if (temperature === null || clarify === null) return;
        save.mutate({
          router_alias: form.router_alias,
          reply_alias: form.reply_alias,
          temperature,
          clarify_before_handoff: clarify,
        });
      }}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Understanding speed"
          htmlFor="ai-router"
          hint="Used to work out what the customer wants."
        >
          <Select
            id="ai-router"
            className={input}
            value={form.router_alias}
            onChange={(e) => setForm({ ...form, router_alias: e.target.value })}
          >
            <option value="fast">Fast</option>
            <option value="balanced">Balanced</option>
          </Select>
        </Field>
        <Field
          label="Reply quality"
          htmlFor="ai-reply"
          hint="Used to write the answer. Deeper is slower but more careful."
        >
          <Select
            id="ai-reply"
            className={input}
            value={form.reply_alias}
            onChange={(e) => setForm({ ...form, reply_alias: e.target.value })}
          >
            <option value="fast">Fast</option>
            <option value="balanced">Balanced</option>
            <option value="reasoning">Deep thinking</option>
          </Select>
        </Field>
        <Field
          label="Creativity"
          htmlFor="ai-temperature"
          hint="0 keeps replies predictable, 1 makes them more varied."
          error={temperature === null ? "Enter a number from 0 to 1." : null}
        >
          <Input
            id="ai-temperature"
            className={input}
            type="number"
            inputMode="decimal"
            min={0}
            max={1}
            step={0.05}
            value={form.temperature}
            onChange={(e) => setForm({ ...form, temperature: e.target.value })}
          />
        </Field>
        <Field
          label="Clarifying questions before handing over"
          htmlFor="ai-clarify"
          hint="How many times Pi may ask the customer to explain (0 to 3)."
          error={clarify === null ? "Enter a whole number from 0 to 3." : null}
        >
          <Input
            id="ai-clarify"
            className={input}
            type="number"
            inputMode="numeric"
            min={0}
            max={3}
            step={1}
            value={form.clarify}
            onChange={(e) => setForm({ ...form, clarify: e.target.value })}
          />
        </Field>
      </div>
    </SectionCard>
  );
}

const PROVIDER_LABEL: Record<string, string> = {
  openai: "OpenAI",
  gemini: "Google Gemini",
  groq: "Groq",
};

function ProvidersCard({ value }: { value: ProviderConfig }) {
  return (
    <SectionCard
      title="AI providers"
      description="Pi tries these providers in order and moves to the next one if a provider is down."
      readOnly
    >
      <ol className="space-y-2">
        {value.order.map((name, i) => (
          <li
            key={name}
            className="flex min-h-11 items-center gap-3 rounded-xl border border-border bg-surface-muted px-3.5"
          >
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent-soft-foreground">
              {i + 1}
            </span>
            <span className="min-w-0 truncate text-sm font-medium">
              {PROVIDER_LABEL[name] ?? name}
            </span>
            {i === 0 ? (
              <Badge tone="accent" className="ms-auto">
                First choice
              </Badge>
            ) : null}
          </li>
        ))}
      </ol>
      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
        <div className="rounded-xl bg-surface-muted p-3">
          <dt className="text-muted-foreground">Retry brief failures</dt>
          <dd className="mt-0.5 font-medium">
            {value.retry_transient ? "Yes" : "No"}
          </dd>
        </div>
        <div className="rounded-xl bg-surface-muted p-3">
          <dt className="text-muted-foreground">Retries per provider</dt>
          <dd className="mt-0.5 font-medium">{value.max_retries}</dd>
        </div>
        <div className="rounded-xl bg-surface-muted p-3">
          <dt className="text-muted-foreground">Wait before giving up</dt>
          <dd className="mt-0.5 font-medium">{value.timeout_seconds}s</dd>
        </div>
      </dl>
      <p className="text-[13px] text-muted-foreground">
        Providers are set up for every business by the Pi team, so they
        can&apos;t be changed here.
      </p>
    </SectionCard>
  );
}

function KeywordEditor({
  id,
  values,
  onChange,
}: {
  id: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const [draft, setDraft] = React.useState("");
  const add = () => {
    const word = draft.trim().slice(0, 80);
    if (!word || values.length >= 30) return;
    if (!values.some((v) => v.toLowerCase() === word.toLowerCase()))
      onChange([...values, word]);
    setDraft("");
  };
  return (
    <div className="space-y-2">
      {values.length ? (
        <ul className="flex flex-wrap gap-2">
          {values.map((word) => (
            <li
              key={word}
              className="inline-flex max-w-full items-center gap-1 rounded-full bg-accent-soft py-1 ps-3 pe-1 text-sm text-accent-soft-foreground"
            >
              <span className="min-w-0 truncate">{word}</span>
              <button
                type="button"
                aria-label={`Remove ${word}`}
                onClick={() => onChange(values.filter((v) => v !== word))}
                className="flex size-8 shrink-0 items-center justify-center rounded-full hover:bg-surface"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">No words yet.</p>
      )}
      <div className="flex gap-2">
        <Input
          id={id}
          className={cn(input, "min-w-0 flex-1")}
          placeholder="e.g. manager"
          maxLength={80}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button
          type="button"
          variant="secondary"
          onClick={add}
          disabled={!draft.trim() || values.length >= 30}
        >
          <Plus className="size-4" aria-hidden />
          Add
        </Button>
      </div>
    </div>
  );
}

const ROLE_LABEL: Record<string, string> = {
  owner: "Business owner",
  admin: "Admin",
  manager: "Manager",
  member: "Sales/Support member",
  support: "Support",
};

function HandoffCard({ value }: { value: HandoffRules }) {
  const [keywords, setKeywords] = React.useState(value.keywords);
  const [threshold, setThreshold] = React.useState(
    String(value.low_confidence_threshold),
  );
  const [turns, setTurns] = React.useState(String(value.max_failed_turns));
  const [complaint, setComplaint] = React.useState(value.handoff_on_complaint);
  const [roles, setRoles] = React.useState(value.notify_roles);
  const save = useSave("handoff_rules");
  const thresholdValue = decimal(threshold);
  const turnsValue = whole(turns, 1, 5);
  const roleOptions = Array.from(
    new Set([...Object.keys(ROLE_LABEL), ...value.notify_roles]),
  );
  const dirty =
    JSON.stringify(keywords) !== JSON.stringify(value.keywords) ||
    thresholdValue !== Number(value.low_confidence_threshold).toFixed(2) ||
    turnsValue !== value.max_failed_turns ||
    complaint !== value.handoff_on_complaint ||
    JSON.stringify([...roles].sort()) !==
      JSON.stringify([...value.notify_roles].sort());
  return (
    <SectionCard
      title="Handing over to your team"
      description="When Pi stops and passes the conversation to a person."
      dirty={dirty}
      saving={save.isPending}
      onSave={() => {
        if (thresholdValue === null || turnsValue === null) return;
        save.mutate({
          keywords,
          low_confidence_threshold: thresholdValue,
          max_failed_turns: turnsValue,
          handoff_on_complaint: complaint,
          notify_roles: roles,
        });
      }}
    >
      <Field
        label="Words that ask for a person"
        htmlFor="handoff-keyword"
        hint="If a customer writes one of these, Pi hands over straight away (up to 30)."
      >
        <KeywordEditor
          id="handoff-keyword"
          values={keywords}
          onChange={setKeywords}
        />
      </Field>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Minimum confidence to reply"
          htmlFor="handoff-threshold"
          hint="Below this (0 to 1), Pi hands over instead of guessing."
          error={thresholdValue === null ? "Enter a number from 0 to 1." : null}
        >
          <Input
            id="handoff-threshold"
            className={input}
            type="number"
            inputMode="decimal"
            min={0}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
          />
        </Field>
        <Field
          label="Failed tries before handing over"
          htmlFor="handoff-turns"
          hint="Replies in a row Pi can't answer before it asks for help (1 to 5)."
          error={
            turnsValue === null ? "Enter a whole number from 1 to 5." : null
          }
        >
          <Input
            id="handoff-turns"
            className={input}
            type="number"
            inputMode="numeric"
            min={1}
            max={5}
            step={1}
            value={turns}
            onChange={(e) => setTurns(e.target.value)}
          />
        </Field>
      </div>
      <ToggleRow
        id="handoff-complaint"
        label="Hand over complaints"
        hint="When a customer is unhappy, a person takes over."
        checked={complaint}
        onChange={setComplaint}
      />
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Who gets notified</legend>
        <p className="text-[13px] text-muted-foreground">
          Team roles that hear about new handovers.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          {roleOptions.map((role) => {
            const on = roles.includes(role);
            return (
              <button
                key={role}
                type="button"
                aria-pressed={on}
                onClick={() =>
                  setRoles(
                    on ? roles.filter((r) => r !== role) : [...roles, role],
                  )
                }
                className={cn(
                  "min-h-11 rounded-full border px-4 text-sm font-medium transition-colors",
                  on
                    ? "border-accent bg-accent-soft text-accent-soft-foreground"
                    : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                )}
              >
                {ROLE_LABEL[role] ?? role}
              </button>
            );
          })}
        </div>
      </fieldset>
    </SectionCard>
  );
}

function KnowledgeCard({ value }: { value: KnowledgeConfig }) {
  const [topK, setTopK] = React.useState(String(value.top_k));
  const [minScore, setMinScore] = React.useState(String(value.min_score));
  const [semantic, setSemantic] = React.useState(value.semantic_enabled);
  const [cite, setCite] = React.useState(value.cite_sources_to_operators);
  const save = useSave("knowledge_config");
  const topKValue = whole(topK, 1, 10);
  const scoreValue = decimal(minScore);
  const dirty =
    topKValue !== value.top_k ||
    scoreValue !== Number(value.min_score).toFixed(2) ||
    semantic !== value.semantic_enabled ||
    cite !== value.cite_sources_to_operators;
  return (
    <SectionCard
      title="Knowledge search"
      description="How Pi looks things up in your business knowledge."
      dirty={dirty}
      saving={save.isPending}
      onSave={() => {
        if (topKValue === null || scoreValue === null) return;
        save.mutate({
          top_k: topKValue,
          min_score: scoreValue,
          semantic_enabled: semantic,
          cite_sources_to_operators: cite,
        });
      }}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          label="Pieces of knowledge to read"
          htmlFor="kn-topk"
          hint="How many matching notes Pi reads before replying (1 to 10)."
          error={
            topKValue === null ? "Enter a whole number from 1 to 10." : null
          }
        >
          <Input
            id="kn-topk"
            className={input}
            type="number"
            inputMode="numeric"
            min={1}
            max={10}
            step={1}
            value={topK}
            onChange={(e) => setTopK(e.target.value)}
          />
        </Field>
        <Field
          label="Minimum match"
          htmlFor="kn-score"
          hint="Ignore notes that match less than this (0 to 1)."
          error={scoreValue === null ? "Enter a number from 0 to 1." : null}
        >
          <Input
            id="kn-score"
            className={input}
            type="number"
            inputMode="decimal"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
          />
        </Field>
      </div>
      <ToggleRow
        id="kn-semantic"
        label="Search by meaning"
        hint="Finds answers even when the customer uses different words. Needs to be available on your plan."
        checked={semantic}
        onChange={setSemantic}
      />
      <ToggleRow
        id="kn-cite"
        label="Show sources to your team"
        hint="Your team sees which notes Pi used for each reply."
        checked={cite}
        onChange={setCite}
      />
    </SectionCard>
  );
}

function ToolsCard({ value }: { value: Record<string, boolean> }) {
  const can = useCan();
  const key = useBusinessKey();
  const canSeeTools = can("pi.agents.manage");
  const tools = useQuery({
    queryKey: key(["tools"]),
    queryFn: () => get<ToolView[]>("/pi/tools"),
    enabled: canSeeTools,
  });
  const [map, setMap] = React.useState(value);
  const save = useSave("tool_permissions");
  const known = tools.data?.map((t) => t.key) ?? Object.keys(value);
  const dirty = known.some((k) => (map[k] !== false) !== (value[k] !== false));
  return (
    <SectionCard
      title="What Pi is allowed to do"
      description="Switch off any action you don't want Pi to take on its own."
      dirty={dirty}
      saving={save.isPending}
      onSave={() =>
        save.mutate(Object.fromEntries(known.map((k) => [k, map[k] !== false])))
      }
    >
      {tools.isLoading ? (
        <LoadingBlock rows={4} label="Loading tools" />
      ) : tools.isError ? (
        <ErrorState
          message={errorText(tools.error)}
          onRetry={() => void tools.refetch()}
        />
      ) : (
        <ul className="divide-y divide-border">
          {(
            tools.data ??
            Object.keys(value).map((k) => ({
              key: k,
              name: k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()),
              description: "",
              requires_confirmation: false,
              enabled: value[k] !== false,
            }))
          ).map((tool) => (
            <li key={tool.key} className="py-3 first:pt-0 last:pb-0">
              <ToggleRow
                id={`tool-${tool.key}`}
                label={tool.name}
                hint={
                  tool.description +
                  (tool.requires_confirmation
                    ? " Asks the customer to confirm first."
                    : "")
                }
                checked={map[tool.key] !== false}
                onChange={(on) => setMap({ ...map, [tool.key]: on })}
              />
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

export function AdvancedSettingsPage() {
  const can = useCan();
  const key = useBusinessKey();
  const allowed = can("pi.settings.manage");
  const settings = useQuery({
    queryKey: key(["settings"]),
    queryFn: () => get<AdvancedSettings>("/pi/settings"),
    enabled: allowed,
  });
  const data = settings.data;
  // Remount forms when the saved values change so they never show stale drafts.
  const stamp = (section: unknown) => JSON.stringify(section);
  return (
    <div className="min-w-0">
      <PageHeader
        title="Advanced"
        description="Fine-tune how Pi thinks, when it hands over and what it may do. The defaults work well for most businesses."
      />
      <SubNav items={SECTIONS} />
      <div className="mt-6 space-y-5">
        {!allowed ? (
          <Notice tone="warning" title="Only admins can change these">
            Ask your business owner for access to Pi settings.
          </Notice>
        ) : settings.isLoading ? (
          <LoadingBlock rows={5} label="Loading settings" />
        ) : settings.isError || !data ? (
          <ErrorState
            message={errorText(settings.error)}
            onRetry={() => void settings.refetch()}
          />
        ) : (
          <>
            <AutoReplyCard enabled={data.auto_reply_enabled} />
            <AiCard key={stamp(data.ai_config)} value={data.ai_config} />
            <ProvidersCard value={data.provider_config} />
            <HandoffCard
              key={stamp(data.handoff_rules)}
              value={data.handoff_rules}
            />
            <KnowledgeCard
              key={stamp(data.knowledge_config)}
              value={data.knowledge_config}
            />
            <ToolsCard
              key={stamp(data.tool_permissions)}
              value={data.tool_permissions}
            />
          </>
        )}
      </div>
    </div>
  );
}
