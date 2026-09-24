"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import {
  CheckCircle2,
  Circle,
  Copy,
  KeyRound,
  MessageCircle,
  Power,
  PowerOff,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import { Input } from "@/components/ui/input";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  ConfirmDialog,
  FormActions,
  FormField,
  FormSection,
  useUnsavedChangesWarning,
} from "@/components/app/forms";
import { PropertyList } from "@/components/app/record";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { piService } from "../../service";
import type { WhatsAppConnection } from "../../types";
import { humanizeError, piKeys } from "../shared";
import { WhatsAppNav } from "./whatsapp-nav";

export function WhatsAppConnectionPage() {
  return (
    <RequirePermission permission="pi.whatsapp.manage" area="WhatsApp settings">
      <Connection />
    </RequirePermission>
  );
}

const STATUS_LABELS: Record<WhatsAppConnection["status"], string> = {
  pending: "Pending activation",
  active: "Active",
  disabled: "Disabled",
  error: "Error",
};

function Connection() {
  const connection = useScopedQuery(piKeys.connection, () =>
    piService.connection(),
  );
  const [confirm, setConfirm] = useState<"active" | "disabled" | null>(null);
  const setStatus = useScopedMutation(
    (status: "active" | "disabled") => piService.setConnectionStatus(status),
    {
      invalidate: [[...piKeys.connection], [...piKeys.overview]],
      success: (c) =>
        c.status === "active"
          ? "WhatsApp number activated"
          : "WhatsApp number disabled",
      onSuccess: () => setConfirm(null),
    },
  );

  const c = connection.data;
  return (
    <PageShell width="default">
      <PageHeader
        title="WhatsApp"
        description="Connect your WhatsApp Business number so PI can receive and answer customer messages."
        actions={
          c ? (
            c.status === "active" ? (
              <Button
                variant="danger-outline"
                onClick={() => setConfirm("disabled")}
              >
                <PowerOff /> Disable
              </Button>
            ) : (
              <Button onClick={() => setConfirm("active")}>
                <Power /> Activate
              </Button>
            )
          ) : undefined
        }
      />
      <WhatsAppNav />

      {connection.isError ? (
        <Card>
          <ErrorState
            error={connection.error}
            onRetry={() => void connection.refetch()}
          />
        </Card>
      ) : connection.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-56 rounded-xl" />
          <Skeleton className="h-80 rounded-xl" />
        </div>
      ) : !c ? (
        <>
          <Card className="mb-4">
            <EmptyState
              tone="pi"
              icon={MessageCircle}
              title="Connect a WhatsApp Business number"
              description="You'll need the phone number ID, the WhatsApp Business account ID and a permanent access token from Meta's WhatsApp Manager."
            />
          </Card>
          <ConnectionForm connection={null} />
        </>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <Summary connection={c} />
            <Checklist connection={c} />
          </div>
          <ConnectionForm connection={c} />
        </div>
      )}

      <ConfirmDialog
        open={confirm === "disabled"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Disable this WhatsApp number?"
        description="PI stops receiving and sending WhatsApp messages until you activate it again."
        consequences={[
          "Incoming customer messages are not processed or answered.",
          "Operators can't reply from the PI inbox through this number.",
          "Your settings and access token are kept.",
        ]}
        confirmLabel="Disable number"
        destructive
        loading={setStatus.isPending}
        onConfirm={() => setStatus.mutate("disabled")}
      />
      <ConfirmDialog
        open={confirm === "active"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Activate this WhatsApp number?"
        description="PI starts receiving messages sent to this number and replies according to your PI settings."
        consequences={[
          "Automatic replies follow the Auto-replies switch in PI settings.",
          "Make sure the webhook is verified so messages reach PI.",
        ]}
        confirmLabel="Activate"
        loading={setStatus.isPending}
        onConfirm={() => setStatus.mutate("active")}
      />
    </PageShell>
  );
}

function Summary({ connection: c }: { connection: WhatsAppConnection }) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(c.webhook_url);
      toast.success("Webhook URL copied");
    } catch {
      toast.error("Couldn't copy. Select the URL and copy it manually.");
    }
  }
  return (
    <Card>
      <CardHeader
        title={c.display_name || "WhatsApp number"}
        description={c.display_phone_number}
        actions={
          <StatusBadge status={c.status} label={STATUS_LABELS[c.status]} />
        }
      />
      <CardBody>
        <PropertyList
          items={[
            {
              label: "Phone number ID",
              value: (
                <span className="font-mono text-xs">{c.phone_number_id}</span>
              ),
            },
            {
              label: "Business account ID",
              value: (
                <span className="font-mono text-xs">
                  {c.business_account_id}
                </span>
              ),
            },
            {
              label: "Access token",
              value: c.has_access_token ? (
                <span className="inline-flex items-center gap-1 text-success">
                  <KeyRound className="size-3.5" aria-hidden="true" /> Token
                  stored
                </span>
              ) : (
                <span className="text-warning">Not set</span>
              ),
            },
            {
              label: "Webhook URL",
              value: (
                <span className="flex items-center justify-end gap-1.5">
                  <span
                    className="min-w-0 truncate font-mono text-xs"
                    title={c.webhook_url}
                  >
                    {c.webhook_url}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    onClick={() => void copy()}
                    aria-label="Copy webhook URL"
                  >
                    <Copy />
                  </Button>
                </span>
              ),
            },
            {
              label: "Webhook",
              value: c.webhook_verified ? (
                <StatusBadge
                  status="success"
                  label={`Verified ${c.verified_at ? formatDateTime(c.verified_at) : ""}`}
                />
              ) : (
                <StatusBadge status="pending" label="Not verified" />
              ),
            },
          ]}
        />
        {c.last_error_code && (
          <Notice tone="danger" className="mt-3" title="Last error">
            {humanizeError(c.last_error_code)}
            {c.last_error_at && ` · ${formatDateTime(c.last_error_at)}`}
          </Notice>
        )}
      </CardBody>
    </Card>
  );
}

function Checklist({ connection: c }: { connection: WhatsAppConnection }) {
  const steps = [
    {
      done: c.has_access_token,
      label: "Access token stored",
      help: "Paste a permanent token from WhatsApp Manager below.",
    },
    {
      done: c.webhook_verified,
      label: "Webhook verified",
      help: "Add the webhook URL in your Meta app and subscribe to messages.",
    },
    {
      done: c.status === "active",
      label: "Number active",
      help: "Activate the number once the token and webhook are in place.",
    },
  ];
  const complete = steps.filter((s) => s.done).length;
  return (
    <Card>
      <CardHeader
        title="Setup"
        description={`${complete} of ${steps.length} steps complete`}
      />
      <CardBody>
        <ol className="space-y-3">
          {steps.map((s) => (
            <li key={s.label} className="flex gap-2.5">
              {s.done ? (
                <CheckCircle2
                  className="mt-0.5 size-4 shrink-0 text-success"
                  aria-hidden="true"
                />
              ) : (
                <Circle
                  className="mt-0.5 size-4 shrink-0 text-border-strong"
                  aria-hidden="true"
                />
              )}
              <div>
                <p
                  className={cn(
                    "text-[13px] font-medium",
                    s.done && "text-foreground-secondary",
                  )}
                >
                  {s.label}
                  <span className="sr-only">
                    {s.done ? " (done)" : " (to do)"}
                  </span>
                </p>
                {!s.done && (
                  <p className="text-xs text-muted-foreground">{s.help}</p>
                )}
              </div>
            </li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}

const digits = (label: string) =>
  z
    .string()
    .trim()
    .regex(
      /^[0-9]{5,32}$/,
      `${label} must be 5–32 digits from WhatsApp Manager`,
    );

const schema = z.object({
  display_name: z
    .string()
    .trim()
    .min(1, "Enter the business display name")
    .max(120),
  display_phone_number: z
    .string()
    .trim()
    .min(5, "Enter the phone number customers see")
    .max(32),
  phone_number_id: digits("Phone number ID"),
  business_account_id: digits("Business account ID"),
  access_token: z.string().max(1024),
});
type Values = z.infer<typeof schema>;

function ConnectionForm({
  connection,
}: {
  connection: WhatsAppConnection | null;
}) {
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const hasToken = Boolean(connection?.has_access_token);
  const form = useForm<Values>({
    resolver: zodResolver(
      schema.refine((v) => hasToken || v.access_token.trim().length > 0, {
        path: ["access_token"],
        message: "Enter the access token",
      }),
    ),
    values: {
      display_name: connection?.display_name ?? "",
      display_phone_number: connection?.display_phone_number ?? "",
      phone_number_id: connection?.phone_number_id ?? "",
      business_account_id: connection?.business_account_id ?? "",
      access_token: "",
    },
    resetOptions: { keepDirtyValues: false },
  });
  const dirty = form.formState.isDirty;
  useUnsavedChangesWarning(dirty);

  const save = useScopedMutation(
    (v: Values) =>
      piService.saveConnection({
        display_name: v.display_name,
        display_phone_number: v.display_phone_number,
        phone_number_id: v.phone_number_id,
        business_account_id: v.business_account_id,
        access_token: v.access_token.trim() || undefined,
      }),
    {
      invalidate: [[...piKeys.connection], [...piKeys.overview]],
      success: connection ? "Connection saved" : "WhatsApp number connected",
      error:
        "The connection couldn't be saved. Check the details and try again.",
    },
  );

  const onSubmit = form.handleSubmit(async (v) => {
    try {
      await save.mutateAsync(v);
      form.resetField("access_token", { defaultValue: "" });
      setSavedAt((n) => (n ?? 0) + 1);
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.serverMessage &&
        error.status === 422
      ) {
        form.setError("phone_number_id", { message: error.serverMessage });
      }
    }
  });

  const err = form.formState.errors;
  return (
    <form onSubmit={onSubmit} noValidate>
      <Card className="p-5 sm:p-6">
        <FormSection
          title="Business number"
          description="As shown in WhatsApp Manager."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              label="Display name"
              htmlFor="wa-name"
              required
              error={err.display_name}
            >
              <Input
                id="wa-name"
                autoComplete="organization"
                aria-invalid={Boolean(err.display_name)}
                {...form.register("display_name")}
              />
            </FormField>
            <FormField
              label="Phone number"
              htmlFor="wa-number"
              required
              error={err.display_phone_number}
            >
              <Input
                id="wa-number"
                inputMode="tel"
                placeholder="+92 300 1234567"
                aria-invalid={Boolean(err.display_phone_number)}
                {...form.register("display_phone_number")}
              />
            </FormField>
            <FormField
              label="Phone number ID"
              htmlFor="wa-pnid"
              required
              error={err.phone_number_id}
            >
              <Input
                id="wa-pnid"
                inputMode="numeric"
                className="font-mono"
                aria-invalid={Boolean(err.phone_number_id)}
                {...form.register("phone_number_id")}
              />
            </FormField>
            <FormField
              label="Business account ID"
              htmlFor="wa-waba"
              required
              error={err.business_account_id}
            >
              <Input
                id="wa-waba"
                inputMode="numeric"
                className="font-mono"
                aria-invalid={Boolean(err.business_account_id)}
                {...form.register("business_account_id")}
              />
            </FormField>
          </div>
        </FormSection>
        <FormSection
          title="Access token"
          description="Stored encrypted on the server and never shown again."
        >
          <FormField
            label="Permanent access token"
            htmlFor="wa-token"
            required={!hasToken}
            error={err.access_token}
            help={
              hasToken
                ? "A token is stored. Leave blank to keep it."
                : "Create a system-user token with whatsapp_business_messaging permission."
            }
          >
            <Input
              id="wa-token"
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              placeholder={
                hasToken
                  ? "Stored securely — enter a new token to replace"
                  : "Paste the access token"
              }
              aria-invalid={Boolean(err.access_token)}
              {...form.register("access_token")}
            />
          </FormField>
        </FormSection>
      </Card>
      <FormActions
        dirty={dirty}
        saving={save.isPending}
        savedAt={savedAt}
        onCancel={dirty ? () => form.reset() : undefined}
        submitLabel={connection ? "Save connection" : "Connect number"}
      />
    </form>
  );
}
