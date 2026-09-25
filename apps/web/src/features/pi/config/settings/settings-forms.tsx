"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Controller,
  useForm,
  type FieldValues,
  type UseFormReturn,
  useWatch,
} from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  KeyRound,
  UserCheck,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber, humanize, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import {
  Checkbox,
  RadioGroup,
  RadioGroupItem,
  Switch,
} from "@/components/ui/controls";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  FormActions,
  FormField,
  FormSection,
  useUnsavedChangesWarning,
} from "@/components/app/forms";
import { ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import { piService } from "../../service";
import type { PiSettings, ProviderName } from "../../types";
import {
  CapabilityBadge,
  MODEL_ALIASES,
  MUTATION_WARNING,
  PROVIDER_LABELS,
  ToggleRow,
  piKeys,
} from "../shared";

/* Shared plumbing ------------------------------------------------------------------- */

function useSaveSection<K extends keyof PiSettings>(key: K) {
  return useScopedMutation(
    (value: PiSettings[K]) => piService.updateSettings(key, value),
    {
      invalidate: [[...piKeys.settings], [...piKeys.overview]],
      success: "Settings saved",
      error: "Settings couldn't be saved. Nothing was changed.",
    },
  );
}

function SettingsForm<T extends FieldValues>({
  form,
  onSubmit,
  saving,
  savedAt,
  children,
}: {
  form: UseFormReturn<T>;
  onSubmit: (values: T) => Promise<void>;
  saving: boolean;
  savedAt: number | null;
  children: React.ReactNode;
}) {
  const dirty = form.formState.isDirty;
  useUnsavedChangesWarning(dirty);
  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
      <Card className="p-5 sm:p-6">{children}</Card>
      <FormActions
        dirty={dirty}
        saving={saving}
        savedAt={savedAt}
        onCancel={dirty ? () => form.reset() : undefined}
        submitLabel="Save changes"
      />
    </form>
  );
}

/** Save a section and treat the saved values as the new clean state. */
function useSubmit<T extends FieldValues, V>(
  form: UseFormReturn<T>,
  save: (value: V) => Promise<unknown>,
  toValue: (values: T) => V,
) {
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const onSubmit = async (values: T) => {
    try {
      await save(toValue(values));
      form.reset(values);
      setSavedAt((n) => (n ?? 0) + 1);
    } catch {
      /* toast already shown */
    }
  };
  return { onSubmit, savedAt };
}

const num = (message = "Enter a number") => z.number({ error: message });

function SwitchField<T extends FieldValues>({
  form,
  name,
  label,
  description,
}: {
  form: UseFormReturn<T>;
  name: Parameters<UseFormReturn<T>["register"]>[0];
  label: string;
  description?: string;
}) {
  return (
    <Controller
      control={form.control}
      name={name}
      render={({ field }) => (
        <ToggleRow
          id={`setting-${String(name).replace(/\./g, "-")}`}
          label={label}
          description={description}
          checked={Boolean(field.value)}
          onCheckedChange={field.onChange}
        />
      )}
    />
  );
}

/* Business hours ------------------------------------------------------------------- */

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const DAY_LABELS: Record<(typeof DAYS)[number], string> = {
  mon: "Monday",
  tue: "Tuesday",
  wed: "Wednesday",
  thu: "Thursday",
  fri: "Friday",
  sat: "Saturday",
  sun: "Sunday",
};
const time = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Use HH:MM");
const day = z
  .object({ open: z.boolean(), start: time, end: time })
  .refine((d) => !d.open || d.end > d.start, {
    message: "Closing time must be after opening time",
    path: ["end"],
  });
const hoursSchema = z.object({
  timezone: z.string().min(1, "Choose a time zone"),
  enabled: z.boolean(),
  days: z.object({
    mon: day,
    tue: day,
    wed: day,
    thu: day,
    fri: day,
    sat: day,
    sun: day,
  }),
  outside_hours: z.enum(["reply", "reply_with_notice", "handoff_only"]),
  notice: z.string().max(300, "Keep the notice under 300 characters"),
});
type HoursValues = z.infer<typeof hoursSchema>;

function timeZones(current: string) {
  try {
    const all = Intl.supportedValuesOf("timeZone");
    return all.includes(current) ? all : [current, ...all];
  } catch {
    return [current, "UTC"];
  }
}

export function BusinessHoursForm({ settings }: { settings: PiSettings }) {
  const form = useForm<HoursValues>({
    resolver: zodResolver(hoursSchema),
    defaultValues: { timezone: settings.timezone, ...settings.business_hours },
  });
  const saveHours = useSaveSection("business_hours");
  const saveZone = useSaveSection("timezone");
  const zones = useMemo(
    () => timeZones(settings.timezone),
    [settings.timezone],
  );
  const { onSubmit, savedAt } = useSubmit(
    form,
    async (v: HoursValues) => {
      const { timezone, ...hours } = v;
      if (timezone !== form.formState.defaultValues?.timezone)
        await saveZone.mutateAsync(timezone);
      await saveHours.mutateAsync(hours);
    },
    (v) => v,
  );
  const enabled = useWatch({ control: form.control, name: "enabled" });
  const outside = useWatch({ control: form.control, name: "outside_hours" });
  const days = useWatch({ control: form.control, name: "days" });
  const err = form.formState.errors;
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={saveHours.isPending || saveZone.isPending}
      savedAt={savedAt}
    >
      <FormSection
        title="Schedule"
        description="PI can answer around the clock; business hours change what it does outside them."
      >
        <SwitchField
          form={form}
          name="enabled"
          label="Use business hours"
          description="When off, PI replies the same way at any time."
        />
        <FormField label="Time zone" htmlFor="bh-tz" error={err.timezone}>
          <NativeSelect id="bh-tz" {...form.register("timezone")}>
            {zones.map((z) => (
              <option key={z} value={z}>
                {z.replace(/_/g, " ")}
              </option>
            ))}
          </NativeSelect>
        </FormField>
        <fieldset
          disabled={!enabled}
          className={cn("space-y-1", !enabled && "opacity-60")}
        >
          <legend className="mb-1.5 text-[13px] font-medium">
            Opening hours
          </legend>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {DAYS.map((d) => {
              const open = days[d].open;
              const dayErr = err.days?.[d];
              return (
                <li
                  key={d}
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2"
                >
                  <Controller
                    control={form.control}
                    name={`days.${d}.open`}
                    render={({ field }) => (
                      <label className="flex w-32 items-center gap-2 text-[13px] font-medium">
                        <Switch
                          checked={field.value}
                          onCheckedChange={field.onChange}
                          aria-label={`Open on ${DAY_LABELS[d]}`}
                        />
                        {DAY_LABELS[d]}
                      </label>
                    )}
                  />
                  {open ? (
                    <div className="flex items-center gap-2">
                      <Input
                        type="time"
                        className="h-8 w-28"
                        aria-label={`${DAY_LABELS[d]} opening time`}
                        aria-invalid={Boolean(dayErr?.start)}
                        {...form.register(`days.${d}.start`)}
                      />
                      <span className="text-xs text-muted-foreground">to</span>
                      <Input
                        type="time"
                        className="h-8 w-28"
                        aria-label={`${DAY_LABELS[d]} closing time`}
                        aria-invalid={Boolean(dayErr?.end)}
                        {...form.register(`days.${d}.end`)}
                      />
                    </div>
                  ) : (
                    <span className="text-[13px] text-muted-foreground">
                      Closed
                    </span>
                  )}
                  {(dayErr?.start || dayErr?.end) && (
                    <p
                      role="alert"
                      className="w-full text-xs font-medium text-danger"
                    >
                      {dayErr.start?.message ?? dayErr.end?.message}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </fieldset>
      </FormSection>
      <FormSection
        title="Outside hours"
        description="What PI does when a message arrives while you're closed."
      >
        <Controller
          control={form.control}
          name="outside_hours"
          render={({ field }) => (
            <RadioGroup
              value={field.value}
              onValueChange={field.onChange}
              aria-label="Outside-hours behaviour"
              disabled={!enabled}
            >
              {[
                [
                  "reply",
                  "Reply as usual",
                  "PI answers normally; handoffs wait for your team.",
                ],
                [
                  "reply_with_notice",
                  "Reply with a notice",
                  "PI answers and mentions when your team is back.",
                ],
                [
                  "handoff_only",
                  "Hand off only",
                  "PI acknowledges the message and queues it for your team.",
                ],
              ].map(([value, label, help]) => (
                <label
                  key={value}
                  htmlFor={`oh-${value}`}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 hover:bg-surface-muted"
                >
                  <RadioGroupItem
                    id={`oh-${value}`}
                    value={value!}
                    className="mt-0.5"
                  />
                  <span>
                    <span className="block text-[13px] font-medium">
                      {label}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {help}
                    </span>
                  </span>
                </label>
              ))}
            </RadioGroup>
          )}
        />
        {outside !== "reply" && (
          <FormField
            label="Notice text"
            htmlFor="bh-notice"
            error={err.notice}
            help="Sent to customers outside business hours."
          >
            <Textarea
              id="bh-notice"
              rows={3}
              maxLength={300}
              disabled={!enabled}
              {...form.register("notice")}
            />
          </FormField>
        )}
      </FormSection>
    </SettingsForm>
  );
}

/* Response rules -------------------------------------------------------------------- */

const responseSchema = z.object({
  language: z
    .string()
    .regex(/^(auto|roman_ur|[a-z]{2,3}([-_][A-Za-z0-9]{2,8})?)$/),
  service_mode: z.enum(["auto", "service"]),
  max_reply_chars: num()
    .int()
    .min(100, "At least 100")
    .max(4096, "WhatsApp allows up to 4,096"),
  tone: z.enum(["friendly", "formal", "concise"]),
  greeting: z.string().max(300, "Keep it under 300 characters"),
  sign_off: z.string().max(120, "Keep it under 120 characters"),
});
type ResponseValues = z.infer<typeof responseSchema>;

export function ResponseRulesForm({ settings }: { settings: PiSettings }) {
  const form = useForm<ResponseValues>({
    resolver: zodResolver(responseSchema),
    defaultValues: {
      ...settings.response_rules,
      service_mode: settings.response_rules.service_mode ?? "auto",
    },
  });
  const save = useSaveSection("response_rules");
  const { onSubmit, savedAt } = useSubmit(form, save.mutateAsync, (v) => v);
  const err = form.formState.errors;
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={save.isPending}
      savedAt={savedAt}
    >
      <FormSection
        title="Language & tone"
        description="How PI writes to customers."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Service enquiries"
            htmlFor="rr-services"
            help="Service conversations collect requirements and send your team a brief. PI never quotes a service price."
          >
            <NativeSelect id="rr-services" {...form.register("service_mode")}>
              <option value="auto">Use business type</option>
              <option value="service">Treat all enquiries as services</option>
            </NativeSelect>
          </FormField>
          <FormField
            label="Reply language"
            htmlFor="rr-lang"
            help="Auto matches the customer's language."
          >
            <NativeSelect id="rr-lang" {...form.register("language")}>
              <option value="auto">Match customer — any language</option>
              <option value="en">English</option>
              <option value="ur">Urdu</option>
              <option value="roman_ur">Roman Urdu</option>
            </NativeSelect>
          </FormField>
          <FormField label="Tone" htmlFor="rr-tone">
            <NativeSelect id="rr-tone" {...form.register("tone")}>
              <option value="friendly">Friendly</option>
              <option value="formal">Formal</option>
              <option value="concise">Concise</option>
            </NativeSelect>
          </FormField>
          <FormField
            label="Maximum reply length"
            htmlFor="rr-max"
            error={err.max_reply_chars}
            help="Characters per message (100–4,096)."
          >
            <Input
              id="rr-max"
              type="number"
              inputMode="numeric"
              min={100}
              max={4096}
              aria-invalid={Boolean(err.max_reply_chars)}
              {...form.register("max_reply_chars", { valueAsNumber: true })}
            />
          </FormField>
        </div>
      </FormSection>
      <FormSection
        title="Greeting & sign-off"
        description="Optional text added to the first reply and to closing messages."
      >
        <FormField
          label="Greeting"
          htmlFor="rr-greet"
          optional
          error={err.greeting}
        >
          <Textarea
            id="rr-greet"
            rows={2}
            maxLength={300}
            {...form.register("greeting")}
          />
        </FormField>
        <FormField
          label="Sign-off"
          htmlFor="rr-sign"
          optional
          error={err.sign_off}
        >
          <Input id="rr-sign" maxLength={120} {...form.register("sign_off")} />
        </FormField>
      </FormSection>
    </SettingsForm>
  );
}

/* AI configuration ------------------------------------------------------------------ */

const aiSchema = z.object({
  router_alias: z.enum(["fast", "balanced"]),
  reply_alias: z.enum(["fast", "balanced", "reasoning"]),
  temperature: num().min(0).max(1),
  clarify_before_handoff: num().int().min(0, "0 or more").max(5, "At most 5"),
});
type AiValues = z.infer<typeof aiSchema>;

export function AiConfigForm({ settings }: { settings: PiSettings }) {
  const form = useForm<AiValues>({
    resolver: zodResolver(aiSchema),
    defaultValues: {
      ...settings.ai_config,
      temperature: Number(settings.ai_config.temperature) || 0,
    },
  });
  const save = useSaveSection("ai_config");
  const { onSubmit, savedAt } = useSubmit(form, save.mutateAsync, (v) => ({
    ...v,
    temperature: v.temperature.toFixed(2),
  }));
  const err = form.formState.errors;
  const aliasOptions = (allowed: string[]) =>
    MODEL_ALIASES.filter((m) => allowed.includes(m.value)).map((m) => (
      <option key={m.value} value={m.value}>
        {m.label}
      </option>
    ));
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={save.isPending}
      savedAt={savedAt}
    >
      <FormSection
        title="Model tiers"
        description="Tiers map to concrete models chosen by the platform operator. Agents can override the reply tier."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Routing tier"
            htmlFor="ai-router"
            help="Used to classify each message. Fast is recommended."
          >
            <NativeSelect id="ai-router" {...form.register("router_alias")}>
              {aliasOptions(["fast", "balanced"])}
            </NativeSelect>
          </FormField>
          <FormField label="Default reply tier" htmlFor="ai-reply">
            <NativeSelect id="ai-reply" {...form.register("reply_alias")}>
              {aliasOptions(["fast", "balanced", "reasoning"])}
            </NativeSelect>
          </FormField>
        </div>
        <Controller
          control={form.control}
          name="temperature"
          render={({ field }) => (
            <FormField
              label="Default temperature"
              htmlFor="ai-temp"
              help="Lower is more consistent. 0.2–0.4 suits customer service."
            >
              <div className="flex items-center gap-3">
                <input
                  id="ai-temp"
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
      </FormSection>
      <FormSection
        title="Clarifications"
        description="When PI isn't sure what the customer means."
      >
        <FormField
          label="Clarifying questions before handoff"
          htmlFor="ai-clarify"
          error={err.clarify_before_handoff}
          help="0 hands off immediately when unsure (0–5)."
        >
          <Input
            id="ai-clarify"
            type="number"
            min={0}
            max={5}
            className="w-28"
            {...form.register("clarify_before_handoff", {
              valueAsNumber: true,
            })}
          />
        </FormField>
      </FormSection>
    </SettingsForm>
  );
}

/* Provider configuration ------------------------------------------------------------ */

const providerSchema = z.object({
  order: z
    .array(z.enum(["openai", "gemini", "groq"]))
    .min(1, "Keep at least one provider")
    .refine(
      (o) => new Set(o).size === o.length,
      "Each provider can appear once",
    ),
  retry_transient: z.boolean(),
  max_retries: num().int().min(0).max(3, "At most 3"),
  timeout_seconds: num()
    .int()
    .min(5, "At least 5 seconds")
    .max(60, "At most 60 seconds"),
});
type ProviderValues = z.infer<typeof providerSchema>;
const ROLE_LABELS = ["Primary", "Fallback", "Secondary fallback"];

export function ProviderConfigForm({ settings }: { settings: PiSettings }) {
  const form = useForm<ProviderValues>({
    resolver: zodResolver(providerSchema),
    defaultValues: settings.provider_config,
  });
  const save = useSaveSection("provider_config");
  const { onSubmit, savedAt } = useSubmit(form, save.mutateAsync, (v) => v);
  const err = form.formState.errors;
  const retry = useWatch({ control: form.control, name: "retry_transient" });
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={save.isPending}
      savedAt={savedAt}
    >
      <Notice tone="neutral" icon={KeyRound} className="mb-6">
        API keys and model IDs are configured by the platform operator in server
        environment settings and are never shown here.
      </Notice>
      <FormSection
        title="Fallback order"
        description="If a provider fails with a transient error, PI moves to the next one. The chain always ends with a human handoff."
      >
        <Controller
          control={form.control}
          name="order"
          render={({ field }) => {
            const move = (index: number, delta: number) => {
              const next = [...field.value];
              const target = index + delta;
              if (target < 0 || target >= next.length) return;
              [next[index], next[target]] = [next[target]!, next[index]!];
              field.onChange(next);
            };
            return (
              <ol className="space-y-2" aria-label="Provider fallback order">
                {field.value.map((p: ProviderName, i: number) => (
                  <li
                    key={p}
                    className="flex items-center gap-3 rounded-lg border border-border px-3 py-2"
                  >
                    <span className="tabular flex size-6 items-center justify-center rounded-full bg-surface-muted text-xs font-semibold">
                      {i + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium">
                        {PROVIDER_LABELS[p]}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {ROLE_LABELS[i] ?? "Fallback"}
                      </span>
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => move(i, -1)}
                      disabled={i === 0}
                      aria-label={`Move ${PROVIDER_LABELS[p]} up`}
                    >
                      <ArrowUp />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => move(i, 1)}
                      disabled={i === field.value.length - 1}
                      aria-label={`Move ${PROVIDER_LABELS[p]} down`}
                    >
                      <ArrowDown />
                    </Button>
                  </li>
                ))}
                <li
                  className="flex items-center gap-3 rounded-lg border border-dashed border-border px-3 py-2"
                  aria-label="Human handoff, always last"
                >
                  <UserCheck
                    className="size-4 text-warning"
                    aria-hidden="true"
                  />
                  <span className="flex-1 text-[13px] font-medium">
                    Human handoff
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Always last
                  </span>
                </li>
              </ol>
            );
          }}
        />
        {err.order && (
          <p role="alert" className="text-xs font-medium text-danger">
            {err.order.message ?? err.order.root?.message}
          </p>
        )}
      </FormSection>
      <FormSection
        title="Retries & timeouts"
        description="Applied to every provider call."
      >
        <SwitchField
          form={form}
          name="retry_transient"
          label="Retry transient errors"
          description="Retry the same provider on rate limits and timeouts before falling back."
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Max retries"
            htmlFor="pc-retries"
            error={err.max_retries}
            help="0–3 per provider."
          >
            <Input
              id="pc-retries"
              type="number"
              min={0}
              max={3}
              disabled={!retry}
              {...form.register("max_retries", { valueAsNumber: true })}
            />
          </FormField>
          <FormField
            label="Timeout (seconds)"
            htmlFor="pc-timeout"
            error={err.timeout_seconds}
            help="5–60 seconds per call."
          >
            <Input
              id="pc-timeout"
              type="number"
              min={5}
              max={60}
              {...form.register("timeout_seconds", { valueAsNumber: true })}
            />
          </FormField>
        </div>
      </FormSection>
    </SettingsForm>
  );
}

/* Tool permissions ------------------------------------------------------------------ */

const toolSchema = z.object({
  tool_permissions: z.record(z.string(), z.boolean()),
});
type ToolValues = z.infer<typeof toolSchema>;

export function ToolPermissionsForm({ settings }: { settings: PiSettings }) {
  const tools = useScopedQuery(piKeys.tools, () => piService.tools());
  const form = useForm<ToolValues>({
    resolver: zodResolver(toolSchema),
    defaultValues: { tool_permissions: settings.tool_permissions },
  });
  const save = useSaveSection("tool_permissions");
  const { onSubmit, savedAt } = useSubmit(
    form,
    save.mutateAsync,
    (v) => v.tool_permissions,
  );
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={save.isPending}
      savedAt={savedAt}
    >
      <FormSection
        title="Tools PI may use"
        description="Turning a tool off here blocks it for every agent. PI still checks the member permission shown on each call."
      >
        {tools.isError ? (
          <ErrorState
            compact
            error={tools.error}
            onRetry={() => void tools.refetch()}
          />
        ) : !tools.data ? (
          <Skeleton className="h-72" />
        ) : (
          <Controller
            control={form.control}
            name="tool_permissions"
            render={({ field }) => (
              <ul className="divide-y divide-border rounded-lg border border-border">
                {tools.data.map((tool) => {
                  const id = `tp-${tool.key}`;
                  const checked = field.value[tool.key] ?? tool.enabled;
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
                          <label
                            htmlFor={id}
                            className="text-[13px] font-medium"
                          >
                            {tool.name}
                          </label>
                          <CapabilityBadge capability={tool.capability} />
                          <span className="font-mono text-2xs text-muted-foreground">
                            {tool.permission}
                          </span>
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {tool.description}
                        </p>
                        {mutation && (
                          <p className="mt-1 flex items-center gap-1 text-xs font-medium text-warning">
                            <AlertTriangle
                              className="size-3.5"
                              aria-hidden="true"
                            />{" "}
                            {MUTATION_WARNING}
                          </p>
                        )}
                      </div>
                      <Switch
                        id={id}
                        checked={checked}
                        onCheckedChange={(on) =>
                          field.onChange({ ...field.value, [tool.key]: on })
                        }
                      />
                    </li>
                  );
                })}
              </ul>
            )}
          />
        )}
      </FormSection>
    </SettingsForm>
  );
}

/* Agent configuration (not a settings key) ------------------------------------------ */

export function AgentConfigurationPanel() {
  const agents = useScopedQuery(piKeys.agents, () => piService.agents());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toggle = useScopedMutation(
    (input: { id: string; enabled: boolean }) =>
      piService.setAgentEnabled(input.id, input.enabled),
    {
      invalidate: [[...piKeys.agents]],
      success: (a) => `${a.name} ${a.enabled ? "enabled" : "disabled"}`,
    },
  );
  return (
    <Card className="p-5 sm:p-6">
      <FormSection
        title="Agents"
        description={
          <>
            Turn PI&apos;s roles on or off. Instructions, models and tools are
            configured per agent in{" "}
            <Link
              href="/pi/agents"
              className="font-medium text-primary hover:underline"
            >
              Agents
            </Link>
            .
          </>
        }
      >
        {agents.isError ? (
          <ErrorState
            compact
            error={agents.error}
            onRetry={() => void agents.refetch()}
          />
        ) : !agents.data ? (
          <Skeleton className="h-64" />
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border px-3">
            {agents.data.map((a) => (
              <li key={a.id}>
                <ToggleRow
                  id={`ac-${a.id}`}
                  label={
                    <span className="flex items-center gap-2">
                      {a.name}
                      <Link
                        href={`/pi/agents/${a.id}`}
                        className="text-xs font-normal text-primary hover:underline"
                      >
                        Configure
                      </Link>
                    </span>
                  }
                  description={
                    errors[a.id] ? (
                      <span className="text-danger">{errors[a.id]}</span>
                    ) : (
                      `${a.role} · v${a.current_version} · last run ${a.last_run_at ? relativeTime(a.last_run_at) : "never"}`
                    )
                  }
                  checked={a.enabled}
                  disabled={toggle.isPending && toggle.variables?.id === a.id}
                  onCheckedChange={(enabled) => {
                    setErrors((e) => ({ ...e, [a.id]: "" }));
                    toggle.mutate(
                      { id: a.id, enabled },
                      {
                        onError: (error) =>
                          setErrors((e) => ({
                            ...e,
                            [a.id]: errorMessage(error),
                          })),
                      },
                    );
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </FormSection>
    </Card>
  );
}

/* Handoff rules --------------------------------------------------------------------- */

const handoffSchema = z.object({
  keywords: z.array(z.string().min(1).max(40)).max(50, "Up to 50 keywords"),
  low_confidence_threshold: num().min(0).max(1),
  max_failed_turns: num().int().min(1, "At least 1").max(10, "At most 10"),
  handoff_on_complaint: z.boolean(),
  notify_roles: z.array(z.string()),
});
type HandoffValues = z.infer<typeof handoffSchema>;

export function HandoffRulesForm({ settings }: { settings: PiSettings }) {
  const form = useForm<HandoffValues>({
    resolver: zodResolver(handoffSchema),
    defaultValues: {
      ...settings.handoff_rules,
      low_confidence_threshold:
        Number(settings.handoff_rules.low_confidence_threshold) || 0,
    },
  });
  const save = useSaveSection("handoff_rules");
  const { onSubmit, savedAt } = useSubmit(form, save.mutateAsync, (v) => ({
    ...v,
    low_confidence_threshold: v.low_confidence_threshold.toFixed(2),
  }));
  const err = form.formState.errors;
  const roles = Array.from(
    new Set([
      ...settings.permissions.map((p) => p.role),
      ...settings.handoff_rules.notify_roles,
    ]),
  );
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={save.isPending}
      savedAt={savedAt}
    >
      <FormSection
        title="Triggers"
        description="PI hands off when any of these apply. It also always hands off when a person should decide."
      >
        <Controller
          control={form.control}
          name="keywords"
          render={({ field }) => (
            <KeywordInput
              value={field.value}
              onChange={field.onChange}
              error={err.keywords?.message}
            />
          )}
        />
        <Controller
          control={form.control}
          name="low_confidence_threshold"
          render={({ field }) => (
            <FormField
              label="Low-confidence threshold"
              htmlFor="hr-threshold"
              help="Below this confidence PI asks to clarify, then hands off."
            >
              <div className="flex items-center gap-3">
                <input
                  id="hr-threshold"
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
        <FormField
          label="Max failed turns"
          htmlFor="hr-turns"
          error={err.max_failed_turns}
          help="Consecutive turns PI couldn't resolve before handing off (1–10)."
        >
          <Input
            id="hr-turns"
            type="number"
            min={1}
            max={10}
            className="w-28"
            {...form.register("max_failed_turns", { valueAsNumber: true })}
          />
        </FormField>
        <SwitchField
          form={form}
          name="handoff_on_complaint"
          label="Hand off complaints"
          description="Escalate as soon as a complaint is detected."
        />
      </FormSection>
      <FormSection
        title="Notifications"
        description="Roles notified when a handoff is created."
      >
        <Controller
          control={form.control}
          name="notify_roles"
          render={({ field }) => (
            <ul className="grid gap-2 sm:grid-cols-2">
              {roles.map((role) => {
                const id = `hr-role-${role}`;
                return (
                  <li key={role} className="flex items-center gap-2">
                    <Checkbox
                      id={id}
                      checked={field.value.includes(role)}
                      onCheckedChange={(c) =>
                        field.onChange(
                          c
                            ? [...field.value, role]
                            : field.value.filter((r: string) => r !== role),
                        )
                      }
                    />
                    <label htmlFor={id} className="text-[13px]">
                      {humanize(role)}
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        />
      </FormSection>
    </SettingsForm>
  );
}

function KeywordInput({
  value,
  onChange,
  error,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  error?: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const words = draft
      .split(",")
      .map((w) => w.trim().toLowerCase())
      .filter((w) => w && w.length <= 40 && !value.includes(w));
    if (words.length) onChange([...value, ...new Set(words)]);
    setDraft("");
  };
  return (
    <FormField
      label="Handoff keywords"
      htmlFor="hr-keywords"
      error={error}
      help="Press Enter or comma to add. Matching is case-insensitive."
    >
      <div className="rounded-md border border-border bg-surface p-1.5 focus-within:border-ring">
        <ul className="flex flex-wrap gap-1.5" aria-label="Keywords">
          {value.map((k) => (
            <li key={k}>
              <Badge tone="neutral" className="gap-1 pr-1">
                {k}
                <button
                  type="button"
                  onClick={() => onChange(value.filter((x) => x !== k))}
                  className="rounded p-0.5 hover:bg-surface-sunken"
                  aria-label={`Remove ${k}`}
                >
                  <X className="size-3" />
                </button>
              </Badge>
            </li>
          ))}
          <li className="min-w-32 flex-1">
            <input
              id="hr-keywords"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  add();
                } else if (e.key === "Backspace" && !draft && value.length) {
                  onChange(value.slice(0, -1));
                }
              }}
              onBlur={add}
              className="h-7 w-full bg-transparent px-1.5 text-sm outline-none"
              placeholder={
                value.length ? "Add keyword" : "e.g. refund, manager"
              }
            />
          </li>
        </ul>
      </div>
    </FormField>
  );
}

/* Knowledge configuration ----------------------------------------------------------- */

const knowledgeSchema = z.object({
  top_k: num().int().min(1, "At least 1").max(20, "At most 20"),
  min_score: num().min(0).max(1),
  semantic_enabled: z.boolean(),
  cite_sources_to_operators: z.boolean(),
});
type KnowledgeValues = z.infer<typeof knowledgeSchema>;

export function KnowledgeConfigForm({ settings }: { settings: PiSettings }) {
  const form = useForm<KnowledgeValues>({
    resolver: zodResolver(knowledgeSchema),
    defaultValues: {
      ...settings.knowledge_config,
      min_score: Number(settings.knowledge_config.min_score) || 0,
    },
  });
  const save = useSaveSection("knowledge_config");
  const { onSubmit, savedAt } = useSubmit(form, save.mutateAsync, (v) => ({
    ...v,
    min_score: v.min_score.toFixed(2),
  }));
  const err = form.formState.errors;
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={save.isPending}
      savedAt={savedAt}
    >
      <FormSection
        title="Retrieval"
        description="How many passages PI reads and how relevant they must be. Retrieval is always scoped to this workspace and environment."
      >
        <FormField
          label="Passages per answer"
          htmlFor="kc-topk"
          error={err.top_k}
          help="1–20. More passages give more context but slower replies."
        >
          <Input
            id="kc-topk"
            type="number"
            min={1}
            max={20}
            className="w-28"
            {...form.register("top_k", { valueAsNumber: true })}
          />
        </FormField>
        <Controller
          control={form.control}
          name="min_score"
          render={({ field }) => (
            <FormField
              label="Minimum relevance"
              htmlFor="kc-score"
              help="Passages below this score are ignored."
            >
              <div className="flex items-center gap-3">
                <input
                  id="kc-score"
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
        <SwitchField
          form={form}
          name="semantic_enabled"
          label="Semantic search"
          description="Adds meaning-based matching on top of full-text search. Requires the pgvector extension on the server; without it PI uses full-text search only."
        />
        <SwitchField
          form={form}
          name="cite_sources_to_operators"
          label="Show sources to operators"
          description="Operators see which passages PI used in the inbox. Customers never see citations."
        />
      </FormSection>
    </SettingsForm>
  );
}

/* WhatsApp configuration ------------------------------------------------------------ */

const waSchema = z.object({
  send_read_receipts: z.boolean(),
  typing_indicator: z.boolean(),
  media_voice: z.boolean(),
  media_images: z.boolean(),
  media_video: z.boolean(),
  reminder_enabled: z.boolean(),
  reminder_after_days: num().int().min(1).max(30),
  reminder_templates: z.record(
    z.string().regex(/^(roman_ur|[a-z]{2,3}([-_][A-Za-z0-9]{2,8})?)$/),
    z.object({
      name: z.string().regex(/^[a-z0-9_]{1,512}$/),
      language: z.string().regex(/^[a-z]{2,3}(_[A-Z]{2})?$/),
    }),
  ),
  max_media_mb: num()
    .int()
    .min(1, "At least 1 MB")
    .max(16, "WhatsApp media is limited to 16 MB"),
});
type WaValues = z.infer<typeof waSchema>;

export function WhatsAppConfigForm({ settings }: { settings: PiSettings }) {
  const form = useForm<WaValues>({
    resolver: zodResolver(waSchema),
    defaultValues: {
      ...settings.whatsapp_config,
      media_video: settings.whatsapp_config.media_video ?? true,
      reminder_enabled: settings.whatsapp_config.reminder_enabled ?? true,
      reminder_after_days: settings.whatsapp_config.reminder_after_days ?? 7,
      reminder_templates: settings.whatsapp_config.reminder_templates ?? {},
    },
  });
  const save = useSaveSection("whatsapp_config");
  const { onSubmit, savedAt } = useSubmit(form, save.mutateAsync, (v) => v);
  const err = form.formState.errors;
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={save.isPending}
      savedAt={savedAt}
    >
      <FormSection
        title="Presence"
        description="Signals customers see in WhatsApp."
      >
        <SwitchField
          form={form}
          name="send_read_receipts"
          label="Send read receipts"
          description="Mark customer messages as read (blue ticks) when PI processes them."
        />
        <SwitchField
          form={form}
          name="typing_indicator"
          label="Typing indicator"
          description="Show “typing…” while PI prepares a reply."
        />
      </FormSection>
      <FormSection
        title="Media"
        description="Which customer media PI processes."
      >
        <SwitchField
          form={form}
          name="media_voice"
          label="Voice notes"
          description="Transcribe voice notes and answer them."
        />
        <SwitchField
          form={form}
          name="media_images"
          label="Images"
          description="Describe images, e.g. product photos, to understand the request."
        />
        <SwitchField
          form={form}
          name="media_video"
          label="Videos"
          description="Understand short videos and their speech. Requires a configured video provider; unsupported files go to your team."
        />
        <FormField
          label="Maximum media size (MB)"
          htmlFor="wa-max"
          error={err.max_media_mb}
          help="Larger files are acknowledged and handed off (1–16)."
        >
          <Input
            id="wa-max"
            type="number"
            min={1}
            max={16}
            className="w-28"
            {...form.register("max_media_mb", { valueAsNumber: true })}
          />
        </FormField>
      </FormSection>
      <FormSection
        title="Follow-up reminders"
        description="One reminder after an unanswered service conversation. PI asks the customer for permission and stops after an opt-out, reply, closure or human takeover."
      >
        <SwitchField
          form={form}
          name="reminder_enabled"
          label="Send follow-up reminders"
          description="Uses an approved WhatsApp template in the customer's language."
        />
        <FormField
          label="Days without a reply"
          htmlFor="wa-reminder-days"
          error={err.reminder_after_days}
        >
          <Input
            id="wa-reminder-days"
            type="number"
            min={1}
            max={30}
            {...form.register("reminder_after_days", { valueAsNumber: true })}
          />
        </FormField>
        <Controller
          control={form.control}
          name="reminder_templates"
          render={({ field }) => (
            <ReminderTemplatesEditor
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
        {err.reminder_templates && (
          <p role="alert" className="text-sm text-danger">
            Check the language codes and template names.
          </p>
        )}
      </FormSection>
    </SettingsForm>
  );
}

function ReminderTemplatesEditor({
  value,
  onChange,
}: {
  value: Record<string, { name: string; language: string }>;
  onChange: (value: Record<string, { name: string; language: string }>) => void;
}) {
  const [customerLanguage, setCustomerLanguage] = useState("");
  const [name, setName] = useState("");
  const [templateLanguage, setTemplateLanguage] = useState("");
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Add an approved text template without variables or buttons for each
        customer language. For Roman Urdu, use customer language roman_ur and
        the language approved by Meta. Set your WhatsApp business account ID on
        the connection page.
      </p>
      {Object.entries(value).map(([language, template]) => (
        <div
          key={language}
          className="flex items-center justify-between gap-2 rounded border p-2 text-sm"
        >
          <span>
            {language}: {template.name} ({template.language})
          </span>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              const next = { ...value };
              delete next[language];
              onChange(next);
            }}
          >
            Remove
          </Button>
        </div>
      ))}
      <div className="grid gap-2 sm:grid-cols-3">
        <Input
          aria-label="Customer language code"
          placeholder="Customer language: en"
          value={customerLanguage}
          onChange={(e) => setCustomerLanguage(e.target.value)}
        />
        <Input
          aria-label="Approved reminder template name"
          placeholder="Template: service_followup"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          aria-label="Meta template language code"
          placeholder="Meta language: en_US"
          value={templateLanguage}
          onChange={(e) => setTemplateLanguage(e.target.value)}
        />
      </div>
      <Button
        type="button"
        variant="outline"
        disabled={
          !customerLanguage.trim() || !name.trim() || !templateLanguage.trim()
        }
        onClick={() => {
          onChange({
            ...value,
            [customerLanguage.trim()]: {
              name: name.trim(),
              language: templateLanguage.trim(),
            },
          });
          setCustomerLanguage("");
          setName("");
          setTemplateLanguage("");
        }}
      >
        Add template
      </Button>
    </div>
  );
}

/* Permissions ------------------------------------------------------------------------ */

const permSchema = z.object({
  permissions: z.array(
    z.object({
      role: z.string(),
      view_inbox: z.boolean(),
      reply: z.boolean(),
      takeover: z.boolean(),
      configure: z.boolean(),
    }),
  ),
});
type PermValues = z.infer<typeof permSchema>;
const PERM_COLUMNS = [
  ["view_inbox", "View inbox"],
  ["reply", "Reply"],
  ["takeover", "Take over"],
  ["configure", "Configure"],
] as const;

export function PermissionsForm({ settings }: { settings: PiSettings }) {
  const form = useForm<PermValues>({
    resolver: zodResolver(permSchema),
    defaultValues: { permissions: settings.permissions },
  });
  const save = useSaveSection("permissions");
  const { onSubmit, savedAt } = useSubmit(
    form,
    save.mutateAsync,
    (v) => v.permissions,
  );
  const rows = useWatch({ control: form.control, name: "permissions" });
  return (
    <SettingsForm
      form={form}
      onSubmit={onSubmit}
      saving={save.isPending}
      savedAt={savedAt}
    >
      <Notice tone="neutral" className="mb-5">
        Roles are managed in{" "}
        <Link
          href="/settings/roles"
          className="font-medium text-primary hover:underline"
        >
          Roles &amp; Permissions
        </Link>
        . These switches refine what each role can do in PI; the server enforces
        them on every request.
      </Notice>
      {rows.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">No roles found.</p>
      ) : (
        <div className="scrollbar-thin overflow-x-auto">
          <table className="w-full min-w-[480px] text-[13px]">
            <caption className="sr-only">PI permissions by role</caption>
            <thead>
              <tr className="border-b border-border">
                <th
                  scope="col"
                  className="px-2 py-2 text-left text-xs font-medium text-muted-foreground"
                >
                  Role
                </th>
                {PERM_COLUMNS.map(([, label]) => (
                  <th
                    key={label}
                    scope="col"
                    className="px-2 py-2 text-center text-xs font-medium text-muted-foreground"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={row.role}
                  className="border-b border-border last:border-0"
                >
                  <th scope="row" className="px-2 py-2.5 text-left font-medium">
                    {humanize(row.role)}
                  </th>
                  {PERM_COLUMNS.map(([key, label]) => (
                    <td key={key} className="px-2 py-2.5 text-center">
                      <Controller
                        control={form.control}
                        name={`permissions.${i}.${key}`}
                        render={({ field }) => (
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                            aria-label={`${humanize(row.role)}: ${label}`}
                          />
                        )}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        {formatNumber(rows.length)} roles
      </p>
    </SettingsForm>
  );
}
