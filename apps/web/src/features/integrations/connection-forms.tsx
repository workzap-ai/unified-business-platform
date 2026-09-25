"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Controller,
  useForm,
  useWatch,
  type Control,
  type FieldErrors,
  type Resolver,
  type UseFormRegister,
} from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { FlaskConical, Lock, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import {
  Label,
  RadioGroup,
  RadioGroupItem,
  Switch,
} from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import { InlineError, Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import { integrationsService } from "./service";
import { applyServerFieldErrors } from "./components";
import { AUTH_LABELS, isOAuth, outboundUrlProblem } from "./lib";
import type {
  ConfigField,
  ConnectionDetail,
  IntegrationDefinition,
  Mode,
} from "./types";

type DynamicValues = {
  display_name: string;
  mode: Mode;
  config: Record<string, string | boolean>;
  credentials: Record<string, string>;
};

function fieldSchema(field: ConfigField, requireSecrets = true) {
  if (field.type === "boolean") return z.boolean();
  let s = z.string().trim();
  if (field.required && (!field.secret || requireSecrets))
    s = s.min(1, `${field.label} is required`);
  return s.superRefine((value, ctx) => {
    if (!value) return;
    if (field.type === "url") {
      const problem = outboundUrlProblem(value);
      if (problem) ctx.addIssue({ code: "custom", message: problem });
    }
    if (field.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
      ctx.addIssue({ code: "custom", message: "Enter a valid email address" });
    if (field.type === "number" && !Number.isFinite(Number(value)))
      ctx.addIssue({ code: "custom", message: "Enter a number" });
    if (field.secret && value.length < 8)
      ctx.addIssue({
        code: "custom",
        message: `${field.label} must be at least 8 characters`,
      });
  });
}

function buildSchema(
  fields: ConfigField[],
  { withName = true, withMode = true, secrets = true, plain = true } = {},
) {
  const config: Record<string, z.ZodType> = {};
  const credentials: Record<string, z.ZodType> = {};
  for (const f of fields) {
    if (f.secret && secrets) credentials[f.key] = fieldSchema(f);
    if (!f.secret && plain) config[f.key] = fieldSchema(f);
  }
  return z.object({
    display_name: withName
      ? z
          .string()
          .trim()
          .min(1, "Name is required")
          .max(80, "Keep the name under 80 characters")
      : z.string().optional(),
    mode: withMode ? z.enum(["sandbox", "production"]) : z.string().optional(),
    config: z.object(config),
    credentials: z.object(credentials),
  });
}

function toPayload(fields: ConfigField[], values: DynamicValues) {
  const config: Record<string, unknown> = {};
  const credentials: Record<string, string> = {};
  for (const f of fields) {
    if (f.secret) {
      const v = values.credentials?.[f.key];
      if (typeof v === "string" && v) credentials[f.key] = v;
      continue;
    }
    const v = values.config?.[f.key];
    if (v === undefined || v === "") continue;
    config[f.key] = f.type === "number" ? Number(v) : v;
  }
  return { config, credentials };
}

function defaultsFor(
  fields: ConfigField[],
  current: Record<string, unknown> = {},
) {
  const config: Record<string, string | boolean> = {};
  const credentials: Record<string, string> = {};
  for (const f of fields) {
    if (f.secret) credentials[f.key] = "";
    else if (f.type === "boolean") config[f.key] = Boolean(current[f.key]);
    else
      config[f.key] =
        current[f.key] === undefined || current[f.key] === null
          ? ""
          : String(current[f.key]);
  }
  return { config, credentials };
}

/** Renders a definition's config_schema. Secret fields are write-only password inputs. */
function DynamicFields({
  fields,
  register,
  control,
  errors,
  disabled,
  idPrefix,
}: {
  fields: ConfigField[];
  register: UseFormRegister<DynamicValues>;
  control: Control<DynamicValues>;
  errors: FieldErrors<DynamicValues>;
  disabled: boolean;
  idPrefix: string;
}) {
  return (
    <>
      {fields.map((f) => {
        const group = f.secret ? "credentials" : "config";
        const name = `${group}.${f.key}` as const;
        const id = `${idPrefix}-${group}-${f.key}`;
        const error = (
          errors[group] as Record<string, { message?: string }> | undefined
        )?.[f.key]?.message;
        const describedBy = error
          ? `${id}-error`
          : f.help || f.secret
            ? `${id}-help`
            : undefined;
        const help = f.secret ? (
          <span className="inline-flex items-start gap-1">
            <Lock className="mt-px size-3 shrink-0" aria-hidden="true" />
            <span>
              Write-only. Stored encrypted; afterwards you&apos;ll only see a
              hint.
              {f.help ? ` ${f.help}` : ""}
            </span>
          </span>
        ) : (
          f.help
        );
        if (f.type === "boolean") {
          return (
            <div
              key={f.key}
              className="flex items-center justify-between gap-3"
            >
              <Label htmlFor={id}>{f.label}</Label>
              <Controller
                control={control}
                name={name}
                render={({ field }) => (
                  <Switch
                    id={id}
                    checked={Boolean(field.value)}
                    onCheckedChange={field.onChange}
                    disabled={disabled}
                  />
                )}
              />
            </div>
          );
        }
        return (
          <FormField
            key={f.key}
            label={f.label}
            htmlFor={id}
            required={f.required}
            optional={!f.required}
            help={help}
            error={error}
          >
            {f.type === "select" ? (
              <NativeSelect
                id={id}
                disabled={disabled}
                aria-invalid={!!error || undefined}
                aria-describedby={describedBy}
                {...register(name)}
              >
                <option value="">Choose…</option>
                {f.options?.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
            ) : (
              <Input
                id={id}
                type={
                  f.secret || f.type === "password"
                    ? "password"
                    : f.type === "number"
                      ? "number"
                      : f.type === "email"
                        ? "email"
                        : f.type === "url"
                          ? "url"
                          : "text"
                }
                inputMode={f.type === "number" ? "numeric" : undefined}
                autoComplete={f.secret ? "new-password" : "off"}
                spellCheck={false}
                className={cn(
                  f.secret || f.type === "url"
                    ? "font-mono text-[13px]"
                    : undefined,
                )}
                disabled={disabled}
                aria-invalid={!!error || undefined}
                aria-describedby={describedBy}
                placeholder={f.type === "url" ? "https://" : undefined}
                {...register(name)}
              />
            )}
          </FormField>
        );
      })}
    </>
  );
}

function useServerErrors(
  setError: (name: string, message: string) => void,
  knownKeys: Set<string>,
) {
  return (error: unknown) =>
    applyServerFieldErrors(error, (key, message) => {
      const normalized = key.replace(/^body\./, "");
      if (!knownKeys.has(normalized)) return false;
      setError(normalized, message);
      return true;
    });
}

function knownKeysFor(fields: ConfigField[], extra: string[]) {
  return new Set([
    ...extra,
    ...fields.map((f) => `${f.secret ? "credentials" : "config"}.${f.key}`),
  ]);
}

/* Connect ------------------------------------------------------------------------ */

export function ConnectDialog({
  definition,
  onClose,
}: {
  definition: IntegrationDefinition;
  onClose: () => void;
}) {
  const router = useRouter();
  const fields = definition.config_schema;
  const oauth = isOAuth(definition.auth_type);
  const schema = useMemo(() => buildSchema(fields), [fields]);
  const form = useForm<DynamicValues>({
    resolver: zodResolver(schema) as unknown as Resolver<DynamicValues>,
    defaultValues: {
      display_name: definition.name,
      mode: "production",
      ...defaultsFor(fields),
    },
  });
  const mode = useWatch({ control: form.control, name: "mode" });
  const [serverError, setServerError] = useState<string | null>(null);
  const [redirecting, setRedirecting] = useState(false);
  const create = useScopedMutation(
    (values: DynamicValues) =>
      integrationsService.createConnection({
        integration_key: definition.key,
        display_name: values.display_name.trim(),
        mode: values.mode,
        ...toPayload(fields, values),
      }),
    { invalidate: [["integrations"]], toastErrors: false },
  );
  const mapErrors = useServerErrors(
    (name, message) =>
      form.setError(name as "display_name", { type: "server", message }),
    knownKeysFor(fields, ["display_name", "mode"]),
  );
  const busy = create.isPending || redirecting;

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent size="md">
        <DialogHeader
          title={`Connect ${definition.name}`}
          description={
            oauth
              ? `After saving you'll be sent to ${definition.provider} to approve the access listed on this page.`
              : "Credentials are tested when you save. You'll see the result before anything is marked connected."
          }
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (values) => {
            setServerError(null);
            try {
              const connection = await create.mutateAsync(values);
              if (oauth) {
                setRedirecting(true);
                const { authorization_url } =
                  await integrationsService.startOAuth(connection.id);
                window.location.assign(authorization_url);
                return;
              }
              if (connection.status === "connected")
                toast.success(
                  `${connection.display_name} connected. The connection test passed.`,
                );
              else
                toast.warning(
                  `${connection.display_name} was saved but isn't connected yet${
                    connection.last_error ? `: ${connection.last_error}` : "."
                  }`,
                );
              router.push(
                `/settings/integrations/connections/${connection.id}`,
              );
            } catch (error) {
              setRedirecting(false);
              const { mapped, leftovers } = mapErrors(error);
              if (!mapped || leftovers.length)
                setServerError(
                  leftovers[0] ??
                    errorMessage(error, "The connection could not be created."),
                );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <FormField
              label="Connection name"
              htmlFor="connect-name"
              required
              error={form.formState.errors.display_name}
              help="Shown to your team, e.g. “Main WhatsApp line”."
            >
              <Input
                id="connect-name"
                autoComplete="off"
                disabled={busy}
                aria-invalid={!!form.formState.errors.display_name || undefined}
                {...form.register("display_name")}
              />
            </FormField>

            <fieldset className="space-y-2">
              <legend className="text-[13px] font-medium">Mode</legend>
              <Controller
                control={form.control}
                name="mode"
                render={({ field }) => (
                  <RadioGroup
                    value={field.value}
                    onValueChange={field.onChange}
                    className="grid gap-2 sm:grid-cols-2"
                    disabled={busy}
                  >
                    <label
                      htmlFor="mode-production"
                      className={cn(
                        "flex cursor-pointer items-start gap-2.5 rounded-lg border p-3",
                        field.value === "production"
                          ? "border-primary bg-primary-soft/40"
                          : "border-border",
                      )}
                    >
                      <RadioGroupItem
                        id="mode-production"
                        value="production"
                        className="mt-0.5"
                      />
                      <span className="text-[13px]">
                        <span className="block font-medium">Production</span>
                        <span className="text-xs text-muted-foreground">
                          Real customers and live provider accounts
                        </span>
                      </span>
                    </label>
                    <label
                      htmlFor="mode-sandbox"
                      className={cn(
                        "flex items-start gap-2.5 rounded-lg border p-3",
                        !definition.supports_sandbox
                          ? "cursor-not-allowed opacity-60"
                          : "cursor-pointer",
                        field.value === "sandbox"
                          ? "border-primary bg-primary-soft/40"
                          : "border-border",
                      )}
                    >
                      <RadioGroupItem
                        id="mode-sandbox"
                        value="sandbox"
                        className="mt-0.5"
                        disabled={!definition.supports_sandbox}
                      />
                      <span className="text-[13px]">
                        <span className="block font-medium">Sandbox</span>
                        <span className="text-xs text-muted-foreground">
                          {definition.supports_sandbox
                            ? "Provider test accounts; nothing reaches customers"
                            : `${definition.provider} doesn't offer a sandbox`}
                        </span>
                      </span>
                    </label>
                  </RadioGroup>
                )}
              />
              {form.formState.errors.mode && (
                <p role="alert" className="text-xs font-medium text-danger">
                  {form.formState.errors.mode.message}
                </p>
              )}
              {mode === "production" ? (
                <Notice
                  tone="warning"
                  icon={ShieldAlert}
                  title="Production mode"
                >
                  This connection will act on real data: messages, emails or
                  payments it sends reach real people.
                </Notice>
              ) : (
                <Notice tone="info" icon={FlaskConical} title="Sandbox mode">
                  Use the provider&apos;s test credentials. Sandbox connections
                  never reach real customers.
                </Notice>
              )}
            </fieldset>

            {fields.length > 0 ? (
              <DynamicFields
                fields={fields}
                register={form.register}
                control={form.control}
                errors={form.formState.errors}
                disabled={busy}
                idPrefix="connect"
              />
            ) : (
              <p className="text-[13px] text-muted-foreground">
                No configuration needed. Authentication:{" "}
                {AUTH_LABELS[definition.auth_type]}.
              </p>
            )}
            {serverError && <InlineError message={serverError} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button type="submit" loading={busy}>
              {oauth
                ? `Save and continue to ${definition.provider}`
                : "Save and test connection"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* Edit configuration ---------------------------------------------------------------- */

export function EditConfigDialog({
  connection,
  definition,
  onClose,
}: {
  connection: ConnectionDetail;
  definition: IntegrationDefinition;
  onClose: () => void;
}) {
  const fields = useMemo(
    () => definition.config_schema.filter((f) => !f.secret),
    [definition.config_schema],
  );
  const schema = useMemo(
    () => buildSchema(fields, { withMode: false, secrets: false }),
    [fields],
  );
  const form = useForm<DynamicValues>({
    resolver: zodResolver(schema) as unknown as Resolver<DynamicValues>,
    defaultValues: {
      display_name: connection.display_name,
      mode: connection.mode,
      ...defaultsFor(fields, connection.config),
    },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const update = useScopedMutation(
    (values: DynamicValues) =>
      integrationsService.updateConnection(connection.id, {
        display_name: values.display_name.trim(),
        config: toPayload(fields, values).config,
      }),
    {
      invalidate: [["integrations"]],
      toastErrors: false,
      success: "Configuration saved",
    },
  );
  const mapErrors = useServerErrors(
    (name, message) =>
      form.setError(name as "display_name", { type: "server", message }),
    knownKeysFor(fields, ["display_name"]),
  );
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !update.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title="Edit configuration"
          description="Credentials aren't edited here; use Rotate credentials."
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (values) => {
            setServerError(null);
            try {
              await update.mutateAsync(values);
              onClose();
            } catch (error) {
              const { mapped, leftovers } = mapErrors(error);
              if (!mapped || leftovers.length)
                setServerError(
                  leftovers[0] ??
                    errorMessage(
                      error,
                      "The configuration could not be saved.",
                    ),
                );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <FormField
              label="Connection name"
              htmlFor="edit-name"
              required
              error={form.formState.errors.display_name}
            >
              <Input
                id="edit-name"
                autoComplete="off"
                disabled={update.isPending}
                aria-invalid={!!form.formState.errors.display_name || undefined}
                {...form.register("display_name")}
              />
            </FormField>
            <DynamicFields
              fields={fields}
              register={form.register}
              control={form.control}
              errors={form.formState.errors}
              disabled={update.isPending}
              idPrefix="edit"
            />
            {serverError && <InlineError message={serverError} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={update.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={update.isPending}
              disabled={!form.formState.isDirty}
            >
              Save changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* Rotate credentials ---------------------------------------------------------------- */

export function RotateCredentialsDialog({
  connection,
  definition,
  onClose,
}: {
  connection: ConnectionDetail;
  definition: IntegrationDefinition;
  onClose: () => void;
}) {
  const fields = useMemo(
    () => definition.config_schema.filter((f) => f.secret),
    [definition.config_schema],
  );
  const schema = useMemo(
    () =>
      buildSchema(fields, { withName: false, withMode: false, plain: false }),
    [fields],
  );
  const form = useForm<DynamicValues>({
    resolver: zodResolver(schema) as unknown as Resolver<DynamicValues>,
    defaultValues: {
      display_name: "",
      mode: connection.mode,
      ...defaultsFor(fields),
    },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const rotate = useScopedMutation(
    (values: DynamicValues) =>
      integrationsService.rotateCredentials(
        connection.id,
        toPayload(fields, values).credentials,
      ),
    {
      invalidate: [["integrations"]],
      toastErrors: false,
      success: "Credentials rotated. Test the connection to verify them.",
    },
  );
  const mapErrors = useServerErrors(
    (name, message) =>
      form.setError(name as "display_name", { type: "server", message }),
    knownKeysFor(fields, []),
  );
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !rotate.isPending && onClose()}
    >
      <DialogContent size="md">
        <DialogHeader
          title={
            connection.status === "revoked"
              ? "Reconnect with new credentials"
              : "Rotate credentials"
          }
          description="The new values replace the stored ones immediately. Old values stop being used."
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={form.handleSubmit(async (values) => {
            setServerError(null);
            try {
              await rotate.mutateAsync(values);
              onClose();
            } catch (error) {
              const { mapped, leftovers } = mapErrors(error);
              if (!mapped || leftovers.length)
                setServerError(
                  leftovers[0] ??
                    errorMessage(
                      error,
                      "The credentials could not be rotated.",
                    ),
                );
            }
          })}
        >
          <DialogBody className="space-y-4">
            <DynamicFields
              fields={fields}
              register={form.register}
              control={form.control}
              errors={form.formState.errors}
              disabled={rotate.isPending}
              idPrefix="rotate"
            />
            {serverError && <InlineError message={serverError} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={rotate.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={rotate.isPending}>
              Save new credentials
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
