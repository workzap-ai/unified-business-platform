"use client";

import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Ban,
  KeyRound,
  ListChecks,
  MoreHorizontal,
  Pencil,
  Plus,
  Power,
  RotateCcw,
  Send,
  Trash2,
} from "lucide-react";
import { formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/display";
import { Input } from "@/components/ui/input";
import { Checkbox, Label, Switch } from "@/components/ui/controls";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  SheetContent,
} from "@/components/ui/overlays";
import { RequirePermission } from "@/components/app/page";
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import {
  EmptyState,
  ErrorState,
  InlineError,
  Notice,
} from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { errorMessage } from "@/services/api-client";
import { integrationsService } from "./service";
import {
  applyServerFieldErrors,
  GatedButton,
  IntegrationsFrame,
  SecretReveal,
  StateBadge,
  When,
} from "./components";
import { outboundUrlProblem, RETRYABLE_DELIVERY } from "./lib";
import type { WebhookSubscription, WebhookSubscriptionCreated } from "./types";

const PAGE_SIZE = 25;

export function WebhooksPage() {
  return (
    <RequirePermission permission="integrations.read" area="integrations">
      <Webhooks />
    </RequirePermission>
  );
}

function Webhooks() {
  const { can } = useSession();
  const canManage = can("integrations.manage");
  const [state, setState] = useUrlState({
    page: "1",
    deliveries: "",
    create: "",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const list = useScopedQuery(
    ["integrations", "webhooks", { page }],
    () => integrationsService.webhooks({ page, pageSize: PAGE_SIZE }),
    { placeholderData: (previous) => previous },
  );
  const [editing, setEditing] = useState<WebhookSubscription | "new" | null>(
    () => (state.create === "1" && canManage ? "new" : null),
  );
  const [rotating, setRotating] = useState<WebhookSubscription | null>(null);
  const [deleting, setDeleting] = useState<WebhookSubscription | null>(null);
  const [revealed, setRevealed] = useState<WebhookSubscriptionCreated | null>(
    null,
  );

  const invalidate = [["integrations"]];
  const toggle = useScopedMutation(
    (w: WebhookSubscription) =>
      integrationsService.updateWebhook(w.id, { enabled: !w.enabled }),
    {
      invalidate,
      success: (w) => (w.enabled ? `${w.name} enabled` : `${w.name} disabled`),
    },
  );
  const rotate = useScopedMutation(
    (w: WebhookSubscription) => integrationsService.rotateWebhookSecret(w.id),
    {
      invalidate,
      onSuccess: (created) => {
        setRotating(null);
        setRevealed(created);
      },
    },
  );
  const remove = useScopedMutation(
    (w: WebhookSubscription) => integrationsService.deleteWebhook(w.id),
    {
      invalidate,
      success: "Subscription deleted",
      onSuccess: () => setDeleting(null),
    },
  );
  const deliveriesFor = list.data?.items.find((w) => w.id === state.deliveries);

  const columns: Column<WebhookSubscription>[] = [
    {
      key: "name",
      header: "Subscription",
      cell: (w) => (
        <div className="min-w-0">
          <button
            type="button"
            onClick={() => setState({ deliveries: w.id }, { resetPage: false })}
            className="block max-w-full truncate text-left font-medium hover:underline"
          >
            {w.name}
          </button>
          <p className="max-w-[60vw] truncate font-mono text-xs text-muted-foreground sm:max-w-80">
            {w.url}
          </p>
        </div>
      ),
    },
    {
      key: "enabled",
      header: "State",
      cell: (w) => (
        <StateBadge
          value={w.enabled ? "connected" : "disabled"}
          label={w.enabled ? "Enabled" : "Disabled"}
        />
      ),
    },
    {
      key: "events",
      header: "Events",
      hideBelow: "lg",
      cell: (w) => (
        <div className="flex max-w-72 flex-wrap gap-1">
          {w.event_types.slice(0, 3).map((t) => (
            <Badge key={t} tone="outline" className="font-mono">
              {t}
            </Badge>
          ))}
          {w.event_types.length > 3 && (
            <Badge tone="neutral">+{w.event_types.length - 3}</Badge>
          )}
        </div>
      ),
    },
    {
      key: "last",
      header: "Last delivery",
      hideBelow: "md",
      cell: (w) =>
        w.last_delivery_status ? (
          <span className="flex items-center gap-2">
            <StateBadge value={w.last_delivery_status} />
            <span className="text-xs text-muted-foreground">
              <When value={w.last_delivery_at} />
            </span>
          </span>
        ) : (
          <span className="text-muted-foreground">No deliveries yet</span>
        ),
    },
    {
      key: "failures",
      header: "Failing",
      hideBelow: "md",
      align: "right",
      cell: (w) => (
        <span
          className={
            w.failure_count
              ? "tabular font-medium text-danger"
              : "tabular text-muted-foreground"
          }
        >
          {w.failure_count}
        </span>
      ),
    },
    {
      key: "secret",
      header: "Secret",
      hideBelow: "xl",
      cell: (w) => (
        <span className="font-mono text-xs">
          {w.secret_hint ? `set • ${w.secret_hint}` : "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (w) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`Actions for ${w.name}`}
            >
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem
              onSelect={() =>
                setState({ deliveries: w.id }, { resetPage: false })
              }
            >
              <ListChecks /> Deliveries
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {canManage ? (
              <>
                <DropdownMenuItem onSelect={() => setEditing(w)}>
                  <Pencil /> Edit
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => toggle.mutate(w)}>
                  {w.enabled ? <Ban /> : <Power />}{" "}
                  {w.enabled ? "Disable" : "Enable"}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setRotating(w)}>
                  <KeyRound /> Rotate secret
                </DropdownMenuItem>
                <DropdownMenuItem destructive onSelect={() => setDeleting(w)}>
                  <Trash2 /> Delete
                </DropdownMenuItem>
              </>
            ) : (
              <DropdownMenuLabel className="normal-case">
                Changes require integrations.manage
              </DropdownMenuLabel>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  return (
    <IntegrationsFrame
      title="Outbound webhooks"
      description="Send signed events from this workspace to your own HTTPS endpoints."
      actions={
        <GatedButton
          permission="integrations.manage"
          onClick={() => setEditing("new")}
        >
          <Plus /> New subscription
        </GatedButton>
      }
    >
      <DataTable
        caption="Webhook subscriptions"
        columns={columns}
        rows={list.data?.items}
        loading={list.isPending}
        error={list.error}
        onRetry={() => void list.refetch()}
        getRowId={(w) => w.id}
        loadingRows={4}
        rowClassName={(w) => (w.enabled ? undefined : "opacity-70")}
        empty={
          <EmptyState
            icon={Send}
            title="No webhook subscriptions"
            description="Create one to notify another system when orders, invoices or customers change."
            action={
              <GatedButton
                permission="integrations.manage"
                onClick={() => setEditing("new")}
              >
                <Plus /> New subscription
              </GatedButton>
            }
          />
        }
      />
      {list.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={list.data.total}
          onPage={(p) => setState({ page: String(p) })}
        />
      )}

      {editing && (
        <WebhookDialog
          subscription={editing === "new" ? null : editing}
          onClose={() => {
            setEditing(null);
            if (state.create) setState({ create: "" }, { resetPage: false });
          }}
        />
      )}
      {revealed && (
        <Dialog open onOpenChange={(open) => !open && setRevealed(null)}>
          <DialogContent size="md">
            <DialogHeader
              title="New signing secret"
              description={`For ${revealed.name}. Update your receiver to verify with it.`}
            />
            <DialogBody>
              <SecretReveal
                label="Signing secret"
                secret={revealed.signing_secret}
                onDone={() => setRevealed(null)}
              />
            </DialogBody>
          </DialogContent>
        </Dialog>
      )}
      <ConfirmDialog
        open={rotating !== null}
        onOpenChange={(open) => !open && setRotating(null)}
        title={`Rotate the secret for ${rotating?.name ?? "subscription"}?`}
        consequences={[
          "The current secret stops being used immediately.",
          "Your receiver will reject deliveries until it's updated with the new secret.",
          "The new secret is shown once.",
        ]}
        confirmLabel="Rotate secret"
        loading={rotate.isPending}
        onConfirm={() => rotating && rotate.mutate(rotating)}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "subscription"}?`}
        description="This can't be undone."
        consequences={[
          "No further events are sent to this endpoint.",
          "Pending retries are cancelled and delivery history is removed.",
        ]}
        confirmLabel="Delete subscription"
        destructive
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting)}
      />
      <Dialog
        open={Boolean(state.deliveries)}
        onOpenChange={(open) =>
          !open && setState({ deliveries: "" }, { resetPage: false })
        }
      >
        {state.deliveries && (
          <SheetContent width="lg">
            <DeliveriesPanel
              subscriptionId={state.deliveries}
              subscription={deliveriesFor}
            />
          </SheetContent>
        )}
      </Dialog>
    </IntegrationsFrame>
  );
}

const webhookSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Name is required")
    .max(80, "Keep the name under 80 characters"),
  url: z
    .string()
    .trim()
    .min(1, "Endpoint URL is required")
    .superRefine((v, ctx) => {
      const problem = v ? outboundUrlProblem(v) : null;
      if (problem) ctx.addIssue({ code: "custom", message: problem });
    }),
  event_types: z.array(z.string()).min(1, "Choose at least one event type"),
  enabled: z.boolean(),
});
type WebhookValues = z.infer<typeof webhookSchema>;

function WebhookDialog({
  subscription,
  onClose,
}: {
  subscription: WebhookSubscription | null;
  onClose: () => void;
}) {
  const types = useScopedQuery(["integrations", "event-types"], () =>
    integrationsService.eventTypes(),
  );
  const form = useForm<WebhookValues>({
    resolver: zodResolver(webhookSchema),
    defaultValues: subscription
      ? {
          name: subscription.name,
          url: subscription.url,
          event_types: subscription.event_types,
          enabled: subscription.enabled,
        }
      : { name: "", url: "", event_types: [], enabled: true },
  });
  const [serverError, setServerError] = useState<string | null>(null);
  const [created, setCreated] = useState<WebhookSubscriptionCreated | null>(
    null,
  );
  const save = useScopedMutation(
    (v: WebhookValues) =>
      subscription
        ? integrationsService.updateWebhook(subscription.id, v)
        : integrationsService.createWebhook(v),
    {
      invalidate: [["integrations"]],
      toastErrors: false,
      success: subscription ? "Subscription saved" : undefined,
    },
  );
  const e = form.formState.errors;
  const busy = save.isPending;

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent size="md">
        {created ? (
          <>
            <DialogHeader
              title="Subscription created"
              description={`${created.name} will receive the selected events.`}
            />
            <DialogBody>
              <SecretReveal
                label="Signing secret"
                secret={created.signing_secret}
                onDone={onClose}
              />
            </DialogBody>
          </>
        ) : (
          <>
            <DialogHeader
              title={
                subscription ? "Edit subscription" : "New webhook subscription"
              }
              description="Payloads are signed with a secret so your receiver can verify they came from here."
            />
            <form
              noValidate
              className="flex min-h-0 flex-1 flex-col"
              onSubmit={form.handleSubmit(async (values) => {
                setServerError(null);
                try {
                  const result = await save.mutateAsync(values);
                  if (!subscription && "signing_secret" in result)
                    setCreated(result as WebhookSubscriptionCreated);
                  else onClose();
                } catch (error) {
                  const { mapped, leftovers } = applyServerFieldErrors(
                    error,
                    (key, message) => {
                      if (
                        !["name", "url", "event_types", "enabled"].includes(key)
                      )
                        return false;
                      form.setError(key as keyof WebhookValues, {
                        type: "server",
                        message,
                      });
                      return true;
                    },
                  );
                  if (!mapped || leftovers.length)
                    setServerError(
                      leftovers[0] ??
                        errorMessage(
                          error,
                          "The subscription could not be saved.",
                        ),
                    );
                }
              })}
            >
              <DialogBody className="space-y-4">
                <FormField
                  label="Name"
                  htmlFor="wh-name"
                  required
                  error={e.name}
                >
                  <Input
                    id="wh-name"
                    autoComplete="off"
                    disabled={busy}
                    aria-invalid={!!e.name || undefined}
                    {...form.register("name")}
                  />
                </FormField>
                <FormField
                  label="Endpoint URL"
                  htmlFor="wh-url"
                  required
                  error={e.url}
                  help="HTTPS on a public address. Private, loopback and cloud-metadata addresses are rejected; redirects aren't followed."
                >
                  <Input
                    id="wh-url"
                    type="url"
                    placeholder="https://"
                    className="font-mono text-[13px]"
                    autoComplete="off"
                    spellCheck={false}
                    disabled={busy}
                    aria-invalid={!!e.url || undefined}
                    {...form.register("url")}
                  />
                </FormField>
                <fieldset>
                  <legend className="mb-1.5 flex items-center gap-1 text-[13px] font-medium">
                    Event types{" "}
                    <span className="text-danger" aria-hidden="true">
                      *
                    </span>
                  </legend>
                  {types.isPending ? (
                    <Skeleton className="h-40" />
                  ) : types.isError ? (
                    <ErrorState
                      compact
                      error={types.error}
                      onRetry={() => void types.refetch()}
                    />
                  ) : (
                    <Controller
                      control={form.control}
                      name="event_types"
                      render={({ field }) => (
                        <ul className="scrollbar-thin max-h-56 divide-y divide-border overflow-y-auto rounded-lg border border-border">
                          {types.data.map((t) => {
                            const id = `wh-type-${t.key}`;
                            const checked = field.value.includes(t.key);
                            return (
                              <li
                                key={t.key}
                                className="flex items-start gap-2.5 px-3 py-2"
                              >
                                <Checkbox
                                  id={id}
                                  checked={checked}
                                  disabled={busy}
                                  className="mt-0.5"
                                  onCheckedChange={(on) =>
                                    field.onChange(
                                      on
                                        ? [...field.value, t.key]
                                        : field.value.filter(
                                            (v) => v !== t.key,
                                          ),
                                    )
                                  }
                                />
                                <Label
                                  htmlFor={id}
                                  className="min-w-0 font-normal"
                                >
                                  <span className="block font-mono text-xs font-medium">
                                    {t.key}
                                  </span>
                                  <span className="text-xs text-muted-foreground">
                                    {t.description}
                                  </span>
                                </Label>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    />
                  )}
                  {e.event_types && (
                    <p
                      role="alert"
                      className="mt-1.5 text-xs font-medium text-danger"
                    >
                      {e.event_types.message}
                    </p>
                  )}
                </fieldset>
                {!subscription && (
                  <Controller
                    control={form.control}
                    name="enabled"
                    render={({ field }) => (
                      <div className="flex items-center justify-between gap-3">
                        <Label htmlFor="wh-enabled">
                          Start sending immediately
                        </Label>
                        <Switch
                          id="wh-enabled"
                          checked={field.value}
                          onCheckedChange={field.onChange}
                          disabled={busy}
                        />
                      </div>
                    )}
                  />
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
                <Button
                  type="submit"
                  loading={busy}
                  disabled={subscription ? !form.formState.isDirty : false}
                >
                  {subscription ? "Save changes" : "Create subscription"}
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DeliveriesPanel({
  subscriptionId,
  subscription,
}: {
  subscriptionId: string;
  subscription: WebhookSubscription | undefined;
}) {
  const deliveries = useScopedQuery(
    ["integrations", "deliveries", subscriptionId],
    () => integrationsService.deliveries(subscriptionId, { pageSize: 50 }),
  );
  const retry = useScopedMutation(
    (id: string) => integrationsService.retryDelivery(id),
    {
      invalidate: [["integrations"]],
      success: (d) =>
        d.status === "succeeded"
          ? "Delivered on retry"
          : `Retry recorded: ${d.status.replace("_", " ")}`,
    },
  );
  return (
    <>
      <DialogHeader
        title={subscription ? `Deliveries: ${subscription.name}` : "Deliveries"}
        description={subscription?.url}
      />
      <DialogBody className="space-y-3">
        {subscription && !subscription.enabled && (
          <Notice tone="neutral" icon={Ban}>
            This subscription is disabled. Enable it to retry deliveries.
          </Notice>
        )}
        {deliveries.isPending ? (
          Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))
        ) : deliveries.isError ? (
          <ErrorState
            compact
            error={deliveries.error}
            onRetry={() => void deliveries.refetch()}
          />
        ) : deliveries.data.items.length === 0 ? (
          <EmptyState
            compact
            icon={Send}
            title="No deliveries yet"
            description="Deliveries appear here when a subscribed event happens."
          />
        ) : (
          <ul className="space-y-2">
            {deliveries.data.items.map((d) => {
              const retryable = RETRYABLE_DELIVERY.includes(d.status);
              return (
                <li
                  key={d.id}
                  className="rounded-lg border border-border p-3"
                  data-delivery={d.id}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-xs font-medium">
                      {d.event_type}
                    </span>
                    <StateBadge value={d.status} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatDateTime(d.created_at)} · {d.attempt_count} attempt
                    {d.attempt_count === 1 ? "" : "s"}
                    {d.response_status !== null &&
                      ` · HTTP ${d.response_status}`}
                  </p>
                  {d.last_error && (
                    <p className="mt-1 text-xs break-words text-danger">
                      {d.last_error}
                    </p>
                  )}
                  {d.next_attempt_at && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Next automatic attempt {formatDateTime(d.next_attempt_at)}
                    </p>
                  )}
                  {retryable && (
                    <GatedButton
                      size="xs"
                      variant="secondary"
                      className="mt-2"
                      permission="integrations.operate"
                      blockedReason={
                        subscription && !subscription.enabled
                          ? "Enable the subscription first"
                          : null
                      }
                      loading={retry.isPending && retry.variables === d.id}
                      onClick={() => retry.mutate(d.id)}
                    >
                      <RotateCcw /> Retry now
                    </GatedButton>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </DialogBody>
    </>
  );
}
