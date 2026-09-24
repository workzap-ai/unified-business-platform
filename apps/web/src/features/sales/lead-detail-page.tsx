"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AlertCircle,
  ArrowRightLeft,
  Bot,
  FileText,
  MessageSquare,
  Pencil,
  Target,
} from "lucide-react";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  humanize,
  relativeTime,
} from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { Textarea } from "@/components/ui/input";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PropertyList, RecordHeader } from "@/components/app/record";
import { FormField } from "@/components/app/forms";
import { ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import type { Lead } from "@/features/business/types";
import { salesService } from "./service";
import {
  formatRequirement,
  isStage,
  LEAD_SOURCE_LABELS,
  LeadSourceBadge,
  requirementEntries,
  STAGE_LABELS,
} from "./lib";
import { LeadFormDialog } from "./components/lead-form-dialog";
import { useMoveLead } from "./components/use-move-lead";

export function LeadDetailPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="sales.read" area="leads">
      <LeadDetailView id={id} />
    </RequirePermission>
  );
}

function LeadDetailView({ id }: { id: string }) {
  const query = useScopedQuery(["leads", "detail", id], () =>
    salesService.lead(id),
  );
  const lead = query.data;
  useBreadcrumbs(
    lead ? [{ label: lead.title }] : [],
    lead ? { href: `/sales/leads/${id}`, kind: "Lead" } : undefined,
  );

  if (query.isError) {
    return (
      <PageShell>
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        <div className="text-center">
          <Link
            href="/sales/leads"
            className="text-sm font-medium text-primary hover:underline"
          >
            Back to leads
          </Link>
        </div>
      </PageShell>
    );
  }
  if (!lead) {
    return (
      <PageShell>
        <RecordHeader title="" loading />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="h-72 animate-pulse rounded-xl bg-surface-sunken" />
          <div className="h-56 animate-pulse rounded-xl bg-surface-sunken" />
        </div>
      </PageShell>
    );
  }
  return <LeadRecord lead={lead} />;
}

const STAGE_BUTTON_LABELS: Record<string, string> = {
  qualified: "Qualify",
  proposal: "Move to proposal",
  won: "Mark won",
  lost: "Mark lost",
  new: "Reopen as new",
};

function LeadRecord({ lead }: { lead: Lead }) {
  const { can } = useSession();
  const canWrite = can("sales.write");
  const [editing, setEditing] = useState(false);
  const { move, dialog, isPending, variables } = useMoveLead();
  const targets = lead.next_stages.filter(isStage);
  const requirements = requirementEntries(lead.requirements);
  const fromPi = lead.source === "pi";

  const actions = (
    <>
      {canWrite &&
        targets.map((stage) => (
          <Button
            key={stage}
            size="sm"
            variant={
              stage === "lost"
                ? "secondary"
                : stage === "won"
                  ? "default"
                  : "soft"
            }
            onClick={() => move(lead, stage)}
            loading={isPending && variables?.stage === stage}
            disabled={isPending}
          >
            {stage !== "won" && stage !== "lost" && <ArrowRightLeft />}{" "}
            {STAGE_BUTTON_LABELS[stage] ?? STAGE_LABELS[stage]}
          </Button>
        ))}
      {can("quotes.write") && lead.customer_id && lead.stage !== "lost" && (
        <Button size="sm" variant="secondary" asChild>
          <Link href={`/quotes/new?customer=${lead.customer_id}`}>
            <FileText /> Create quote
          </Link>
        </Button>
      )}
      {canWrite && (
        <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
          <Pencil /> Edit
        </Button>
      )}
    </>
  );

  return (
    <PageShell>
      <RecordHeader
        icon={Target}
        title={lead.title}
        status={
          <>
            <StatusBadge status={lead.stage} />
            {fromPi && <LeadSourceBadge source="pi" />}
          </>
        }
        subtitle={lead.customer_name ?? "No customer linked"}
        meta={
          <>
            <span className="tabular">
              {lead.estimated_value
                ? `${formatMoney(lead.estimated_value, lead.currency)} estimated`
                : "No estimated value"}
            </span>
            <span>Updated {relativeTime(lead.updated_at)}</span>
          </>
        }
        actions={actions}
      />

      {lead.stage === "won" && (
        <Notice tone="success" className="mb-4" title="Won">
          This lead closed on {formatDate(lead.closed_at)}. Won is a final
          stage.
        </Notice>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader
              title={
                <span className="flex items-center gap-1.5">
                  {fromPi && (
                    <Bot className="size-4 text-pi" aria-hidden="true" />
                  )}{" "}
                  Requirements
                </span>
              }
              description={
                fromPi
                  ? "Captured by PI from WhatsApp"
                  : "What the customer needs"
              }
              actions={
                fromPi && lead.conversation_id && can("pi.read") ? (
                  <Button size="xs" variant="secondary" asChild>
                    <Link
                      href={`/pi/inbox?conversation=${encodeURIComponent(lead.conversation_id)}`}
                    >
                      <MessageSquare /> Open conversation
                    </Link>
                  </Button>
                ) : undefined
              }
            />
            <CardBody className="space-y-3">
              {requirements.length ? (
                <PropertyList
                  columns={2}
                  items={requirements.map(([key, value]) => ({
                    label: humanize(key),
                    value: formatRequirement(value),
                  }))}
                />
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  {fromPi
                    ? "PI hasn't recorded structured requirements for this lead yet."
                    : "No structured requirements. Use notes to capture what the customer needs."}
                </p>
              )}
              {lead.missing_information.length > 0 && (
                <div className="rounded-lg border border-warning/25 bg-warning-soft/60 p-3">
                  <p className="text-[13px] font-medium">Missing information</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Confirm these with the customer before quoting.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {lead.missing_information.map((m) => (
                      <Badge key={m} tone="warning">
                        <AlertCircle aria-hidden="true" /> {humanize(m)}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>

          <LeadNotes lead={lead} canWrite={canWrite} />
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Details" />
            <CardBody className="pb-2">
              <PropertyList
                items={[
                  {
                    label: "Customer",
                    value: lead.customer_id ? (
                      <Link
                        href={`/customers/${lead.customer_id}`}
                        className="text-primary hover:underline"
                      >
                        {lead.customer_name ?? "View customer"}
                      </Link>
                    ) : null,
                  },
                  {
                    label: "Stage",
                    value: <StatusBadge status={lead.stage} />,
                  },
                  {
                    label: "Estimated value",
                    value: lead.estimated_value ? (
                      <span className="tabular">
                        {formatMoney(lead.estimated_value, lead.currency)}
                      </span>
                    ) : null,
                  },
                  { label: "Source", value: LEAD_SOURCE_LABELS[lead.source] },
                  {
                    label: "Created",
                    value: (
                      <span title={formatDateTime(lead.created_at)}>
                        {formatDate(lead.created_at)}
                      </span>
                    ),
                  },
                  {
                    label: "Closed",
                    value: lead.closed_at ? (
                      <span title={formatDateTime(lead.closed_at)}>
                        {formatDate(lead.closed_at)}
                      </span>
                    ) : null,
                  },
                ]}
              />
            </CardBody>
          </Card>
          <Card>
            <CardHeader
              title="Next stages"
              description="Where this lead can move from here"
            />
            <CardBody>
              {targets.length ? (
                <ul className="flex flex-wrap gap-1.5">
                  {targets.map((stage) => (
                    <li key={stage}>
                      <StatusBadge status={stage} />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] text-muted-foreground">
                  This lead is in a final stage.
                </p>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      {canWrite && (
        <LeadFormDialog open={editing} onOpenChange={setEditing} lead={lead} />
      )}
      {dialog}
    </PageShell>
  );
}

const notesSchema = z.object({
  notes: z.string().max(5000, "Keep notes under 5,000 characters"),
});
type NotesValues = z.infer<typeof notesSchema>;

function LeadNotes({ lead, canWrite }: { lead: Lead; canWrite: boolean }) {
  const form = useForm<NotesValues>({
    resolver: zodResolver(notesSchema),
    defaultValues: { notes: lead.notes },
  });
  const error = form.formState.errors.notes;
  useEffect(() => {
    if (!form.formState.isDirty) form.reset({ notes: lead.notes });
    // Sync when the saved notes change and there's no local draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lead.notes]);

  const save = useScopedMutation(
    (values: NotesValues) =>
      salesService.update(lead.id, { notes: values.notes }),
    {
      invalidate: [["leads"]],
      success: "Notes saved",
      onSuccess: (updated) => form.reset({ notes: updated.notes }),
    },
  );

  return (
    <Card>
      <CardHeader
        title="Notes"
        description="Context for your team; not shared with the customer"
      />
      <CardBody>
        {canWrite ? (
          <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
            <FormField
              label="Lead notes"
              htmlFor="lead-notes-body"
              error={error}
            >
              <Textarea
                id="lead-notes-body"
                rows={5}
                placeholder="Budget, timing, decision makers, competitors…"
                aria-invalid={!!error || undefined}
                aria-describedby={error ? "lead-notes-body-error" : undefined}
                {...form.register("notes")}
              />
            </FormField>
            <div className="mt-3 flex items-center justify-end gap-2">
              {form.formState.isDirty && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => form.reset({ notes: lead.notes })}
                  disabled={save.isPending}
                >
                  Discard
                </Button>
              )}
              <Button
                type="submit"
                size="sm"
                loading={save.isPending}
                disabled={save.isPending || !form.formState.isDirty}
              >
                Save notes
              </Button>
            </div>
          </form>
        ) : lead.notes ? (
          <p className="text-[13px] leading-relaxed whitespace-pre-wrap">
            {lead.notes}
          </p>
        ) : (
          <p className="text-[13px] text-muted-foreground">No notes yet.</p>
        )}
      </CardBody>
    </Card>
  );
}
