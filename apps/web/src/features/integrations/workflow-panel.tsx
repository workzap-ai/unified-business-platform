"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, CardBody, CardHeader } from "@/components/ui/display";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { integrationsService } from "./service";
import { workflowService, type WorkflowRule } from "./workflow-service";

export function WorkflowPanel({
  id,
  provider,
  active,
}: {
  id: string;
  provider: string;
  active: boolean;
}) {
  const { can } = useSession();
  const events = useScopedQuery(["integrations", "event-types"], () =>
    integrationsService.eventTypes(),
  );
  const rule = useScopedQuery(["integrations", "workflow", id], () =>
    workflowService.rule(id),
  );
  const history = useScopedQuery(
    ["integrations", "operations", id],
    () => workflowService.operations(id),
    { refetchInterval: 10000 },
  );
  const [draft, setDraft] = useState<WorkflowRule | null>(null);
  const [recipientText, setRecipientText] = useState<string | null>(null);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [acknowledge, setAcknowledge] = useState(false);
  const editable = [
    "resend",
    "smtp",
    "sendgrid",
    "slack",
    "generic_webhook",
  ].includes(provider);
  const email = ["resend", "smtp", "sendgrid"].includes(provider);
  const value = draft ??
    rule.data ?? { enabled: false, event_types: [], recipients: [] };
  const invalidate = [["integrations"]];
  const save = useScopedMutation(
    () =>
      workflowService.save(id, {
        ...value,
        recipients: (recipientText ?? value.recipients.join(", "))
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    {
      invalidate,
      success: "Workflow settings saved",
      onSuccess: () => {
        setDraft(null);
        setRecipientText(null);
      },
    },
  );
  const retry = useScopedMutation(
    (v: { id: string; ack: boolean }) => workflowService.retry(v.id, v.ack),
    {
      invalidate,
      success: "Delivery queued",
      onSuccess: () => {
        setReviewId(null);
        setAcknowledge(false);
      },
    },
  );
  const pi = useScopedMutation(() => workflowService.activatePi(id), {
    invalidate,
    success: "WhatsApp connected to PI",
  });
  return (
    <Card>
      <CardHeader
        title="Use this integration"
        description="Connect this provider to business features and track completed work."
      />
      <CardBody className="space-y-4">
        {rule.isError && (
          <ErrorState error={rule.error} onRetry={() => void rule.refetch()} />
        )}
        {editable && rule.data && (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(undefined);
            }}
          >
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.enabled}
                disabled={!can("integrations.manage") || !active}
                onChange={(e) =>
                  setDraft({ ...value, enabled: e.target.checked })
                }
              />
              Automatically deliver selected events
            </label>
            <fieldset
              disabled={!can("integrations.manage") || !active}
              className="grid gap-2 sm:grid-cols-2"
            >
              <legend className="mb-2 text-sm font-medium">
                Business events
              </legend>
              {(events.data ?? []).map((event) => (
                <label
                  key={event.key}
                  className="flex items-start gap-2 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={value.event_types.includes(event.key)}
                    onChange={(e) =>
                      setDraft({
                        ...value,
                        event_types: e.target.checked
                          ? [...value.event_types, event.key]
                          : value.event_types.filter((k) => k !== event.key),
                      })
                    }
                  />
                  {event.description}
                </label>
              ))}
            </fieldset>
            {email && (
              <label className="block space-y-1 text-sm">
                Email recipients
                <Input
                  aria-label="Email recipients"
                  value={recipientText ?? value.recipients.join(", ")}
                  disabled={!can("integrations.manage")}
                  placeholder="team@example.com"
                  onChange={(e) => setRecipientText(e.target.value)}
                />
                <span className="text-xs text-muted-foreground">
                  Separate addresses with commas. Only new events after saving
                  are eligible.
                </span>
              </label>
            )}
            {can("integrations.manage") && (
              <Button
                type="submit"
                loading={save.isPending}
                disabled={!active || (!draft && recipientText === null)}
              >
                Save workflow
              </Button>
            )}
            {save.isError && <ErrorState error={save.error} />}
          </form>
        )}
        {provider === "stripe" && (
          <Notice tone="info" title="Invoice payments">
            Open an issued invoice and choose Create payment link. Verified
            Stripe webhooks record the payment automatically. Configure your
            webhook signing secret and endpoint first.{" "}
            <Link className="underline" href="/billing/invoices">
              Open invoices
            </Link>
          </Notice>
        )}
        {provider === "s3" && (
          <Notice tone="info" title="Record attachments">
            Upload and download files from invoices, orders and customer
            records. Files stay scoped to their workspace and environment.
          </Notice>
        )}
        {email && (
          <Notice tone="info" title="Invoice email">
            The Email invoice action uses a connected email provider and the
            customer&apos;s saved email address. Verify your sending domain
            before use.
          </Notice>
        )}
        {provider === "whatsapp_meta" && (
          <div className="space-y-2">
            <p className="text-sm">
              Use these credentials for PI messaging. PI must be enabled in this
              environment; configure the app secret and verification token
              first.
            </p>
            <Button
              disabled={
                !active ||
                !can("pi.whatsapp.manage") ||
                !can("integrations.manage")
              }
              loading={pi.isPending}
              onClick={() => pi.mutate(undefined)}
            >
              Use for PI messaging
            </Button>
            {pi.isError && <ErrorState error={pi.error} />}
          </div>
        )}
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Recent workflow activity</h3>
          {history.isError ? (
            <ErrorState
              error={history.error}
              onRetry={() => void history.refetch()}
            />
          ) : history.isPending ? (
            <p className="text-sm">Loading activityâ€¦</p>
          ) : !history.data?.length ? (
            <p className="text-sm text-muted-foreground">
              No workflow activity yet. Connection tests are shown separately.
            </p>
          ) : (
            history.data.map((op) => (
              <div key={op.id} className="rounded-lg border p-3 text-sm">
                <div className="flex flex-wrap justify-between gap-2">
                  <span>
                    {op.kind} Â· {op.status.replaceAll("_", " ")} Â·{" "}
                    {op.attempts} attempts
                  </span>
                  {op.kind === "notification" &&
                    ["failed", "needs_review"].includes(op.status) &&
                    can("integrations.operate") && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          op.status === "needs_review"
                            ? setReviewId(op.id)
                            : retry.mutate({ id: op.id, ack: false })
                        }
                      >
                        Retry delivery
                      </Button>
                    )}
                </div>
                {op.last_error && (
                  <p className="mt-1 text-danger">{op.last_error}</p>
                )}
                {reviewId === op.id && (
                  <div className="mt-2 space-y-2">
                    <label className="flex gap-2">
                      <input
                        type="checkbox"
                        checked={acknowledge}
                        onChange={(e) => setAcknowledge(e.target.checked)}
                      />
                      I checked the provider history. Retrying could send a
                      duplicate.
                    </label>
                    <Button
                      size="sm"
                      disabled={!acknowledge}
                      loading={retry.isPending}
                      onClick={() => retry.mutate({ id: op.id, ack: true })}
                    >
                      Confirm retry
                    </Button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
        {retry.isError && <ErrorState error={retry.error} />}
      </CardBody>
    </Card>
  );
}
